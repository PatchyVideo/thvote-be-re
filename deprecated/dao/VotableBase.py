from typing import List

from pydantic import BaseModel


class VotableBase(BaseModel):
    """
    可投票对象的通用DAO。
    Attributes:
        name: 名称
        altnames: 别名
        image: 图像链接
    """
    name: str
    altnames: List[str]
    image: str
