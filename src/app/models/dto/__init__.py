"""DTO models package."""

from .auth import EmailLoginRequest, LoginResult
from .submit import (
    CPSubmitRequest,
    CharacterSubmitRequest,
    DojinSubmitRequest,
    EmptyResult,
    MusicSubmitRequest,
    PaperSubmitRequest,
    QuerySubmitRequest,
    SubmitMetadata,
    VotingStatistics,
    VotingStatus,
)

__all__ = [
    "EmailLoginRequest",
    "LoginResult",
    "SubmitMetadata",
    "CharacterSubmitRequest",
    "MusicSubmitRequest",
    "CPSubmitRequest",
    "PaperSubmitRequest",
    "DojinSubmitRequest",
    "QuerySubmitRequest",
    "VotingStatus",
    "VotingStatistics",
    "EmptyResult",
]
