"""
Helpers for applying a user's saved goal/profile to simulation prompts.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


PROFILE_FIELDS = {
    "goal": "Goal",
    "goal_category": "Goal type",
    "experience_level": "Current level",
    "target_timeline": "Target timeline",
    "personal_details": "Personal details",
    "constraints": "Constraints",
    "preferred_language": "Preferred language",
}


def clean_text(value: Any, max_length: int = 1200) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    return text[:max_length]


def build_user_goal_context(user: Optional[Dict[str, Any]]) -> str:
    """Return a compact private context block for LLM simulation calls."""
    if not user:
        return ""

    profile = user.get("profile") or {}
    lines = []

    name = clean_text(user.get("name"), 160)
    if name:
        lines.append(f"User name: {name}")

    for field, label in PROFILE_FIELDS.items():
        value = clean_text(profile.get(field), 1200)
        if value:
            lines.append(f"{label}: {value}")

    if not lines:
        return ""

    return (
        "## Private User Goal Context\n"
        + "\n".join(f"- {line}" for line in lines)
        + "\nUse this context only when it is relevant to the scenario. "
        "For career, exam, skill-building, decision, study, or roadmap simulations, "
        "adapt agent assumptions, constraints, milestones, risk factors, and recommendations "
        "to this user's goal. Include a practical achievement roadmap in the final report when applicable."
    )


def apply_user_goal_context(text: str, user: Optional[Dict[str, Any]]) -> str:
    context = build_user_goal_context(user)
    base = clean_text(text, 20000)
    if not context:
        return base
    return f"{base}\n\n{context}".strip()


def strip_user_goal_context(text: str) -> str:
    marker = "## Private User Goal Context"
    value = str(text or "")
    if marker not in value:
        return value
    return value.split(marker, 1)[0].strip()
