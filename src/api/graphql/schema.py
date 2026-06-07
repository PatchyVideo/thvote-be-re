"""GraphQL Schema definition."""

import strawberry

from .resolvers.result import ResultQuery
from .resolvers.submit import SubmitMutation, SubmitQuery
from .resolvers.submit_bridge import SubmitBridgeMutation, SubmitBridgeQuery
from .resolvers.user import UserMutation


@strawberry.type
class Query(SubmitQuery, ResultQuery, SubmitBridgeQuery):
    """Root GraphQL Query."""

    pass


@strawberry.type
class Mutation(SubmitBridgeMutation, SubmitMutation, UserMutation):
    """Root GraphQL Mutation.

    SubmitBridgeMutation 列在首位:它与旧 SubmitMutation 共享 submit_dojin
    方法名,MRO 使新桥接实现优先生效;其余桥接方法名带 _vote 后缀,无冲突。
    """

    pass


schema = strawberry.Schema(query=Query, mutation=Mutation)
