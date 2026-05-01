"""
Intelligent Simulation Configuration Generator
Uses LLM to automatically generate detailed simulation parameters based on simulation requirements, document content, and graph information.
Fully automated, no manual parameter setup needed.

Uses a step-by-step generation strategy to avoid failures from generating excessively long content at once:
1. Generate time configuration
2. Generate event configuration
3. Generate Agent configurations in batches
4. Generate platform configuration
"""

import json
import math
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from openai import OpenAI

from ..config import Config
from ..utils.logger import get_logger
from ..utils.llm_base import normalize_openai_base_url
from ..utils.llm_rate_limiter import wait_for_llm_slot
from .graph_entity_reader import EntityNode, GraphEntityReader

logger = get_logger('univerra.simulation_config')

RHYTHM_PRESETS = {
    "asia": {
        "region": "Asia-Pacific",
        "timezone": "Asia/Singapore",
        "peak_hours": [19, 20, 21, 22],
        "off_peak_hours": [0, 1, 2, 3, 4, 5],
        "morning_hours": [6, 7, 8],
        "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
    },
    "us": {
        "region": "United States",
        "timezone": "America/New_York",
        "peak_hours": [18, 19, 20, 21, 22],
        "off_peak_hours": [1, 2, 3, 4, 5, 6],
        "morning_hours": [6, 7, 8, 9],
        "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17],
    },
    "europe": {
        "region": "Europe",
        "timezone": "Europe/London",
        "peak_hours": [18, 19, 20, 21, 22],
        "off_peak_hours": [1, 2, 3, 4, 5],
        "morning_hours": [6, 7, 8],
        "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
    },
    "global": {
        "region": "Global",
        "timezone": "UTC",
        "peak_hours": [12, 13, 18, 19, 20, 21],
        "off_peak_hours": [3, 4, 5],
        "morning_hours": [6, 7, 8, 9],
        "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17],
    },
}


@dataclass
class AgentActivityConfig:
    """Activity configuration for a single Agent"""
    agent_id: int
    entity_uuid: str
    entity_name: str
    entity_type: str
    entity_summary: str = ""
    interested_topics: List[str] = field(default_factory=list)

    # Activity level configuration (0.0-1.0)
    activity_level: float = 0.5  # Overall activity level

    # Posting frequency (expected posts per hour)
    posts_per_hour: float = 1.0
    comments_per_hour: float = 2.0

    # Active time periods (24-hour format, 0-23)
    active_hours: List[int] = field(default_factory=lambda: list(range(8, 23)))

    # Response speed (reaction delay to trending events, unit: simulated minutes)
    response_delay_min: int = 5
    response_delay_max: int = 60

    # Sentiment bias (-1.0 to 1.0, negative to positive)
    sentiment_bias: float = 0.0

    # Stance (attitude toward specific topics)
    stance: str = "neutral"  # supportive, opposing, neutral, observer

    # Influence weight (determines probability of posts being seen by other Agents)
    influence_weight: float = 1.0


@dataclass
class TimeSimulationConfig:
    """Time simulation configuration based on generic regional activity patterns."""
    # Total simulation duration (in simulated hours)
    total_simulation_hours: int = 72  # Default: simulate 72 hours (3 days)

    # Time per round (in simulated minutes) - default 60 minutes (1 hour), accelerated time flow
    minutes_per_round: int = 60

    # Number of Agents activated per hour (range)
    agents_per_hour_min: int = 5
    agents_per_hour_max: int = 20

    # Peak hours
    peak_hours: List[int] = field(default_factory=lambda: [19, 20, 21, 22])
    peak_activity_multiplier: float = 1.5

    # Off-peak hours (0-5 AM, almost no activity)
    off_peak_hours: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5])
    off_peak_activity_multiplier: float = 0.05  # Extremely low activity at dawn

    # Morning hours
    morning_hours: List[int] = field(default_factory=lambda: [6, 7, 8])
    morning_activity_multiplier: float = 0.4

    # Work hours
    work_hours: List[int] = field(default_factory=lambda: [9, 10, 11, 12, 13, 14, 15, 16, 17, 18])
    work_activity_multiplier: float = 0.7


@dataclass
class TemporalForecastConfig:
    """Calendar-aware forecast metadata for time-grounded future simulation."""
    timezone: str = "UTC"
    forecast_start_at: str = ""
    forecast_end_at: str = ""
    horizon_label: str = "next_72_hours"
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    phase_windows: List[Dict[str, Any]] = field(default_factory=list)
    future_scenarios: List[Dict[str, Any]] = field(default_factory=list)
    accuracy_protocol: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EnsembleConfig:
    """Multi-run ensemble planning metadata."""
    enabled: bool = True
    recommended_runs: int = 7
    minimum_runs: int = 3
    seed_strategy: str = "simulation_id_platform_run_index_variant"
    variation_dimensions: List[str] = field(default_factory=list)
    aggregation_metrics: List[str] = field(default_factory=list)
    run_variants: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class EvidenceScoringProfile:
    """How forecast claims should be scored and audited."""
    scoring_scale: str = "0-100"
    minimum_high_confidence_score: int = 75
    claim_types: Dict[str, int] = field(default_factory=dict)
    source_weights: Dict[str, float] = field(default_factory=dict)
    required_claim_fields: List[str] = field(default_factory=list)
    low_confidence_rules: List[str] = field(default_factory=list)


@dataclass
class CalibrationDashboard:
    """Compact quality dashboard shown to users and report agents."""
    overall_quality_score: float = 0.0
    real_world_prediction_score: float = 0.0
    agent_diversity_score: float = 0.0
    data_coverage_score: float = 0.0
    temporal_resolution_score: float = 0.0
    uncertainty_score: float = 0.0
    recommended_next_step: str = ""
    warning_flags: List[str] = field(default_factory=list)


@dataclass
class EventConfig:
    """Event configuration"""
    # Initial events (triggered at simulation start)
    initial_posts: List[Dict[str, Any]] = field(default_factory=list)

    # Scheduled events (triggered at specific times)
    scheduled_events: List[Dict[str, Any]] = field(default_factory=list)

    # Trending topic keywords
    hot_topics: List[str] = field(default_factory=list)

    # Public opinion narrative direction
    narrative_direction: str = ""


@dataclass
class EnvironmentContext:
    """Structured real-world environment inferred from the user's scenario."""
    primary_region: str = "Global"
    timezone: str = "UTC"
    social_rhythm: str = "global"
    event_type: str = "public_opinion"
    volatility: str = "medium"
    stakeholder_pressure: str = "medium"
    realism_focus: str = "public_reaction"
    reasoning: str = ""


@dataclass
class CalibrationProfile:
    """Estimated confidence and uncertainty drivers for scenario prediction."""
    confidence_score: float = 0.45
    confidence_label: str = "moderate"
    scenario_complexity: str = "medium"
    entity_coverage_score: float = 0.5
    recommended_mode: str = "balanced"
    uncertainty_factors: List[str] = field(default_factory=list)
    reasoning: str = ""


@dataclass
class PlatformConfig:
    """Platform-specific configuration"""
    platform: str  # twitter or reddit

    # Recommendation algorithm weights
    recency_weight: float = 0.4  # Time freshness
    popularity_weight: float = 0.3  # Popularity
    relevance_weight: float = 0.3  # Relevance

    # Viral spread threshold (number of interactions before triggering spread)
    viral_threshold: int = 10

    # Echo chamber effect strength (degree of similar opinion clustering)
    echo_chamber_strength: float = 0.5


@dataclass
class SimulationParameters:
    """Complete simulation parameters configuration"""
    # Basic information
    simulation_id: str
    project_id: str
    graph_id: str
    simulation_requirement: str
    environment_context: EnvironmentContext = field(default_factory=EnvironmentContext)
    calibration_profile: CalibrationProfile = field(default_factory=CalibrationProfile)
    temporal_forecast_config: TemporalForecastConfig = field(default_factory=TemporalForecastConfig)
    ensemble_config: EnsembleConfig = field(default_factory=EnsembleConfig)
    evidence_scoring_profile: EvidenceScoringProfile = field(default_factory=EvidenceScoringProfile)
    outcome_probability_table: List[Dict[str, Any]] = field(default_factory=list)
    counterfactual_controls: List[Dict[str, Any]] = field(default_factory=list)
    real_world_signal_plan: Dict[str, Any] = field(default_factory=dict)
    validation_plan: Dict[str, Any] = field(default_factory=dict)
    evaluator_config: Dict[str, Any] = field(default_factory=dict)
    calibration_dashboard: CalibrationDashboard = field(default_factory=CalibrationDashboard)

    # Time configuration
    time_config: TimeSimulationConfig = field(default_factory=TimeSimulationConfig)

    # Agent configuration list
    agent_configs: List[AgentActivityConfig] = field(default_factory=list)

    # Event configuration
    event_config: EventConfig = field(default_factory=EventConfig)

    # Platform configuration
    twitter_config: Optional[PlatformConfig] = None
    reddit_config: Optional[PlatformConfig] = None

    # LLM config
    llm_model: str = ""
    llm_base_url: str = ""

    # Generation metadata
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    generation_reasoning: str = ""  # LLM reasoning explanation

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        time_dict = asdict(self.time_config)
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "environment_context": asdict(self.environment_context),
            "calibration_profile": asdict(self.calibration_profile),
            "temporal_forecast_config": asdict(self.temporal_forecast_config),
            "ensemble_config": asdict(self.ensemble_config),
            "evidence_scoring_profile": asdict(self.evidence_scoring_profile),
            "outcome_probability_table": self.outcome_probability_table,
            "counterfactual_controls": self.counterfactual_controls,
            "real_world_signal_plan": self.real_world_signal_plan,
            "validation_plan": self.validation_plan,
            "evaluator_config": self.evaluator_config,
            "calibration_dashboard": asdict(self.calibration_dashboard),
            "time_config": time_dict,
            "agent_configs": [asdict(a) for a in self.agent_configs],
            "event_config": asdict(self.event_config),
            "twitter_config": asdict(self.twitter_config) if self.twitter_config else None,
            "reddit_config": asdict(self.reddit_config) if self.reddit_config else None,
            "llm_model": self.llm_model,
            "llm_base_url": self.llm_base_url,
            "generated_at": self.generated_at,
            "generation_reasoning": self.generation_reasoning,
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


