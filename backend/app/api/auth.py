"""
Authentication, profile, and user simulation history API.
"""

from __future__ import annotations

from flask import jsonify, request

from . import auth_bp
from ..config import Config
from ..models.project import ProjectManager
from ..services.auth_service import create_auth_token, require_auth
from ..services.simulation_manager import SimulationManager
from ..services.simulation_runner import SimulationRunner
from ..services.user_context import build_user_goal_context, strip_user_goal_context
from ..services.user_store import DuplicateUserError, UserStore, UserStoreUnavailable
from ..utils.logger import get_logger
from ..utils.rate_limiter import check_rate_limit, get_client_ip
from .simulation import _get_report_id_for_simulation

logger = get_logger("univerra.api.auth")


def _auth_rate_identity(email: str) -> str:
    return f"{get_client_ip()}:{UserStore.normalize_email(email)}"


def _session_payload(user):
    return {
        "user": user,
        "token": create_auth_token(user),
        "token_expires_in": Config.AUTH_TOKEN_MAX_AGE_SECONDS,
        "storage": UserStore.status(),
    }


def _profile_from_payload(data):
    return {
        "goal": data.get("goal", ""),
        "goal_category": data.get("goal_category", ""),
        "personal_details": data.get("personal_details", ""),
        "experience_level": data.get("experience_level", ""),
        "target_timeline": data.get("target_timeline", ""),
        "constraints": data.get("constraints", ""),
        "preferred_language": data.get("preferred_language", ""),
    }


@auth_bp.route("/signup", methods=["POST"])
def signup():
    data = request.get_json() or {}
    email = data.get("email", "")
    blocked = check_rate_limit(
        "auth:signup",
        _auth_rate_identity(email),
        Config.RATE_LIMIT_AUTH_ATTEMPTS,
        Config.RATE_LIMIT_AUTH_WINDOW_SECONDS,
    )
    if blocked:
        return blocked

    try:
        user = UserStore.create_user(
            email=email,
            password=data.get("password", ""),
            name=data.get("name", ""),
            profile=_profile_from_payload(data),
        )
        return jsonify({"success": True, "data": _session_payload(user)})
    except DuplicateUserError as exc:
        return jsonify({"success": False, "error": str(exc)}), 409
    except (ValueError, UserStoreUnavailable) as exc:
        status = 503 if isinstance(exc, UserStoreUnavailable) else 400
        return jsonify({"success": False, "error": str(exc), "storage": UserStore.status()}), status
    except Exception as exc:
        logger.error(f"Signup failed: {exc}")
        return jsonify({"success": False, "error": "Signup failed"}), 500


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = data.get("email", "")
    blocked = check_rate_limit(
        "auth:login",
        _auth_rate_identity(email),
        Config.RATE_LIMIT_AUTH_ATTEMPTS,
        Config.RATE_LIMIT_AUTH_WINDOW_SECONDS,
    )
    if blocked:
        return blocked

    try:
        user = UserStore.authenticate(email, data.get("password", ""))
        if not user:
            return jsonify({"success": False, "error": "Invalid email or password"}), 401
        return jsonify({"success": True, "data": _session_payload(user)})
    except UserStoreUnavailable as exc:
        return jsonify({"success": False, "error": str(exc), "storage": UserStore.status()}), 503
    except Exception as exc:
        logger.error(f"Login failed: {exc}")
        return jsonify({"success": False, "error": "Login failed"}), 500


@auth_bp.route("/me", methods=["GET"])
@require_auth
def me():
    user = request.current_user
    return jsonify({
        "success": True,
        "data": {
            "user": user,
            "goal_context_available": bool(build_user_goal_context(user)),
            "storage": UserStore.status(),
        },
    })


@auth_bp.route("/profile", methods=["PATCH"])
@require_auth
def update_profile():
    data = request.get_json() or {}
    try:
        user = UserStore.update_profile(
            request.current_user["user_id"],
            name=data.get("name"),
            profile=_profile_from_payload(data),
        )
        if not user:
            return jsonify({"success": False, "error": "User not found"}), 404
        return jsonify({
            "success": True,
            "data": {
                "user": user,
                "goal_context_available": bool(build_user_goal_context(user)),
            },
        })
    except UserStoreUnavailable as exc:
        return jsonify({"success": False, "error": str(exc), "storage": UserStore.status()}), 503


def _enrich_simulation(sim):
    manager = SimulationManager()
    sim_dict = sim.to_dict()
    config = manager.get_simulation_config(sim.simulation_id) or {}

    sim_dict["simulation_requirement"] = strip_user_goal_context(config.get("simulation_requirement", ""))
    time_config = config.get("time_config", {})
    sim_dict["total_simulation_hours"] = time_config.get("total_simulation_hours", 0)
    recommended_rounds = int(
        time_config.get("total_simulation_hours", 0) * 60 /
        max(time_config.get("minutes_per_round", 60), 1)
    ) if time_config else 0

    run_state = SimulationRunner.get_run_state(sim.simulation_id)
    if run_state:
        sim_dict["current_round"] = run_state.current_round
        sim_dict["runner_status"] = run_state.runner_status.value
        sim_dict["total_rounds"] = run_state.total_rounds if run_state.total_rounds > 0 else recommended_rounds
    else:
        sim_dict["current_round"] = 0
        sim_dict["runner_status"] = "idle"
        sim_dict["total_rounds"] = recommended_rounds

    project = ProjectManager.get_project(sim.project_id)
    sim_dict["project_name"] = project.name if project else "Unknown Project"
    sim_dict["files"] = [
        {"filename": f.get("filename", "Unknown file")}
        for f in (project.files[:3] if project and project.files else [])
    ]
    sim_dict["report_id"] = _get_report_id_for_simulation(sim.simulation_id)
    return sim_dict


@auth_bp.route("/simulations", methods=["GET"])
@require_auth
def my_simulations():
    limit = request.args.get("limit", 50, type=int)
    user_id = request.current_user["user_id"]
    manager = SimulationManager()
    simulations = manager.list_simulations(user_id=user_id)[: max(1, min(limit, 100))]
    enriched = [_enrich_simulation(sim) for sim in simulations]

    try:
        mongo_records = UserStore.list_user_simulations(user_id, limit=limit)
    except UserStoreUnavailable:
        mongo_records = []

    return jsonify({
        "success": True,
        "data": enriched,
        "mongo_records": mongo_records,
        "count": len(enriched),
    })


@auth_bp.route("/logout", methods=["POST"])
@require_auth
def logout():
    return jsonify({"success": True, "message": "Logged out"})
