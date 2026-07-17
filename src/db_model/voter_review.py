from __future__ import annotations

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class VoterReview(Base):
    """管理端对某账号的人工复核记录(B-049):标记状态 + 备注。

    每账号一行(user_id 作 PK,= 投票用户 id)。不破坏投票数据,纯附加复核信息。
    """

    __tablename__ = "voter_review"

    user_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="")
    note: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
