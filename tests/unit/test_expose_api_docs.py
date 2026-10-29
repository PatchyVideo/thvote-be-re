"""P-1: ``EXPOSE_API_DOCS`` 开关控制 API 文档与 GraphQL IDE 是否暴露。

生产默认 ``false``:/docs、/redoc、/openapi.json 全部 404,GraphQL 只保留
POST(纯 API),不再返回 GraphiQL 页面。测试环境可在 Nacos 显式打开。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.common import config as config_module
from src.main import create_app


@pytest.fixture(autouse=True)
def _restore_settings():
    """每个用例结束后清掉缓存,避免把开关状态串到别的测试模块。"""
    yield
    config_module.reload_settings()


def _client(monkeypatch: pytest.MonkeyPatch, expose: str) -> TestClient:
    monkeypatch.setenv("EXPOSE_API_DOCS", expose)
    monkeypatch.setenv("NACOS_ENABLED", "false")
    config_module.reload_settings()
    return TestClient(create_app())


@pytest.mark.parametrize("expose, expected", [("false", 404), ("true", 200)])
@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_api_docs_endpoints_follow_switch(
    monkeypatch: pytest.MonkeyPatch, expose: str, expected: int, path: str
) -> None:
    client = _client(monkeypatch, expose)
    assert client.get(path).status_code == expected


def test_graphql_ide_disabled_but_post_still_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(monkeypatch, "false")

    # 浏览器直接打开 /graphql 不再给出 IDE 页面
    assert (
        client.get("/graphql", headers={"Accept": "text/html"}).status_code == 404
    )

    # 真正的 GraphQL 调用不受影响
    resp = client.post("/graphql", json={"query": "{ __typename }"})
    assert resp.status_code == 200
    assert resp.json()["data"]["__typename"] == "Query"


def test_graphql_ide_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, "true")
    resp = client.get("/graphql", headers={"Accept": "text/html"})
    assert resp.status_code == 200
    assert "graphiql" in resp.text.lower()
