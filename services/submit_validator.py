from __future__ import annotations

from fastapi import HTTPException

from dao.submit_models import (
    CPSubmitRest,
    CharacterSubmitRest,
    DojinSubmitRest,
    MusicSubmitRest,
    PaperSubmitRest,
)


def _invalid(msg: str) -> HTTPException:
    return HTTPException(status_code=400, detail=msg)


class SubmitValidatorV1:
    async def validate_character(self, data: CharacterSubmitRest) -> CharacterSubmitRest:
        chset: set[str] = set()
        first_set = False
        if len(data.characters) < 1 or len(data.characters) > 8:
            raise _invalid(f"数量{len(data.characters)}不在范围内[1,8]")
        for c in data.characters:
            if (c.reason is not None) and len(c.reason) > 4096:
                raise _invalid("理由过长")
            if bool(c.first):
                if first_set:
                    raise _invalid("多个本命")
                first_set = True
            if c.id in chset:
                raise _invalid(f"{c.id}已存在")
            chset.add(c.id)
        return data

    async def validate_music(self, data: MusicSubmitRest) -> MusicSubmitRest:
        chset: set[str] = set()
        first_set = False
        if len(data.music) < 1 or len(data.music) > 12:
            raise _invalid(f"数量{len(data.music)}不在范围内[1,12]")
        for c in data.music:
            if (c.reason is not None) and len(c.reason) > 4096:
                raise _invalid("理由过长")
            if bool(c.first):
                if first_set:
                    raise _invalid("多个本命")
                first_set = True
            if c.id in chset:
                raise _invalid(f"{c.id}已存在")
            chset.add(c.id)
        return data

    async def validate_cp(self, data: CPSubmitRest) -> CPSubmitRest:
        first_set = False
        if len(data.cps) < 1 or len(data.cps) > 4:
            raise _invalid(f"数量{len(data.cps)}不在范围内[1,4]")
        for c in data.cps:
            if (c.reason is not None) and len(c.reason) > 4096:
                raise _invalid("理由过长")
            if bool(c.first):
                if first_set:
                    raise _invalid("多个本命")
                first_set = True
            if c.active is not None and c.active not in {c.id_a, c.id_b, c.id_c}:
                raise _invalid(f"主动方{c.active}不存在")
        return data

    async def validate_paper(self, data: PaperSubmitRest) -> PaperSubmitRest:
        return data

    async def validate_dojin(self, data: DojinSubmitRest) -> DojinSubmitRest:
        for item in data.dojins:
            if len(item.author) > 4096:
                raise _invalid("作者名过长")
            if len(item.reason) > 4096:
                raise _invalid("理由过长")
            if len(item.title) > 4096:
                raise _invalid("作品名过长")
            if len(item.url) > 4096:
                raise _invalid("URL过长")
        return data

