"""Contract: structured questionnaire v2 GraphQL operations exist in SDL (B-039)."""
from src.api.graphql.schema import schema


def test_submit_paper_v2_in_sdl():
    sdl = schema.as_str()
    assert "submitPaperV2(" in sdl
    assert "getPaperV2(" in sdl


def test_paper_v2_signatures():
    sdl = schema.as_str()
    assert "submitPaperV2(voteToken: String!, answers: JSON!): Boolean!" in sdl
    assert "getPaperV2(voteToken: String!): JSON!" in sdl
