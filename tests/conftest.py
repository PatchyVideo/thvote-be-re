"""Shared pytest config / fixtures.

The test suite is organized by layer:
- ``tests/unit``        — pure logic, all external deps mocked
- ``tests/integration`` — real Postgres + Redis (CI provides them);
                          Aliyun is always mocked
- ``tests/contract``    — wire-format (JSON shape) checks against the FastAPI
                          app via httpx.AsyncClient
"""

from __future__ import annotations

import base64
import os
import tempfile
from pathlib import Path

# Ensure required env vars exist for Settings() before importing app modules.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./.test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-do-not-use-in-prod")
os.environ.setdefault("VOTE_START_ISO", "2020-01-01T00:00:00+00:00")
os.environ.setdefault("VOTE_END_ISO", "2099-12-31T23:59:59+00:00")

# PII 字段级加密需要一个 DEK。测试进程用一个一次性随机密钥写入临时文件，
# 让 subject_enc / register_ip_enc / created_ip_enc 的读写路径都能跑通。
# 必须在这里(导入任何 src 模块之前)设置,否则 crypto.DEK_PATH 读不到。
_test_dek = base64.b64encode(os.urandom(32)).decode()
_test_dek_path = Path(tempfile.gettempdir()) / f"thvote-test-dek-{os.getpid()}"
_test_dek_path.write_text(_test_dek, encoding="utf-8")
os.environ["PII_DEK_PATH"] = str(_test_dek_path)
