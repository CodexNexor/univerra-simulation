"""
Graph Building Service
Builds a local lightweight knowledge graph without external graph infrastructure.
"""

import re
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from ..models.task import TaskManager, TaskStatus
from ..utils.logger import get_logger
from ..utils.llm_client import LLMClient
from .local_graph_store import LocalGraphStore
from .text_processor import TextProcessor


logger = get_logger("univerra.graph_builder")


@dataclass
class GraphInfo:
    graph_id: str
    node_count: int
    edge_count: int
    entity_types: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


class GraphBuilderService:
    """
    Local graph builder driven by the configured LLM plus lightweight on-disk storage.
    """

    EXTRACTION_SYSTEM_PROMPT = """You extract structured entities and relationships from text for a social-simulation graph.

Rules:
1. Return valid JSON only.
2. Use only entities clearly supported by the text chunk.
3. Entity `type` must match one of the provided ontology entity type names when possible.
4. Relationship `type` must match one of the provided ontology edge type names when possible.
5. Keep summaries factual and short.
6. Do not invent missing facts.

Return:
{
  "entities": [
    {"name": "...", "type": "...", "summary": "...", "attributes": {}}
  ],
  "relationships": [
    {"source": "...", "target": "...", "type": "...", "fact": "...", "attributes": {}}
  ]
}
"""

    def __init__(self, api_key: Optional[str] = None):
        self.task_manager = TaskManager()
        self.llm = LLMClient()

    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "Univerra Knowledge Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        batch_size: int = 3,
    ) -> str:
        task_id = self.task_manager.create_task(
            task_type="graph_build",
            metadata={"graph_name": graph_name, "text_length": len(text)},
        )
        thread = threading.Thread(
            target=self._build_graph_worker,
            args=(task_id, text, ontology, graph_name, chunk_size, chunk_overlap, batch_size),
            daemon=True,
        )
        thread.start()
        return task_id

    def _build_graph_worker(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int,
    ):
        try:
            self.task_manager.update_task(task_id, status=TaskStatus.PROCESSING, progress=5, message="Creating local graph...")
            graph_id = self.create_graph(graph_name)
            self.set_ontology(graph_id, ontology)

            chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
            self.task_manager.update_task(task_id, progress=15, message=f"Processing {len(chunks)} chunks...")
            self.add_text_batches(graph_id, chunks, batch_size=batch_size)

            graph_info = self._get_graph_info(graph_id)
            self.task_manager.complete_task(task_id, {
                "graph_id": graph_id,
                "graph_info": graph_info.to_dict(),
                "chunks_processed": len(chunks),
            })
        except Exception as error:
            self.task_manager.fail_task(task_id, str(error))

    def create_graph(self, name: str) -> str:
        graph_id = f"univerra_{uuid.uuid4().hex[:16]}"
        LocalGraphStore.create_graph(
            graph_id=graph_id,
            name=name,
            description="Local Univerra simulation knowledge graph",
        )
        return graph_id

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]):
        LocalGraphStore.set_ontology(graph_id, ontology)

    def add_text_batches(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 3,
        progress_callback: Optional[Callable[[str, float], None]] = None,
    ) -> List[str]:
        episode_ids: List[str] = []
        ontology = LocalGraphStore.load_graph(graph_id).get("ontology", {})
        total_chunks = max(1, len(chunks))

        for index, chunk in enumerate(chunks, start=1):
            if progress_callback:
                progress_callback(f"Extracting chunk {index}/{total_chunks}...", index / total_chunks)

            extraction = self._extract_from_chunk(chunk, ontology)
            episode_id = LocalGraphStore.add_episode(
                graph_id,
                text=chunk,
                metadata={"chunk_index": index, "entity_count": len(extraction["entities"])},
            )
            LocalGraphStore.add_entities_and_relationships(
                graph_id,
                entities=extraction["entities"],
                relationships=extraction["relationships"],
                episode_id=episode_id,
            )
            episode_ids.append(episode_id)

        return episode_ids

    def _wait_for_episodes(
        self,
        episode_uuids: List[str],
        progress_callback: Optional[Callable[[str, float], None]] = None,
        timeout: int = 600,
    ):
        if progress_callback:
            progress_callback("Local graph extraction completed", 1.0)

    def _extract_from_chunk(self, chunk: str, ontology: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        entity_types = [entity.get("name", "Entity") for entity in ontology.get("entity_types", [])]
        edge_types = [edge.get("name", "RELATED_TO") for edge in ontology.get("edge_types", [])]
        user_prompt = f"""Ontology entity types: {entity_types}
Ontology relationship types: {edge_types}

Text chunk:
{chunk[:5000]}
"""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": self.EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=1800,
            )
            entities = self._sanitize_entities(response.get("entities", []), entity_types)
            relationships = self._sanitize_relationships(response.get("relationships", []), edge_types)
            if entities or relationships:
                return {"entities": entities, "relationships": relationships}
        except Exception as error:
            logger.warning(f"Chunk extraction fallback activated: {str(error)[:120]}")

        return self._heuristic_extract(chunk, entity_types, edge_types)

    def _sanitize_entities(self, entities: List[Dict[str, Any]], valid_types: List[str]) -> List[Dict[str, Any]]:
        allowed = set(valid_types or ["Entity"])
        sanitized = []
        for entity in entities or []:
            name = str(entity.get("name", "")).strip()
            if not name:
                continue
            entity_type = str(entity.get("type", "Entity") or "Entity").strip()
            if entity_type not in allowed:
                entity_type = "Entity"
            sanitized.append({
                "name": name,
                "type": entity_type,
                "summary": str(entity.get("summary", "") or "").strip(),
                "attributes": entity.get("attributes") or {},
            })
        return sanitized

    def _sanitize_relationships(self, relationships: List[Dict[str, Any]], valid_types: List[str]) -> List[Dict[str, Any]]:
        allowed = set(valid_types or ["RELATED_TO"])
        sanitized = []
        for relation in relationships or []:
            source = str(relation.get("source", "")).strip()
            target = str(relation.get("target", "")).strip()
            if not source or not target or source == target:
                continue
            relation_type = str(relation.get("type", relation.get("name", "RELATED_TO")) or "RELATED_TO").strip()
            if relation_type not in allowed:
                relation_type = "RELATED_TO"
            sanitized.append({
                "source": source,
                "target": target,
                "type": relation_type,
                "fact": str(relation.get("fact", "") or f"{source} {relation_type} {target}").strip(),
                "attributes": relation.get("attributes") or {},
            })
        return sanitized

    def _heuristic_extract(
        self,
        chunk: str,
        entity_types: List[str],
        edge_types: List[str],
    ) -> Dict[str, List[Dict[str, Any]]]:
        candidates = re.findall(r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3}\b", chunk)
        deduped = []
        seen = set()
        for candidate in candidates:
            cleaned = candidate.strip()
            if cleaned.lower() in seen or len(cleaned) < 3:
                continue
            seen.add(cleaned.lower())
            deduped.append(cleaned)

        fallback_type = entity_types[0] if entity_types else "Entity"
        entities = [
            {
                "name": name,
                "type": fallback_type,
                "summary": f"Mentioned in source text: {name}",
                "attributes": {},
            }
            for name in deduped[:12]
        ]

        relationships = []
        relation_type = edge_types[0] if edge_types else "RELATED_TO"
        for left, right in zip(deduped, deduped[1:]):
            relationships.append({
                "source": left,
                "target": right,
                "type": relation_type,
                "fact": f"{left} appears in the same context as {right}",
                "attributes": {"heuristic": True},
            })

        return {"entities": entities, "relationships": relationships}

    def _get_graph_info(self, graph_id: str) -> GraphInfo:
        graph_data = LocalGraphStore.get_graph_data(graph_id)
        entity_types = set()
        for node in graph_data["nodes"]:
            for label in node.get("labels", []):
                if label not in {"Entity", "Node"}:
                    entity_types.add(label)
        return GraphInfo(
            graph_id=graph_id,
            node_count=graph_data["node_count"],
            edge_count=graph_data["edge_count"],
            entity_types=sorted(entity_types),
        )

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        return LocalGraphStore.get_graph_data(graph_id)

    def delete_graph(self, graph_id: str):
        LocalGraphStore.delete_graph(graph_id)
