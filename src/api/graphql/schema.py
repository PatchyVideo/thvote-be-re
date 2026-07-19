"""GraphQL Schema definition."""

from datetime import datetime

import strawberry

from .resolvers.questionnaire_v2 import PaperV2Mutation, PaperV2Query
from .resolvers.result import ResultQuery
from .resolvers.result_compat import ResultCompatQuery
from .resolvers.submit_bridge import SubmitBridgeMutation, SubmitBridgeQuery
from .resolvers.user import UserMutation
from .types import DateTimeUtc


@strawberry.type
class Query(ResultQuery, ResultCompatQuery, SubmitBridgeQuery, PaperV2Query):
    """Root GraphQL Query."""

    pass


@strawberry.type
class Mutation(SubmitBridgeMutation, UserMutation, PaperV2Mutation):
    """Root GraphQL Mutation."""

    pass


schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    scalar_overrides={datetime: DateTimeUtc},
)
