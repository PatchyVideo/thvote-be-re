from .VotableBase import VotableBase


class VotableMusic(VotableBase):
    """
    可投票音乐的DAO。
    Attributes:
        origin: 出场作品
        character: 音乐所属角色
    """
    origin: str
    character: str
