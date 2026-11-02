from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.conversation.models import ConversationRecord, QueryFeedbackRecord, UserPreferenceRecord, UserRecord
from app.core.errors import AppError, ConflictError, NotFoundError


class AuthenticationError(AppError):
    def __init__(self, message: str = "请先登录") -> None:
        super().__init__("UNAUTHENTICATED", message, 401, False)


class AuthorizationError(AppError):
    def __init__(self, message: str = "没有权限执行此操作") -> None:
        super().__init__("FORBIDDEN", message, 403, False)


@dataclass(frozen=True)
class Actor:
    tenant_id: str
    user_id: str
    username: str
    display_name: str
    role: str
    must_change_password: bool = False


def hash_password(password: str, salt: bytes | None = None) -> str:
    if len(password) < 8:
        raise ValueError("密码至少需要8个字符")
    salt = salt or os.urandom(16)
    rounds = 310_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return f"pbkdf2_sha256${rounds}${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), base64.urlsafe_b64decode(salt), int(rounds)
        )
        return hmac.compare_digest(actual, base64.urlsafe_b64decode(expected))
    except (ValueError, TypeError):
        return False


class AuthService:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], secret_key: str, token_ttl_seconds: int = 28_800) -> None:
        self.sessions = sessions
        self.secret_key = (secret_key or "sqlpilot-development-secret-change-me").encode("utf-8")
        self.token_ttl_seconds = token_ttl_seconds

    async def bootstrap_admin(self, username: str, password: str, tenant_id: str = "default") -> None:
        async with self.sessions.begin() as session:
            admin = (await session.execute(select(UserRecord).where(
                UserRecord.tenant_id == tenant_id, UserRecord.username == username.strip().lower()
            ))).scalar_one_or_none()
            if not admin:
                any_user = (await session.execute(select(UserRecord.id).limit(1))).scalar_one_or_none()
                if any_user:
                    return
                admin = UserRecord(
                    tenant_id=tenant_id, username=username.strip().lower(), display_name="系统管理员",
                    password_hash=hash_password(password), role="admin", must_change_password=1,
                )
                session.add(admin)
                await session.flush()
            # One-time compatibility migration: attach prototype records to the first real administrator.
            await session.execute(update(ConversationRecord).where(
                ConversationRecord.tenant_id == tenant_id, ConversationRecord.user_id == "local-user"
            ).values(user_id=admin.id))
            await session.execute(update(UserPreferenceRecord).where(
                UserPreferenceRecord.tenant_id == tenant_id, UserPreferenceRecord.user_id == "local-user"
            ).values(user_id=admin.id))
            await session.execute(update(QueryFeedbackRecord).where(
                QueryFeedbackRecord.tenant_id == tenant_id, QueryFeedbackRecord.user_id == "local-user"
            ).values(user_id=admin.id))

    async def login(self, username: str, password: str, tenant_id: str = "default") -> tuple[str, Actor]:
        async with self.sessions.begin() as session:
            user = (await session.execute(select(UserRecord).where(
                UserRecord.tenant_id == tenant_id,
                UserRecord.username == username.strip().lower(),
            ))).scalar_one_or_none()
            if not user or user.status != "active" or not verify_password(password, user.password_hash):
                raise AuthenticationError("用户名或密码错误")
            user.last_login_at = datetime.now(timezone.utc)
            actor = self._actor(user)
            return self._encode(user), actor

    async def authenticate(self, token: str) -> Actor:
        payload = self._decode(token)
        async with self.sessions() as session:
            user = await session.get(UserRecord, payload.get("sub"))
            if not user or user.status != "active" or user.token_version != payload.get("ver"):
                raise AuthenticationError("登录状态已失效，请重新登录")
            return self._actor(user)

    async def list_users(self, actor: Actor) -> list[dict]:
        self.require_admin(actor)
        async with self.sessions() as session:
            rows = (await session.execute(select(UserRecord).where(
                UserRecord.tenant_id == actor.tenant_id
            ).order_by(UserRecord.created_at))).scalars()
            return [self._public(row) for row in rows]

    async def create_user(self, actor: Actor, data: dict) -> dict:
        self.require_admin(actor)
        username = data["username"].strip().lower()
        async with self.sessions.begin() as session:
            exists = (await session.execute(select(UserRecord.id).where(
                UserRecord.tenant_id == actor.tenant_id, UserRecord.username == username
            ))).scalar_one_or_none()
            if exists:
                raise ConflictError("用户名已存在")
            user = UserRecord(
                tenant_id=actor.tenant_id, username=username, display_name=data["display_name"].strip(),
                password_hash=hash_password(data["password"]), role=data["role"], must_change_password=1,
            )
            session.add(user)
        return self._public(user)

    async def update_user(self, actor: Actor, user_id: str, data: dict) -> dict:
        self.require_admin(actor)
        async with self.sessions.begin() as session:
            user = await session.get(UserRecord, user_id)
            if not user or user.tenant_id != actor.tenant_id:
                raise NotFoundError("用户")
            if user.id == actor.user_id and data.get("status") == "disabled":
                raise ConflictError("不能停用当前登录用户")
            if data.get("display_name") is not None:
                user.display_name = data["display_name"].strip()
            if data.get("role") is not None:
                user.role = data["role"]
            if data.get("status") is not None:
                user.status = data["status"]
                user.token_version += 1
            if data.get("password"):
                user.password_hash = hash_password(data["password"])
                user.must_change_password = 1
                user.token_version += 1
        return self._public(user)

    async def change_password(self, actor: Actor, current_password: str, new_password: str) -> None:
        async with self.sessions.begin() as session:
            user = await session.get(UserRecord, actor.user_id)
            if not user or not verify_password(current_password, user.password_hash):
                raise AuthenticationError("当前密码不正确")
            user.password_hash = hash_password(new_password)
            user.must_change_password = 0
            user.token_version += 1

    @staticmethod
    def require_admin(actor: Actor) -> None:
        if actor.role != "admin":
            raise AuthorizationError()

    def _encode(self, user: UserRecord) -> str:
        payload = {"sub": user.id, "tenant": user.tenant_id, "ver": user.token_version,
                   "iat": int(time.time()), "exp": int(time.time()) + self.token_ttl_seconds,
                   "nonce": secrets.token_hex(4)}
        body = self._b64(json.dumps(payload, separators=(",", ":")).encode())
        signature = self._b64(hmac.new(self.secret_key, body.encode(), hashlib.sha256).digest())
        return f"{body}.{signature}"

    def _decode(self, token: str) -> dict:
        try:
            body, signature = token.split(".", 1)
            expected = self._b64(hmac.new(self.secret_key, body.encode(), hashlib.sha256).digest())
            if not hmac.compare_digest(signature, expected):
                raise ValueError
            payload = json.loads(self._unb64(body))
            if int(payload["exp"]) < int(time.time()):
                raise ValueError
            return payload
        except (ValueError, KeyError, json.JSONDecodeError):
            raise AuthenticationError("登录状态无效或已过期，请重新登录")

    @staticmethod
    def _b64(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode()

    @staticmethod
    def _unb64(value: str) -> bytes:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

    @staticmethod
    def _actor(user: UserRecord) -> Actor:
        return Actor(user.tenant_id, user.id, user.username, user.display_name, user.role, bool(user.must_change_password))

    @staticmethod
    def _public(user: UserRecord) -> dict:
        return {"id": user.id, "username": user.username, "display_name": user.display_name,
                "role": user.role, "status": user.status, "must_change_password": bool(user.must_change_password),
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
                "created_at": user.created_at.isoformat()}


async def actor_from_request(request: Request) -> Actor:
    if not request.app.state.settings.auth_required:
        return Actor("default", "local-user", "local-user", "本地用户", "admin")
    authorization = request.headers.get("Authorization", "")
    token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else request.cookies.get("sqlpilot_session", "")
    if not token:
        raise AuthenticationError()
    return await request.app.state.auth_service.authenticate(token)
