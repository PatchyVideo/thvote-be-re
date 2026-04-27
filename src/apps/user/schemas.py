"""User module Pydantic request/response schemas.

Aligned with thvote-be (Rust user-manager) wire format:
- ``Meta`` is embedded in every mutation request body.
- ``additional_fingureprint`` retains the Rust-side typo intentionally
  to preserve frontend compatibility.
- ``user_token`` is carried in the request body (not the Authorization
  header) for endpoints that mutate state — matches Rust convention.
- ``LoginResponse`` wraps the user as a ``VoterFE`` plus session/vote
  tokens.  ``vote_token`` is an empty string outside the vote window
  or when the account has no verified contact.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ── shared building blocks ───────────────────────────────────────────


class Meta(BaseModel):
    """Per-request fingerprint metadata, mirroring Rust ``Meta``."""

    user_ip: str = ""
    additional_fingureprint: Optional[str] = None  # Rust spelling preserved


class VoterFE(BaseModel):
    """Frontend-facing user representation, byte-for-byte aligned with Rust."""

    username: Optional[str] = None
    pfp: Optional[str] = None
    password: bool
    phone: Optional[str] = None
    email: Optional[str] = None
    thbwiki: bool = False
    patchyvideo: bool = False
    created_at: datetime


class EmptyResponse(BaseModel):
    """`{}` placeholder for endpoints that succeed without a body."""

    model_config = ConfigDict(extra="forbid")


# ── request schemas ──────────────────────────────────────────────────


class LoginEmailPasswordRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)
    meta: Meta = Field(default_factory=Meta)


class LoginEmailRequest(BaseModel):
    email: EmailStr
    nickname: Optional[str] = Field(None, max_length=64)
    verify_code: str = Field(..., min_length=4, max_length=8)
    meta: Meta = Field(default_factory=Meta)


class LoginPhoneRequest(BaseModel):
    phone: str = Field(..., min_length=1, max_length=32)
    nickname: Optional[str] = Field(None, max_length=64)
    verify_code: str = Field(..., min_length=4, max_length=8)
    meta: Meta = Field(default_factory=Meta)


class SendEmailCodeRequest(BaseModel):
    email: EmailStr
    meta: Meta = Field(default_factory=Meta)


class SendSmsCodeRequest(BaseModel):
    phone: str = Field(..., min_length=1, max_length=32)
    meta: Meta = Field(default_factory=Meta)


class UpdateEmailRequest(BaseModel):
    user_token: str
    email: EmailStr
    verify_code: str = Field(..., min_length=4, max_length=8)
    meta: Meta = Field(default_factory=Meta)


class UpdatePhoneRequest(BaseModel):
    user_token: str
    phone: str = Field(..., min_length=1, max_length=32)
    verify_code: str = Field(..., min_length=4, max_length=8)
    meta: Meta = Field(default_factory=Meta)


class UpdateNicknameRequest(BaseModel):
    user_token: str
    nickname: str = Field(..., min_length=1, max_length=64)
    meta: Meta = Field(default_factory=Meta)


class UpdatePasswordRequest(BaseModel):
    user_token: str
    old_password: Optional[str] = None
    new_password: str = Field(..., min_length=6)
    meta: Meta = Field(default_factory=Meta)


class TokenStatusRequest(BaseModel):
    user_token: str


class RemoveVoterRequest(BaseModel):
    user_token: str
    old_password: Optional[str] = None
    meta: Meta = Field(default_factory=Meta)


# ── response schemas ─────────────────────────────────────────────────


class LoginResponse(BaseModel):
    """Standard login envelope returned by all login-* endpoints."""

    user: VoterFE
    session_token: str
    vote_token: str  # empty string outside vote window / unverified


# ── helpers ──────────────────────────────────────────────────────────


def generate_user_id() -> str:
    """Return a fresh UUID4 string for use as a user primary key."""
    return str(uuid.uuid4())


def voter_fe_from_user(user) -> VoterFE:
    """Build a VoterFE from a User ORM row (kept here so the wire shape
    has a single owner)."""
    return VoterFE(
        username=user.nickname,
        pfp=user.pfp,
        password=bool(user.password_hash),
        phone=user.phone_number,
        email=user.email,
        thbwiki=False,
        patchyvideo=False,
        created_at=user.register_date,
    )