class SimulationConfigGenerator:
    """
    Intelligent Simulation Configuration Generator

    Uses LLM to analyze simulation requirements, document content, and graph entity information
    to automatically generate optimal simulation parameter configurations.

    Uses a step-by-step generation strategy:
    1. Generate time configuration and event configuration (lightweight)
    2. Generate Agent configurations in batches (10-20 per batch)
    3. Generate platform configuration
    """

    # Maximum context character count
    MAX_CONTEXT_LENGTH = 50000
    # Number of Agents per batch
    AGENTS_PER_BATCH = 15

    # Context truncation lengths per step (in characters)
    TIME_CONFIG_CONTEXT_LENGTH = 10000   # Time configuration
    EVENT_CONFIG_CONTEXT_LENGTH = 8000   # Event configuration
    ENTITY_SUMMARY_LENGTH = 300          # Entity summary
    AGENT_SUMMARY_LENGTH = 300           # Entity summary in Agent configuration
    ENTITIES_PER_TYPE_DISPLAY = 20       # Number of entities displayed per type

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = normalize_openai_base_url(base_url or Config.LLM_BASE_URL)
        self.model_name = model_name or Config.LLM_MODEL_NAME

        if not self.api_key:
            raise ValueError("LLM_API_KEY is not configured")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    def generate_config(
        self,
        simulation_id: str,
        project_id: str,
        graph_id: str,
        simulation_requirement: str,
        document_text: str,
        entities: List[EntityNode],
        profiles: Optional[List[Any]] = None,
        enable_twitter: bool = True,
        enable_reddit: bool = True,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> SimulationParameters:
        """
        Intelligently generate complete simulation configuration (step-by-step)

        Args:
            simulation_id: Simulation ID
            project_id: Project ID
            graph_id: Graph ID
            simulation_requirement: Simulation requirement description
            document_text: Original document content
            entities: Filtered entity list
            enable_twitter: Whether to enable Twitter
            enable_reddit: Whether to enable Reddit
            progress_callback: Progress callback function(current_step, total_steps, message)

        Returns:
            SimulationParameters: Complete simulation parameters
        """
        logger.info(f"Starting intelligent config generation: simulation_id={simulation_id}, entities={len(entities)}")

        # Calculate total number of steps
        num_batches = math.ceil(len(entities) / self.AGENTS_PER_BATCH)
        total_steps = 5 + num_batches  # Env context + calibration + time + events + N Agent batches + platform config
        current_step = 0

        def report_progress(step: int, message: str):
            nonlocal current_step
            current_step = step
            if progress_callback:
                progress_callback(step, total_steps, message)
            logger.info(f"[{step}/{total_steps}] {message}")

        # 1. Build base context information
        context = self._build_context(
            simulation_requirement=simulation_requirement,
            document_text=document_text,
            entities=entities
        )

        reasoning_parts = []

        # ========== Step 1: Infer environment context ==========
        report_progress(1, "Inferring real-world environment context...")
        environment_context = self._generate_environment_context(
            simulation_requirement=simulation_requirement,
            document_text=document_text
        )
        reasoning_parts.append(f"Environment: {environment_context.reasoning or environment_context.social_rhythm}")

        # ========== Step 2: Build calibration profile ==========
        report_progress(2, "Estimating scenario confidence and uncertainty...")
        calibration_profile = self._build_calibration_profile(
            simulation_requirement=simulation_requirement,
            document_text=document_text,
            entities=entities,
            environment_context=environment_context
        )
        reasoning_parts.append(f"Calibration: {calibration_profile.reasoning or calibration_profile.confidence_label}")

        # ========== Step 3: Generate time configuration ==========
        report_progress(3, "Generating time configuration...")
        num_entities = len(entities)
        time_config_result = self._generate_time_config(context, num_entities, environment_context)
        time_config = self._parse_time_config(time_config_result, num_entities, environment_context)
        reasoning_parts.append(f"Time config: {time_config_result.get('reasoning', 'Success')}")

        temporal_forecast_config = self._build_temporal_forecast_config(
            time_config=time_config,
            environment_context=environment_context,
            calibration_profile=calibration_profile,
        )
        reasoning_parts.append(
            "Forecast horizon: "
            f"{temporal_forecast_config.forecast_start_at} to {temporal_forecast_config.forecast_end_at} "
            f"({temporal_forecast_config.timezone})"
        )

        # ========== Step 4: Generate event configuration ==========
        report_progress(4, "Generating event configuration and trending topics...")
        event_config_result = self._generate_event_config(
            context,
            simulation_requirement,
            entities,
            environment_context,
            temporal_forecast_config,
        )
        event_config = self._parse_event_config(event_config_result)
        event_config = self._annotate_event_times(event_config, temporal_forecast_config)
        reasoning_parts.append(f"Event config: {event_config_result.get('reasoning', 'Success')}")

        # ========== Steps 5-N: Generate Agent configurations in batches ==========
        all_agent_configs = []
        for batch_idx in range(num_batches):
            start_idx = batch_idx * self.AGENTS_PER_BATCH
            end_idx = min(start_idx + self.AGENTS_PER_BATCH, len(entities))
            batch_entities = entities[start_idx:end_idx]

            report_progress(
                5 + batch_idx,
                f"Generating Agent configs ({start_idx + 1}-{end_idx}/{len(entities)})..."
            )

            batch_configs = self._generate_agent_configs_batch(
                context=context,
                entities=batch_entities,
                start_idx=start_idx,
                simulation_requirement=simulation_requirement,
                profiles=profiles
            )
            all_agent_configs.extend(batch_configs)

        reasoning_parts.append(f"Agent config: Successfully generated {len(all_agent_configs)}")

        # ========== Assign poster Agents to initial posts ==========
        logger.info("Assigning appropriate poster Agents to initial posts...")
        event_config = self._assign_event_agents(event_config, all_agent_configs)
        assigned_count = len([p for p in event_config.initial_posts if p.get("poster_agent_id") is not None])
        scheduled_assigned_count = len([p for p in event_config.scheduled_events if p.get("poster_agent_id") is not None])
        reasoning_parts.append(
            f"Event assignment: {assigned_count} initial posts and {scheduled_assigned_count} scheduled posts assigned"
        )

        ensemble_config = self._build_ensemble_config(
            calibration_profile=calibration_profile,
            environment_context=environment_context,
            temporal_forecast_config=temporal_forecast_config,
        )
        evidence_scoring_profile = self._build_evidence_scoring_profile(calibration_profile)
        outcome_probability_table = self._build_outcome_probability_table(
            environment_context=environment_context,
            calibration_profile=calibration_profile,
            temporal_forecast_config=temporal_forecast_config,
            event_config=event_config,
        )
        counterfactual_controls = self._build_counterfactual_controls(
            environment_context=environment_context,
            temporal_forecast_config=temporal_forecast_config,
            event_config=event_config,
        )
        real_world_signal_plan = self._build_real_world_signal_plan(environment_context)
        validation_plan = self._build_validation_plan(
            simulation_requirement=simulation_requirement,
            temporal_forecast_config=temporal_forecast_config,
        )
        evaluator_config = self._build_evaluator_config()
        calibration_dashboard = self._build_calibration_dashboard(
            calibration_profile=calibration_profile,
            environment_context=environment_context,
            temporal_forecast_config=temporal_forecast_config,
            entities=entities,
            event_config=event_config,
            ensemble_config=ensemble_config,
        )
        reasoning_parts.append(
            f"Ensemble/evaluation: {ensemble_config.recommended_runs} recommended runs, "
            f"{len(outcome_probability_table)} outcome paths, {len(counterfactual_controls)} counterfactuals"
        )

        # ========== Final step: Generate platform configuration ==========
        report_progress(total_steps, "Generating platform configuration...")
        twitter_config = None
        reddit_config = None

        volatility = environment_context.volatility.lower()
        stakeholder_pressure = environment_context.stakeholder_pressure.lower()
        volatility_bonus = 3 if volatility == "high" else (1 if volatility == "medium" else -1)
        echo_bonus = 0.1 if stakeholder_pressure == "high" else 0.0

        if enable_twitter:
            twitter_config = PlatformConfig(
                platform="twitter",
                recency_weight=0.4,
                popularity_weight=0.3,
                relevance_weight=0.3,
                viral_threshold=max(6, 10 - volatility_bonus),
                echo_chamber_strength=min(0.9, 0.5 + echo_bonus)
            )

        if enable_reddit:
            reddit_config = PlatformConfig(
                platform="reddit",
                recency_weight=0.3,
                popularity_weight=0.4,
                relevance_weight=0.3,
                viral_threshold=max(8, 15 - volatility_bonus),
                echo_chamber_strength=min(0.95, 0.6 + echo_bonus)
            )

        # Build final parameters
        params = SimulationParameters(
            simulation_id=simulation_id,
            project_id=project_id,
            graph_id=graph_id,
            simulation_requirement=simulation_requirement,
            environment_context=environment_context,
            calibration_profile=calibration_profile,
            temporal_forecast_config=temporal_forecast_config,
            ensemble_config=ensemble_config,
            evidence_scoring_profile=evidence_scoring_profile,
            outcome_probability_table=outcome_probability_table,
            counterfactual_controls=counterfactual_controls,
            real_world_signal_plan=real_world_signal_plan,
            validation_plan=validation_plan,
            evaluator_config=evaluator_config,
            calibration_dashboard=calibration_dashboard,
            time_config=time_config,
            agent_configs=all_agent_configs,
            event_config=event_config,
            twitter_config=twitter_config,
            reddit_config=reddit_config,
            llm_model=self.model_name,
            llm_base_url=self.base_url,
            generation_reasoning=" | ".join(reasoning_parts)
        )

        logger.info(f"Simulation config generation complete: {len(params.agent_configs)} Agent configs")

        return params

    def _build_context(
        self,
        simulation_requirement: str,
        document_text: str,
        entities: List[EntityNode]
    ) -> str:
        """Build LLM context, truncated to maximum length"""

        # Entity summary
        entity_summary = self._summarize_entities(entities)

        # Build context
        context_parts = [
            f"## Simulation Requirement\n{simulation_requirement}",
            f"\n## Entity Information ({len(entities)} total)\n{entity_summary}",
        ]

        current_length = sum(len(p) for p in context_parts)
        remaining_length = self.MAX_CONTEXT_LENGTH - current_length - 500  # Reserve 500 chars buffer

        if remaining_length > 0 and document_text:
            doc_text = document_text[:remaining_length]
            if len(document_text) > remaining_length:
                doc_text += "\n...(document truncated)"
            context_parts.append(f"\n## Original Document Content\n{doc_text}")

        return "\n".join(context_parts)

    def _detect_rhythm_fallback(self, text: str) -> str:
        text_lower = text.lower()
        if any(token in text_lower for token in ["usa", "united states", "american", "new york", "california", "washington"]):
            return "us"
        if any(token in text_lower for token in ["europe", "european", "uk", "london", "germany", "france"]):
            return "europe"
        if any(token in text_lower for token in ["global", "international", "worldwide", "multiple countries"]):
            return "global"
        return "global"

    def _generate_environment_context(
        self,
        simulation_requirement: str,
        document_text: str
    ) -> EnvironmentContext:
        source_text = f"{simulation_requirement}\n\n{document_text[:8000]}"
        fallback_key = self._detect_rhythm_fallback(source_text)
        preset = RHYTHM_PRESETS.get(fallback_key, RHYTHM_PRESETS["global"])

        prompt = f"""Infer the real-world environment for a social simulation from the user's scenario.

Scenario:
{simulation_requirement}

Document excerpt:
{document_text[:4000]}

Return pure JSON:
{{
  "primary_region": "country or region",
  "timezone": "IANA timezone string",
  "social_rhythm": "us|europe|global",
  "event_type": "policy|financial|public_opinion|campus|brand|emergency|geopolitical|other",
  "volatility": "low|medium|high",
  "stakeholder_pressure": "low|medium|high",
  "realism_focus": "public_reaction|institutional_response|market_behavior|community_conflict|mixed",
  "reasoning": "brief explanation"
}}"""

        system_prompt = "You are an expert at inferring real-world simulation context. Be conservative and grounded in the user scenario. Return pure JSON."

        try:
            result = self._call_llm_with_retry(prompt, system_prompt)
            rhythm = result.get("social_rhythm", fallback_key)
            preset = RHYTHM_PRESETS.get(rhythm, preset)
            return EnvironmentContext(
                primary_region=result.get("primary_region", preset["region"]),
                timezone=result.get("timezone", preset["timezone"]),
                social_rhythm=rhythm if rhythm in RHYTHM_PRESETS else fallback_key,
                event_type=result.get("event_type", "public_opinion"),
                volatility=result.get("volatility", "medium"),
                stakeholder_pressure=result.get("stakeholder_pressure", "medium"),
                realism_focus=result.get("realism_focus", "public_reaction"),
                reasoning=result.get("reasoning", f"Fallback to {preset['region']} rhythm"),
            )
        except Exception as e:
            logger.warning(f"Environment context generation failed: {e}, using fallback rhythm {fallback_key}")
            return EnvironmentContext(
                primary_region=preset["region"],
                timezone=preset["timezone"],
                social_rhythm=fallback_key,
                event_type="public_opinion",
                volatility="medium",
                stakeholder_pressure="medium",
                realism_focus="public_reaction",
                reasoning=f"Fallback rhythm inferred from scenario keywords: {fallback_key}",
            )

    def _build_calibration_profile(
        self,
        simulation_requirement: str,
        document_text: str,
        entities: List[EntityNode],
        environment_context: EnvironmentContext
    ) -> CalibrationProfile:
        requirement_lower = simulation_requirement.lower()
        document_lower = document_text.lower()
        combined_text = f"{requirement_lower}\n{document_lower[:12000]}"

        uncertainty_factors: List[str] = []
        complexity_score = 0

        if len(entities) < 15:
            uncertainty_factors.append("Limited entity coverage")
            complexity_score += 1
        elif len(entities) > 120:
            uncertainty_factors.append("Large multi-actor system")
            complexity_score += 2

        if any(token in combined_text for token in ["policy", "election", "regulation", "court", "war", "market", "stock", "macro"]):
            uncertainty_factors.append("High-impact institutional dynamics")
            complexity_score += 2

        if environment_context.volatility == "high":
            uncertainty_factors.append("High volatility scenario")
            complexity_score += 2

        if environment_context.social_rhythm == "global":
            uncertainty_factors.append("Cross-region timing complexity")
            complexity_score += 1

        if len(simulation_requirement) < 80:
            uncertainty_factors.append("Short user requirement may underspecify scenario")
            complexity_score += 1

        entity_coverage_score = min(0.95, max(0.25, len(entities) / 80))
        base_confidence = 0.78
        confidence_score = base_confidence - complexity_score * 0.08 + (entity_coverage_score - 0.5) * 0.18
        confidence_score = max(0.2, min(0.9, round(confidence_score, 2)))

        if confidence_score >= 0.7:
            confidence_label = "high"
        elif confidence_score >= 0.5:
            confidence_label = "moderate"
        else:
            confidence_label = "cautious"

        if complexity_score >= 4:
            scenario_complexity = "high"
            recommended_mode = "precision"
        elif complexity_score >= 2:
            scenario_complexity = "medium"
            recommended_mode = "balanced"
        else:
            scenario_complexity = "low"
            recommended_mode = "exploratory"

        reasoning = (
            f"Confidence {confidence_label} based on {len(entities)} entities, "
            f"{environment_context.volatility} volatility, {environment_context.social_rhythm} rhythm, "
            f"and complexity score {complexity_score}."
        )

        return CalibrationProfile(
            confidence_score=confidence_score,
            confidence_label=confidence_label,
            scenario_complexity=scenario_complexity,
            entity_coverage_score=round(entity_coverage_score, 2),
            recommended_mode=recommended_mode,
            uncertainty_factors=uncertainty_factors or ["Normal scenario uncertainty"],
            reasoning=reasoning,
        )

    def _summarize_entities(self, entities: List[EntityNode]) -> str:
        """Generate entity summary"""
        lines = []

        # Group by type
        by_type: Dict[str, List[EntityNode]] = {}
        for e in entities:
            t = e.get_entity_type() or "Unknown"
            if t not in by_type:
                by_type[t] = []
            by_type[t].append(e)

        for entity_type, type_entities in by_type.items():
            lines.append(f"\n### {entity_type} ({len(type_entities)} total)")
            # Use configured display count and summary length
            display_count = self.ENTITIES_PER_TYPE_DISPLAY
            summary_len = self.ENTITY_SUMMARY_LENGTH
            for e in type_entities[:display_count]:
                summary_preview = (e.summary[:summary_len] + "...") if len(e.summary) > summary_len else e.summary
                lines.append(f"- {e.name}: {summary_preview}")
            if len(type_entities) > display_count:
                lines.append(f"  ... and {len(type_entities) - display_count} more")

        return "\n".join(lines)

    def _call_llm_with_retry(self, prompt: str, system_prompt: str) -> Dict[str, Any]:
        """LLM call with retry, including JSON repair logic"""
        import re

        max_attempts = 3
        last_error = None

        for attempt in range(max_attempts):
            try:
                wait_for_llm_slot()
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7 - (attempt * 0.1)  # Lower temperature with each retry
                    # No max_tokens set, let LLM generate freely
                )

                content = response.choices[0].message.content
                finish_reason = response.choices[0].finish_reason

                # Check if output was truncated
                if finish_reason == 'length':
                    logger.warning(f"LLM output truncated (attempt {attempt+1})")
                    content = self._fix_truncated_json(content)

                # Attempt to parse JSON
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON parse failed (attempt {attempt+1}): {str(e)[:80]}")

                    # Attempt to fix JSON
                    fixed = self._try_fix_config_json(content)
                    if fixed:
                        return fixed

                    last_error = e

            except Exception as e:
                logger.warning(f"LLM call failed (attempt {attempt+1}): {str(e)[:80]}")
                last_error = e
                import time
                time.sleep(2 * (attempt + 1))

        raise last_error or Exception("LLM call failed")

    def _fix_truncated_json(self, content: str) -> str:
        """Fix truncated JSON"""
        content = content.strip()

        # Count unclosed brackets
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')

        # Check for unclosed strings
        if content and content[-1] not in '",}]':
            content += '"'

        # Close brackets
        content += ']' * open_brackets
        content += '}' * open_braces

        return content

    def _try_fix_config_json(self, content: str) -> Optional[Dict[str, Any]]:
        """Attempt to fix configuration JSON"""
        import re

        # Fix truncated content
        content = self._fix_truncated_json(content)

        # Extract JSON portion
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            json_str = json_match.group()

            # Remove newlines within strings
            def fix_string(match):
                s = match.group(0)
                s = s.replace('\n', ' ').replace('\r', ' ')
                s = re.sub(r'\s+', ' ', s)
                return s

            json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', fix_string, json_str)

            try:
                return json.loads(json_str)
            except:
                # Attempt to remove all control characters
                json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                json_str = re.sub(r'\s+', ' ', json_str)
                try:
                    return json.loads(json_str)
                except:
                    pass

        return None

    def _generate_time_config(
        self,
        context: str,
        num_entities: int,
        environment_context: EnvironmentContext
    ) -> Dict[str, Any]:
        """Generate time configuration"""
        # Use configured context truncation length
        context_truncated = context[:self.TIME_CONFIG_CONTEXT_LENGTH]

        # Calculate maximum allowed value (90% of agent count)
        max_agents_allowed = max(1, int(num_entities * 0.9))

        prompt = f"""Based on the following simulation requirements, generate a time simulation configuration.

{context_truncated}

## Task
Please generate a time configuration JSON.

### Environment Context
- Primary region: {environment_context.primary_region}
- Timezone: {environment_context.timezone}
- Social rhythm preset: {environment_context.social_rhythm}
- Event type: {environment_context.event_type}
- Volatility: {environment_context.volatility}
- Stakeholder pressure: {environment_context.stakeholder_pressure}

### Basic Principles
- Follow the inferred real-world region and timezone instead of assuming one default culture.
- Keep a realistic human daily rhythm for that region.
- Prefer 30-60 minute rounds when accuracy matters; use 15-30 minutes only for very fast breaking scenarios.
- High-volatility / emergency scenarios may have later-night spillover and more sustained activity.
- Institutional actors should stay more work-hour aligned unless the event is urgent.
- If the scenario is global, use broader overlap windows.
- Choose a duration that covers the whole plausible forecast horizon: early reaction, amplification, and stabilization/escalation.

### Return JSON format (no markdown)

Example:
{{
    "total_simulation_hours": 72,
    "minutes_per_round": 60,
    "agents_per_hour_min": 5,
    "agents_per_hour_max": 50,
    "peak_hours": [19, 20, 21, 22],
    "off_peak_hours": [0, 1, 2, 3, 4, 5],
    "morning_hours": [6, 7, 8],
    "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
    "reasoning": "Explanation of the time configuration for this event"
}}

Field descriptions:
- total_simulation_hours (int): Total simulation duration, 24-336 hours; shorter for breaking events, longer for sustained topics
- minutes_per_round (int): Duration per round, 15-120 minutes, recommended 30-60 minutes for precision
- agents_per_hour_min (int): Minimum Agents activated per hour (range: 1-{max_agents_allowed})
- agents_per_hour_max (int): Maximum Agents activated per hour (range: 1-{max_agents_allowed})
- peak_hours (int array): Peak hours, adjusted based on event participant groups
- off_peak_hours (int array): Off-peak hours, typically late night/dawn
- morning_hours (int array): Morning hours
- work_hours (int array): Work hours
- reasoning (string): Brief explanation of why this configuration was chosen"""

        system_prompt = "You are a social media simulation expert. Return pure JSON format. Time configuration must follow the inferred real-world region and event context."

        try:
            return self._call_llm_with_retry(prompt, system_prompt)
        except Exception as e:
            logger.warning(f"Time config LLM generation failed: {e}, using default config")
            return self._get_default_time_config(num_entities, environment_context)

    def _get_default_time_config(self, num_entities: int, environment_context: EnvironmentContext) -> Dict[str, Any]:
        """Get default time configuration based on inferred environment."""
        preset = RHYTHM_PRESETS.get(environment_context.social_rhythm, RHYTHM_PRESETS["global"])
        volatility_bonus = 1 if environment_context.volatility == "high" else 0
        return {
            "total_simulation_hours": 72,
            "minutes_per_round": 60,  # 1 hour per round, accelerated time flow
            "agents_per_hour_min": max(1, num_entities // 15),
            "agents_per_hour_max": max(5 + volatility_bonus, num_entities // 5),
            "peak_hours": preset["peak_hours"],
            "off_peak_hours": preset["off_peak_hours"],
            "morning_hours": preset["morning_hours"],
            "work_hours": preset["work_hours"],
            "reasoning": f"Using default {preset['region']} rhythm config ({environment_context.timezone})"
        }

    def _parse_time_config(
        self,
        result: Dict[str, Any],
        num_entities: int,
        environment_context: EnvironmentContext
    ) -> TimeSimulationConfig:
        """Parse time config result and validate agents_per_hour does not exceed total agent count"""
        preset = RHYTHM_PRESETS.get(environment_context.social_rhythm, RHYTHM_PRESETS["global"])
        # Get raw values
        total_hours = self._clamp_int(result.get("total_simulation_hours", 72), 24, 336, 72)
        minutes_per_round = self._clamp_int(result.get("minutes_per_round", 60), 15, 120, 60)
        agents_per_hour_min = self._safe_int(result.get("agents_per_hour_min", max(1, num_entities // 15)), 1)
        agents_per_hour_max = self._safe_int(result.get("agents_per_hour_max", max(5, num_entities // 5)), 5)

        max_agents_allowed = max(1, min(num_entities, int(num_entities * 0.9) if num_entities > 3 else num_entities))
        agents_per_hour_min = max(1, min(agents_per_hour_min, max_agents_allowed))
        agents_per_hour_max = max(1, min(agents_per_hour_max, max_agents_allowed))

        if max_agents_allowed > 1 and agents_per_hour_min >= agents_per_hour_max:
            agents_per_hour_min = max(1, agents_per_hour_max - 1)
            logger.warning(f"agents_per_hour_min >= max, corrected to {agents_per_hour_min}")
        elif max_agents_allowed == 1:
            agents_per_hour_min = 1
            agents_per_hour_max = 1

        return TimeSimulationConfig(
            total_simulation_hours=total_hours,
            minutes_per_round=minutes_per_round,
            agents_per_hour_min=agents_per_hour_min,
            agents_per_hour_max=agents_per_hour_max,
            peak_hours=self._parse_hour_list(result.get("peak_hours"), preset["peak_hours"]),
            off_peak_hours=self._parse_hour_list(result.get("off_peak_hours"), preset["off_peak_hours"]),
            off_peak_activity_multiplier=0.05,  # Almost no one at dawn
            morning_hours=self._parse_hour_list(result.get("morning_hours"), preset["morning_hours"]),
            morning_activity_multiplier=0.4,
            work_hours=self._parse_hour_list(result.get("work_hours"), preset["work_hours"]),
            work_activity_multiplier=0.7,
            peak_activity_multiplier=1.5
        )

    def _safe_int(self, value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _clamp_int(self, value: Any, min_value: int, max_value: int, default: int) -> int:
        parsed = self._safe_int(value, default)
        return max(min_value, min(max_value, parsed))

    def _parse_hour_list(self, raw_value: Any, default: List[int]) -> List[int]:
        if not isinstance(raw_value, list):
            return list(default)
        hours = []
        for item in raw_value:
            hour = self._safe_int(item, -1)
            if 0 <= hour <= 23 and hour not in hours:
                hours.append(hour)
        return hours or list(default)

    def _safe_zoneinfo(self, timezone_name: str) -> ZoneInfo:
        try:
            return ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            return ZoneInfo("UTC")

    def _format_datetime(self, value: datetime) -> str:
        return value.replace(microsecond=0).isoformat()

    def _build_phase_window(
        self,
        name: str,
        start_hour: float,
        end_hour: float,
        start_at: datetime,
        expected_focus: str,
        multiplier: float,
    ) -> Dict[str, Any]:
        start_at_dt = start_at + timedelta(hours=start_hour)
        end_at_dt = start_at + timedelta(hours=end_hour)
        return {
            "name": name,
            "start_hour": round(start_hour, 2),
            "end_hour": round(end_hour, 2),
            "start_at": self._format_datetime(start_at_dt),
            "end_at": self._format_datetime(end_at_dt),
            "expected_focus": expected_focus,
            "activity_multiplier": multiplier,
        }

    def _build_temporal_forecast_config(
        self,
        time_config: TimeSimulationConfig,
        environment_context: EnvironmentContext,
        calibration_profile: CalibrationProfile,
    ) -> TemporalForecastConfig:
        timezone_name = environment_context.timezone or RHYTHM_PRESETS.get(
            environment_context.social_rhythm,
            RHYTHM_PRESETS["global"],
        )["timezone"]
        tzinfo = self._safe_zoneinfo(timezone_name)
        generated_at = datetime.now(tzinfo).replace(microsecond=0)
        forecast_start_at = (generated_at + timedelta(hours=1)).replace(minute=0, second=0)
        forecast_end_at = forecast_start_at + timedelta(hours=time_config.total_simulation_hours)
        total_hours = max(1, time_config.total_simulation_hours)

        early_end = max(6.0, round(total_hours * 0.25, 2))
        middle_end = max(early_end + 1.0, round(total_hours * 0.65, 2))
        if middle_end >= total_hours:
            middle_end = max(early_end + 1.0, total_hours - 1.0)

        volatility = environment_context.volatility.lower()
        pressure = environment_context.stakeholder_pressure.lower()
        phase_windows = [
            self._build_phase_window(
                "early_reaction",
                0,
                min(early_end, total_hours),
                forecast_start_at,
                "Initial awareness, first reactions, and immediate framing contests",
                1.15 if volatility == "high" else 1.0,
            ),
            self._build_phase_window(
                "amplification",
                min(early_end, total_hours),
                min(middle_end, total_hours),
                forecast_start_at,
                "Cross-group spread, media/community amplification, and stance formation",
                1.25 if pressure == "high" else 1.1,
            ),
            self._build_phase_window(
                "stabilization_or_escalation",
                min(middle_end, total_hours),
                total_hours,
                forecast_start_at,
                "Outcome consolidation, fatigue, backlash, escalation, or institutional response",
                1.15 if volatility == "high" else 0.95,
            ),
        ]

        future_scenarios = [
            {
                "name": "baseline_path",
                "relative_likelihood": "primary",
                "trigger_conditions": [
                    "Scheduled events unfold near the planned trigger hours",
                    "Agent reactions follow the generated stance and activity profile",
                ],
                "expected_outcome": "The central trajectory reflected by the simulation's configured events and most active actor groups.",
                "leading_indicators": ["early reaction volume", "topic momentum", "cross-platform repetition"],
            },
            {
                "name": "escalation_path",
                "relative_likelihood": "conditional",
                "trigger_conditions": [
                    "High-influence agents repeat the same negative or urgent framing",
                    "Scheduled follow-up posts land during peak activity windows",
                ],
                "expected_outcome": "The scenario becomes more volatile, with faster spread and stronger opposition or alarm.",
                "leading_indicators": ["peak-hour repost/comment bursts", "negative sentiment clustering", "official-response delays"],
            },
            {
                "name": "stabilization_path",
                "relative_likelihood": "conditional",
                "trigger_conditions": [
                    "Authoritative or trusted agents answer during work-hour windows",
                    "Topic momentum decays before a second peak",
                ],
                "expected_outcome": "The scenario cools into narrower discussion, with less broad contagion across communities.",
                "leading_indicators": ["declining action load", "fewer new hot-topic tokens", "balanced or neutral agent responses"],
            },
        ]

        accuracy_protocol = {
            "mode": calibration_profile.recommended_mode,
            "confidence_label": calibration_profile.confidence_label,
            "confidence_score": calibration_profile.confidence_score,
            "rules": [
                "Every forecast claim should be tied to simulated actions, retrieved facts, or explicit uncertainty.",
                "Use the configured phase windows when describing when outcomes happen.",
                "Separate observed simulation evidence from inferred future interpretation.",
                "Do not invent exact percentages or guarantees when the simulation evidence does not contain them.",
                "End generated reports with a concise small summary.",
            ],
            "uncertainty_factors": calibration_profile.uncertainty_factors,
        }

        return TemporalForecastConfig(
            timezone=timezone_name if timezone_name else "UTC",
            forecast_start_at=self._format_datetime(forecast_start_at),
            forecast_end_at=self._format_datetime(forecast_end_at),
            horizon_label=f"next_{total_hours}_hours",
            generated_at=self._format_datetime(generated_at),
            phase_windows=phase_windows,
            future_scenarios=future_scenarios,
            accuracy_protocol=accuracy_protocol,
        )

    def _phase_for_hour(
        self,
        absolute_hour: float,
        temporal_forecast_config: TemporalForecastConfig,
    ) -> Dict[str, Any]:
        for phase in temporal_forecast_config.phase_windows:
            if phase.get("start_hour", 0) <= absolute_hour <= phase.get("end_hour", 0):
                return phase
        return temporal_forecast_config.phase_windows[-1] if temporal_forecast_config.phase_windows else {}

    def _simulated_time_at(
        self,
        absolute_hour: float,
        temporal_forecast_config: TemporalForecastConfig,
    ) -> str:
        try:
            start_at = datetime.fromisoformat(temporal_forecast_config.forecast_start_at)
        except ValueError:
            start_at = datetime.now(self._safe_zoneinfo(temporal_forecast_config.timezone))
        return self._format_datetime(start_at + timedelta(hours=absolute_hour))

    def _annotate_event_times(
        self,
        event_config: EventConfig,
        temporal_forecast_config: TemporalForecastConfig,
    ) -> EventConfig:
        for post in event_config.initial_posts:
            phase = self._phase_for_hour(0, temporal_forecast_config)
            post["trigger_hour"] = 0
            post["phase"] = phase.get("name", "early_reaction")
            post["simulated_at"] = temporal_forecast_config.forecast_start_at
            post["time_context"] = (
                f"{temporal_forecast_config.forecast_start_at} "
                f"({temporal_forecast_config.timezone}, {post['phase']})"
            )

        total_hours = 0
        try:
            start_at = datetime.fromisoformat(temporal_forecast_config.forecast_start_at)
            end_at = datetime.fromisoformat(temporal_forecast_config.forecast_end_at)
            total_hours = max(0, int((end_at - start_at).total_seconds() // 3600))
        except ValueError:
            total_hours = 0

        for index, event in enumerate(event_config.scheduled_events):
            trigger_hour = event.get("trigger_hour")
            if trigger_hour is None and event.get("trigger_round") is not None:
                trigger_hour = event.get("trigger_round")
            trigger_hour = self._safe_int(trigger_hour, (index + 1) * 6)
            if total_hours:
                trigger_hour = max(1, min(total_hours, trigger_hour))
            else:
                trigger_hour = max(1, trigger_hour)
            phase = self._phase_for_hour(trigger_hour, temporal_forecast_config)
            simulated_at = self._simulated_time_at(trigger_hour, temporal_forecast_config)
            event["trigger_hour"] = trigger_hour
            event["phase"] = phase.get("name", "")
            event["simulated_at"] = simulated_at
            event["time_context"] = f"{simulated_at} ({temporal_forecast_config.timezone}, {event['phase']})"

        return event_config

    def _normalize_probabilities(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        total = sum(max(0.0, float(row.get("probability", 0.0) or 0.0)) for row in rows)
        if total <= 0:
            return rows
        for row in rows:
            probability = max(0.0, float(row.get("probability", 0.0) or 0.0)) / total
            row["probability"] = round(probability, 2)
            row["probability_percent"] = round(probability * 100)
        drift = 100 - sum(int(row.get("probability_percent", 0)) for row in rows)
        if rows and drift:
            rows[0]["probability_percent"] = int(rows[0].get("probability_percent", 0)) + drift
            rows[0]["probability"] = round(rows[0]["probability_percent"] / 100, 2)
        return rows

    def _build_ensemble_config(
        self,
        calibration_profile: CalibrationProfile,
        environment_context: EnvironmentContext,
        temporal_forecast_config: TemporalForecastConfig,
    ) -> EnsembleConfig:
        complexity = calibration_profile.scenario_complexity.lower()
        volatility = environment_context.volatility.lower()
        if complexity == "high" or volatility == "high":
            recommended_runs = 11
        elif complexity == "medium":
            recommended_runs = 7
        else:
            recommended_runs = 5

        run_variants = []
        scenario_names = [s.get("name", "scenario") for s in temporal_forecast_config.future_scenarios]
        for index in range(recommended_runs):
            scenario_name = scenario_names[index % len(scenario_names)] if scenario_names else "baseline_path"
            run_variants.append({
                "run_index": index,
                "scenario_variant": scenario_name,
                "seed_offset": index * 9973,
                "description": f"Run {index + 1} explores {scenario_name} with deterministic seed variation.",
            })

        return EnsembleConfig(
            enabled=True,
            recommended_runs=recommended_runs,
            minimum_runs=3,
            variation_dimensions=[
                "agent activation randomness",
                "scheduled-event timing sensitivity",
                "stance amplification",
                "platform spread speed",
                "official-response timing",
            ],
            aggregation_metrics=[
                "outcome frequency",
                "mean and range of action volume",
                "time-to-peak discussion",
                "dominant sentiment/stance path",
                "rare high-impact failure path",
                "agreement score across runs",
            ],
            run_variants=run_variants,
        )

    def _build_evidence_scoring_profile(
        self,
        calibration_profile: CalibrationProfile,
    ) -> EvidenceScoringProfile:
        minimum_high = 80 if calibration_profile.recommended_mode == "precision" else 75
        return EvidenceScoringProfile(
            minimum_high_confidence_score=minimum_high,
            claim_types={
                "direct_simulation_observation": 90,
                "agent_quote_or_action": 85,
                "relationship_chain": 78,
                "fresh_external_signal": 72,
                "inferred_forecast_interpretation": 58,
                "unsupported_or_generic_claim": 20,
            },
            source_weights={
                "simulation_actions": 1.0,
                "agent_interviews": 0.9,
                "graph_facts": 0.85,
                "fresh_research": 0.75,
                "llm_inference": 0.45,
            },
            required_claim_fields=[
                "claim",
                "evidence_type",
                "evidence_text_or_reference",
                "confidence",
                "uncertainty_reason",
            ],
            low_confidence_rules=[
                "No exact probability unless it comes from ensemble frequency or the generated probability table.",
                "Mark claims low-confidence when no agent action, quote, graph fact, or scheduled event supports them.",
                "Separate observed simulation behavior from interpretation about the real world.",
                "Flag missing stakeholders, weak entity coverage, and short user requirements.",
            ],
        )

    def _build_outcome_probability_table(
        self,
        environment_context: EnvironmentContext,
        calibration_profile: CalibrationProfile,
        temporal_forecast_config: TemporalForecastConfig,
        event_config: EventConfig,
    ) -> List[Dict[str, Any]]:
        volatility = environment_context.volatility.lower()
        pressure = environment_context.stakeholder_pressure.lower()
        confidence = calibration_profile.confidence_score
        scheduled_count = len(event_config.scheduled_events)

        escalation = 0.28
        stabilization = 0.32
        fragmentation = 0.22
        delayed = 0.18

        if volatility == "high":
            escalation += 0.17
            stabilization -= 0.07
        elif volatility == "low":
            escalation -= 0.08
            stabilization += 0.1

        if pressure == "high":
            escalation += 0.08
            delayed -= 0.04
        elif pressure == "low":
            fragmentation += 0.05
            escalation -= 0.03

        if scheduled_count >= 5:
            escalation += 0.04
            delayed -= 0.02

        if confidence < 0.5:
            fragmentation += 0.08
            stabilization -= 0.04

        rows = [
            {
                "outcome": "Escalation / rapid amplification",
                "probability": escalation,
                "time_window": "early_reaction to amplification",
                "why": "High activity or high-pressure signals can turn early posts into a larger public reaction.",
                "leading_indicators": ["fast peak-hour spread", "negative stance clustering", "high-influence reposts"],
                "confidence": calibration_profile.confidence_label,
            },
            {
                "outcome": "Stabilization / controlled response",
                "probability": stabilization,
                "time_window": "amplification to stabilization_or_escalation",
                "why": "Trusted or official actors can narrow uncertainty if they respond inside work-hour windows.",
                "leading_indicators": ["balanced agent replies", "authoritative clarifications", "declining topic momentum"],
                "confidence": calibration_profile.confidence_label,
            },
            {
                "outcome": "Fragmented community discussion",
                "probability": fragmentation,
                "time_window": temporal_forecast_config.horizon_label,
                "why": "The scenario may remain inside separate clusters when bridges between groups are weak.",
                "leading_indicators": ["cluster-specific language", "low cross-platform repetition", "few bridge actors"],
                "confidence": "cautious" if confidence < 0.6 else calibration_profile.confidence_label,
            },
            {
                "outcome": "Delayed secondary wave",
                "probability": delayed,
                "time_window": "late horizon",
                "why": "A later scheduled update or external proof point can restart attention after initial fatigue.",
                "leading_indicators": ["late scheduled events", "renewed media framing", "new evidence tokens"],
                "confidence": "cautious",
            },
        ]
        return self._normalize_probabilities(rows)

    def _build_counterfactual_controls(
        self,
        environment_context: EnvironmentContext,
        temporal_forecast_config: TemporalForecastConfig,
        event_config: EventConfig,
    ) -> List[Dict[str, Any]]:
        first_followup_hour = min(
            [self._safe_int(event.get("trigger_hour"), 999) for event in event_config.scheduled_events] or [6]
        )
        controls = [
            {
                "id": "official_response_early",
                "label": "Official response 6 hours earlier",
                "change": {"scheduled_event_shift_hours": -6, "poster_type_focus": "official"},
                "expected_effect": "Tests whether earlier trusted communication lowers escalation probability.",
                "recommended_trigger_hour": max(1, first_followup_hour - 6),
            },
            {
                "id": "official_response_delayed",
                "label": "Official response 12 hours delayed",
                "change": {"scheduled_event_shift_hours": 12, "poster_type_focus": "official"},
                "expected_effect": "Tests whether silence or delay creates a larger second-wave reaction.",
                "recommended_trigger_hour": first_followup_hour + 12,
            },
            {
                "id": "media_amplification_low",
                "label": "Media amplification reduced",
                "change": {"media_activity_multiplier": 0.55, "platform_viral_threshold_multiplier": 1.35},
                "expected_effect": "Tests whether the event stays inside smaller communities without broad media lift.",
            },
            {
                "id": "influencer_opposition_high",
                "label": "Influencer opposition increases",
                "change": {"opposing_influence_multiplier": 1.4, "echo_chamber_strength_delta": 0.12},
                "expected_effect": "Tests whether one-sided high-influence criticism drives escalation.",
            },
            {
                "id": "cross_platform_bridge_high",
                "label": "More bridge users connect platforms",
                "change": {"bridge_actor_multiplier": 1.5, "cross_platform_repetition_multiplier": 1.25},
                "expected_effect": "Tests whether the scenario spreads beyond the initial platform/community.",
            },
        ]

        if environment_context.volatility.lower() == "high":
            controls.append({
                "id": "night_spillover",
                "label": "Late-night spillover remains active",
                "change": {"off_peak_activity_multiplier": 0.18},
                "expected_effect": "Tests whether urgency keeps discussion active outside normal rhythm.",
            })

        return controls

    def _build_real_world_signal_plan(self, environment_context: EnvironmentContext) -> Dict[str, Any]:
        return {
            "enabled": True,
            "purpose": "Refresh initial conditions before simulation and ground reports in observable external signals.",
            "sources": [
                {
                    "name": "knowledge_graph",
                    "status": "required",
                    "use": "Entity coverage, relationship facts, and scenario-specific memory.",
                },
                {
                    "name": "reddit_research",
                    "status": "enabled_when_available",
                    "use": "Community language, objections, and live discussion patterns.",
                },
                {
                    "name": "web_or_news_research",
                    "status": "enabled_when_available",
                    "use": "Fresh official, market, media, or public signals relevant to the scenario.",
                },
                {
                    "name": "official_sources",
                    "status": "recommended",
                    "use": "High-confidence facts for institutional, policy, financial, or emergency scenarios.",
                },
            ],
            "refresh_policy": {
                "before_prepare": True,
                "before_report": True,
                "timezone": environment_context.timezone,
                "high_volatility_refresh_hours": 6,
                "normal_refresh_hours": 24,
            },
            "quality_rule": "If fresh signals are unavailable, mark affected forecast claims as lower-confidence instead of filling gaps.",
        }

    def _build_validation_plan(
        self,
        simulation_requirement: str,
        temporal_forecast_config: TemporalForecastConfig,
    ) -> Dict[str, Any]:
        return {
            "mode": "historical_backtest_ready",
            "instructions": [
                "For an old event, provide only information available at the forecast start time.",
                "Run the simulation without leaking the real outcome.",
                "Compare predicted outcome table, peak timing, actor reactions, and final trajectory with the actual event.",
                "Record misses as calibration examples for future confidence scoring.",
            ],
            "comparison_metrics": [
                "directional outcome match",
                "time-to-peak error",
                "top stakeholder match",
                "sentiment/stance trend match",
                "missed-risk count",
            ],
            "forecast_window": {
                "start": temporal_forecast_config.forecast_start_at,
                "end": temporal_forecast_config.forecast_end_at,
                "timezone": temporal_forecast_config.timezone,
            },
            "scenario_fingerprint": simulation_requirement[:240],
        }

    def _build_evaluator_config(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "checks": [
                "unsupported_probability_or_percentage",
                "unanchored_time_claim",
                "missing_small_summary",
                "generic_filler_language",
                "contradiction_between_sections",
                "low_evidence_high_confidence_claim",
                "missing_counterfactual_sensitivity",
            ],
            "required_report_outputs": [
                "outcome probability table",
                "evidence strength notes",
                "counterfactual sensitivity notes",
                "calibration dashboard",
                "small summary",
            ],
            "severity_levels": ["info", "warning", "critical"],
        }

    def _build_calibration_dashboard(
        self,
        calibration_profile: CalibrationProfile,
        environment_context: EnvironmentContext,
        temporal_forecast_config: TemporalForecastConfig,
        entities: List[EntityNode],
        event_config: EventConfig,
        ensemble_config: EnsembleConfig,
    ) -> CalibrationDashboard:
        entity_types = {entity.get_entity_type() or "Unknown" for entity in entities}
        data_coverage = calibration_profile.entity_coverage_score
        agent_diversity = min(0.95, max(0.25, len(entity_types) / 8))
        minutes_per_phase = len(temporal_forecast_config.phase_windows) * 0.18
        temporal_resolution = min(0.92, 0.45 + minutes_per_phase + min(0.2, len(event_config.scheduled_events) * 0.03))
        uncertainty_score = round(1.0 - calibration_profile.confidence_score, 2)
        ensemble_bonus = min(0.08, ensemble_config.recommended_runs / 100)
        overall = (
            calibration_profile.confidence_score * 0.32
            + data_coverage * 0.22
            + agent_diversity * 0.16
            + temporal_resolution * 0.18
            + ensemble_bonus
        )
        real_world_score = min(0.9, overall - 0.08 if calibration_profile.scenario_complexity == "high" else overall)

        warning_flags = []
        if len(entities) < 20:
            warning_flags.append("limited_agent_population")
        if len(entity_types) < 4:
            warning_flags.append("low_actor_diversity")
        if len(event_config.scheduled_events) < 3:
            warning_flags.append("few_time_anchored_future_events")
        if environment_context.social_rhythm == "global":
            warning_flags.append("global_timing_uncertainty")
        if calibration_profile.confidence_score < 0.55:
            warning_flags.append("cautious_confidence")

        return CalibrationDashboard(
            overall_quality_score=round(max(0.0, min(1.0, overall)), 2),
            real_world_prediction_score=round(max(0.0, min(1.0, real_world_score)), 2),
            agent_diversity_score=round(agent_diversity, 2),
            data_coverage_score=round(data_coverage, 2),
            temporal_resolution_score=round(temporal_resolution, 2),
            uncertainty_score=uncertainty_score,
            recommended_next_step=(
                f"Run at least {ensemble_config.minimum_runs}-{ensemble_config.recommended_runs} seeded variants "
                "and compare outcome frequencies before treating results as decision-grade."
            ),
            warning_flags=warning_flags,
        )

    def _generate_event_config(
        self,
        context: str,
        simulation_requirement: str,
        entities: List[EntityNode],
        environment_context: EnvironmentContext,
        temporal_forecast_config: TemporalForecastConfig
    ) -> Dict[str, Any]:
        """Generate event configuration"""

        # Get available entity type list for LLM reference
        entity_types_available = list(set(
            e.get_entity_type() or "Unknown" for e in entities
        ))

        # List representative entity names for each type
        type_examples = {}
        for e in entities:
            etype = e.get_entity_type() or "Unknown"
            if etype not in type_examples:
                type_examples[etype] = []
            if len(type_examples[etype]) < 3:
                type_examples[etype].append(e.name)

        type_info = "\n".join([
            f"- {t}: {', '.join(examples)}"
            for t, examples in type_examples.items()
        ])

        # Use configured context truncation length
        context_truncated = context[:self.EVENT_CONFIG_CONTEXT_LENGTH]
        phase_summary = "\n".join(
            "- {name}: hour {start_hour}-{end_hour}, {start_at} to {end_at}; focus: {expected_focus}".format(**phase)
            for phase in temporal_forecast_config.phase_windows
        )

        prompt = f"""Based on the following simulation requirements, generate event configuration.

Simulation requirement: {simulation_requirement}

Environment context:
- Region: {environment_context.primary_region}
- Timezone: {environment_context.timezone}
- Event type: {environment_context.event_type}
- Volatility: {environment_context.volatility}
- Realism focus: {environment_context.realism_focus}

Forecast clock:
- Timezone: {temporal_forecast_config.timezone}
- Forecast start: {temporal_forecast_config.forecast_start_at}
- Forecast end: {temporal_forecast_config.forecast_end_at}
- Horizon: {temporal_forecast_config.horizon_label}

Forecast phases:
{phase_summary}

{context_truncated}

## Available Entity Types and Examples
{type_info}

## Task
Please generate an event configuration JSON:
- Extract trending topic keywords
- Describe the public opinion development direction
- Design initial post content, **each post must specify poster_type (publisher type)**
- Design 3-7 scheduled follow-up posts with concrete trigger_hour values inside the forecast horizon
- Spread scheduled events across the phase windows so the simulation has early, middle, and late future movement
- Each scheduled event should model a plausible time-based update: official response, media amplification, public reaction shift, corrective evidence, backlash, or fatigue

**Important**: poster_type must be selected from the "Available Entity Types" above, so initial posts can be assigned to appropriate Agents for publishing.
For example: official statements should be published by Official/University types, news by MediaOutlet, student opinions by Student.
Do not use vague wording like "later" without trigger_hour. All future updates must be anchored to simulated hours.

Return JSON format (no markdown):
{{
    "hot_topics": ["keyword1", "keyword2", ...],
    "narrative_direction": "<public opinion development direction description>",
    "initial_posts": [
        {{"content": "post content", "poster_type": "entity type (must be from available types)"}},
        ...
    ],
    "scheduled_events": [
        {{
            "event_id": "event_1",
            "trigger_hour": 6,
            "platform": "twitter|reddit|both",
            "content": "follow-up content",
            "poster_type": "entity type (must be from available types)",
            "phase": "one of the phase names above"
        }}
    ],
    "reasoning": "<brief explanation>"
}}"""

        system_prompt = "You are a public opinion analysis expert. Return pure JSON format. Note that poster_type must exactly match available entity types."

        try:
            return self._call_llm_with_retry(prompt, system_prompt)
        except Exception as e:
            logger.warning(f"Event config LLM generation failed: {e}, using default config")
            phase_events = []
            for index, phase in enumerate(temporal_forecast_config.phase_windows[:3], start=1):
                trigger_hour = max(1, self._safe_int(phase.get("start_hour", index * 6), index * 6))
                phase_events.append({
                    "event_id": f"fallback_phase_{index}",
                    "trigger_hour": trigger_hour,
                    "platform": "both",
                    "content": f"Simulated update for {phase.get('name', 'future phase')}: discussion continues around {simulation_requirement[:180]}",
                    "poster_type": entity_types_available[0] if entity_types_available else "Unknown",
                    "phase": phase.get("name", ""),
                })
            return {
                "hot_topics": [simulation_requirement[:40]] if simulation_requirement else [],
                "narrative_direction": "Fallback timeline generated because event configuration LLM call failed.",
                "initial_posts": [
                    {
                        "content": f"Initial simulated scenario injection: {simulation_requirement[:240]}",
                        "poster_type": entity_types_available[0] if entity_types_available else "Unknown",
                    }
                ],
                "scheduled_events": phase_events,
                "reasoning": "Using fallback time-anchored event config"
            }

    def _parse_event_config(self, result: Dict[str, Any]) -> EventConfig:
        """Parse event configuration result"""
        scheduled_events = []
        for idx, event in enumerate(result.get("scheduled_events", [])):
            if not isinstance(event, dict):
                continue
            scheduled_events.append({
                "event_id": event.get("event_id", f"scheduled_{idx}"),
                "trigger_hour": event.get("trigger_hour"),
                "trigger_round": event.get("trigger_round"),
                "platform": event.get("platform", "both"),
                "content": event.get("content", ""),
                "poster_type": event.get("poster_type", ""),
                "phase": event.get("phase", ""),
            })

        return EventConfig(
            initial_posts=result.get("initial_posts", []),
            scheduled_events=scheduled_events,
            hot_topics=result.get("hot_topics", []),
            narrative_direction=result.get("narrative_direction", "")
        )

    def _assign_event_agents(
        self,
        event_config: EventConfig,
        agent_configs: List[AgentActivityConfig]
    ) -> EventConfig:
        """
        Assign appropriate poster Agents to initial and scheduled posts

        Match the most suitable agent_id based on each post's poster_type
        """
        if not event_config.initial_posts and not event_config.scheduled_events:
            return event_config

        # Build agent index by entity type
        agents_by_type: Dict[str, List[AgentActivityConfig]] = {}
        for agent in agent_configs:
            etype = agent.entity_type.lower()
            if etype not in agents_by_type:
                agents_by_type[etype] = []
            agents_by_type[etype].append(agent)

        # Type alias mapping (handles different formats LLM may output)
        type_aliases = {
            "official": ["official", "university", "governmentagency", "government"],
            "university": ["university", "official"],
            "mediaoutlet": ["mediaoutlet", "media"],
            "student": ["student", "person"],
            "professor": ["professor", "expert", "teacher"],
            "alumni": ["alumni", "person"],
            "organization": ["organization", "ngo", "company", "group"],
            "person": ["person", "student", "alumni"],
        }

        # Track used agent index per type to avoid reusing the same agent
        used_indices: Dict[str, int] = {}

        def assign_posts(posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            updated_posts = []
            for post in posts:
                poster_type = post.get("poster_type", "").lower()
                matched_agent_id = None

                if poster_type in agents_by_type:
                    agents = agents_by_type[poster_type]
                    idx = used_indices.get(poster_type, 0) % len(agents)
                    matched_agent_id = agents[idx].agent_id
                    used_indices[poster_type] = idx + 1
                else:
                    for alias_key, aliases in type_aliases.items():
                        if poster_type in aliases or alias_key == poster_type:
                            for alias in aliases:
                                if alias in agents_by_type:
                                    agents = agents_by_type[alias]
                                    idx = used_indices.get(alias, 0) % len(agents)
                                    matched_agent_id = agents[idx].agent_id
                                    used_indices[alias] = idx + 1
                                    break
                        if matched_agent_id is not None:
                            break

                if matched_agent_id is None:
                    logger.warning(f"No matching Agent found for type '{poster_type}', using highest influence Agent")
                    if agent_configs:
                        sorted_agents = sorted(agent_configs, key=lambda a: a.influence_weight, reverse=True)
                        matched_agent_id = sorted_agents[0].agent_id
                    else:
                        matched_agent_id = 0

                updated_post = dict(post)
                updated_post["poster_type"] = post.get("poster_type", "Unknown")
                updated_post["poster_agent_id"] = matched_agent_id
                updated_posts.append(updated_post)
                logger.info(f"Event assignment: poster_type='{poster_type}' -> agent_id={matched_agent_id}")

            return updated_posts

        event_config.initial_posts = assign_posts(event_config.initial_posts)
        event_config.scheduled_events = assign_posts(event_config.scheduled_events)
        return event_config

    def _generate_agent_configs_batch(
        self,
        context: str,
        entities: List[EntityNode],
        start_idx: int,
        simulation_requirement: str,
        profiles: Optional[List[Any]] = None
    ) -> List[AgentActivityConfig]:
        """Generate Agent configurations in batches"""
        profile_by_entity_uuid = {}
        if profiles:
            for profile in profiles:
                entity_uuid = getattr(profile, "source_entity_uuid", None)
                if entity_uuid:
                    profile_by_entity_uuid[entity_uuid] = profile

        # Build entity info (using configured summary length)
        entity_list = []
        summary_len = self.AGENT_SUMMARY_LENGTH
        for i, e in enumerate(entities):
            profile = profile_by_entity_uuid.get(e.uuid)
            entity_list.append({
                "agent_id": start_idx + i,
                "entity_name": e.name,
                "entity_type": e.get_entity_type() or "Unknown",
                "summary": e.summary[:summary_len] if e.summary else "",
                "interested_topics": getattr(profile, "interested_topics", []) if profile else [],
                "profession": getattr(profile, "profession", "") if profile else "",
                "preset_stance": (e.attributes or {}).get("stance", ""),
                "perspective": (e.attributes or {}).get("perspective", ""),
                "synthetic": bool((e.attributes or {}).get("synthetic")),
            })

        prompt = f"""Based on the following information, generate social media activity configuration for each entity.

Simulation requirement: {simulation_requirement}

## Entity list
```json
{json.dumps(entity_list, ensure_ascii=False, indent=2)}
```

## Task
Generate activity configuration for each entity. Note:
- **Times follow realistic regional activity patterns**: late-night activity is low and evening activity is usually strongest
- **Official institutions** (University/GovernmentAgency): Low activity (0.1-0.3), active during work hours (9-17), slow response (60-240 min), high influence (2.5-3.0)
- **Media** (MediaOutlet): Medium activity (0.4-0.6), active all day (8-23), fast response (5-30 min), high influence (2.0-2.5)
- **Individuals** (Student/Person/Alumni): High activity (0.6-0.9), mainly active evenings (18-23), fast response (1-15 min), low influence (0.8-1.2)
- **Public figures/experts**: Medium activity (0.4-0.6), medium-high influence (1.5-2.0)
- If preset_stance is present, preserve it instead of collapsing everyone to neutral
- Synthetic archetype agents should not all agree with each other; keep meaningful disagreement and tradeoff tension

Return JSON format (no markdown):
{{
    "agent_configs": [
        {{
            "agent_id": <must match input>,
            "activity_level": <0.0-1.0>,
            "posts_per_hour": <posting frequency>,
            "comments_per_hour": <comment frequency>,
            "active_hours": [<active hours list, matching realistic regional activity patterns>],
            "response_delay_min": <min response delay in minutes>,
            "response_delay_max": <max response delay in minutes>,
            "sentiment_bias": <-1.0 to 1.0>,
            "stance": "<supportive/opposing/neutral/observer>",
            "influence_weight": <influence weight>
        }},
        ...
    ]
}}"""

        system_prompt = "You are a social media behavior analysis expert. Return pure JSON. Configuration must follow realistic regional activity patterns."

        try:
            result = self._call_llm_with_retry(prompt, system_prompt)
            llm_configs = {cfg["agent_id"]: cfg for cfg in result.get("agent_configs", [])}
        except Exception as e:
            logger.warning(f"Agent config batch LLM generation failed: {e}, using rule-based generation")
            llm_configs = {}

        # Build AgentActivityConfig objects
        configs = []
        for i, entity in enumerate(entities):
            agent_id = start_idx + i
            cfg = llm_configs.get(agent_id, {})
            profile = profile_by_entity_uuid.get(entity.uuid)

            # If LLM did not generate, use rule-based generation
            if not cfg:
                cfg = self._generate_agent_config_by_rule(entity)

            config = AgentActivityConfig(
                agent_id=agent_id,
                entity_uuid=entity.uuid,
                entity_name=entity.name,
                entity_type=entity.get_entity_type() or "Unknown",
                entity_summary=entity.summary[:summary_len] if entity.summary else "",
                interested_topics=getattr(profile, "interested_topics", []) if profile else [],
                activity_level=cfg.get("activity_level", 0.5),
                posts_per_hour=cfg.get("posts_per_hour", 0.5),
                comments_per_hour=cfg.get("comments_per_hour", 1.0),
                active_hours=cfg.get("active_hours", list(range(9, 23))),
                response_delay_min=cfg.get("response_delay_min", 5),
                response_delay_max=cfg.get("response_delay_max", 60),
                sentiment_bias=cfg.get("sentiment_bias", 0.0),
                stance=cfg.get("stance", "neutral"),
                influence_weight=cfg.get("influence_weight", 1.0)
            )
            configs.append(config)

        return configs

    def _generate_agent_config_by_rule(self, entity: EntityNode) -> Dict[str, Any]:
        """Generate a single Agent config using generic regional activity patterns."""
        entity_type = (entity.get_entity_type() or "Unknown").lower()
        attributes = entity.attributes or {}
        if attributes.get("synthetic"):
            stance = str(attributes.get("stance", "neutral")).lower()
            if stance == "supportive":
                return {
                    "activity_level": 0.65,
                    "posts_per_hour": 0.45,
                    "comments_per_hour": 1.1,
                    "active_hours": [8, 9, 12, 13, 18, 19, 20, 21, 22],
                    "response_delay_min": 3,
                    "response_delay_max": 25,
                    "sentiment_bias": 0.35,
                    "stance": "supportive",
                    "influence_weight": 1.4,
                }
            if stance == "opposing":
                return {
                    "activity_level": 0.7,
                    "posts_per_hour": 0.5,
                    "comments_per_hour": 1.3,
                    "active_hours": [9, 10, 12, 13, 19, 20, 21, 22, 23],
                    "response_delay_min": 2,
                    "response_delay_max": 20,
                    "sentiment_bias": -0.4,
                    "stance": "opposing",
                    "influence_weight": 1.5,
                }
            if stance == "observer":
                return {
                    "activity_level": 0.55,
                    "posts_per_hour": 0.35,
                    "comments_per_hour": 0.95,
                    "active_hours": [8, 9, 10, 12, 13, 18, 19, 20, 21],
                    "response_delay_min": 5,
                    "response_delay_max": 35,
                    "sentiment_bias": 0.0,
                    "stance": "observer",
                    "influence_weight": 1.35,
                }
            return {
                "activity_level": 0.5,
                "posts_per_hour": 0.3,
                "comments_per_hour": 0.8,
                "active_hours": [9, 10, 12, 13, 18, 19, 20, 21],
                "response_delay_min": 5,
                "response_delay_max": 30,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 1.2,
            }

        if entity_type in ["university", "governmentagency", "ngo"]:
            # Official institutions: active during work hours, low frequency, high influence
            return {
                "activity_level": 0.2,
                "posts_per_hour": 0.1,
                "comments_per_hour": 0.05,
                "active_hours": list(range(9, 18)),  # 9:00-17:59
                "response_delay_min": 60,
                "response_delay_max": 240,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 3.0
            }
        elif entity_type in ["mediaoutlet"]:
            # Media: active all day, medium frequency, high influence
            return {
                "activity_level": 0.5,
                "posts_per_hour": 0.8,
                "comments_per_hour": 0.3,
                "active_hours": list(range(7, 24)),  # 7:00-23:59
                "response_delay_min": 5,
                "response_delay_max": 30,
                "sentiment_bias": 0.0,
                "stance": "observer",
                "influence_weight": 2.5
            }
        elif entity_type in ["professor", "expert", "official"]:
            # Experts/professors: active during work + evening hours, medium frequency
            return {
                "activity_level": 0.4,
                "posts_per_hour": 0.3,
                "comments_per_hour": 0.5,
                "active_hours": list(range(8, 22)),  # 8:00-21:59
                "response_delay_min": 15,
                "response_delay_max": 90,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 2.0
            }
        elif entity_type in ["student"]:
            # Students: mainly evening, high frequency
            return {
                "activity_level": 0.8,
                "posts_per_hour": 0.6,
                "comments_per_hour": 1.5,
                "active_hours": [8, 9, 10, 11, 12, 13, 18, 19, 20, 21, 22, 23],  # Morning + evening
                "response_delay_min": 1,
                "response_delay_max": 15,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 0.8
            }
        elif entity_type in ["alumni"]:
            # Alumni: mainly evening
            return {
                "activity_level": 0.6,
                "posts_per_hour": 0.4,
                "comments_per_hour": 0.8,
                "active_hours": [12, 13, 19, 20, 21, 22, 23],  # Lunch break + evening
                "response_delay_min": 5,
                "response_delay_max": 30,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 1.0
            }
        else:
            # Regular people: evening peak
            return {
                "activity_level": 0.7,
                "posts_per_hour": 0.5,
                "comments_per_hour": 1.2,
                "active_hours": [9, 10, 11, 12, 13, 18, 19, 20, 21, 22, 23],  # Daytime + evening
                "response_delay_min": 2,
                "response_delay_max": 20,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 1.0
            }

