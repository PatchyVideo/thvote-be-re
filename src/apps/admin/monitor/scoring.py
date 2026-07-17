"""固定加权可疑分(B-049)。权重集中此处便于迭代;纯函数,不碰 DB。

只排序供人工复核,不自动处置(延续"取证不拦截")。阈值/权重是初版,
按投票期实际数据调这里的常量即可,不改调用方。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# 命中即加分。数值越大越可疑。调参只动这张表。
SCORING_WEIGHTS: dict[str, int] = {
    "fast_fill": 3,          # 首投填写耗时过短(瞎点)
    "no_client_env": 3,      # 无 client_env(纯 API 机器人)
    "scripted_ua": 3,        # ua 含 headless / 脚本特征
    "instant_vote": 2,       # 注册→首投过快
    "ip_cluster": 2,         # 所在 IP 组规模达阈值
    "device_cluster": 2,     # 所在设备组规模达阈值
    "duplicate_payload": 3,  # 与他人 payload 完全雷同(初版未启用,见 dao)
}

FAST_FILL_MS = 2000
INSTANT_VOTE_SECONDS = 5
CLUSTER_MIN_SIZE = 5


@dataclass
class AccountFeatures:
    """单账号聚合信号(由 MonitorDAO.account_features 装配)。"""

    min_fill_duration_ms: int | None
    has_client_env: bool
    ua_is_scripted: bool
    seconds_register_to_first_vote: float | None
    max_ip_group_size: int
    max_device_group_size: int
    has_duplicate_payload: bool


@dataclass
class ScoreResult:
    score: int = 0
    reasons: list[str] = field(default_factory=list)


def score_account(f: AccountFeatures) -> ScoreResult:
    result = ScoreResult()

    def hit(key: str, reason: str) -> None:
        result.score += SCORING_WEIGHTS[key]
        result.reasons.append(reason)

    if f.min_fill_duration_ms is not None and f.min_fill_duration_ms < FAST_FILL_MS:
        hit("fast_fill", f"首投耗时 {f.min_fill_duration_ms}ms < {FAST_FILL_MS}ms")
    if not f.has_client_env:
        hit("no_client_env", "缺 client_env / ua")
    if f.ua_is_scripted:
        hit("scripted_ua", "ua 含 headless/脚本特征")
    if (
        f.seconds_register_to_first_vote is not None
        and f.seconds_register_to_first_vote < INSTANT_VOTE_SECONDS
    ):
        hit("instant_vote", f"注册→首投 {f.seconds_register_to_first_vote:.0f}s")
    if f.max_ip_group_size >= CLUSTER_MIN_SIZE:
        hit("ip_cluster", f"IP 组规模 {f.max_ip_group_size}")
    if f.max_device_group_size >= CLUSTER_MIN_SIZE:
        hit("device_cluster", f"设备组规模 {f.max_device_group_size}")
    if f.has_duplicate_payload:
        hit("duplicate_payload", "payload 与他人完全雷同")

    return result
