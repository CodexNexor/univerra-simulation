"""
Local graph retrieval service.
"""

import csv
import json
import os
import re
from dataclasses import dataclass, field
from collections import Counter
from typing import Any, Dict, List, Optional

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .local_graph_store import LocalGraphStore, tokenize_text
from .reddit_research import RedditResearchService, RedditResearchResult
from .tavily_research import TavilyResearchService, WebResearchResult


logger = get_logger("univerra.graph_tools")


@dataclass
class SearchResult:
    facts: List[str]
    edges: List[Dict[str, Any]]
    nodes: List[Dict[str, Any]]
    query: str
    total_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "facts": self.facts,
            "edges": self.edges,
            "nodes": self.nodes,
            "query": self.query,
            "total_count": self.total_count,
        }

    def to_text(self) -> str:
        lines = [
            f"Search query: {self.query}",
            f"Found {self.total_count} items",
        ]

        if self.facts:
            lines.append("")
            lines.append("### Related facts:")
            for index, fact in enumerate(self.facts, 1):
                lines.append(f"{index}. {fact}")

        if self.edges:
            lines.append("")
            lines.append("### Related Edges:")
            for edge in self.edges:
                source = edge.get("source_node_name") or edge.get("source_node_uuid", "")[:8]
                target = edge.get("target_node_name") or edge.get("target_node_uuid", "")[:8]
                relation = edge.get("name", "RELATED_TO")
                lines.append(f"- {source} --[{relation}]--> {target}")

        if self.nodes:
            lines.append("")
            lines.append("### Related Nodes:")
            for node in self.nodes:
                labels = node.get("labels", [])
                entity_type = next((label for label in labels if label not in {"Entity", "Node"}), "")
                if entity_type:
                    lines.append(f"- **{node.get('name', '')}** ({entity_type})")
                else:
                    lines.append(f"- {node.get('name', '')}")

        return "\n".join(lines)


@dataclass
class NodeInfo:
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
        }


@dataclass
class EdgeInfo:
    uuid: str
    name: str
    fact: str
    source_node_uuid: str
    target_node_uuid: str
    source_node_name: Optional[str] = None
    target_node_name: Optional[str] = None
    created_at: Optional[str] = None
    valid_at: Optional[str] = None
    invalid_at: Optional[str] = None
    expired_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "fact": self.fact,
            "source_node_uuid": self.source_node_uuid,
            "target_node_uuid": self.target_node_uuid,
            "source_node_name": self.source_node_name,
            "target_node_name": self.target_node_name,
            "created_at": self.created_at,
            "valid_at": self.valid_at,
            "invalid_at": self.invalid_at,
            "expired_at": self.expired_at,
        }

    @property
    def is_expired(self) -> bool:
        return bool(self.expired_at)

    @property
    def is_invalid(self) -> bool:
        return bool(self.invalid_at)


@dataclass
class InsightForgeResult:
    query: str
    simulation_requirement: str
    sub_queries: List[str]
    semantic_facts: List[str] = field(default_factory=list)
    entity_insights: List[Dict[str, Any]] = field(default_factory=list)
    relationship_chains: List[str] = field(default_factory=list)
    total_facts: int = 0
    total_entities: int = 0
    total_relationships: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "simulation_requirement": self.simulation_requirement,
            "sub_queries": self.sub_queries,
            "semantic_facts": self.semantic_facts,
            "entity_insights": self.entity_insights,
            "relationship_chains": self.relationship_chains,
            "total_facts": self.total_facts,
            "total_entities": self.total_entities,
            "total_relationships": self.total_relationships,
        }

    def to_text(self) -> str:
        lines = [
            "## Future Prediction Deep Analysis",
            f"Analysis question: {self.query}",
            f"Prediction scenario: {self.simulation_requirement}",
            "",
            "### Prediction DataStatistics",
            f"- Related prediction facts: {self.total_facts}",
            f"- Entities involved: {self.total_entities}",
            f"- Relationship chains: {self.total_relationships}",
        ]

        if self.sub_queries:
            lines.append("")
            lines.append("### Analysis Sub-questions")
            for index, sub_query in enumerate(self.sub_queries, 1):
                lines.append(f"{index}. {sub_query}")

        if self.semantic_facts:
            lines.append("")
            lines.append("### [Key Facts]")
            for index, fact in enumerate(self.semantic_facts, 1):
                lines.append(f'{index}. "{fact}"')

        if self.entity_insights:
            lines.append("")
            lines.append("### [Core Entities]")
            for entity in self.entity_insights:
                lines.append(f"- **{entity.get('name', 'Unknown')}** ({entity.get('type', 'Entity')})")
                if entity.get("summary"):
                    lines.append(f'  Summary: "{entity.get("summary", "")}"')
                lines.append(f'  Related facts: {len(entity.get("related_facts", []))}')

        if self.relationship_chains:
            lines.append("")
            lines.append("### [Relationship Chains]")
            for chain in self.relationship_chains:
                lines.append(f"- {chain}")

        return "\n".join(lines)


