"""
retriever_impl 단위 회귀 테스트.
"""

class ImmutablePineconeMatch(dict):
    """Pinecone SDK match처럼 알 수 없는 key assignment를 거부하는 테스트 더블."""

    def __setitem__(self, key, value):
        raise KeyError(key)


def test_tag_ruling_match_does_not_mutate_pinecone_match():
    from src.retrieval.retriever_impl import _tag_ruling_match

    match = ImmutablePineconeMatch(
        {
            "id": "ruling-1",
            "score": 0.7,
            "metadata": {
                "full_text": "질의회신 본문",
                "source_label": "국세청 질의회신",
            },
        }
    )

    tagged = _tag_ruling_match(match, "tax-ruling-nts")

    assert tagged["_ruling_namespace"] == "tax-ruling-nts"
    assert tagged["id"] == "ruling-1"
    assert tagged["metadata"]["full_text"] == "질의회신 본문"
    assert "_ruling_namespace" not in match


def test_tag_ruling_match_copies_metadata():
    from src.retrieval.retriever_impl import _tag_ruling_match

    metadata = {"full_text": "원문"}
    tagged = _tag_ruling_match({"id": "ruling-2", "metadata": metadata}, "tax-ruling-moef")

    tagged["metadata"]["full_text"] = "수정"

    assert metadata["full_text"] == "원문"
