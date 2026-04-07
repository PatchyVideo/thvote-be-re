from .BaseQuery import BaseQuery


class SingleQuery(BaseQuery):
    """
    通用的单项查询对象。
    Attributes:
        rank: 查询指定的名次
    """
    rank: int
