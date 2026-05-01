"""
Local entity reader and filter service.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from ..utils.logger import get_logger
from .local_graph_store import LocalGraphStore


logger = get_logger("univerra.entity_reader")


@dataclass
class EntityNode:
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    related_edges: List[Dict[str, Any]] = field(default_factory=list)
    related_nodes: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
            "related_edges": self.related_edges,
            "related_nodes": self.related_nodes,
        }

    def get_entity_type(self) -> Optional[str]:
        for label in self.labels:
            if label not in {"Entity", "Node"}:
                return label
        return None


@dataclass
class FilteredEntities:
    entities: List[EntityNode]
    entity_types: Set[str]
    total_count: int
    filtered_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities": [entity.to_dict() for entity in self.entities],
            "entity_types": sorted(self.entity_types),
            "total_count": self.total_count,
            "filtered_count": self.filtered_count,
        }


class GraphEntityReader:
    """
    Compatibility wrapper over local graph storage.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    def get_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        graph_data = LocalGraphStore.get_graph_data(graph_id)
        return graph_data.get("nodes", [])

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        graph_data = LocalGraphStore.get_graph_data(graph_id)
        return graph_data.get("edges", [])

    def get_node_edges(self, graph_id: str, node_uuid: str) -> List[Dict[str, Any]]:
        return [
            edge for edge in self.get_all_edges(graph_id)
            if edge.get("source_node_uuid") == node_uuid or edge.get("target_node_uuid") == node_uuid
        ]

    def filter_defined_entities(
        self,
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True,
    ) -> FilteredEntities:
        logger.info(f"Filtering entities from local graph: {graph_id}")
        all_nodes = self.get_all_nodes(graph_id)
        all_edges = self.get_all_edges(graph_id) if enrich_with_edges else []
        total_count = len(all_nodes)
        node_map = {node["uuid"]: node for node in all_nodes}

        entities: List[EntityNode] = []
        entity_types_found: Set[str] = set()

        for node in all_nodes:
            labels = node.get("labels", [])
            custom_labels = [label for label in labels if label not in {"Entity", "Node"}]
            if not custom_labels:
                continue

            entity_type = custom_labels[0]
            if defined_entity_types and entity_type not in defined_entity_types:
                continue

            entity_types_found.add(entity_type)
            entity = EntityNode(
                uuid=node.get("uuid", ""),
                name=node.get("name", ""),
                labels=labels,
                summary=node.get("summary", ""),
                attributes=node.get("attributes", {}),
            )

            if enrich_with_edges:
                related_node_uuids = set()
                for edge in all_edges:
                    if edge.get("source_node_uuid") == entity.uuid:
                        entity.related_edges.append({
                            "direction": "outgoing",
                            "edge_name": edge.get("name", ""),
                            "fact": edge.get("fact", ""),
                            "target_node_uuid": edge.get("target_node_uuid", ""),
                        })
                        related_node_uuids.add(edge.get("target_node_uuid", ""))
                    elif edge.get("target_node_uuid") == entity.uuid:
                        entity.related_edges.append({
                            "direction": "incoming",
                            "edge_name": edge.get("name", ""),
                            "fact": edge.get("fact", ""),
                            "source_node_uuid": edge.get("source_node_uuid", ""),
                        })
                        related_node_uuids.add(edge.get("source_node_uuid", ""))

                for related_uuid in related_node_uuids:
                    related = node_map.get(related_uuid)
                    if not related:
                        continue
                    entity.related_nodes.append({
                        "uuid": related.get("uuid", ""),
                        "name": related.get("name", ""),
                        "labels": related.get("labels", []),
                        "summary": related.get("summary", ""),
                    })

            entities.append(entity)

        return FilteredEntities(
            entities=entities,
            entity_types=entity_types_found,
            total_count=total_count,
            filtered_count=len(entities),
        )

    def get_entity_with_context(self, graph_id: str, entity_uuid: str) -> Optional[EntityNode]:
        entities = self.filter_defined_entities(graph_id=graph_id, enrich_with_edges=True).entities
        for entity in entities:
            if entity.uuid == entity_uuid:
                return entity

        all_nodes = self.get_all_nodes(graph_id)
        for node in all_nodes:
            if node.get("uuid") != entity_uuid:
                continue
            return EntityNode(
                uuid=node.get("uuid", ""),
                name=node.get("name", ""),
                labels=node.get("labels", []),
                summary=node.get("summary", ""),
                attributes=node.get("attributes", {}),
                related_edges=[],
                related_nodes=[],
            )
        return None

    def get_entities_by_type(
        self,
        graph_id: str,
        entity_type: str,
        enrich_with_edges: bool = True,
    ) -> List[EntityNode]:
        result = self.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=[entity_type],
            enrich_with_edges=enrich_with_edges,
        )
        return result.entities
