"""GraphQL Schema definition."""

import strawberry

from .resolvers.result import ResultQuery
from .resolvers.submit import SubmitMutation, SubmitQuery


@strawberry.type
class Query(SubmitQuery, ResultQuery):
    """Root GraphQL Query."""

    pass


@strawberry.type
class Mutation(SubmitMutation):
    """Root GraphQL Mutation."""

    pass


schema = strawberry.Schema(query=Query, mutation=Mutation)
