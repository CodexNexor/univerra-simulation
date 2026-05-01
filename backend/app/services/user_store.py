"""
MongoDB-backed users, profiles, and simulation history.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from werkzeug.security import check_password_hash, generate_password_hash

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("univerra.user_store")


class UserStoreUnavailable(RuntimeError):
    """Raised when MongoDB is not configured or cannot be reached."""


class DuplicateUserError(ValueError):
    """Raised when an email address already exists."""


class UserStore:
    _client = None
    _db = None
    _indexes_ready = False
    _connection_error: Optional[str] = None

    @classmethod
    def enabled(cls) -> bool:
        return bool(Config.MONGODB_URI)

    @classmethod
    def status(cls) -> Dict[str, Any]:
        return {
            "enabled": cls.enabled(),
            "connected": cls._db is not None,
            "database": Config.MONGODB_DB_NAME if cls.enabled() else None,
            "error": cls._connection_error,
        }

    @classmethod
    def _get_db(cls):
        if cls._db is not None:
            return cls._db

        if not Config.MONGODB_URI:
            raise UserStoreUnavailable("MONGODB_URI is not configured")

        try:
            from pymongo import ASCENDING, MongoClient
        except ImportError as exc:
            cls._connection_error = "pymongo is not installed"
            raise UserStoreUnavailable("pymongo is not installed. Install backend requirements first.") from exc

        try:
            cls._client = MongoClient(
                Config.MONGODB_URI,
                serverSelectionTimeoutMS=Config.MONGODB_TIMEOUT_MS,
                connectTimeoutMS=Config.MONGODB_TIMEOUT_MS,
                socketTimeoutMS=Config.MONGODB_TIMEOUT_MS,
            )
            cls._client.admin.command("ping")
            cls._db = cls._client[Config.MONGODB_DB_NAME]

            if not cls._indexes_ready:
                cls._db.users.create_index([("email", ASCENDING)], unique=True)
                cls._db.simulations.create_index([("user_id", ASCENDING), ("updated_at", ASCENDING)])
                cls._db.simulations.create_index([("simulation_id", ASCENDING)], unique=True)
                cls._db.projects.create_index([("user_id", ASCENDING), ("updated_at", ASCENDING)])
                cls._db.projects.create_index([("project_id", ASCENDING)], unique=True)
                cls._indexes_ready = True

            cls._connection_error = None
            return cls._db
        except Exception as exc:
            cls._connection_error = str(exc)
            logger.warning(f"MongoDB connection failed: {exc}")
            raise UserStoreUnavailable(f"MongoDB is unavailable: {exc}") from exc

    @staticmethod
    def _now() -> str:
        return datetime.utcnow().isoformat() + "Z"

    @staticmethod
    def normalize_email(email: str) -> str:
        return (email or "").strip().lower()

    @staticmethod
    def _object_id(user_id: str):
        from bson import ObjectId
        return ObjectId(user_id)

    @classmethod
    def _serialize_user(cls, user: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not user:
            return None
        data = dict(user)
        data["user_id"] = str(data.pop("_id"))
        data.pop("password_hash", None)
        data.setdefault("profile", {})
        return data

    @classmethod
    def _serialize_record(cls, record: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(record)
        if "_id" in data:
            data["id"] = str(data.pop("_id"))
        return data

    @classmethod
    def create_user(
        cls,
        email: str,
        password: str,
        name: str = "",
        profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        db = cls._get_db()
        email = cls.normalize_email(email)
        if not email or "@" not in email:
            raise ValueError("Please enter a valid email address")
        if len(password or "") < 8:
            raise ValueError("Password must be at least 8 characters")

        now = cls._now()
        user_doc = {
            "email": email,
            "name": (name or "").strip()[:160],
            "password_hash": generate_password_hash(password),
            "profile": cls.sanitize_profile(profile or {}),
            "created_at": now,
            "updated_at": now,
            "last_login_at": None,
        }

        try:
            result = db.users.insert_one(user_doc)
        except Exception as exc:
            if exc.__class__.__name__ == "DuplicateKeyError":
                raise DuplicateUserError("An account with this email already exists") from exc
            raise

        user_doc["_id"] = result.inserted_id
        return cls._serialize_user(user_doc)

    @classmethod
    def authenticate(cls, email: str, password: str) -> Optional[Dict[str, Any]]:
        db = cls._get_db()
        user = db.users.find_one({"email": cls.normalize_email(email)})
        if not user or not check_password_hash(user.get("password_hash", ""), password or ""):
            return None

        now = cls._now()
        db.users.update_one(
            {"_id": user["_id"]},
            {"$set": {"last_login_at": now, "updated_at": now}},
        )
        user["last_login_at"] = now
        user["updated_at"] = now
        return cls._serialize_user(user)

    @classmethod
    def get_user(cls, user_id: str) -> Optional[Dict[str, Any]]:
        db = cls._get_db()
        try:
            user = db.users.find_one({"_id": cls._object_id(user_id)})
        except Exception:
            return None
        return cls._serialize_user(user)

    @staticmethod
    def sanitize_profile(profile: Dict[str, Any]) -> Dict[str, str]:
        allowed_lengths = {
            "goal": 1200,
            "goal_category": 80,
            "personal_details": 2000,
            "experience_level": 120,
            "target_timeline": 160,
            "constraints": 1200,
            "preferred_language": 80,
        }
        clean = {}
        for key, max_length in allowed_lengths.items():
            value = profile.get(key, "")
            clean[key] = str(value or "").strip()[:max_length]
        return clean

    @classmethod
    def update_profile(
        cls,
        user_id: str,
        *,
        name: Optional[str] = None,
        profile: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        db = cls._get_db()
        updates: Dict[str, Any] = {"updated_at": cls._now()}
        if name is not None:
            updates["name"] = str(name or "").strip()[:160]
        if profile is not None:
            updates["profile"] = cls.sanitize_profile(profile)

        try:
            db.users.update_one({"_id": cls._object_id(user_id)}, {"$set": updates})
        except Exception:
            return None
        return cls.get_user(user_id)

    @classmethod
    def save_project(cls, user_id: Optional[str], project_id: str, metadata: Dict[str, Any]) -> None:
        if not user_id or not cls.enabled():
            return
        db = cls._get_db()
        now = cls._now()
        doc = {
            "user_id": user_id,
            "project_id": project_id,
            "updated_at": now,
            **metadata,
        }
        db.projects.update_one(
            {"project_id": project_id},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )

    @classmethod
    def save_simulation(cls, user_id: Optional[str], simulation_id: str, metadata: Dict[str, Any]) -> None:
        if not user_id or not cls.enabled():
            return
        db = cls._get_db()
        now = cls._now()
        doc = {
            "user_id": user_id,
            "simulation_id": simulation_id,
            "updated_at": now,
            **metadata,
        }
        db.simulations.update_one(
            {"simulation_id": simulation_id},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )

    @classmethod
    def list_user_simulations(cls, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        db = cls._get_db()
        cursor = (
            db.simulations.find({"user_id": user_id})
            .sort("updated_at", -1)
            .limit(max(1, min(limit, 100)))
        )
        return [cls._serialize_record(record) for record in cursor]
