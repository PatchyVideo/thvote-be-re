from typing import List

from .VotableBase import VotableBase


class VotableCharacter(VotableBase):
    """
    可投票角色的DAO。
    Attributes:
        title: 标题
        color: 角色配色
        origin: 出场作品
    """
    title: str
    color: str
    origin: List[str]
