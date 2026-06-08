"""GraphQL Schema definition."""

from datetime import datetime

import strawberry

from .resolvers.questionnaire_v2 import PaperV2Mutation, PaperV2Query
from .resolvers.result import ResultQuery
from .resolvers.submit import SubmitMutation, SubmitQuery
from .resolvers.submit_bridge import SubmitBridgeMutation, SubmitBridgeQuery
from .resolvers.user import UserMutation
from .types import DateTimeUtc


@strawberry.type
class Query(SubmitQuery, ResultQuery, SubmitBridgeQuery, PaperV2Query):
    """Root GraphQL Query."""

    pass


@strawberry.type
class Mutation(
    SubmitBridgeMutation, SubmitMutation, UserMutation, PaperV2Mutation
):
    """Root GraphQL Mutation.

    SubmitBridgeMutation 列在首位:它与旧 SubmitMutation 共享 submit_dojin
    方法名,MRO 使新桥接实现优先生效;其余桥接方法名带 _vote 后缀,无冲突。
    """

    pass


schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    scalar_overrides={datetime: DateTimeUtc},
)
