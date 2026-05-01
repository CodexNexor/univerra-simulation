import math
import os
import random
import re
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Set, Tuple


TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def _normalize_tokens(text: str) -> Set[str]:
    if not text:
        return set()
    return {token.lower() for token in TOKEN_PATTERN.findall(str(text)) if token}


def _get_configured_rpm() -> int | None:
    raw_value = os.environ.get("UNIVERRA_LLM_RPM") or os.environ.get("LLM_REQUESTS_PER_MINUTE")
    if not raw_value:
        return None

    try:
        rpm = int(raw_value)
    except ValueError:
        return None

    return rpm if rpm > 0 else None


def get_recommended_semaphore(agent_count: int) -> int:
    override = os.environ.get("UNIVERRA_SIM_SEMAPHORE")
    if override:
        try:
            return max(1, int(override))
        except ValueError:
            pass

    cpu_count = max(1, os.cpu_count() or 2)
    population_limit = max(2, agent_count // 4) if agent_count else 2
    recommended = max(2, min(8, cpu_count * 2, population_limit))
    rpm_limit = _get_configured_rpm()
    if rpm_limit:
        recommended = min(recommended, max(1, rpm_limit // 30))
    return max(1, recommended)


def get_max_active_agents_per_round(agent_count: int) -> int:
    override = os.environ.get("UNIVERRA_MAX_ACTIVE_AGENTS")
    if override:
        try:
            return max(1, int(override))
        except ValueError:
            pass

    recommended = max(4, min(12, get_recommended_semaphore(agent_count) * 2))
    rpm_limit = _get_configured_rpm()
    if rpm_limit:
        recommended = min(recommended, max(2, math.ceil(rpm_limit / 15)))
    return max(1, recommended)


def compute_simulation_seed(config: Dict[str, Any], platform: str) -> int:
    simulation_id = config.get("simulation_id", "sim")
    requirement = config.get("simulation_requirement", "")
    run_index = config.get("ensemble_run_index", 0)
    scenario_variant = config.get("scenario_variant", "baseline")
    seed_offset = config.get("seed_offset", 0)
    seed_material = f"{simulation_id}:{platform}:{run_index}:{scenario_variant}:{seed_offset}:{requirement[:200]}"
    digest = hashlib.sha256(seed_material.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


@dataclass
class AgentRuntimeState:
    carryover_budget: float = 0.0
    next_available_round: int = 0
    last_action_round: int = -999


class PlatformRuntimePolicy:
    def __init__(self, config: Dict[str, Any], platform: str):
        self.config = config
        self.platform = platform
        self.rng = random.Random(compute_simulation_seed(config, platform))
        self.environment_context = config.get("environment_context", {})
        self.calibration_profile = config.get("calibration_profile", {})
        self.temporal_forecast_config = config.get("temporal_forecast_config", {})
        self.time_config = config.get("time_config", {})
        self.event_config = config.get("event_config", {})
        self.platform_config = config.get(f"{platform}_config", {}) if platform in {"twitter", "reddit"} else {}
        self.agent_configs = config.get("agent_configs", [])
        self.agent_config_map = {
            cfg.get("agent_id", 0): cfg
            for cfg in self.agent_configs
        }
        self.hot_topics = _normalize_tokens(" ".join(self.event_config.get("hot_topics", [])))
        self.narrative_tokens = _normalize_tokens(self.event_config.get("narrative_direction", ""))
        self.agent_states = {
            cfg.get("agent_id", 0): AgentRuntimeState()
            for cfg in self.agent_configs
        }
        self.processed_scheduled_events: Set[str] = set()
        self.max_active_agents = get_max_active_agents_per_round(len(self.agent_configs))
        self.topic_momentum: Dict[str, float] = {}
        self.recent_action_load = 0.0
        self.last_decay_round = -1
        self.precision_mode = str(self.calibration_profile.get("recommended_mode", "balanced")).lower()

    def _volatility_multiplier(self) -> float:
        volatility = str(self.environment_context.get("volatility", "medium")).lower()
        if volatility == "high":
            return 1.2
        if volatility == "low":
            return 0.9
        return 1.0

    def _stakeholder_multiplier(self) -> float:
        pressure = str(self.environment_context.get("stakeholder_pressure", "medium")).lower()
        if pressure == "high":
            return 1.1
        if pressure == "low":
            return 0.95
        return 1.0

    def _precision_target_adjustment(self) -> int:
        confidence = float(self.calibration_profile.get("confidence_score", 0.5) or 0.5)
        if self.precision_mode == "precision":
            return -1 if confidence < 0.65 else 0
        if self.precision_mode == "exploratory":
            return 1
        return 0

    def _decay_trends(self, round_num: int):
        if self.last_decay_round == round_num:
            return
        self.last_decay_round = round_num
        decay_ratio = 0.6 if str(self.environment_context.get("volatility", "medium")).lower() != "high" else 0.72
        if self.precision_mode == "precision":
            decay_ratio = min(0.8, decay_ratio + 0.08)
        self.recent_action_load *= decay_ratio
        decayed = {}
        for token, score in self.topic_momentum.items():
            next_score = score * 0.85
            if next_score >= 0.2:
                decayed[token] = next_score
        self.topic_momentum = decayed

    def _current_topic_pool(self) -> Set[str]:
        dynamic_topics = {
            token for token, score in self.topic_momentum.items()
            if score >= (1.1 if self.precision_mode == "precision" else 0.8)
        }
        return set(self.hot_topics) | dynamic_topics

    def _extract_action_tokens(self, payload: Dict[str, Any]) -> Set[str]:
        collected: List[str] = []
        for key in (
            "content",
            "query",
            "post_content",
            "quote_content",
            "comment_content",
            "original_content",
        ):
            value = payload.get(key)
            if isinstance(value, str):
                collected.append(value)
        return _normalize_tokens(" ".join(collected))

    def observe_posts(self, posts: List[Dict[str, Any]]):
        if not posts:
            return
        self.recent_action_load += len(posts)
        for post in posts:
            for token in _normalize_tokens(post.get("content", "")):
                self.topic_momentum[token] = self.topic_momentum.get(token, 0.0) + 1.0

    def observe_actions(self, actions: List[Dict[str, Any]]):
        if not actions:
            return
        self.recent_action_load += len(actions)
        for action in actions:
            payload = action.get("action_args", {}) if isinstance(action, dict) else {}
            for token in self._extract_action_tokens(payload):
                self.topic_momentum[token] = self.topic_momentum.get(token, 0.0) + 0.35

    def _time_multiplier(self, current_hour: int) -> float:
        if current_hour in self.time_config.get("peak_hours", []):
            return self.time_config.get("peak_activity_multiplier", 1.5)
        if current_hour in self.time_config.get("off_peak_hours", []):
            return self.time_config.get("off_peak_activity_multiplier", 0.05)
        if current_hour in self.time_config.get("morning_hours", []):
            return self.time_config.get("morning_activity_multiplier", 0.4)
        if current_hour in self.time_config.get("work_hours", []):
            return self.time_config.get("work_activity_multiplier", 0.7)
        return 1.0

    def _phase_for_hour(self, current_absolute_hour: float) -> Dict[str, Any]:
        for phase in self.temporal_forecast_config.get("phase_windows", []) or []:
            try:
                start_hour = float(phase.get("start_hour", 0))
                end_hour = float(phase.get("end_hour", 0))
            except (TypeError, ValueError):
                continue
            if start_hour <= current_absolute_hour <= end_hour:
                return phase
        phases = self.temporal_forecast_config.get("phase_windows", []) or []
        return phases[-1] if phases else {}

    def _phase_multiplier(self, current_absolute_hour: float | None) -> float:
        if current_absolute_hour is None:
            return 1.0
        phase = self._phase_for_hour(current_absolute_hour)
        try:
            return float(phase.get("activity_multiplier", 1.0))
        except (TypeError, ValueError):
            return 1.0

    def simulated_time_label(self, current_absolute_hour: float) -> str:
        start_at_raw = self.temporal_forecast_config.get("forecast_start_at")
        timezone_name = self.temporal_forecast_config.get("timezone", "UTC")
        if not start_at_raw:
            day = int(current_absolute_hour // 24) + 1
            hour = int(current_absolute_hour % 24)
            return f"Day {day}, {hour:02d}:00 ({timezone_name})"
        try:
            start_at = datetime.fromisoformat(str(start_at_raw))
            simulated_at = start_at + timedelta(hours=current_absolute_hour)
            return f"{simulated_at.replace(microsecond=0).isoformat()} ({timezone_name})"
        except ValueError:
            day = int(current_absolute_hour // 24) + 1
            hour = int(current_absolute_hour % 24)
            return f"Day {day}, {hour:02d}:00 ({timezone_name})"

    def annotate_initial_posts(self, posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        annotated = []
        phase = self._phase_for_hour(0)
        for post in posts:
            updated = dict(post)
            updated.setdefault("trigger_hour", 0)
            updated.setdefault("phase", phase.get("name", "early_reaction"))
            updated.setdefault("time_context", f"{self.simulated_time_label(0)} {updated.get('phase', '')}".strip())
            annotated.append(updated)
        return annotated

    def _topic_match_bonus(self, agent_config: Dict[str, Any]) -> float:
        topic_pool = self._current_topic_pool()
        if not topic_pool and not self.narrative_tokens:
            return 0.0

        haystack = " ".join([
            agent_config.get("entity_name", ""),
            agent_config.get("entity_type", ""),
            agent_config.get("entity_summary", ""),
            " ".join(agent_config.get("interested_topics", [])),
            agent_config.get("stance", ""),
        ])
        tokens = _normalize_tokens(haystack)
        if not tokens:
            return 0.0

        keyword_matches = len(tokens & topic_pool)
        narrative_matches = len(tokens & self.narrative_tokens)
        return min(0.45, keyword_matches * 0.12 + narrative_matches * 0.05)

    def _cooldown_rounds(self, agent_config: Dict[str, Any], minutes_per_round: int) -> int:
        min_delay = max(0, int(agent_config.get("response_delay_min", 0)))
        max_delay = max(min_delay, int(agent_config.get("response_delay_max", min_delay)))
        sampled_delay = self.rng.randint(min_delay, max_delay) if max_delay > min_delay else min_delay
        if sampled_delay <= 0:
            return 0
        return max(1, math.ceil(sampled_delay / max(minutes_per_round, 1)))

    def select_active_agents(
        self,
        env,
        current_hour: int,
        round_num: int,
        minutes_per_round: int,
        current_absolute_hour: float | None = None
    ) -> List[Tuple[int, Any]]:
        self._decay_trends(round_num)
        base_min = self.time_config.get("agents_per_hour_min", 5)
        base_max = self.time_config.get("agents_per_hour_max", 20)
        multiplier = (
            self._time_multiplier(current_hour)
            * self._phase_multiplier(current_absolute_hour)
            * self._volatility_multiplier()
            * self._stakeholder_multiplier()
        )
        target_count = math.ceil(self.rng.uniform(base_min, base_max) * multiplier)
        target_count += self._precision_target_adjustment()
        if self.recent_action_load >= 6:
            target_count += 1
        if self.recent_action_load >= 12:
            target_count += 1
        target_count = min(target_count, self.max_active_agents, len(self.agent_configs))
        target_count = max(1, target_count)

        candidates: List[Tuple[float, int]] = []
        viral_threshold = max(1, int(self.platform_config.get("viral_threshold", 10) or 10))
        echo_strength = float(self.platform_config.get("echo_chamber_strength", 0.5) or 0.5)
        for cfg in self.agent_configs:
            agent_id = cfg.get("agent_id", 0)
            state = self.agent_states.setdefault(agent_id, AgentRuntimeState())
            active_hours = cfg.get("active_hours", list(range(8, 23)))
            if current_hour not in active_hours or round_num < state.next_available_round:
                continue

            activity_level = max(0.0, min(1.0, float(cfg.get("activity_level", 0.5))))
            posts_per_hour = max(0.0, float(cfg.get("posts_per_hour", 0.0)))
            comments_per_hour = max(0.0, float(cfg.get("comments_per_hour", 0.0)))
            interaction_rate = max(0.05, posts_per_hour + comments_per_hour * 0.6)
            per_round_budget = interaction_rate * (minutes_per_round / 60.0) * activity_level * multiplier
            state.carryover_budget = min(3.5, state.carryover_budget + per_round_budget)

            influence = max(0.0, float(cfg.get("influence_weight", 1.0)))
            topic_bonus = self._topic_match_bonus(cfg)
            inactivity_bonus = min(0.3, max(0, round_num - state.last_action_round - 1) * 0.02)
            influence_bonus = min(0.35, (influence - 1.0) * 0.12) if influence > 1.0 else 0.0
            trend_bonus = min(0.25, self.recent_action_load / viral_threshold * 0.08)
            stance_bonus = echo_strength * 0.08 if topic_bonus > 0 and cfg.get("stance") not in {"neutral", "observer"} else 0.0
            selection_score = state.carryover_budget + topic_bonus + inactivity_bonus + influence_bonus + trend_bonus + stance_bonus

            threshold = 0.55 if topic_bonus > 0 else 0.7
            if self.precision_mode == "precision":
                threshold += 0.05
            if selection_score >= threshold:
                candidates.append((selection_score + self.rng.random() * 0.08, agent_id))

        if not candidates:
            return []

        candidates.sort(reverse=True)
        selected_ids = [agent_id for _, agent_id in candidates[:target_count]]

        active_agents = []
        for agent_id in selected_ids:
            try:
                agent = env.agent_graph.get_agent(agent_id)
            except Exception:
                continue

            state = self.agent_states.setdefault(agent_id, AgentRuntimeState())
            cfg = self.agent_config_map.get(agent_id, {})
            state.carryover_budget = max(0.0, state.carryover_budget - 1.0)
            state.last_action_round = round_num
            state.next_available_round = round_num + self._cooldown_rounds(cfg, minutes_per_round)
            active_agents.append((agent_id, agent))

        return active_agents

    def get_due_scheduled_posts(
        self,
        round_num: int,
        minutes_per_round: int
    ) -> List[Dict[str, Any]]:
        scheduled_events = self.event_config.get("scheduled_events", [])
        if not scheduled_events:
            return []

        current_absolute_hour = (round_num * minutes_per_round) / 60.0
        due_posts = []
        for idx, event in enumerate(scheduled_events):
            event_key = str(event.get("event_id") or f"{self.platform}:{idx}")
            if event_key in self.processed_scheduled_events:
                continue

            event_platform = str(event.get("platform", "")).lower()
            if event_platform and event_platform not in {self.platform, "both", "parallel"}:
                continue

            trigger_round = event.get("trigger_round")
            trigger_hour = event.get("trigger_hour")
            should_fire = False
            if trigger_round is not None:
                try:
                    should_fire = round_num >= int(trigger_round)
                except (TypeError, ValueError):
                    should_fire = False
            elif trigger_hour is not None:
                try:
                    should_fire = current_absolute_hour >= float(trigger_hour)
                except (TypeError, ValueError):
                    should_fire = False

            if should_fire:
                self.processed_scheduled_events.add(event_key)
                updated_event = dict(event)
                updated_event.setdefault("simulated_at", self.simulated_time_label(current_absolute_hour))
                updated_event.setdefault("phase", self._phase_for_hour(current_absolute_hour).get("name", ""))
                updated_event.setdefault(
                    "time_context",
                    f"{updated_event.get('simulated_at', '')} {updated_event.get('phase', '')}".strip(),
                )
                due_posts.append(updated_event)

        return due_posts


def build_create_post_actions(
    env,
    posts: List[Dict[str, Any]],
    manual_action_cls,
    create_post_action_type,
    allow_multiple: bool = False
):
    actions = {}
    prepared_posts = []

    for post in posts:
        content = str(post.get("content", "")).strip()
        agent_id = post.get("poster_agent_id")
        if not content or agent_id is None:
            continue

        time_context = str(post.get("time_context") or post.get("simulated_at") or "").strip()
        if time_context and "simulated time:" not in content.lower():
            content = f"[Simulated time: {time_context}] {content}"

        try:
            agent = env.agent_graph.get_agent(int(agent_id))
        except Exception:
            continue

        action = manual_action_cls(
            action_type=create_post_action_type,
            action_args={"content": content}
        )

        if allow_multiple and agent in actions:
            if not isinstance(actions[agent], list):
                actions[agent] = [actions[agent]]
            actions[agent].append(action)
        else:
            actions[agent] = action

        prepared_posts.append({
            "agent_id": int(agent_id),
            "content": content,
            "poster_type": post.get("poster_type", ""),
        })

    return actions, prepared_posts
