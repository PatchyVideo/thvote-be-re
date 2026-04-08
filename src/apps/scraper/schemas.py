"""Scraper schemas for request/response validation."""

from typing import Optional

from pydantic import BaseModel


class ReqBody(BaseModel):
    """Request body for scraper."""

    url: str


class BaseResp(BaseModel):
    """Base response model."""

    status: str = "ok"
    msg: str = ""


class ScrapeData(BaseModel):
    """Scraped data model."""

    title: Optional[str] = None
    udid: Optional[str] = None
    cover: Optional[str] = None
    media: Optional[list[str]] = None
    desc: Optional[str] = None
    ptime: Optional[str] = None
    author: Optional[list[str]] = None
    author_name: Optional[list[str]] = None
    tname: Optional[str] = None
    repost: Optional[bool] = None


class RespBody(BaseResp):
    """Response body for scraper."""

    data: Optional[ScrapeData] = None
