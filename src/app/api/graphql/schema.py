"""GraphQL Schema definition."""

import strawberry

from .resolvers.submit import SubmitMutation, SubmitQuery


@strawberry.type
class Query(SubmitQuery):
    """Root GraphQL Query."""


@strawberry.type
class Mutation(SubmitMutation):
    """Root GraphQL Mutation."""


schema = strawberry.Schema(query=Query, mutation=Mutation)
