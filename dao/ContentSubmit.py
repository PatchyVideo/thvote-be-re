from pydantic import BaseModel


class ContentSubmit(BaseModel):
    """
    通用的投票提交对象。\n
    注意：由于CP有主动方，该对象不适用。请使用CPSubmit。
    Attributes:
        id: 投票对象ID
        reason: 投票原因
        favorite: 本命投票对象
    """
    id: str
    reason: str
    favorite: str
