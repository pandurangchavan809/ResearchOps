"""Deterministic checks that hold regardless of what a model returns."""

import asyncio
import difflib
import html
import ipaddress
import re
import socket
from collections.abc import Iterable, Mapping
from urllib.parse import urlsplit

_INJECTION = re.compile(
    r"(ignore|disregard|forget)\s+((all|any|the|your)\s+){0,2}((previous|prior|above|earlier)\s+)"
    r"(instructions?|prompts?|rules?)"
    r"|(ignore|disregard|forget)\s+your\s+(instructions?|prompts?|rules?)"
    r"|(reveal|show|print|repeat)\s+(me\s+)?(your|the)\s+(system\s+prompt|instructions|api\s+keys?)"
    r"|you\s+are\s+now\s+(in\s+)?(dan|developer\s+mode|jailbreak)",
    re.IGNORECASE,
)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_CITATION = re.compile(r"\[(\d{1,3})\]")
_CITATION_GROUP = re.compile(r"\[\s*\d{1,3}(?:\s*[,;]\s*\d{1,3})+\s*\]")
_TRAILING_SOURCES = re.compile(r"\n#{1,6}\s*(sources|references)\s*\n.*\Z", re.IGNORECASE | re.DOTALL)
_GENERIC_TITLES = {"report", "research report", "technical report", "research", "untitled", "title", "research summary"}
_DANGLING_WORDS = {"a", "an", "and", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to", "vs", "with"}
_TITLE_PREFIX = re.compile(r"^(title|report|report title|research report)\s*[:\-–—]\s*", re.IGNORECASE)
_QUESTION_LEAD = re.compile(
    r"^(please\s+)?(what|which|how|why|when|where|who|should|can|could|does|do|is|are|compare|evaluate|explain)"
    r"\b(\s+(is|are|do|does|the|should|i|we))*\s+",
    re.IGNORECASE,
)


def is_prompt_attack(question: str) -> bool:
    return bool(_INJECTION.search(question))


def sanitize_untrusted(text: str) -> str:
    """Prepare web text for a prompt: remove control characters and stop it closing our delimiters."""
    text = _CONTROL_CHARS.sub("", text)
    return re.sub(r"</?\s*source\b[^>]*>", " ", text, flags=re.IGNORECASE)


def clean_source_title(title: str) -> str:
    """Web titles sometimes contain markup such as <p>A&nbsp;guide</p>."""
    return _normalize(re.sub(r"<[^>]+>", " ", html.unescape(title)))


async def is_public_url(url: str) -> bool:
    """Block SSRF: only http(s) URLs on standard ports that resolve entirely to public addresses."""
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        return False
    try:
        if parts.port not in {None, 80, 443}:
            return False
        infos = await asyncio.to_thread(socket.getaddrinfo, parts.hostname, parts.port or 443, type=socket.SOCK_STREAM)
    except (OSError, ValueError):
        return False
    return bool(infos) and all(ipaddress.ip_address(info[4][0].split("%")[0]).is_global for info in infos)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def locate_excerpt(excerpt: str, source_text: str, min_ratio: float = 0.8) -> str | None:
    """Return the source's own wording for an excerpt, or None if the model did not really quote it."""
    excerpt, source = _normalize(excerpt), _normalize(source_text)
    if len(excerpt) < 20:
        return None
    position = source.lower().find(excerpt.lower())
    if position >= 0:
        return source[position : position + len(excerpt)]
    matcher = difflib.SequenceMatcher(None, source.lower(), excerpt.lower(), autojunk=False)
    match = matcher.find_longest_match(0, len(source), 0, len(excerpt))
    return source[match.a : match.a + match.size] if match.size >= len(excerpt) * min_ratio else None


def _split_citation_groups(text: str) -> str:
    """Models sometimes write [5,6]; turn that into [5][6] so every number is checked and renumbered."""
    return _CITATION_GROUP.sub(lambda m: "".join(f"[{n}]" for n in re.findall(r"\d+", m.group())), text)


def cited_ids(text: str) -> list[int]:
    """Citation numbers in first-appearance order."""
    return list(dict.fromkeys(int(n) for n in _CITATION.findall(_split_citation_groups(text))))


def rewrite_citations(text: str, mapping: Mapping[int, int]) -> str:
    """Renumber citations and remove any that do not resolve to a real source."""

    def replace(match: re.Match[str]) -> str:
        new_id = mapping.get(int(match.group(1)))
        return f"[{new_id}]" if new_id is not None else ""

    return re.sub(r"[ \t]+([.,;:])", r"\1", _CITATION.sub(replace, _split_citation_groups(text)))


def strip_sources_section(markdown: str) -> str:
    """The UI and report list sources themselves; a model-written list could not be trusted."""
    return _TRAILING_SOURCES.sub("", markdown).strip()


def clean_title(raw: str | None, question: str, max_length: int = 90) -> str:
    """Produce a clean title from model output, falling back to the question when it is unusable."""
    title = _tidy_title(raw or "", max_length)
    if len(title) >= 8 and title.lower() not in _GENERIC_TITLES:
        return title
    fallback = _tidy_title(_QUESTION_LEAD.sub("", question.strip()), max_length)
    if len(fallback) < 8:
        return "Technical Research Report"
    return fallback[0].upper() + fallback[1:]


def _tidy_title(text: str, max_length: int) -> str:
    text = _normalize(re.sub(r"[`*_#]+|\[\d+\]", "", text))
    text = _TITLE_PREFIX.sub("", text.strip(" \"'“”‘’")).strip(" \"'“”‘’")
    if len(text) > max_length:
        # The part before a colon is usually a complete title on its own.
        head, colon, _ = text.partition(":")
        text = head if colon and 20 <= len(head) <= max_length else text[:max_length].rsplit(" ", 1)[0]
        # A shortened title must not end mid-phrase, as in "Throughput, Latency and".
        words = text.rstrip(" .,:;!?-–—").split()
        while len(words) > 1 and words[-1].lower().strip(",:;") in _DANGLING_WORDS:
            words.pop()
        text = " ".join(words)
    return text.rstrip(" .,:;!?-–—")


_NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")


def numbers_in(texts: Iterable[str]) -> set[float]:
    return {float(token.replace(",", "")) for text in texts for token in _NUMBER.findall(text)}


_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "twenty": 20,
}
_PAGE_COUNT = re.compile(r"\b(\d{1,3}|" + "|".join(_NUMBER_WORDS) + r")[\s-]*pages?\b", re.IGNORECASE)
_REPORT_REQUEST = re.compile(
    r"\b(generate|create|make|write|give|prepare|produce|build)\b(?:\W+\w+){0,6}?\W+(pdf|report)\b"
    r"|\b(\d{1,3}|" + "|".join(_NUMBER_WORDS) + r")[\s-]*pages?\W+(?:\w+\W+)?(pdf|report)\b",
    re.IGNORECASE,
)


def requested_report(question: str) -> tuple[bool, int | None]:
    """Whether the question itself asks for a PDF or report, and for how many pages."""
    if not _REPORT_REQUEST.search(question):
        return False, None
    match = _PAGE_COUNT.search(question)
    if match is None:
        return True, None
    token = match.group(1).lower()
    return True, _NUMBER_WORDS[token] if token in _NUMBER_WORDS else int(token)
