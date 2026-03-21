from typing import List

from .BaseQuery import BaseQuery


class QuestionnaireTrendQuery(BaseQuery):
    questionIds: List[str]
