"""General purpose validators."""

import re
from typing import Optional


def validate_email(email: str) -> bool:
    """Validate email format."""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def validate_username(username: str) -> tuple[bool, Optional[str]]:
    """Validate username format.

    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(username) < 3:
        return False, "Username must be at least 3 characters"
    if len(username) > 32:
        return False, "Username must be at most 32 characters"
    if not re.match(r"^[a-zA-Z0-9_-]+$", username):
        return False, "Username can only contain letters, numbers, underscores, and hyphens"
    return True, None


def validate_url(url: str) -> bool:
    """Validate URL format."""
    pattern = r"^https?://"
    return bool(re.match(pattern, url))


def sanitize_string(value: str, max_length: int = 255) -> str:
    """Sanitize and truncate a string value."""
    return value.strip()[:max_length]
