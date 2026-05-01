"""
Compatibility helpers retained after removing the external graph dependency.
"""

from __future__ import annotations

from typing import Any


def fetch_all_nodes(client: Any, graph_id: str, *args: Any, **kwargs: Any) -> list[Any]:
    if hasattr(client, "get_all_nodes"):
        return client.get_all_nodes(graph_id)
    return []


def fetch_all_edges(client: Any, graph_id: str, *args: Any, **kwargs: Any) -> list[Any]:
    if hasattr(client, "get_all_edges"):
        return client.get_all_edges(graph_id)
    return []
