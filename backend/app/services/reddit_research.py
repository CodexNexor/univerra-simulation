"""
Reddit-backed research service with query decomposition and recency-aware filtering.
Uses public Reddit JSON endpoints for lightweight retrieval.
"""

import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger


logger = get_logger("univerra.reddit_research")


def _iso_from_utc(timestamp: Optional[float]) -> str:
    if not timestamp:
        return ""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _age_days(timestamp: Optional[float]) -> Optional[int]:
    if not timestamp:
        return None
    seconds = time.time() - float(timestamp)
    return max(0, int(seconds // 86400))


@dataclass
class RedditComment:
    author: str
    body: str
    score: int = 0
    created_utc: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "author": self.author,
            "body": self.body,
            "score": self.score,
            "created_utc": self.created_utc,
            "created_at": _iso_from_utc(self.created_utc),
            "age_days": _age_days(self.created_utc),
        }


@dataclass
class RedditPost:
    post_id: str
    title: str
    subreddit: str
    author: str
    permalink: str
    url: str
    selftext: str = ""
    score: int = 0
    num_comments: int = 0
    created_utc: Optional[float] = None
    matched_query: str = ""
    comments: List[RedditComment] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "post_id": self.post_id,
            "title": self.title,
            "subreddit": self.subreddit,
            "author": self.author,
            "permalink": self.permalink,
            "url": self.url,
            "selftext": self.selftext,
            "score": self.score,
            "num_comments": self.num_comments,
            "created_utc": self.created_utc,
            "created_at": _iso_from_utc(self.created_utc),
            "age_days": _age_days(self.created_utc),
            "matched_query": self.matched_query,
            "comments": [comment.to_dict() for comment in self.comments],
        }


@dataclass
class RedditResearchResult:
    query: str
    refined_queries: List[str] = field(default_factory=list)
    posts: List[RedditPost] = field(default_factory=list)
    summary: str = ""
    recency_note: str = ""
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "refined_queries": self.refined_queries,
            "posts": [post.to_dict() for post in self.posts],
            "summary": self.summary,
            "recency_note": self.recency_note,
            "error": self.error,
            "total_posts": len(self.posts),
        }

    def to_text(self) -> str:
        lines = [
            "## Reddit Field Research",
            f"Original query: {self.query}",
        ]

        if self.error:
            lines.extend(["", f"Error: {self.error}"])
            return "\n".join(lines)

        if self.refined_queries:
            lines.extend(["", "### Refined Search Prompts"])
            for index, query in enumerate(self.refined_queries, 1):
                lines.append(f"{index}. {query}")

        if self.recency_note:
            lines.extend(["", f"### Recency note\n{self.recency_note}"])

        if self.summary:
            lines.extend(["", "### Summary", self.summary])

        if self.posts:
            lines.extend(["", "### Relevant Reddit Threads"])
            for index, post in enumerate(self.posts[:6], 1):
                age = _age_days(post.created_utc)
                age_text = f"{age}d old" if age is not None else "date unknown"
                lines.append(
                    f"{index}. r/{post.subreddit} | {post.title} | score={post.score} | comments={post.num_comments} | {age_text}"
                )
                if post.selftext:
                    lines.append(f"   - {post.selftext[:220]}")
                lines.append(f"   - https://www.reddit.com{post.permalink}")
                for comment in post.comments[:2]:
                    snippet = comment.body[:180]
                    lines.append(f'   - Comment by u/{comment.author}: "{snippet}"')

        return "\n".join(lines)

    def to_context_text(self, max_posts: int = 4) -> str:
        lines = [
            f"Original query: {self.query}",
        ]
        if self.refined_queries:
            lines.append("Refined queries: " + " | ".join(self.refined_queries[:4]))
        if self.recency_note:
            lines.append("Recency note: " + self.recency_note)
        if self.summary:
            lines.append("Summary: " + self.summary)
        for post in self.posts[:max_posts]:
            age = _age_days(post.created_utc)
            age_text = f"{age} days old" if age is not None else "date unknown"
            lines.append(
                f"Thread: r/{post.subreddit} | {post.title} | {age_text} | score {post.score} | comments {post.num_comments}"
            )
            if post.comments:
                lines.append("Comment signals: " + " | ".join(comment.body[:120] for comment in post.comments[:2]))
        return "\n".join(lines)


