"""Public candidate matching with regenerable Redis caches."""

from hashlib import sha256

import redis.asyncio as aioredis

from src.apps.autocomplete.dao import AutocompleteDAO
from src.apps.autocomplete.pinyin import PreparedText, TextUnit, contains, prepare_text
from src.apps.autocomplete.schemas import (
    CandidateCategory,
    CandidateSearchRequest,
    CandidateSearchResponse,
)
from src.common.cache import cache_get_json, cache_set_json

CACHE_TTL = 60
CACHE_PREFIX = "autocomplete:pinyin:v1"
Corpus = list[tuple[int, tuple[PreparedText, ...]]]


class CandidateSearchService:
    def __init__(
        self, dao: AutocompleteDAO, redis: aioredis.Redis, default_year: int
    ) -> None:
        self.dao = dao
        self.redis = redis
        self.default_year = default_year

    async def _corpus(self, category: CandidateCategory, year: int) -> Corpus:
        key = f"{CACHE_PREFIX}:{year}:{category}:corpus"
        cached = await cache_get_json(self.redis, key)
        if cached is not None:
            return [
                (cid, tuple(
                    tuple(TextUnit(literal, tuple(tuple(r) for r in readings))
                          for literal, readings in text)
                    for text in texts
                ))
                for cid, texts in cached
            ]
        documents = await self.dao.load_search_documents(category, year)
        corpus = [
            (cid, tuple(prepare_text(text) for text in texts))
            for cid, texts in documents
        ]
        serialized = [
            [cid, [[[unit.literal, unit.readings] for unit in text] for text in texts]]
            for cid, texts in corpus
        ]
        await cache_set_json(self.redis, key, serialized, CACHE_TTL)
        return corpus

    async def search(self, request: CandidateSearchRequest) -> CandidateSearchResponse:
        query = request.query.strip().lower()
        year = request.vote_year if request.vote_year is not None else self.default_year
        fingerprint = sha256(query.encode("utf-8")).hexdigest()
        key = f"{CACHE_PREFIX}:{year}:{request.category}:q:{fingerprint}"
        ids = await cache_get_json(self.redis, key) if query else None
        if ids is None:
            corpus = await self._corpus(request.category, year)
            ids = sorted({
                cid for cid, texts in corpus
                if not query or any(contains(text, query) for text in texts)
            })
            if query:
                await cache_set_json(self.redis, key, ids, CACHE_TTL)
        return CandidateSearchResponse(
            category=request.category, query=query, vote_year=year, candidate_ids=ids,
        )
