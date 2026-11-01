"""Model provider layer: the catalog from settings, plus Auto routing with fallback."""

import logging
from dataclasses import dataclass
from typing import TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, SecretStr

from app.config import Settings
from app.schemas import ModelInfo

logger = logging.getLogger(__name__)

AUTO = "auto"
UNUSABLE_OUTPUT_ATTEMPTS = 2
PROVIDER_LABELS = {"openai": "OpenAI", "gemini": "Google Gemini", "nebius": "Nebius"}

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class AllModelsFailed(Exception):
    pass


class TokenBudgetExceeded(Exception):
    pass


@dataclass(frozen=True)
class ModelSpec:
    id: str
    provider: str
    name: str
    role: str


def _api_key(settings: Settings, provider: str) -> SecretStr | None:
    return {
        "openai": settings.openai_api_key,
        "gemini": settings.gemini_api_key,
        "nebius": settings.nebius_api_key,
    }.get(provider)


def _spec(settings: Settings, model_id: str, role: str) -> ModelSpec | None:
    """Return a spec only for a well-formed model whose provider has a key, so nothing uncallable is offered."""
    provider, _, name = model_id.partition(":")
    if not name or _api_key(settings, provider) is None:
        return None
    return ModelSpec(id=model_id, provider=provider, name=name, role=role)


def auto_chain(settings: Settings) -> list[ModelSpec]:
    ids = dict.fromkeys([settings.primary_model, *settings.fallback_models])
    roles = {model_id: "fallback" for model_id in settings.fallback_models} | {settings.primary_model: "primary"}
    return [spec for model_id in ids if (spec := _spec(settings, model_id, roles[model_id]))]


def available_models(settings: Settings) -> list[ModelSpec]:
    specs = auto_chain(settings)
    known = {spec.id for spec in specs}
    extras = (_spec(settings, model_id, "optional") for model_id in dict.fromkeys(settings.extra_models))
    return specs + [spec for spec in extras if spec and spec.id not in known]


def to_model_info(spec: ModelSpec) -> ModelInfo:
    return ModelInfo(
        id=spec.id,
        label=spec.name,
        name=spec.name,
        provider=spec.provider,
        provider_label=PROVIDER_LABELS.get(spec.provider, spec.provider),
        role=spec.role,
    )


def resolve_chain(settings: Settings, requested: str) -> list[ModelSpec]:
    """Auto uses the configured chain. A chosen model runs first, with the same fallbacks behind it."""
    chain = auto_chain(settings)
    if requested == AUTO:
        return chain
    chosen = next(spec for spec in available_models(settings) if spec.id == requested)
    return [chosen, *(spec for spec in chain if spec.id != chosen.id)]


def build_chat_model(settings: Settings, spec: ModelSpec) -> BaseChatModel:
    key = _api_key(settings, spec.provider)
    if spec.provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=spec.name, google_api_key=key, timeout=settings.llm_timeout_seconds, max_retries=1
        )
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=spec.name,
        api_key=key,
        base_url=settings.nebius_base_url if spec.provider == "nebius" else None,
        timeout=settings.llm_timeout_seconds,
        max_retries=1,
    )


class LLMRouter:
    """Runs structured calls down the fallback chain and tracks tokens against the budget for one run."""

    def __init__(self, settings: Settings, chain: list[ModelSpec], token_budget: int, model_factory=build_chat_model):
        self._settings = settings
        self._chain = chain
        self._budget = token_budget
        self._factory = model_factory
        self.tokens_used = 0
        self.models_used: list[str] = []

    @property
    def budget_used_ratio(self) -> float:
        return self.tokens_used / self._budget

    async def structured(self, schema: type[SchemaT], system: str, user: str) -> SchemaT:
        if self.tokens_used >= self._budget:
            raise TokenBudgetExceeded
        messages = [SystemMessage(content=system), HumanMessage(content=user)]
        for spec in list(self._chain):
            # Output varies between calls, so a bad response earns one retry on the same model.
            # That is far cheaper than failing over to a provider that may be slow.
            for attempt in range(UNUSABLE_OUTPUT_ATTEMPTS):
                try:
                    model = self._factory(self._settings, spec)
                    runnable = model.with_structured_output(schema, method="function_calling", include_raw=True)
                    output = await runnable.ainvoke(messages)
                except Exception as exc:  # Provider SDKs raise many types; any failure moves to the next model.
                    logger.warning("Model %s failed: %s", spec.id, type(exc).__name__)
                    break
                raw = output["raw"]
                usage = getattr(raw, "usage_metadata", None) or {}
                self.tokens_used += usage.get("total_tokens", 0)
                if output.get("parsed") is not None:
                    if spec.id not in self.models_used:
                        self.models_used.append(spec.id)
                    return output["parsed"]
                logger.warning(
                    "Model %s returned unusable output for %s (attempt %d, finish_reason=%s, output_tokens=%s)",
                    spec.id,
                    schema.__name__,
                    attempt + 1,
                    getattr(raw, "response_metadata", {}).get("finish_reason"),
                    usage.get("output_tokens"),
                )
            self._demote(spec)
        raise AllModelsFailed

    def _demote(self, spec: ModelSpec) -> None:
        """Later calls in this run start with a model that has not just failed."""
        self._chain = [item for item in self._chain if item != spec] + [spec]
