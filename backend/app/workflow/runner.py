import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

from app.config import Settings
from app.services.llm import LLMRouter
from app.services.web import WebClient
from app.workflow.graph import Context, build_graph


class ResearchTimeout(Exception):
    pass


async def run_workflow(
    settings: Settings, llm: LLMRouter, web: WebClient, question: str
) -> AsyncIterator[dict[str, Any]]:
    """Yield progress steps, then a final {"final": state}, inside the runtime ceiling.

    The graph runs in its own task so the deadline can cancel it, including
    while the consumer is waiting on a slow client.
    """
    started = time.monotonic()
    graph = build_graph(Context(settings=settings, llm=llm, web=web, started_at=started))
    queue: asyncio.Queue[tuple[str, Any] | None] = asyncio.Queue()
    recursion_limit = (settings.max_iterations + 1) * 8 + 5

    async def pump() -> None:
        try:
            async for mode, chunk in graph.astream(
                {"question": question},
                config={"recursion_limit": recursion_limit, "run_name": "research"},
                stream_mode=["custom", "values"],
            ):
                await queue.put((mode, chunk))
        finally:
            await queue.put(None)

    task = asyncio.create_task(pump())
    final: dict[str, Any] = {}
    try:
        while True:
            remaining = settings.max_runtime_seconds - (time.monotonic() - started)
            try:
                item = await asyncio.wait_for(queue.get(), timeout=max(remaining, 0.001))
            except TimeoutError as exc:
                raise ResearchTimeout from exc
            if item is None:
                break
            mode, chunk = item
            if mode == "custom":
                yield chunk
            else:
                final = chunk
        await task  # Re-raises any workflow failure.
    finally:
        task.cancel()
    yield {"final": final}
