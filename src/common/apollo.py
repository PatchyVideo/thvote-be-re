from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import time
from typing import Any, Optional

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_TRUTHY_VALUES = {"1", "true", "yes", "on"}


def _generate_apollo_signature(access_key: str, timestamp_ms: int, path: str) -> str:
    """Generate HMAC-SHA1 signature for Apollo access key authentication."""
    message = f"{timestamp_ms}\n{path}"
    signature = hmac.new(
        access_key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    return base64.b64encode(signature).decode("utf-8")


def _env_flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in _TRUTHY_VALUES


def _parse_namespaces(raw_value: str | None) -> list[str]:
    value = raw_value or "application"
    return [item.strip() for item in value.split(",") if item.strip()]


def _normalize_meta_server(raw_value: str | None) -> str:
    value = (raw_value or "http://apollo-configservice:8080").strip().rstrip("/")
    if not value.startswith(("http://", "https://")):
        value = f"http://{value}"
    return value


def _extract_configurations(payload: dict[str, Any]) -> dict[str, str]:
    configurations = payload.get("configurations")
    if not isinstance(configurations, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in configurations.items()
        if value is not None
    }


def _fetch_namespace(
    client: httpx.Client,
    app_id: str,
    cluster: str,
    namespace: str,
    access_key: Optional[str] = None,
) -> dict[str, str]:
    namespace = namespace.strip()
    if not namespace:
        return {}

    candidate_paths = (
        f"/configs/{app_id}/{cluster}/{namespace}",
        f"/configfiles/json/{app_id}/{cluster}/{namespace}",
    )
    for path in candidate_paths:
        headers = {}
        if access_key:
            timestamp_ms = int(time.time() * 1000)
            signature = _generate_apollo_signature(access_key, timestamp_ms, path)
            headers["Authorization"] = f"Apollo {app_id}:{signature}"
            headers["Timestamp"] = str(timestamp_ms)
        response = client.get(path, headers=headers)
        if response.status_code == 404:
            continue
        response.raise_for_status()
        payload = response.json()
        if path.startswith("/configfiles/json/") and isinstance(payload, dict):
            return {
                str(key): str(value)
                for key, value in payload.items()
                if value is not None
            }
        if isinstance(payload, dict):
            return _extract_configurations(payload)
    return {}


def load_apollo_overrides() -> dict[str, str]:
    """Load Apollo configuration without overriding explicit environment variables."""

    load_dotenv(override=False)

    if not _env_flag("APOLLO_ENABLED", "false"):
        logger.debug("Apollo disabled (APOLLO_ENABLED != true)")
        return {}

    app_id = os.getenv("APOLLO_APP_ID", "thvote-backend").strip()
    cluster = os.getenv("APOLLO_CLUSTER", "default").strip()
    namespaces = _parse_namespaces(os.getenv("APOLLO_NAMESPACES"))
    meta_server = _normalize_meta_server(os.getenv("APOLLO_META"))
    access_key = os.getenv("APOLLO_ACCESS_KEY")
    timeout = float(os.getenv("APOLLO_TIMEOUT_SECONDS", "5"))

    logger.debug(
        "Apollo config: meta=%s, app_id=%s, cluster=%s, namespaces=%s, timeout=%s",
        meta_server, app_id, cluster, namespaces, timeout,
    )

    merged: dict[str, str] = {}
    try:
        with httpx.Client(base_url=meta_server, timeout=timeout) as client:
            for namespace in namespaces:
                logger.debug("Fetching Apollo namespace: %s", namespace)
                namespace_config = _fetch_namespace(
                    client=client,
                    app_id=app_id,
                    cluster=cluster,
                    namespace=namespace,
                    access_key=access_key,
                )
                if namespace_config:
                    logger.debug("  - %s: got %d keys", namespace, len(namespace_config))
                merged.update(namespace_config)
    except Exception as exc:
        logger.warning("Failed to load Apollo config from %s: %s", meta_server, exc)
        return {}

    for key, value in merged.items():
        os.environ.setdefault(key, value)

    logger.info("Apollo loaded %d config values", len(merged))
    return merged
