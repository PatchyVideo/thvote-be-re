"""Scraper schemas for request/response validation."""

from pydantic import BaseModel


class ReqBody(BaseModel):
    url: str


class BaseResp(BaseModel):
    status: str = "ok"
    msg: str = ""


class ScrapeData(BaseModel):
    title: str | None = None
    udid: str | None = None
    cover: str | None = None
    media: list[str] | None = None
    desc: str | None = None
    ptime: str | None = None
    author: list[str] | None = None
    author_name: list[str] | None = None
    tname: str | None = None
    repost: bool | None = None


class RespBody(BaseResp):
    data: ScrapeData | None = None
