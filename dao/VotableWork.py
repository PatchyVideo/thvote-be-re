from .VotableBase import VotableBase


class VotableWork(VotableBase):
    """
    可投票作品的DAO。
    Attributes:
        name: 名称
        altnames: 别名
        image: 图像URL
        release_date: 发售日期
    """
    release_date: str