@dataclass
class PanoramaResult:
    query: str
    all_nodes: List[NodeInfo] = field(default_factory=list)
    all_edges: List[EdgeInfo] = field(default_factory=list)
    active_facts: List[str] = field(default_factory=list)
    historical_facts: List[str] = field(default_factory=list)
    total_nodes: int = 0
    total_edges: int = 0
    active_count: int = 0
    historical_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "all_nodes": [node.to_dict() for node in self.all_nodes],
            "all_edges": [edge.to_dict() for edge in self.all_edges],
            "active_facts": self.active_facts,
            "historical_facts": self.historical_facts,
            "total_nodes": self.total_nodes,
            "total_edges": self.total_edges,
            "active_count": self.active_count,
            "historical_count": self.historical_count,
        }

    def to_text(self) -> str:
        lines = [
            "## Panorama Search Results (Future Full View)",
            f"Query: {self.query}",
            "",
            "### Statistics",
            f"- Total nodes: {self.total_nodes}",
            f"- Total edges: {self.total_edges}",
            f"- Current valid facts: {self.active_count}",
            f"- Historical/expired facts: {self.historical_count}",
        ]

        if self.active_facts:
            lines.append("")
            lines.append("### [Current Valid Facts]")
            for index, fact in enumerate(self.active_facts, 1):
                lines.append(f'{index}. "{fact}"')

        if self.historical_facts:
            lines.append("")
            lines.append("### 【Historical/expired facts】")
            for index, fact in enumerate(self.historical_facts, 1):
                lines.append(f'{index}. "{fact}"')

        if self.all_nodes:
            lines.append("")
            lines.append("### [Involved Entities]")
            for node in self.all_nodes:
                entity_type = next((label for label in node.labels if label not in {"Entity", "Node"}), "Entity")
                lines.append(f"- **{node.name}** ({entity_type})")

        return "\n".join(lines)


@dataclass
class AgentInterview:
    agent_name: str
    agent_role: str
    agent_bio: str
    question: str
    response: str
    key_quotes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "agent_role": self.agent_role,
            "agent_bio": self.agent_bio,
            "question": self.question,
            "response": self.response,
            "key_quotes": self.key_quotes,
        }


@dataclass
class InterviewResult:
    interview_topic: str
    interview_questions: List[str] = field(default_factory=list)
    selected_agents: List[Dict[str, Any]] = field(default_factory=list)
    selection_reasoning: str = ""
    total_agents: int = 0
    interviewed_count: int = 0
    interviews: List[AgentInterview] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "interview_topic": self.interview_topic,
            "interview_questions": self.interview_questions,
            "selected_agents": self.selected_agents,
            "selection_reasoning": self.selection_reasoning,
            "total_agents": self.total_agents,
            "interviewed_count": self.interviewed_count,
            "interviews": [interview.to_dict() for interview in self.interviews],
            "summary": self.summary,
        }

    def to_text(self) -> str:
        lines = [
            f"**Interview Topic:** {self.interview_topic}",
            f"**Interview Count:** {self.interviewed_count} / {self.total_agents}",
            "",
            "### Interview Subject Selection Reasons",
        ]

        if self.selected_agents:
            for index, agent in enumerate(self.selected_agents, 1):
                name = agent.get("realname", agent.get("username", f"Agent_{index}"))
                profession = agent.get("profession", "Unknown")
                bio = agent.get("bio", "")[:140]
                lines.append(f"{index}. **{name}(index={index - 1})**: Selected for relevance as {profession}. {bio}".strip())
        elif self.selection_reasoning:
            lines.append(self.selection_reasoning)
        else:
            lines.append("Selected the most relevant available agents for the topic.")

        for index, interview in enumerate(self.interviews, 1):
            lines.extend([
                "",
                "---",
                f"#### Interview #{index}: {interview.agent_name}",
                f"**{interview.agent_name}** ({interview.agent_role})",
                f"_Bio: {interview.agent_bio}_",
                f"**Q:** {interview.question}",
                "**A:**",
                interview.response.replace("[Twitter]\n", "[Twitter Platform Answer]\n").replace("[Reddit]\n", "[Reddit Platform Answer]\n"),
                "",
                "**Key Quotes:**",
            ])
            for quote in interview.key_quotes:
                lines.append(f'> "{quote}"')

        lines.extend([
            "",
            "### Interview Summary and Key Insights",
            self.summary or "No interview summary available.",
        ])
        return "\n".join(lines)