class RedditResearchService:
    SEARCH_BASE = "https://www.reddit.com/search.json"

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self._llm_client = llm_client
        self._cache: Dict[str, RedditResearchResult] = {}

    @property
    def llm(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client

    @property
    def enabled(self) -> bool:
        return Config.REDDIT_RESEARCH_ENABLED

    def research(
        self,
        query: str,
        scenario_context: str = "",
        max_subqueries: Optional[int] = None,
        posts_per_query: Optional[int] = None,
        comments_per_post: Optional[int] = None,
        max_age_days: Optional[int] = None,
    ) -> RedditResearchResult:
        query = (query or "").strip()
        if not query:
            return RedditResearchResult(query=query, error="empty query")
        if not self.enabled:
            return RedditResearchResult(query=query, error="reddit research disabled")

        cache_key = json.dumps({
            "query": query,
            "scenario_context": scenario_context[:1200],
            "max_subqueries": max_subqueries or Config.REDDIT_MAX_SUBQUERIES,
            "posts_per_query": posts_per_query or Config.REDDIT_POSTS_PER_QUERY,
            "comments_per_post": comments_per_post or Config.REDDIT_COMMENTS_PER_POST,
            "max_age_days": max_age_days or Config.REDDIT_MAX_AGE_DAYS,
        }, sort_keys=True, ensure_ascii=False)
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = RedditResearchResult(query=query)
        max_subqueries = max_subqueries or Config.REDDIT_MAX_SUBQUERIES
        posts_per_query = posts_per_query or Config.REDDIT_POSTS_PER_QUERY
        comments_per_post = comments_per_post or Config.REDDIT_COMMENTS_PER_POST
        max_age_days = max_age_days or Config.REDDIT_MAX_AGE_DAYS

        refined_queries = self._decompose_query(query, scenario_context, max_queries=max_subqueries)
        result.refined_queries = refined_queries

        posts_by_id: Dict[str, RedditPost] = {}
        recent_posts = 0

        for refined_query in refined_queries:
            listing = self._search_posts(refined_query, limit=posts_per_query * 2)
            for post in listing:
                age = _age_days(post.created_utc)
                if age is not None and age <= max_age_days:
                    recent_posts += 1
                if age is not None and age > max_age_days:
                    continue
                if not self._is_plausibly_relevant(post, refined_query):
                    continue
                if post.post_id in posts_by_id:
                    continue
                post.matched_query = refined_query
                posts_by_id[post.post_id] = post

        ranked_posts = sorted(
            posts_by_id.values(),
            key=lambda post: self._score_post(post, query),
            reverse=True,
        )
        selected_posts = self._select_relevant_posts(
            original_query=query,
            scenario_context=scenario_context,
            posts=ranked_posts[:12],
            max_posts=max(4, posts_per_query * 2),
        )
        for post in selected_posts:
            post.comments = self._fetch_comments(post.permalink, limit=comments_per_post)
        result.posts = selected_posts
        result.recency_note = self._build_recency_note(result.posts, recent_posts, max_age_days)
        result.summary = self._summarize(query, scenario_context, result)
        self._cache[cache_key] = result
        return result

    def _request_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
        params = dict(params or {})
        params["raw_json"] = 1
        query_string = urllib.parse.urlencode(params)
        full_url = f"{url}?{query_string}" if query_string else url
        request = urllib.request.Request(
            full_url,
            headers={
                "User-Agent": Config.REDDIT_USER_AGENT,
                "Accept": "application/json",
            },
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=Config.REDDIT_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))

    def _decompose_query(self, query: str, scenario_context: str, max_queries: int) -> List[str]:
        prompt = (
            "Break the user's request into focused search prompts for Reddit research. "
            "Return concise keyword-style prompts, not full sentences, and do not include the word Reddit in the prompts. "
            "Prefer prompts that surface real experiences, tradeoffs, recent market sentiment, and conflicting opinions. "
            f"Return JSON as {{\"queries\": [\"...\"]}} with up to {max_queries} items."
        )
        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": prompt},
                    {
                        "role": "user",
                        "content": f"User query: {query}\nScenario context: {scenario_context[:2500]}",
                    },
                ],
                temperature=0.2,
                max_tokens=500,
            )
            queries = [str(item).strip() for item in response.get("queries", []) if str(item).strip()]
        except Exception as exc:
            logger.warning(f"Reddit query decomposition failed, using fallback: {exc}")
            queries = []

        if not queries:
            queries = [
                query,
                f"{query} recent experience",
                f"{query} real world advice",
                f"{query} reddit discussion",
            ]

        deduped = []
        for item in queries:
            if item not in deduped:
                deduped.append(item)
        return deduped[:max_queries]

    def _search_posts(self, query: str, limit: int) -> List[RedditPost]:
        try:
            payload = self._request_json(
                self.SEARCH_BASE,
                params={
                    "q": query,
                    "sort": "relevance",
                    "t": "year",
                    "limit": max(1, min(limit, 15)),
                    "type": "link",
                    "include_over_18": "off",
                },
            )
        except urllib.error.HTTPError as exc:
            logger.warning(f"Reddit search HTTP error for '{query[:80]}': {exc.code}")
            return []
        except Exception as exc:
            logger.warning(f"Reddit search failed for '{query[:80]}': {exc}")
            return []

        posts: List[RedditPost] = []
        for child in (((payload or {}).get("data") or {}).get("children") or []):
            data = child.get("data") or {}
            post = RedditPost(
                post_id=str(data.get("id") or ""),
                title=(data.get("title") or "").strip(),
                subreddit=(data.get("subreddit") or "").strip(),
                author=(data.get("author") or "").strip(),
                permalink=(data.get("permalink") or "").strip(),
                url=(data.get("url") or "").strip(),
                selftext=(data.get("selftext") or "").strip()[:500],
                score=int(data.get("score") or 0),
                num_comments=int(data.get("num_comments") or 0),
                created_utc=float(data.get("created_utc") or 0) or None,
            )
            if post.post_id and post.title:
                posts.append(post)
        return posts

    def _fetch_comments(self, permalink: str, limit: int) -> List[RedditComment]:
        permalink = (permalink or "").strip()
        if not permalink:
            return []
        url = f"https://www.reddit.com{permalink}.json"
        try:
            payload = self._request_json(
                url,
                params={
                    "sort": "top",
                    "limit": max(1, min(limit, 8)),
                },
            )
        except Exception as exc:
            logger.warning(f"Reddit comment fetch failed for '{permalink[:80]}': {exc}")
            return []

        if not isinstance(payload, list) or len(payload) < 2:
            return []
        comments_root = ((payload[1] or {}).get("data") or {}).get("children") or []
        comments: List[RedditComment] = []

        def walk(children: List[Dict[str, Any]]):
            for child in children:
                if child.get("kind") != "t1":
                    continue
                data = child.get("data") or {}
                body = (data.get("body") or "").strip()
                if body:
                    comments.append(
                        RedditComment(
                            author=(data.get("author") or "").strip(),
                            body=body[:500],
                            score=int(data.get("score") or 0),
                            created_utc=float(data.get("created_utc") or 0) or None,
                        )
                    )
                replies = data.get("replies")
                if isinstance(replies, dict):
                    walk(((replies.get("data") or {}).get("children") or []))

        walk(comments_root)
        comments.sort(key=lambda item: (item.score, -(item.created_utc or 0)), reverse=True)
        return comments[:limit]

    def _score_post(self, post: RedditPost, original_query: str) -> float:
        age = _age_days(post.created_utc)
        recency_score = 0.0
        if age is not None:
            recency_score = max(0.0, 1.0 - min(age, Config.REDDIT_MAX_AGE_DAYS) / max(1, Config.REDDIT_MAX_AGE_DAYS))

        text = f"{post.title} {post.selftext} {' '.join(comment.body for comment in post.comments[:3])}".lower()
        query_tokens = self._query_tokens(original_query)
        overlap = sum(1 for token in query_tokens if token in text)
        match_score = overlap / max(1, len(query_tokens))
        engagement_score = math.log1p(max(0, post.score) + max(0, post.num_comments))
        return recency_score * 2.5 + match_score * 5 + engagement_score

    def _query_tokens(self, query: str) -> List[str]:
        stopwords = {
            "reddit", "discussion", "recent", "about", "with", "from", "into", "real",
            "world", "opinions", "threads", "experience", "experiences", "impact",
            "what", "how", "does", "will", "would", "could", "should", "and", "the",
        }
        tokens = []
        for raw in query.lower().replace("‑", "-").replace("/", " ").split():
            token = "".join(ch for ch in raw if ch.isalnum() or ch in {"-", "+"}).strip("-+")
            if len(token) >= 3 and token not in stopwords:
                tokens.append(token)
        deduped = []
        for token in tokens:
            if token not in deduped:
                deduped.append(token)
        return deduped

    def _is_plausibly_relevant(self, post: RedditPost, query: str) -> bool:
        tokens = self._query_tokens(query)
        if not tokens:
            return True
        text = f"{post.title} {post.selftext} {post.subreddit}".lower()
        overlap = sum(1 for token in tokens if token in text)
        if overlap >= min(2, len(tokens)):
            return True
        if len(tokens) <= 3 and overlap >= 1:
            return True
        return False

    def _select_relevant_posts(
        self,
        original_query: str,
        scenario_context: str,
        posts: List[RedditPost],
        max_posts: int,
    ) -> List[RedditPost]:
        if not posts:
            return []

        compact = []
        for index, post in enumerate(posts):
            compact.append({
                "index": index,
                "title": post.title,
                "subreddit": post.subreddit,
                "selftext": post.selftext[:100],
                "age_days": _age_days(post.created_utc),
                "score": post.score,
                "num_comments": post.num_comments,
                "matched_query": post.matched_query,
            })

        try:
            response = self.llm.chat_json(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Select the most relevant Reddit threads for the user query. "
                            "Prefer threads that are actually about the topic, recent, concrete, and not spam, hiring noise, or unrelated promotion. "
                            "Return JSON as {\"selected_indices\": [..], \"reasoning\": \"...\"}. "
                            "Keep reasoning under 20 words."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Original query: {original_query}\n"
                            f"Scenario context: {scenario_context[:1500]}\n"
                            f"Candidate Reddit threads: {json.dumps(compact, ensure_ascii=False)}\n"
                            f"Pick up to {max_posts} relevant threads."
                        ),
                    },
                ],
                temperature=0.1,
                max_tokens=220,
            )
            selected_indices = [
                int(item) for item in response.get("selected_indices", [])
                if str(item).isdigit() and 0 <= int(item) < len(posts)
            ]
        except Exception as exc:
            logger.warning(f"Reddit post selection fallback due to: {exc}")
            selected_indices = []

        if not selected_indices:
            return posts[:max_posts]

        chosen = []
        seen = set()
        for index in selected_indices:
            if index not in seen:
                chosen.append(posts[index])
                seen.add(index)
            if len(chosen) >= max_posts:
                break
        return chosen or posts[:max_posts]

    def _build_recency_note(self, posts: List[RedditPost], recent_posts: int, max_age_days: int) -> str:
        if not posts:
            return "No sufficiently relevant recent Reddit threads were retrieved."

        ages = [age for age in (_age_days(post.created_utc) for post in posts) if age is not None]
        if not ages:
            return "Reddit threads were retrieved, but publish dates could not be verified consistently."

        newest = min(ages)
        oldest = max(ages)
        return (
            f"Selected {len(posts)} Reddit threads after recency filtering. "
            f"Freshness window: <= {max_age_days} days. "
            f"Retrieved threads range from {newest} to {oldest} days old; "
            f"{recent_posts} candidate posts met the recency threshold before ranking."
        )

    def _summarize(self, query: str, scenario_context: str, result: RedditResearchResult) -> str:
        if not result.posts:
            return "No strong recent Reddit evidence was retrieved for this question."

        compact_posts = []
        for post in result.posts[:5]:
            compact_posts.append({
                "title": post.title,
                "subreddit": post.subreddit,
                "age_days": _age_days(post.created_utc),
                "score": post.score,
                "num_comments": post.num_comments,
                "matched_query": post.matched_query,
                "selftext": post.selftext[:220],
                "comment_signals": [comment.body[:180] for comment in post.comments[:2]],
            })

        try:
            response = self.llm.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Summarize recent Reddit evidence for a simulation system. "
                            "Be concrete, mention disagreements, mention freshness limits, and do not invent facts."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Original query: {query}\n"
                            f"Scenario context: {scenario_context[:2000]}\n"
                            f"Reddit evidence JSON:\n{json.dumps(compact_posts, ensure_ascii=False)}\n\n"
                            "Write a short paragraph that captures the strongest recurring views, meaningful disagreement, "
                            "and any obvious evidence limits."
                        ),
                    },
                ],
                temperature=0.2,
                max_tokens=500,
            )
            return response.strip()
        except Exception as exc:
            logger.warning(f"Reddit evidence summary failed, using fallback: {exc}")
            titles = "; ".join(post.title for post in result.posts[:3])
            return (
                "Recent Reddit threads point to recurring discussion around: "
                + titles
                + ". Evidence should still be treated as anecdotal discussion rather than ground truth."
            )
