"""GraphQL Schema definition."""

import strawberry

from api.graphql.resolvers.submit import SubmitMutation, SubmitQuery


@strawberry.type
class Query(SubmitQuery):
    """Root GraphQL Query."""
    pass


@strawberry.type
class Mutation(SubmitMutation):
    """Root GraphQL Mutation."""
    pass


schema = strawberry.Schema(query=Query, mutation=Mutation)
