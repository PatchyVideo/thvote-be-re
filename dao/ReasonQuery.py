from .BaseQuery import BaseQuery


class ReasonQuery(BaseQuery):
    """
    通用的原因查询对象。
    Attributes:
        rank: 查询指定的名次
    """
    rank: int
