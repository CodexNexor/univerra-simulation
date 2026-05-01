"""
Local graph memory updater for simulation activities.
"""

import threading
import time
from dataclasses import dataclass
from datetime import datetime
from queue import Empty, Queue
from typing import Any, Dict, List, Optional

from ..utils.logger import get_logger
from .local_graph_store import LocalGraphStore


logger = get_logger("univerra.graph_memory")


@dataclass
class AgentActivity:
    platform: str
    agent_id: int
    agent_name: str
    action_type: str
    action_args: Dict[str, Any]
    round_num: int
    timestamp: str

    def to_episode_text(self) -> str:
        content = self.action_args.get("content") or self.action_args.get("comment_content") or self.action_args.get("post_content") or ""
        detail = f": {content}" if content else ""
        return f"{self.agent_name} [{self.platform}] performed {self.action_type}{detail}"


class GraphMemoryUpdater:
    BATCH_SIZE = 5
    SEND_INTERVAL = 0.5

    def __init__(self, graph_id: str, api_key: Optional[str] = None):
        self.graph_id = graph_id
        self.api_key = api_key
        self._activity_queue: Queue[AgentActivity] = Queue()
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._total_activities = 0
        self._total_sent = 0
        self._failed_count = 0
        self._skipped_count = 0

    def start(self):
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True, name=f"GraphMemory-{self.graph_id[:8]}")
        self._worker_thread.start()

    def stop(self):
        self._running = False
        self._flush_remaining()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5)

    def add_activity(self, activity: AgentActivity):
        if activity.action_type == "DO_NOTHING":
            self._skipped_count += 1
            return
        self._activity_queue.put(activity)
        self._total_activities += 1

    def add_activity_from_dict(self, data: Dict[str, Any], platform: str):
        if "event_type" in data:
            return
        self.add_activity(AgentActivity(
            platform=platform,
            agent_id=int(data.get("agent_id", 0) or 0),
            agent_name=str(data.get("agent_name", "") or ""),
            action_type=str(data.get("action_type", "") or ""),
            action_args=data.get("action_args", {}) or {},
            round_num=int(data.get("round", 0) or 0),
            timestamp=str(data.get("timestamp", datetime.now().isoformat())),
        ))

    def _worker_loop(self):
        buffer: List[AgentActivity] = []
        while self._running or not self._activity_queue.empty():
            try:
                activity = self._activity_queue.get(timeout=1)
                buffer.append(activity)
                if len(buffer) >= self.BATCH_SIZE:
                    self._send_batch_activities(buffer)
                    buffer = []
                    time.sleep(self.SEND_INTERVAL)
            except Empty:
                if buffer:
                    self._send_batch_activities(buffer)
                    buffer = []
            except Exception as error:
                logger.error(f"Graph memory updater worker error: {error}")
                self._failed_count += 1

    def _send_batch_activities(self, activities: List[AgentActivity]):
        if not activities:
            return
        try:
            combined_text = "\n".join(activity.to_episode_text() for activity in activities)
            episode_id = LocalGraphStore.add_episode(
                self.graph_id,
                text=combined_text,
                metadata={"source": "simulation_activity", "count": len(activities)},
            )
            entities = []
            relationships = []
            for activity in activities:
                entities.append({
                    "name": activity.agent_name or f"Agent {activity.agent_id}",
                    "type": "SimulationAgent",
                    "summary": f"{activity.platform} actor active in simulation",
                    "attributes": {"platform": activity.platform, "agent_id": activity.agent_id},
                })
                event_name = f"{activity.action_type}_{activity.platform}_{activity.round_num}_{activity.agent_id}"
                entities.append({
                    "name": event_name,
                    "type": "SimulationEvent",
                    "summary": activity.to_episode_text(),
                    "attributes": {"timestamp": activity.timestamp},
                })
                relationships.append({
                    "source": activity.agent_name or f"Agent {activity.agent_id}",
                    "target": event_name,
                    "type": "PERFORMED_ACTION",
                    "fact": activity.to_episode_text(),
                    "attributes": {"round": activity.round_num, "platform": activity.platform},
                })
            LocalGraphStore.add_entities_and_relationships(
                self.graph_id,
                entities=entities,
                relationships=relationships,
                episode_id=episode_id,
            )
            self._total_sent += len(activities)
        except Exception as error:
            logger.error(f"Failed to persist graph memory batch: {error}")
            self._failed_count += 1

    def _flush_remaining(self):
        remaining: List[AgentActivity] = []
        while not self._activity_queue.empty():
            try:
                remaining.append(self._activity_queue.get_nowait())
            except Empty:
                break
        if remaining:
            self._send_batch_activities(remaining)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "batch_size": self.BATCH_SIZE,
            "total_activities": self._total_activities,
            "items_sent": self._total_sent,
            "failed_count": self._failed_count,
            "skipped_count": self._skipped_count,
            "queue_size": self._activity_queue.qsize(),
            "running": self._running,
        }


class GraphMemoryManager:
    _updaters: Dict[str, GraphMemoryUpdater] = {}
    _lock = threading.Lock()
    _stop_all_done = False

    @classmethod
    def create_updater(cls, simulation_id: str, graph_id: str) -> GraphMemoryUpdater:
        with cls._lock:
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
            updater = GraphMemoryUpdater(graph_id)
            updater.start()
            cls._updaters[simulation_id] = updater
            return updater

    @classmethod
    def get_updater(cls, simulation_id: str) -> Optional[GraphMemoryUpdater]:
        return cls._updaters.get(simulation_id)

    @classmethod
    def stop_updater(cls, simulation_id: str):
        with cls._lock:
            updater = cls._updaters.pop(simulation_id, None)
            if updater:
                updater.stop()

    @classmethod
    def stop_all(cls):
        if cls._stop_all_done:
            return
        cls._stop_all_done = True
        with cls._lock:
            for updater in cls._updaters.values():
                try:
                    updater.stop()
                except Exception as error:
                    logger.error(f"Failed to stop graph memory updater: {error}")
            cls._updaters.clear()

    @classmethod
    def get_all_stats(cls) -> Dict[str, Dict[str, Any]]:
        return {simulation_id: updater.get_stats() for simulation_id, updater in cls._updaters.items()}