class GraphToolsService:
    MAX_RETRIES = 3

    def __init__(
        self,
        api_key: Optional[str] = None,
        llm_client: Optional[LLMClient] = None,
        web_research: Optional[TavilyResearchService] = None,
        reddit_research: Optional[RedditResearchService] = None,
    ):
        self.api_key = api_key
        self._llm_client = llm_client
        self._web_research = web_research
        self._reddit_research = reddit_research

    @property
    def llm(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client

    @property
    def web_research(self) -> TavilyResearchService:
        if self._web_research is None:
            self._web_research = TavilyResearchService()
        return self._web_research

    @property
    def reddit_research(self) -> RedditResearchService:
        if self._reddit_research is None:
            self._reddit_research = RedditResearchService(llm_client=self.llm)
        return self._reddit_research

    def _run_web_research(self, query: str, max_results: int = 3) -> WebResearchResult:
        query = (query or "").strip()
        if not query or not self.web_research.enabled:
            return WebResearchResult(query=query, error="web research disabled")
        return self.web_research.search(query=query, max_results=max_results)

    def _run_reddit_research(
        self,
        query: str,
        scenario_context: str = "",
        max_age_days: Optional[int] = None,
    ) -> RedditResearchResult:
        query = (query or "").strip()
        if not query or not self.reddit_research.enabled:
            return RedditResearchResult(query=query, error="reddit research disabled")
        return self.reddit_research.research(
            query=query,
            scenario_context=scenario_context,
            max_age_days=max_age_days or Config.REDDIT_MAX_AGE_DAYS,
        )

    def _web_result_to_facts(self, result: WebResearchResult, limit: int = 3) -> List[str]:
        if result.error:
            return []

        facts: List[str] = []
        if result.answer:
            facts.append(f"[Web summary] {result.answer}")

        for source in result.sources[:limit]:
            domain = source.domain or "web"
            title = source.title or domain
            snippet = source.content or "Source retrieved with limited snippet text."
            facts.append(f"[Web source] {title} ({domain}): {snippet} [{source.url}]")

        return facts

    def _reddit_result_to_facts(self, result: RedditResearchResult, limit: int = 3) -> List[str]:
        if result.error:
            return []

        facts: List[str] = []
        if result.summary:
            facts.append(f"[Reddit summary] {result.summary}")
        if result.recency_note:
            facts.append(f"[Reddit recency] {result.recency_note}")

        for post in result.posts[:limit]:
            age = post.to_dict().get("age_days")
            age_text = f"{age} days old" if age is not None else "date unknown"
            facts.append(
                f"[Reddit thread] r/{post.subreddit} | {post.title} | {age_text} | score {post.score} | comments {post.num_comments}"
            )
            for comment in post.comments[:2]:
                facts.append(
                    f"[Reddit comment] r/{post.subreddit} | u/{comment.author}: {comment.body}"
                )
        return facts

    def _graph_data(self, graph_id: str) -> Dict[str, Any]:
        return LocalGraphStore.get_graph_data(graph_id)

    def search_graph(self, graph_id: str, query: str, limit: int = 10, scope: str = "edges") -> SearchResult:
        graph = self._graph_data(graph_id)
        query_tokens = set(tokenize_text(query))
        node_map = {node["uuid"]: node.get("name", "") for node in graph.get("nodes", [])}
        episode_map = {episode.get("episode_id", ""): episode for episode in graph.get("episodes", [])}
        nodes = []
        edges = []
        facts = []
        seen_facts = set()

        def score_text(*parts: str) -> int:
            text = " ".join(part for part in parts if part)
            return LocalGraphStore.score_text_match(query, text)

        if scope in {"nodes", "both"}:
            scored_nodes = []
            for node in graph.get("nodes", []):
                attribute_text = " ".join(
                    str(value)
                    for value in (node.get("attributes") or {}).values()
                    if value not in (None, "", [], {})
                )
                score = score_text(
                    node.get("name", ""),
                    node.get("summary", ""),
                    " ".join(node.get("labels", [])),
                    attribute_text,
                )
                mention_count = int((node.get("attributes") or {}).get("mention_count", 0) or 0)
                score += min(mention_count, 6)
                if score > 0:
                    scored_nodes.append((score, node))
            for _, node in sorted(scored_nodes, key=lambda item: item[0], reverse=True)[:limit]:
                nodes.append({
                    "uuid": node.get("uuid", ""),
                    "name": node.get("name", ""),
                    "labels": node.get("labels", []),
                    "summary": node.get("summary", ""),
                })
                if node.get("summary"):
                    fact = f"[{node.get('name', '')}] {node.get('summary', '')}"
                    if fact not in seen_facts:
                        facts.append(fact)
                        seen_facts.add(fact)

        if scope in {"edges", "both"}:
            scored_edges = []
            for edge in graph.get("edges", []):
                source_name = node_map.get(edge.get("source_node_uuid", ""), "")
                target_name = node_map.get(edge.get("target_node_uuid", ""), "")
                episode_snippets = []
                for episode_id in edge.get("episodes", [])[:2]:
                    episode = episode_map.get(episode_id) or {}
                    if episode.get("text"):
                        episode_snippets.append(episode.get("text", "")[:220])
                score = score_text(
                    edge.get("name", ""),
                    edge.get("fact", ""),
                    source_name,
                    target_name,
                    " ".join(episode_snippets),
                )
                edge_weight = int((edge.get("attributes") or {}).get("weight", 0) or 0)
                score += min(edge_weight * 2, 12)
                if score > 0:
                    scored_edges.append((score, edge))
            for _, edge in sorted(scored_edges, key=lambda item: item[0], reverse=True)[:limit]:
                edges.append({
                    "uuid": edge.get("uuid", ""),
                    "name": edge.get("name", ""),
                    "fact": edge.get("fact", ""),
                    "source_node_uuid": edge.get("source_node_uuid", ""),
                    "target_node_uuid": edge.get("target_node_uuid", ""),
                    "source_node_name": node_map.get(edge.get("source_node_uuid", ""), ""),
                    "target_node_name": node_map.get(edge.get("target_node_uuid", ""), ""),
                })
                if edge.get("fact"):
                    fact = edge["fact"]
                    if fact not in seen_facts:
                        facts.append(fact)
                        seen_facts.add(fact)

        if graph.get("episodes"):
            scored_episodes = []
            for episode in graph.get("episodes", []):
                score = score_text(episode.get("text", ""))
                if score > 0:
                    scored_episodes.append((score, episode))
            for _, episode in sorted(scored_episodes, key=lambda item: item[0], reverse=True)[:limit]:
                snippet = episode.get("text", "").strip()
                if snippet:
                    fact = snippet[:280] + ("..." if len(snippet) > 280 else "")
                    if fact not in seen_facts:
                        facts.append(fact)
                        seen_facts.add(fact)

        # If direct token matches are weak, include related nodes by edge endpoints.
        if query_tokens and not facts and graph.get("edges"):
            node_names = {node["uuid"]: node.get("name", "") for node in graph.get("nodes", [])}
            for edge in graph.get("edges", [])[:limit]:
                source = node_names.get(edge.get("source_node_uuid", ""), "")
                target = node_names.get(edge.get("target_node_uuid", ""), "")
                if query_tokens & set(tokenize_text(source + " " + target)):
                    fact = edge.get("fact", "")
                    if fact and fact not in seen_facts:
                        facts.append(fact)
                        seen_facts.add(fact)

        return SearchResult(
            facts=facts[:limit],
            edges=edges[:limit],
            nodes=nodes[:limit],
            query=query,
            total_count=len(facts[:limit]),
        )

    def get_all_nodes(self, graph_id: str) -> List[NodeInfo]:
        graph = self._graph_data(graph_id)
        return [
            NodeInfo(
                uuid=node.get("uuid", ""),
                name=node.get("name", ""),
                labels=node.get("labels", []),
                summary=node.get("summary", ""),
                attributes=node.get("attributes", {}),
            )
            for node in graph.get("nodes", [])
        ]

    def get_all_edges(self, graph_id: str, include_temporal: bool = True) -> List[EdgeInfo]:
        graph = self._graph_data(graph_id)
        node_map = {node["uuid"]: node.get("name", "") for node in graph.get("nodes", [])}
        return [
            EdgeInfo(
                uuid=edge.get("uuid", ""),
                name=edge.get("name", ""),
                fact=edge.get("fact", ""),
                source_node_uuid=edge.get("source_node_uuid", ""),
                target_node_uuid=edge.get("target_node_uuid", ""),
                source_node_name=node_map.get(edge.get("source_node_uuid", ""), ""),
                target_node_name=node_map.get(edge.get("target_node_uuid", ""), ""),
                created_at=edge.get("created_at"),
                valid_at=edge.get("valid_at"),
                invalid_at=edge.get("invalid_at"),
                expired_at=edge.get("expired_at"),
            )
            for edge in graph.get("edges", [])
        ]

    def get_node_detail(self, node_uuid: str) -> Optional[NodeInfo]:
        graphs_root = LocalGraphStore.ROOT_DIR
        if not os.path.exists(graphs_root):
            return None
        for graph_id in os.listdir(graphs_root):
            try:
                graph = self._graph_data(graph_id)
            except FileNotFoundError:
                continue
            for node in graph.get("nodes", []):
                if node.get("uuid") == node_uuid:
                    return NodeInfo(
                        uuid=node.get("uuid", ""),
                        name=node.get("name", ""),
                        labels=node.get("labels", []),
                        summary=node.get("summary", ""),
                        attributes=node.get("attributes", {}),
                    )
        return None

    def get_node_edges(self, graph_id: str, node_uuid: str) -> List[EdgeInfo]:
        return [
            edge for edge in self.get_all_edges(graph_id)
            if edge.source_node_uuid == node_uuid or edge.target_node_uuid == node_uuid
        ]

    def get_entities_by_type(self, graph_id: str, entity_type: str) -> List[NodeInfo]:
        return [node for node in self.get_all_nodes(graph_id) if entity_type in node.labels]

    def get_entity_summary(self, graph_id: str, entity_name: str) -> Dict[str, Any]:
        entity = next((node for node in self.get_all_nodes(graph_id) if node.name.lower() == entity_name.lower()), None)
        related_edges = self.get_node_edges(graph_id, entity.uuid) if entity else []
        search = self.search_graph(graph_id, entity_name, limit=20, scope="both")
        return {
            "entity_name": entity_name,
            "entity_info": entity.to_dict() if entity else None,
            "related_facts": search.facts,
            "related_edges": [edge.to_dict() for edge in related_edges],
            "total_relations": len(related_edges),
        }

    def get_graph_statistics(self, graph_id: str) -> Dict[str, Any]:
        nodes = self.get_all_nodes(graph_id)
        edges = self.get_all_edges(graph_id)
        entity_types: Dict[str, int] = {}
        relation_types: Dict[str, int] = {}
        for node in nodes:
            for label in node.labels:
                if label not in {"Entity", "Node"}:
                    entity_types[label] = entity_types.get(label, 0) + 1
        for edge in edges:
            relation_types[edge.name] = relation_types.get(edge.name, 0) + 1
        return {
            "graph_id": graph_id,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "entity_types": entity_types,
            "relation_types": relation_types,
        }

    def get_simulation_context(self, graph_id: str, simulation_requirement: str, limit: int = 30) -> Dict[str, Any]:
        search = self.search_graph(graph_id, simulation_requirement, limit=limit, scope="both")
        web_result = self._run_web_research(simulation_requirement, max_results=min(3, max(1, limit // 10 or 1)))
        reddit_result = self._run_reddit_research(simulation_requirement, scenario_context=simulation_requirement)
        related_facts = list(search.facts)
        for fact in self._web_result_to_facts(web_result, limit=2):
            if fact not in related_facts:
                related_facts.append(fact)
        for fact in self._reddit_result_to_facts(reddit_result, limit=2):
            if fact not in related_facts:
                related_facts.append(fact)
        entities = []
        for node in self.get_all_nodes(graph_id):
            custom_labels = [label for label in node.labels if label not in {"Entity", "Node"}]
            if custom_labels:
                entities.append({
                    "name": node.name,
                    "type": custom_labels[0],
                    "summary": node.summary,
                })
        return {
            "simulation_requirement": simulation_requirement,
            "related_facts": related_facts[:limit],
            "graph_statistics": self.get_graph_statistics(graph_id),
            "entities": entities[:limit],
            "total_entities": len(entities),
            "supporting_evidence_count": len(related_facts[:limit]),
            "web_research": web_result.to_dict() if not web_result.error else None,
            "reddit_research": reddit_result.to_dict() if not reddit_result.error else None,
        }

    def build_evidence_bundle(
        self,
        graph_id: str,
        query: str,
        simulation_requirement: str = "",
        limit: int = 8,
    ) -> Dict[str, Any]:
        query = (query or "").strip()
        simulation_requirement = (simulation_requirement or "").strip()
        combined_query = " ".join(part for part in [simulation_requirement, query] if part).strip()

        query_variants = []
        for candidate in [query, simulation_requirement, combined_query]:
            candidate = (candidate or "").strip()
            if candidate and candidate not in query_variants:
                query_variants.append(candidate)

        facts: List[str] = []
        relation_chains: List[str] = []
        nodes_by_uuid: Dict[str, Dict[str, Any]] = {}
        all_edges: List[Dict[str, Any]] = []
        historical_counter = Counter()
        web_result = self._run_web_research(combined_query or query or simulation_requirement, max_results=min(limit, 4))
        reddit_result = self._run_reddit_research(
            combined_query or query or simulation_requirement,
            scenario_context=simulation_requirement,
        )

        for variant in query_variants or [query]:
            search = self.search_graph(graph_id, variant, limit=max(limit, 10), scope="both")
            for fact in search.facts:
                if fact not in facts:
                    facts.append(fact)
            for edge in search.edges:
                all_edges.append(edge)
                chain = f"{edge.get('source_node_name') or edge.get('source_node_uuid', '')[:8]} --[{edge.get('name', 'RELATED_TO')}]--> {edge.get('target_node_name') or edge.get('target_node_uuid', '')[:8]}"
                if chain not in relation_chains:
                    relation_chains.append(chain)
            for node in search.nodes:
                nodes_by_uuid[node.get("uuid", node.get("name", ""))] = node

        panorama = self.panorama_search(graph_id, combined_query or query or simulation_requirement, include_expired=True, limit=max(limit, 12))
        for fact in panorama.historical_facts[: limit * 2]:
            historical_counter[fact] += 1
        for node in panorama.all_nodes:
            score = LocalGraphStore.score_text_match(combined_query or query or simulation_requirement, " ".join([
                node.name,
                node.summary,
                " ".join(node.labels),
            ]))
            if score > 0 and node.uuid not in nodes_by_uuid:
                nodes_by_uuid[node.uuid] = {
                    "uuid": node.uuid,
                    "name": node.name,
                    "labels": node.labels,
                    "summary": node.summary,
                }

        ranked_entities = []
        for node in nodes_by_uuid.values():
            labels = node.get("labels", [])
            entity_type = next((label for label in labels if label not in {"Entity", "Node"}), "Entity")
            score = LocalGraphStore.score_text_match(
                combined_query or query or simulation_requirement,
                " ".join([
                    node.get("name", ""),
                    node.get("summary", ""),
                    " ".join(labels),
                ]),
            )
            ranked_entities.append({
                "uuid": node.get("uuid", ""),
                "name": node.get("name", ""),
                "type": entity_type,
                "summary": node.get("summary", ""),
                "score": score,
            })

        ranked_entities.sort(key=lambda item: (item.get("score", 0), item.get("name", "")), reverse=True)
        entities = ranked_entities[:limit]
        historical_facts = [fact for fact, _ in historical_counter.most_common(limit)]
        web_facts = self._web_result_to_facts(web_result, limit=min(limit, 3))
        for fact in web_facts:
            if fact not in facts:
                facts.append(fact)
        reddit_facts = self._reddit_result_to_facts(reddit_result, limit=min(limit, 3))
        for fact in reddit_facts:
            if fact not in facts:
                facts.append(fact)

        evidence_gaps = []
        if len(facts) < 3:
            evidence_gaps.append("limited direct fact matches")
        if not entities:
            evidence_gaps.append("no clearly matched entities")
        if not relation_chains:
            evidence_gaps.append("weak relationship coverage")
        if not historical_facts:
            evidence_gaps.append("no clear change-over-time evidence")
        if web_result.error:
            evidence_gaps.append("no live web evidence available")
        if reddit_result.error:
            evidence_gaps.append("no recent Reddit evidence available")

        return {
            "query": query,
            "combined_query": combined_query or query or simulation_requirement,
            "top_facts": facts[:limit],
            "active_facts": panorama.active_facts[:limit],
            "historical_facts": historical_facts,
            "entities": entities,
            "relation_chains": relation_chains[:limit],
            "supporting_evidence_count": len(facts),
            "active_count": panorama.active_count,
            "historical_count": panorama.historical_count,
            "total_nodes": panorama.total_nodes,
            "total_edges": panorama.total_edges,
            "evidence_strength": min(len(facts), limit) + min(len(entities), limit) + min(len(relation_chains), limit),
            "evidence_gaps": evidence_gaps,
            "web_research": web_result.to_dict() if not web_result.error else None,
            "reddit_research": reddit_result.to_dict() if not reddit_result.error else None,
        }

    def _generate_sub_queries(
        self,
        query: str,
        simulation_requirement: str,
        report_context: str = "",
        max_queries: int = 5,
    ) -> List[str]:
        prompt = f"""Question: {query}
Simulation background: {simulation_requirement}
Report context: {report_context[:400]}

Return JSON as {{"sub_queries": ["...", "..."]}} with up to {max_queries} concrete retrieval questions."""
        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": "Decompose the question into specific graph-searchable sub-questions."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            sub_queries = [str(item) for item in response.get("sub_queries", []) if str(item).strip()]
            return sub_queries[:max_queries] or [query]
        except Exception:
            return [query, f"Main actors in {query}", f"Timeline and reactions for {query}"][:max_queries]

    def insight_forge(
        self,
        graph_id: str,
        query: str,
        simulation_requirement: str,
        report_context: str = "",
        max_sub_queries: int = 5,
    ) -> InsightForgeResult:
        result = InsightForgeResult(query=query, simulation_requirement=simulation_requirement, sub_queries=[])
        result.sub_queries = self._generate_sub_queries(query, simulation_requirement, report_context, max_sub_queries)
        web_result = self._run_web_research(" ".join(part for part in [query, simulation_requirement] if part).strip(), max_results=3)
        reddit_result = self._run_reddit_research(
            " ".join(part for part in [query, simulation_requirement] if part).strip(),
            scenario_context=report_context or simulation_requirement,
        )

        all_facts: List[str] = []
        all_edges: List[Dict[str, Any]] = []
        seen_facts = set()
        for sub_query in result.sub_queries + [query]:
            search = self.search_graph(graph_id, sub_query, limit=15, scope="edges")
            all_edges.extend(search.edges)
            for fact in search.facts:
                if fact not in seen_facts:
                    seen_facts.add(fact)
                    all_facts.append(fact)

        for fact in self._web_result_to_facts(web_result, limit=3):
            if fact not in seen_facts:
                seen_facts.add(fact)
                all_facts.append(fact)
        for fact in self._reddit_result_to_facts(reddit_result, limit=3):
            if fact not in seen_facts:
                seen_facts.add(fact)
                all_facts.append(fact)

        result.semantic_facts = all_facts
        result.total_facts = len(all_facts)

        entity_uuids = set()
        for edge in all_edges:
            if edge.get("source_node_uuid"):
                entity_uuids.add(edge["source_node_uuid"])
            if edge.get("target_node_uuid"):
                entity_uuids.add(edge["target_node_uuid"])

        node_map = {}
        for uuid_ in entity_uuids:
            node = self.get_node_detail(uuid_)
            if not node:
                continue
            node_map[uuid_] = node
            entity_type = next((label for label in node.labels if label not in {"Entity", "Node"}), "Entity")
            result.entity_insights.append({
                "uuid": node.uuid,
                "name": node.name,
                "type": entity_type,
                "summary": node.summary,
                "related_facts": [fact for fact in all_facts if node.name.lower() in fact.lower()],
            })

        result.total_entities = len(result.entity_insights)
        chains = []
        for edge in all_edges:
            source_name = node_map.get(edge.get("source_node_uuid", ""), NodeInfo("", "", [], "", {})).name or edge.get("source_node_uuid", "")[:8]
            target_name = node_map.get(edge.get("target_node_uuid", ""), NodeInfo("", "", [], "", {})).name or edge.get("target_node_uuid", "")[:8]
            chain = f"{source_name} --[{edge.get('name', '')}]--> {target_name}"
            if chain not in chains:
                chains.append(chain)
        result.relationship_chains = chains
        result.total_relationships = len(chains)
        return result

    def panorama_search(self, graph_id: str, query: str, include_expired: bool = True, limit: int = 50) -> PanoramaResult:
        result = PanoramaResult(query=query)
        result.all_nodes = self.get_all_nodes(graph_id)
        result.all_edges = self.get_all_edges(graph_id, include_temporal=True)
        result.total_nodes = len(result.all_nodes)
        result.total_edges = len(result.all_edges)

        def relevance(fact: str) -> int:
            return LocalGraphStore.score_text_match(query, fact)

        active = [edge.fact for edge in result.all_edges if edge.fact and not edge.is_expired and not edge.is_invalid]
        historical = [edge.fact for edge in result.all_edges if edge.fact and (edge.is_expired or edge.is_invalid)]
        result.active_facts = sorted(active, key=relevance, reverse=True)[:limit]
        result.historical_facts = sorted(historical, key=relevance, reverse=True)[:limit] if include_expired else []
        result.active_count = len(active)
        result.historical_count = len(historical)
        return result

    def quick_search(self, graph_id: str, query: str, limit: int = 10) -> SearchResult:
        return self.search_graph(graph_id, query, limit=limit, scope="edges")

    @staticmethod
    def _clean_tool_call_response(response: str) -> str:
        if not response or not response.strip().startswith("{"):
            return response
        if "tool_name" not in response[:80]:
            return response
        try:
            data = json.loads(response)
            arguments = data.get("arguments", {})
            for key in ("content", "text", "body", "message", "reply"):
                if key in arguments:
                    return str(arguments[key])
        except Exception:
            pass
        return response

    def _load_agent_profiles(self, simulation_id: str) -> List[Dict[str, Any]]:
        sim_dir = os.path.join(Config.UPLOAD_FOLDER, "simulations", simulation_id)
        profiles: List[Dict[str, Any]] = []

        reddit_path = os.path.join(sim_dir, "reddit_profiles.json")
        if os.path.exists(reddit_path):
            with open(reddit_path, "r", encoding="utf-8") as file:
                return json.load(file)

        twitter_path = os.path.join(sim_dir, "twitter_profiles.csv")
        if os.path.exists(twitter_path):
            with open(twitter_path, "r", encoding="utf-8") as file:
                reader = csv.DictReader(file)
                for row in reader:
                    profiles.append({
                        "realname": row.get("name", ""),
                        "username": row.get("username", ""),
                        "bio": row.get("description", ""),
                        "persona": row.get("user_char", ""),
                        "profession": row.get("profession", "Unknown"),
                    })
        return profiles

    def _select_agents_for_interview(
        self,
        profiles: List[Dict[str, Any]],
        interview_requirement: str,
        simulation_requirement: str,
        max_agents: int,
    ) -> tuple[list[Dict[str, Any]], list[int], str]:
        summaries = []
        for index, profile in enumerate(profiles):
            summaries.append({
                "index": index,
                "name": profile.get("realname", profile.get("username", f"Agent_{index}")),
                "profession": profile.get("profession", "Unknown"),
                "bio": profile.get("bio", "")[:180],
                "persona": profile.get("persona", "")[:240],
            })

        prompt = json.dumps(summaries[:100], ensure_ascii=False)
        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": "Select the best interview targets and return JSON: {\"selected_indices\": [..], \"reasoning\": \"...\"}."},
                    {"role": "user", "content": f"Interview goal: {interview_requirement}\nScenario: {simulation_requirement}\nAgents: {prompt}\nPick up to {max_agents}."},
                ],
                temperature=0.2,
            )
            indices = [int(item) for item in response.get("selected_indices", []) if str(item).isdigit()][:max_agents]
            if not indices:
                indices = list(range(min(max_agents, len(profiles))))
            return [profiles[index] for index in indices], indices, str(response.get("reasoning", "") or "Selected for topical relevance.")
        except Exception:
            indices = list(range(min(max_agents, len(profiles))))
            return [profiles[index] for index in indices], indices, "Selected using fallback top-of-list strategy."

    def _generate_interview_questions(
        self,
        interview_requirement: str,
        simulation_requirement: str,
        selected_agents: List[Dict[str, Any]],
    ) -> List[str]:
        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": "Generate 3 concise interview questions. Return JSON: {\"questions\": [..]}."},
                    {"role": "user", "content": f"Interview goal: {interview_requirement}\nScenario: {simulation_requirement}\nSelected agents: {json.dumps(selected_agents[:5], ensure_ascii=False)}"},
                ],
                temperature=0.3,
            )
            questions = [str(item) for item in response.get("questions", []) if str(item).strip()]
            return questions[:3] or [interview_requirement]
        except Exception:
            return [
                f"What is your view on {interview_requirement}?",
                "What outcome do you expect next?",
                "What is influencing your position the most?",
            ]

    def _generate_interview_summary(self, interviews: List[AgentInterview], interview_requirement: str) -> str:
        combined = "\n\n".join(
            f"{interview.agent_name} ({interview.agent_role}): {interview.response[:800]}"
            for interview in interviews
        )
        try:
            response = self.llm.chat(
                messages=[
                    {"role": "system", "content": "Summarize the interview findings in a concise analyst tone."},
                    {"role": "user", "content": f"Interview topic: {interview_requirement}\n\nResponses:\n{combined[:8000]}"},
                ],
                temperature=0.2,
                max_tokens=700,
            )
            return response
        except Exception:
            return f"Completed {len(interviews)} interviews for: {interview_requirement}"

    def interview_agents(
        self,
        simulation_id: str,
        interview_requirement: str,
        simulation_requirement: str = "",
        max_agents: int = 5,
        custom_questions: List[str] | None = None,
    ) -> InterviewResult:
        from .simulation_runner import SimulationRunner

        result = InterviewResult(interview_topic=interview_requirement)
        profiles = self._load_agent_profiles(simulation_id)
        if not profiles:
            result.summary = "No interviewable agent profiles found."
            return result

        result.total_agents = len(profiles)
        selected_agents, selected_indices, reasoning = self._select_agents_for_interview(
            profiles=profiles,
            interview_requirement=interview_requirement,
            simulation_requirement=simulation_requirement,
            max_agents=max_agents,
        )
        result.selected_agents = selected_agents
        result.selection_reasoning = reasoning
        result.interview_questions = custom_questions or self._generate_interview_questions(
            interview_requirement=interview_requirement,
            simulation_requirement=simulation_requirement,
            selected_agents=selected_agents,
        )

        prompt = "\n".join(f"{index + 1}. {question}" for index, question in enumerate(result.interview_questions))
        interviews_request = [{"agent_id": index, "prompt": prompt} for index in selected_indices]

        try:
            api_result = SimulationRunner.interview_agents_batch(
                simulation_id=simulation_id,
                interviews=interviews_request,
                platform=None,
                timeout=180.0,
            )
        except Exception as error:
            result.summary = f"Interview failed: {error}"
            return result

        results_map = (api_result.get("result", {}) or {}).get("results", {}) if api_result.get("success") else {}
        for i, agent_index in enumerate(selected_indices):
            profile = selected_agents[i]
            twitter_response = self._clean_tool_call_response((results_map.get(f"twitter_{agent_index}", {}) or {}).get("response", ""))
            reddit_response = self._clean_tool_call_response((results_map.get(f"reddit_{agent_index}", {}) or {}).get("response", ""))
            response = f"[Twitter]\n{twitter_response or '(No response)'}\n\n[Reddit]\n{reddit_response or '(No response)'}"
            quotes = [sentence.strip() for sentence in re.split(r"[。.!?]\s*", f"{twitter_response} {reddit_response}") if 20 <= len(sentence.strip()) <= 140][:3]
            result.interviews.append(AgentInterview(
                agent_name=profile.get("realname", profile.get("username", f"Agent_{agent_index}")),
                agent_role=profile.get("profession", "Unknown"),
                agent_bio=profile.get("bio", ""),
                question=prompt,
                response=response,
                key_quotes=quotes,
            ))

        result.interviewed_count = len(result.interviews)
        result.summary = self._generate_interview_summary(result.interviews, interview_requirement) if result.interviews else "No interviews were completed."
        return result
