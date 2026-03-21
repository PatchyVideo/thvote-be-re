from typing import List

from pydantic import BaseModel


class Reasons(BaseModel):
    reasons: List[str]
