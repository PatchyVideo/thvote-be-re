#!/usr/bin/env python3
"""把前端静态表里的投票对象资源 URL 一次性迁移进 voteable 表。

背景
----
历史上角色立绘 / 曲目封面 / 试听 URL 存在前端 ``packages/shared/data/
character.ts``、``music.ts`` 里，由前端按 ``name`` 匹配挂到后端候选上。
本脚本把这份数据（已导出为 ``scripts/voteable_resources.json``）
按 ``name`` 写回 ``voteable_character`` / ``voteable_music``，之后前端
只认后端字段，静态表可删。

字段映射
--------
    character.image    -> voteable_character.image_url
    character.altnames -> voteable_character.aliases   (并集)
    music.image        -> voteable_music.image_url
    music.music        -> voteable_music.music_url
    music.include      -> voteable_music.include       (并集)

默认策略
--------
- **dry-run**：不带 ``--apply`` 只打印迁移计划，不写库。
- **只填空值**：目标列已有非空值时跳过（不覆盖运维手改）；``--overwrite``
  才覆盖。``aliases`` / ``include`` 默认做并集，``--overwrite`` 时整体替换。
- 名称必须精确匹配；有 unmatched 时退出码非 0，便于 CI/人工发现漂移。

用法::

    # 预览（默认 dry-run）
    python scripts/import_voteable_resources.py

    # 写入测试库（当前 .env 指向 test_db）
    python scripts/import_voteable_resources.py --apply --yes

    # 容器内
    docker exec thvote-backend python scripts/import_voteable_resources.py --apply --yes
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

DEFAULT_FILE = Path(__file__).resolve().parent / "voteable_resources.json"


def _merge(existing: Any, incoming: list[str]) -> list[str]:
    """保序去重并集：existing 在前，incoming 追加缺失项。"""
    out: list[str] = []
    seen: set[str] = set()
    for raw in list(existing or []) + list(incoming or []):
        text = str(raw).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


class Report:
    def __init__(self) -> None:
        self.matched = 0
        self.unmatched: list[str] = []
        self.updated: dict[str, int] = {}
        self.skipped: dict[str, int] = {}

    def bump(self, bucket: dict[str, int], field: str) -> None:
        bucket[field] = bucket.get(field, 0) + 1


async def run(
    data: dict[str, Any],
    categories: list[str],
    apply: bool,
    overwrite: bool,
) -> dict[str, Report]:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from src.common.config import get_settings
    from src.common.database import normalize_async_database_url
    from src.db_model.voteable import VoteableCharacter, VoteableMusic

    settings = get_settings()
    db_url = normalize_async_database_url(settings.database_url)
    safe_url = db_url.split("@")[-1]
    print(f"目标库: {safe_url}")
    print(f"模式: {'APPLY(写库)' if apply else 'DRY-RUN(只预览)'}"
          f"{' | overwrite=on' if overwrite else ' | 只填空值'}")

    engine = create_async_engine(db_url, echo=False)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    reports: dict[str, Report] = {}
    try:
        async with maker() as session:
            for category in categories:
                model = VoteableCharacter if category == "character" else VoteableMusic
                key = "characters" if category == "character" else "music"
                entries = data.get(key) or []
                rows = (await session.execute(select(model))).scalars().all()
                by_name = {row.name: row for row in rows}
                rep = Report()
                reports[category] = rep

                for entry in entries:
                    name = entry.get("name")
                    row = by_name.get(name) if name else None
                    if row is None:
                        rep.unmatched.append(str(name))
                        continue
                    rep.matched += 1

                    # image_url（两类别通用）
                    src_image = (entry.get("image") or "").strip()
                    if src_image:
                        if not row.image_url or overwrite:
                            row.image_url = src_image
                            rep.bump(rep.updated, "image_url")
                        else:
                            rep.bump(rep.skipped, "image_url")

                    # aliases：并集（overwrite 时整体替换）
                    src_aliases = entry.get("aliases") or []
                    if src_aliases:
                        new_aliases = (
                            [str(x).strip() for x in src_aliases if str(x).strip()]
                            if overwrite
                            else _merge(row.aliases, src_aliases)
                        )
                        if list(row.aliases or []) != new_aliases:
                            row.aliases = new_aliases
                            rep.bump(rep.updated, "aliases")
                        else:
                            rep.bump(rep.skipped, "aliases")

                    if category == "music":
                        src_music = (entry.get("music") or "").strip()
                        if src_music:
                            if not row.music_url or overwrite:
                                row.music_url = src_music
                                rep.bump(rep.updated, "music_url")
                            else:
                                rep.bump(rep.skipped, "music_url")

                        src_include = entry.get("include") or []
                        if src_include:
                            new_include = (
                                [str(x).strip() for x in src_include if str(x).strip()]
                                if overwrite
                                else _merge(row.include, src_include)
                            )
                            if list(row.include or []) != new_include:
                                row.include = new_include
                                rep.bump(rep.updated, "include")
                            else:
                                rep.bump(rep.skipped, "include")

                print(f"\n[{category}] 源 {len(entries)} 条 / 匹配 {rep.matched}"
                      f" / 未匹配 {len(rep.unmatched)}")
                print(f"  更新: {rep.updated or '{}'}")
                if rep.skipped:
                    print(f"  跳过(已有非空): {rep.skipped}")
                if rep.unmatched:
                    print(f"  未匹配名单(前10): {rep.unmatched[:10]}"
                          f"{' ...' if len(rep.unmatched) > 10 else ''}")

            if apply:
                await session.commit()
                print("\n已提交。")
            else:
                print("\nDRY-RUN 未写库（加 --apply 生效）。")
    finally:
        await engine.dispose()
    return reports


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE,
                        help=f"迁移 JSON（默认 {DEFAULT_FILE}）")
    parser.add_argument("--category", choices=["both", "character", "music"],
                        default="both")
    parser.add_argument("--apply", action="store_true", help="真正写库（默认 dry-run）")
    parser.add_argument("--overwrite", action="store_true",
                        help="覆盖已有非空值 / aliases、include 整体替换")
    parser.add_argument("--yes", action="store_true", help="写库时跳过交互确认")
    args = parser.parse_args()

    if not args.file.exists():
        print(f"找不到迁移文件: {args.file}", file=sys.stderr)
        sys.exit(2)
    data = json.loads(args.file.read_text(encoding="utf-8"))

    if args.apply and not args.yes:
        if input("确认对上面目标库写库?仅限测试环境![yes/N] ").strip().lower() != "yes":
            print("已取消")
            return

    categories = (
        ["character", "music"] if args.category == "both" else [args.category]
    )
    reports = asyncio.run(
        run(data, categories, apply=args.apply, overwrite=args.overwrite)
    )
    unmatched = sum(len(r.unmatched) for r in reports.values())
    if unmatched:
        print(f"\n⚠️ 有 {unmatched} 条名称未匹配，退出码 1", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
