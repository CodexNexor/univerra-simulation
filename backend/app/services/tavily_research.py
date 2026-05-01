"""
Lightweight Tavily-backed web research service.
"""

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from ..config import Config
from ..utils.logger import get_logger


logger = get_logger("univerra.tavily")


@dataclass
class WebSource:
    title: str
    url: str
    content: str = ""
    score: Optional[float] = None
    published_date: str = ""

    @property
    def domain(self) -> str:
        try:
            return urlparse(self.url).netloc
        except Exception:
            return ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "content": self.content,
            "score": self.score,
            "published_date": self.published_date,
            "domain": self.domain,
        }


@dataclass
class WebResearchResult:
    query: str
    answer: str = ""
    sources: List[WebSource] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "answer": self.answer,
            "sources": [source.to_dict() for source in self.sources],
            "error": self.error,
            "total_results": len(self.sources),
        }

    def to_text(self) -> str:
        lines = [
            "## Deep Web Research",
            f"Query: {self.query}",
        ]

        if self.error:
            lines.extend(["", f"Error: {self.error}"])
            return "\n".join(lines)

        if self.answer:
            lines.extend(["", "### Summary Answer", self.answer])

        if self.sources:
            lines.extend(["", "### Fresh Sources"])
            for index, source in enumerate(self.sources, 1):
                meta = source.domain
                if source.published_date:
                    meta = f"{meta} | {source.published_date}" if meta else source.published_date
                lines.append(f"{index}. {source.title} [{meta}]")
                if source.content:
                    lines.append(f"   - {source.content}")
                if source.url:
                    lines.append(f"   - {source.url}")

        return "\n".join(lines)


class TavilyResearchService:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        max_results: Optional[int] = None,
        search_depth: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ):
        self.api_key = api_key or Config.TAVILY_API_KEY
        self.base_url = (base_url or Config.TAVILY_BASE_URL).rstrip("/")
        self.max_results = max_results or Config.TAVILY_MAX_RESULTS
        self.search_depth = search_depth or Config.TAVILY_SEARCH_DEPTH
        self.timeout_seconds = timeout_seconds or Config.TAVILY_TIMEOUT_SECONDS
        self.max_age_days = Config.TAVILY_MAX_AGE_DAYS

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: Optional[int] = None) -> WebResearchResult:
        query = (query or "").strip()
        if not query:
            return WebResearchResult(query=query, error="empty query")

        if not self.enabled:
            return WebResearchResult(query=query, error="Tavily is not configured")

        payload = {
            "query": query,
            "search_depth": self.search_depth,
            "max_results": max(1, min(max_results or self.max_results, 5)),
            "include_answer": True,
            "include_raw_content": False,
            "include_images": False,
            "topic": "general",
        }

        request = urllib.request.Request(
            f"{self.base_url}/search",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
            data = json.loads(raw)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            logger.warning(f"Tavily HTTP error for query '{query[:80]}': {exc.code} {body[:300]}")
            return WebResearchResult(query=query, error=f"Tavily HTTP {exc.code}")
        except Exception as exc:
            logger.warning(f"Tavily request failed for query '{query[:80]}': {exc}")
            return WebResearchResult(query=query, error=str(exc))

        results = data.get("results", []) or []
        sources: List[WebSource] = []
        for item in results:
            snippet = (item.get("content") or item.get("raw_content") or "").strip()
            if len(snippet) > 320:
                snippet = snippet[:317].rstrip() + "..."
            sources.append(
                WebSource(
                    title=(item.get("title") or "Untitled source").strip(),
                    url=(item.get("url") or "").strip(),
                    content=snippet,
                    score=item.get("score"),
                    published_date=(item.get("published_date") or "").strip(),
                )
            )

        answer = (data.get("answer") or "").strip()
        sources = self._prefer_recent_sources(sources)
        return WebResearchResult(
            query=query,
            answer=answer,
            sources=sources,
        )

    def _prefer_recent_sources(self, sources: List[WebSource]) -> List[WebSource]:
        def parse_age_days(source: WebSource) -> int:
            raw = (source.published_date or "").strip()
            if not raw:
                return self.max_age_days + 999
            for candidate in [raw, raw.replace("Z", "+00:00")]:
                try:
                    parsed = datetime.fromisoformat(candidate)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    return max(0, int((datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).days))
                except Exception:
                    continue
            return self.max_age_days + 999

        dated_recent = []
        undated = []
        stale = []
        for source in sources:
            age_days = parse_age_days(source)
            if age_days <= self.max_age_days:
                dated_recent.append((age_days, source))
            elif age_days == self.max_age_days + 999:
                undated.append(source)
            else:
                stale.append((age_days, source))

        dated_recent.sort(key=lambda item: (item[0], -(item[1].score or 0)))
        stale.sort(key=lambda item: (item[0], -(item[1].score or 0)))
        ordered = [source for _, source in dated_recent] + undated + [source for _, source in stale]
        return ordered[: self.max_results]
