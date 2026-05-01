"""
Lightweight local graph storage used instead of external graph services.
"""

import json
import os
import re
import threading
import uuid
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List

from ..config import Config


TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def normalize_name(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", (value or "").strip()).lower()
    return cleaned


def tokenize_text(value: str) -> List[str]:
    if not value:
        return []
    return [token.lower() for token in TOKEN_PATTERN.findall(str(value))]


class LocalGraphStore:
    ROOT_DIR = os.path.join(Config.UPLOAD_FOLDER, "graphs")
    _lock = threading.Lock()

    @classmethod
    def _ensure_root(cls):
        os.makedirs(cls.ROOT_DIR, exist_ok=True)

    @classmethod
    def _graph_dir(cls, graph_id: str) -> str:
        return os.path.join(cls.ROOT_DIR, graph_id)

    @classmethod
    def _graph_path(cls, graph_id: str) -> str:
        return os.path.join(cls._graph_dir(graph_id), "graph.json")

    @classmethod
    def create_graph(cls, graph_id: str, name: str, description: str = "") -> Dict[str, Any]:
        cls._ensure_root()
        graph_dir = cls._graph_dir(graph_id)
        os.makedirs(graph_dir, exist_ok=True)
        now = datetime.now().isoformat()
        graph = {
            "graph_id": graph_id,
            "name": name,
            "description": description,
            "created_at": now,
            "updated_at": now,
            "ontology": {"entity_types": [], "edge_types": []},
            "episodes": [],
            "nodes": [],
            "edges": [],
        }
        cls.save_graph(graph)
        return graph

    @classmethod
    def load_graph(cls, graph_id: str) -> Dict[str, Any]:
        path = cls._graph_path(graph_id)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Graph not found: {graph_id}")
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)

    @classmethod
    def save_graph(cls, graph: Dict[str, Any]):
        cls._ensure_root()
        graph["updated_at"] = datetime.now().isoformat()
        os.makedirs(cls._graph_dir(graph["graph_id"]), exist_ok=True)
        with cls._lock:
            with open(cls._graph_path(graph["graph_id"]), "w", encoding="utf-8") as file:
                json.dump(graph, file, ensure_ascii=False, indent=2)

    @classmethod
    def delete_graph(cls, graph_id: str):
        graph_dir = cls._graph_dir(graph_id)
        if not os.path.exists(graph_dir):
            return
        for root, dirs, files in os.walk(graph_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(graph_dir)

    @classmethod
    def set_ontology(cls, graph_id: str, ontology: Dict[str, Any]):
        graph = cls.load_graph(graph_id)
        graph["ontology"] = deepcopy(ontology or {"entity_types": [], "edge_types": []})
        cls.save_graph(graph)

    @classmethod
    def add_episode(cls, graph_id: str, text: str, metadata: Dict[str, Any] | None = None) -> str:
        graph = cls.load_graph(graph_id)
        episode_id = f"episode_{uuid.uuid4().hex[:12]}"
        graph["episodes"].append({
            "episode_id": episode_id,
            "text": text,
            "metadata": metadata or {},
            "created_at": datetime.now().isoformat(),
        })
        cls.save_graph(graph)
        return episode_id

    @classmethod
    def _find_node(cls, graph: Dict[str, Any], name: str) -> Dict[str, Any] | None:
        normalized = normalize_name(name)
        if not normalized:
            return None
        for node in graph.get("nodes", []):
            if normalize_name(node.get("name", "")) == normalized:
                return node
            aliases = node.get("attributes", {}).get("aliases", [])
            if any(normalize_name(alias) == normalized for alias in aliases):
                return node
        return None

    @classmethod
    def _merge_summary(cls, current: str, incoming: str) -> str:
        current = (current or "").strip()
        incoming = (incoming or "").strip()
        if not current:
            return incoming
        if not incoming or incoming.lower() in current.lower():
            return current
        if current.lower() in incoming.lower():
            return incoming
        return f"{current} {incoming}".strip()

    @classmethod
    def upsert_node(
        cls,
        graph: Dict[str, Any],
        name: str,
        entity_type: str = "Entity",
        summary: str = "",
        attributes: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        attributes = deepcopy(attributes or {})
        node = cls._find_node(graph, name)
        if node:
            labels = set(node.get("labels", []) or ["Entity"])
            labels.add("Entity")
            if entity_type:
                labels.add(entity_type)
            node["labels"] = list(labels)
            node["summary"] = cls._merge_summary(node.get("summary", ""), summary)
            node_attributes = node.setdefault("attributes", {})
            for key, value in attributes.items():
                if value in (None, "", [], {}):
                    continue
                if key == "aliases":
                    merged_aliases = set(node_attributes.get("aliases", []))
                    merged_aliases.update(value if isinstance(value, list) else [value])
                    node_attributes["aliases"] = sorted(merged_aliases)
                elif key not in node_attributes or not node_attributes[key]:
                    node_attributes[key] = value
            node_attributes["mention_count"] = int(node_attributes.get("mention_count", 1)) + 1
            node["updated_at"] = datetime.now().isoformat()
            return node

        node = {
            "uuid": f"node_{uuid.uuid4().hex[:12]}",
            "name": name.strip(),
            "labels": ["Entity"] + ([entity_type] if entity_type and entity_type != "Entity" else []),
            "summary": summary.strip(),
            "attributes": attributes,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        node["attributes"]["mention_count"] = int(node["attributes"].get("mention_count", 0)) + 1
        graph.setdefault("nodes", []).append(node)
        return node

    @classmethod
    def _edge_identity(cls, source_uuid: str, target_uuid: str, name: str, fact: str) -> str:
        return "|".join([
            source_uuid,
            target_uuid,
            normalize_name(name),
            normalize_name(fact),
        ])

    @classmethod
    def add_entities_and_relationships(
        cls,
        graph_id: str,
        entities: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]],
        episode_id: str | None = None,
    ):
        graph = cls.load_graph(graph_id)
        node_map: Dict[str, Dict[str, Any]] = {}

        for entity in entities:
            name = str(entity.get("name", "")).strip()
            if not name:
                continue
            node = cls.upsert_node(
                graph=graph,
                name=name,
                entity_type=str(entity.get("type", "Entity") or "Entity"),
                summary=str(entity.get("summary", "") or ""),
                attributes=entity.get("attributes") or {},
            )
            node_map[normalize_name(name)] = node

        existing_edges = {
            cls._edge_identity(
                edge.get("source_node_uuid", ""),
                edge.get("target_node_uuid", ""),
                edge.get("name", ""),
                edge.get("fact", ""),
            ): edge
            for edge in graph.get("edges", [])
        }

        for relation in relationships:
            source_name = str(relation.get("source", "")).strip()
            target_name = str(relation.get("target", "")).strip()
            relation_name = str(relation.get("type", "") or relation.get("name", "") or "RELATED_TO").strip()
            if not source_name or not target_name:
                continue

            source_node = node_map.get(normalize_name(source_name)) or cls.upsert_node(
                graph, source_name, str(relation.get("source_type", "Entity") or "Entity")
            )
            target_node = node_map.get(normalize_name(target_name)) or cls.upsert_node(
                graph, target_name, str(relation.get("target_type", "Entity") or "Entity")
            )
            edge_key = cls._edge_identity(
                source_node["uuid"],
                target_node["uuid"],
                relation_name,
                str(relation.get("fact", "") or relation_name),
            )

            if edge_key in existing_edges:
                edge = existing_edges[edge_key]
                edge["attributes"]["weight"] = int(edge["attributes"].get("weight", 1)) + 1
                if episode_id and episode_id not in edge["episodes"]:
                    edge["episodes"].append(episode_id)
                edge["updated_at"] = datetime.now().isoformat()
                continue

            edge = {
                "uuid": f"edge_{uuid.uuid4().hex[:12]}",
                "name": relation_name,
                "fact": str(relation.get("fact", "") or relation_name),
                "source_node_uuid": source_node["uuid"],
                "target_node_uuid": target_node["uuid"],
                "attributes": deepcopy(relation.get("attributes") or {}),
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "valid_at": datetime.now().isoformat(),
                "invalid_at": None,
                "expired_at": None,
                "episodes": [episode_id] if episode_id else [],
            }
            edge["attributes"]["weight"] = int(edge["attributes"].get("weight", 0)) + 1
            graph.setdefault("edges", []).append(edge)
            existing_edges[edge_key] = edge

        cls.save_graph(graph)

    @classmethod
    def get_graph_data(cls, graph_id: str) -> Dict[str, Any]:
        graph = cls.load_graph(graph_id)
        node_map = {node["uuid"]: node for node in graph.get("nodes", [])}
        edges = []
        for edge in graph.get("edges", []):
            edge_copy = deepcopy(edge)
            edge_copy["source_node_name"] = node_map.get(edge["source_node_uuid"], {}).get("name", "")
            edge_copy["target_node_name"] = node_map.get(edge["target_node_uuid"], {}).get("name", "")
            edges.append(edge_copy)
        return {
            "graph_id": graph_id,
            "name": graph.get("name", ""),
            "description": graph.get("description", ""),
            "ontology": deepcopy(graph.get("ontology", {})),
            "nodes": deepcopy(graph.get("nodes", [])),
            "edges": edges,
            "episodes": deepcopy(graph.get("episodes", [])),
            "node_count": len(graph.get("nodes", [])),
            "edge_count": len(graph.get("edges", [])),
        }

    @classmethod
    def score_text_match(cls, query: str, text: str) -> int:
        if not text:
            return 0
        query_lower = query.lower().strip()
        text_lower = text.lower()
        if not query_lower:
            return 0
        score = 100 if query_lower in text_lower else 0
        for token in tokenize_text(query):
            if token in text_lower:
                score += 12
        return score
