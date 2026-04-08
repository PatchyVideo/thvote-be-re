from typing import List, Optional

from .ContentSubmit import ContentSubmit


class CPSubmit(ContentSubmit):
    """
    CP投票对象。
    Attributes:
        id: 投票对象ID（可填写至多3个，至少应有2个）
        active: 主动方（可选）
    """
    id: List[str]
    active: Optional[str]
