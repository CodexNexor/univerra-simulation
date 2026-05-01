"""
Submission clarification helper.

Uses lightweight heuristics so the backend can ask for missing scenario details
without burning extra model calls before the main pipeline starts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List


TIME_HINT_PATTERNS = [
    r"\b\d{4}\b",
    r"\b\d{1,2}[:.]\d{2}\b",
    r"\b(today|tomorrow|yesterday|tonight|this week|next week|this month|next month|near future|soon|currently|right now)\b",
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b",
    r"\b(\d+\s*(day|days|week|weeks|month|months|year|years|hour|hours))\b",
]

OUTCOME_HINT_PATTERNS = [
    r"\b(predict|forecast|simulate|what happens|what will happen|what should i do|should i|chance|outcome|risk|future)\b",
]

CURRENT_STATE_HINT_PATTERNS = [
    r"\b(i am|i'm|currently|right now|working on|learning|studying|managing|dealing with|facing)\b",
]

OTHER_PEOPLE_HINT_PATTERNS = [
    r"\b(manager|teacher|client|team|friend|family|partner|company|interviewer|recruiter|customer|doctor|lawyer|mentor|investor)\b",
]


@dataclass
class ClarificationResult:
    needs_clarification: bool
    missing_context: List[str] = field(default_factory=list)
    questions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "needs_clarification": self.needs_clarification,
            "missing_context": self.missing_context,
            "questions": self.questions,
        }


class ClarificationService:
    """Detect when a submission is too thin for a grounded simulation."""

    def assess(
        self,
        simulation_requirement: str,
        source_text: str = "",
        additional_context: str = "",
        has_uploaded_files: bool = False,
    ) -> ClarificationResult:
        combined = " ".join(
            part.strip()
            for part in [simulation_requirement or "", source_text or "", additional_context or ""]
            if part and part.strip()
        )
        normalized = re.sub(r"\s+", " ", combined).strip().lower()
        word_count = len(normalized.split())

        if not normalized:
            return ClarificationResult(
                needs_clarification=True,
                missing_context=["No scenario details were provided"],
                questions=["What situation should Univerra analyze, and what outcome do you want to explore?"],
            )

        missing_context: List[str] = []
        questions: List[str] = []
        uncertainty_score = 0

        if word_count < 18 and not has_uploaded_files:
            missing_context.append("The scenario is very short, so the intent may be underspecified")
            questions.append("What is happening right now, in one or two specific sentences?")
            uncertainty_score += 1

        if not self._matches_any(normalized, TIME_HINT_PATTERNS):
            missing_context.append("No concrete date, timeframe, or timing signal was provided")
            questions.append("What exact date, deadline, or time window should the simulation focus on?")
            uncertainty_score += 1

        if not self._matches_any(normalized, CURRENT_STATE_HINT_PATTERNS):
            missing_context.append("Your current state or baseline situation is unclear")
            questions.append("What is your current situation, level, or starting point right now?")
            uncertainty_score += 1

        if not self._matches_any(normalized, OUTCOME_HINT_PATTERNS):
            missing_context.append("The desired prediction target is not explicit")
            questions.append("What outcome do you want predicted or compared?")
            uncertainty_score += 1

        if not has_uploaded_files and not self._matches_any(normalized, OTHER_PEOPLE_HINT_PATTERNS) and word_count < 45:
            missing_context.append("Other people, groups, or stakeholders involved are not very clear")
            questions.append("Who else is involved or affected in this situation?")
            uncertainty_score += 1

        threshold = 3 if has_uploaded_files else 2
        needs_clarification = uncertainty_score >= threshold and not additional_context.strip()

        return ClarificationResult(
            needs_clarification=needs_clarification,
            missing_context=missing_context[:4],
            questions=questions[:3],
        )

    def _matches_any(self, text: str, patterns: List[str]) -> bool:
        return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)
