from pydantic import BaseModel


class RankingGlobal(BaseModel):
    """
    总计投票数据对象。
    Attributes:
        total_unique_items: 角色/音乐数
        total_favorite: 总本命数
        total_votes: 总票数
        average_votes_per_item: 全角色平均票数
        median_votes_per_item: 全角色中位票数
    """
    total_unique_items: int
    total_favorite: int
    total_votes: int
    average_votes_per_item: float
    median_votes_per_item: float
