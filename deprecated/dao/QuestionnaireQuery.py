from typing import List

from .BaseQuery import BaseQuery


class QuestionnaireQuery(BaseQuery):
    questionnaire_of_interest: List[str]
