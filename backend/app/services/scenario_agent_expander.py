"""
Deterministic low-compute expansion for sparse simulations.
"""

import re
from typing import List, Set

from ..config import Config
from ..utils.logger import get_logger
from .graph_entity_reader import EntityNode, FilteredEntities


logger = get_logger("univerra.agent_expander")


class ScenarioAgentExpander:
    CAREER_HINTS = {
        "career", "job", "hire", "hiring", "developer", "backend", "frontend",
        "engineer", "python", "cybersecurity", "security", "resume", "interview",
        "learning", "learn", "ai", "automation", "employment", "internship",
    }

    def expand(
        self,
        filtered: FilteredEntities,
        simulation_requirement: str,
        document_text: str = "",
    ) -> FilteredEntities:
        min_agents = max(1, Config.SIMULATION_MIN_AGENT_COUNT)
        max_synthetic = max(0, Config.SIMULATION_MAX_SYNTHETIC_AGENTS)

        if filtered.filtered_count == 0 or filtered.filtered_count >= min_agents or max_synthetic == 0:
            return filtered

        base_entities = list(filtered.entities)
        target_count = min_agents
        synthetic_needed = min(max_synthetic, max(0, target_count - len(base_entities)))
        if synthetic_needed <= 0:
            return filtered

        context = " ".join(part for part in [simulation_requirement, document_text] if part).strip()
        is_career = self._looks_like_career_scenario(context)
        subject = self._build_subject_phrase(context, fallback="the current scenario")
        primary_name = base_entities[0].name if base_entities else "the main participant"

        archetypes = (
            self._career_archetypes(subject=subject, primary_name=primary_name)
            if is_career else
            self._general_archetypes(subject=subject, primary_name=primary_name)
        )

        existing_names = {entity.name.strip().lower() for entity in base_entities}
        synthetic_entities: List[EntityNode] = []
        synthetic_types: Set[str] = set()

        for index, archetype in enumerate(archetypes, start=1):
            name = archetype["name"]
            if name.strip().lower() in existing_names:
                continue

            labels = ["Entity", "Node", archetype["entity_type"]]
            entity = EntityNode(
                uuid=f"synthetic_{re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')}_{index}",
                name=name,
                labels=labels,
                summary=archetype["summary"],
                attributes={
                    "synthetic": True,
                    "role": archetype["entity_type"],
                    "stance": archetype.get("stance", "neutral"),
                    "perspective": archetype.get("perspective", ""),
                    "origin": "scenario_agent_expander",
                },
                related_edges=[],
                related_nodes=[],
            )
            synthetic_entities.append(entity)
            synthetic_types.add(archetype["entity_type"])
            existing_names.add(name.strip().lower())

            if len(synthetic_entities) >= synthetic_needed:
                break

        if not synthetic_entities:
            return filtered

        expanded_entities = base_entities + synthetic_entities
        expanded_types = set(filtered.entity_types) | synthetic_types

        logger.info(
            f"Expanded sparse simulation from {filtered.filtered_count} to {len(expanded_entities)} agents"
        )

        return FilteredEntities(
            entities=expanded_entities,
            entity_types=expanded_types,
            total_count=filtered.total_count,
            filtered_count=len(expanded_entities),
        )

    def _looks_like_career_scenario(self, text: str) -> bool:
        tokens = set(re.findall(r"[a-zA-Z]{3,}", (text or "").lower()))
        return bool(tokens & self.CAREER_HINTS)

    def _build_subject_phrase(self, text: str, fallback: str) -> str:
        lowered = (text or "").lower()

        if "cyber" in lowered or "security" in lowered:
            return "a cybersecurity career with Python and AI-assisted workflows"
        if "backend" in lowered:
            return "a backend development career with Python and AI-assisted workflows"
        if "frontend" in lowered:
            return "a frontend development path in an AI-assisted market"
        if "data" in lowered:
            return "a data-focused technical career in an AI-assisted market"
        if "python" in lowered:
            return "a Python-based technical career in an AI-assisted market"
        return fallback

    def _career_archetypes(self, subject: str, primary_name: str) -> List[dict]:
        return [
            {
                "name": "Hiring Manager",
                "entity_type": "HiringManager",
                "summary": f"Evaluates whether candidates like {primary_name} can turn {subject} into dependable entry-level execution.",
                "stance": "observer",
                "perspective": "selective and standards-heavy",
            },
            {
                "name": "Senior Practitioner",
                "entity_type": "SeniorPractitioner",
                "summary": f"Brings field-tested perspective on how newcomers build credibility, avoid shallow learning, and stay useful as tools change around {subject}.",
                "stance": "supportive",
                "perspective": "long-term skill compounding",
            },
            {
                "name": "Technical Recruiter",
                "entity_type": "Recruiter",
                "summary": f"Tracks junior hiring demand, portfolio expectations, and interview filters related to {subject}.",
                "stance": "supportive",
                "perspective": "market access and job filters",
            },
            {
                "name": "Peer Learner",
                "entity_type": "PeerLearner",
                "summary": f"Represents people on a similar path to {primary_name}, comparing learning pace, motivation, and job-search friction in {subject}.",
                "stance": "observer",
                "perspective": "anxious and comparison-driven",
            },
            {
                "name": "Mentor",
                "entity_type": "Mentor",
                "summary": f"Guides realistic milestone planning, project selection, and skills compounding for {subject}.",
                "stance": "supportive",
                "perspective": "practical and coaching-oriented",
            },
            {
                "name": "Automation Skeptic",
                "entity_type": "AIAutomationSpecialist",
                "summary": f"Believes routine junior work may compress quickly and pushes hard on which parts of {subject} are actually defensible against automation.",
                "stance": "opposing",
                "perspective": "automation pressure and role compression",
            },
            {
                "name": "Industry Analyst",
                "entity_type": "IndustryAnalyst",
                "summary": f"Observes hiring momentum, technology shifts, and broader labor-market signals affecting {subject}.",
                "stance": "neutral",
                "perspective": "evidence-first and trend-aware",
            },
            {
                "name": "Open Source Maintainer",
                "entity_type": "Maintainer",
                "summary": f"Judges practical skill through public code, contribution quality, and real collaboration patterns relevant to {subject}.",
                "stance": "observer",
                "perspective": "quality bar and execution realism",
            },
        ]

    def _general_archetypes(self, subject: str, primary_name: str) -> List[dict]:
        return [
            {
                "name": "Domain Expert",
                "entity_type": "DomainExpert",
                "summary": f"Offers expert judgment on the most credible pathways and constraints around {subject}.",
            },
            {
                "name": "Decision Maker",
                "entity_type": "DecisionMaker",
                "summary": f"Represents the stakeholder weighing outcomes, tradeoffs, and timing for {primary_name}.",
            },
            {
                "name": "Interested Peer",
                "entity_type": "InterestedPeer",
                "summary": f"Reflects how similarly affected people react, compare notes, and shape momentum around {subject}.",
            },
            {
                "name": "Skeptical Observer",
                "entity_type": "SkepticalObserver",
                "summary": f"Questions weak assumptions and exposes the fragile parts of the current case around {subject}.",
            },
            {
                "name": "Supportive Advisor",
                "entity_type": "Advisor",
                "summary": f"Pushes toward practical next steps and more resilient choices for {primary_name}.",
            },
            {
                "name": "Market Signal Tracker",
                "entity_type": "MarketAnalyst",
                "summary": f"Watches change over time and adds external pressure signals that can alter {subject}.",
            },
            {
                "name": "Community Voice",
                "entity_type": "CommunityMember",
                "summary": f"Represents the broader public response, informal advice, and social reinforcement around {subject}.",
            },
            {
                "name": "Risk Reviewer",
                "entity_type": "RiskReviewer",
                "summary": f"Surfaces downside scenarios, weak evidence, and failure modes in {subject}.",
            },
        ]
