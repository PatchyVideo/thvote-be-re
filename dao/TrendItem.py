from pydantic import BaseModel


class TrendItem(BaseModel):
    """
    通用的趋势数据容器。
    Attributes:
        hrs: 小时计数
        cnt: 票数计数
    """
    hrs: int
    cnt: int
