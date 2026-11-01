"""External retrieval: Tavily search, guarded page fetching, and Trafilatura extraction."""

import asyncio
import logging
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx
import trafilatura

from app.config import Settings
from app.guardrails import clean_source_title, is_public_url

logger = logging.getLogger(__name__)

TAVILY_URL = "https://api.tavily.com/search"
MAX_REDIRECTS = 3
USER_AGENT = "ResearchOpsBot/1.0 (technical research agent)"


class SearchUnavailable(Exception):
    pass


@dataclass(frozen=True)
class SearchHit:
    url: str
    title: str
    snippet: str
    score: float
    published_date: str | None = None


@dataclass(frozen=True)
class FetchedPage:
    text: str
    published_date: str | None = None


class WebClient:
    """Wraps retrieval so the workflow can be exercised with a stub in tests."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def search(self, query: str) -> list[SearchHit]:
        key = self._settings.tavily_api_key
        if key is None:
            raise SearchUnavailable("TAVILY_API_KEY is not configured")
        async with httpx.AsyncClient(timeout=self._settings.fetch_timeout_seconds * 2) as client:
            response = await client.post(
                TAVILY_URL,
                headers={"Authorization": f"Bearer {key.get_secret_value()}"},
                json={"query": query, "search_depth": "advanced", "max_results": 6},
            )
        if response.status_code != 200:
            raise SearchUnavailable(f"Tavily returned HTTP {response.status_code}")
        return [
            SearchHit(
                url=item["url"],
                title=clean_source_title(item.get("title") or "") or item["url"],
                snippet=item.get("content") or "",
                score=float(item.get("score") or 0),
                published_date=item.get("published_date"),
            )
            for item in response.json().get("results", [])
            if item.get("url")
        ]

    async def fetch(self, url: str) -> FetchedPage | None:
        """Return extracted page text, or None when the page is blocked, unreadable, or not HTML."""
        html = await self._download(url)
        if html is None:
            return None
        return await asyncio.to_thread(self._extract, html, url)

    async def _download(self, url: str) -> str | None:
        limit = self._settings.max_fetch_bytes
        timeout = httpx.Timeout(self._settings.fetch_timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": USER_AGENT}) as client:
                # Redirects are followed by hand so every hop gets the SSRF check.
                for _ in range(MAX_REDIRECTS + 1):
                    if not await is_public_url(url):
                        logger.warning("Blocked non-public URL: %s", url)
                        return None
                    async with client.stream("GET", url) as response:
                        if response.is_redirect:
                            url = urljoin(url, response.headers.get("location", ""))
                            continue
                        content_type = response.headers.get("content-type", "")
                        if response.status_code != 200 or not ("html" in content_type or "text/plain" in content_type):
                            return None
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body += chunk
                            if len(body) > limit:
                                break
                        return bytes(body[:limit]).decode(response.encoding or "utf-8", errors="replace")
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            logger.info("Fetch failed for %s: %s", url, exc)
        return None

    @staticmethod
    def _extract(html: str, url: str) -> FetchedPage | None:
        text = trafilatura.extract(html, url=url, include_tables=True, include_comments=False)
        if not text:
            return None
        metadata = trafilatura.extract_metadata(html)
        return FetchedPage(text=text, published_date=metadata.date if metadata else None)
