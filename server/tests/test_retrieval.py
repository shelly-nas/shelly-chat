from app.retrieval import Hit, auto_merge


def _hit(id: str, parent: str | None, score: float) -> Hit:
    return Hit(
        id=id, parent_id=parent, content=id, metadata={}, file_path="f.md",
        file_name="f.md", source_url="", score=score,
    )


def test_merges_into_parent_above_threshold():
    hits = [_hit("a1", "A", 0.9), _hit("a2", "A", 0.7), _hit("b1", "B", 0.75)]
    parents = {"A": _hit("A", None, 0), "B": _hit("B", None, 0)}
    result = auto_merge(hits, parents, {"A": 3, "B": 4}, threshold=0.5)

    # 2 of 3 leaves of A were found: A replaces them, scored as their average.
    # 1 of 4 leaves of B is not enough: b1 stays.
    assert [(h.id, h.chunk_type) for h in result] == [("A", "parent"), ("b1", "child")]
    assert result[0].score == 0.8
    assert result[0].merged_ids == ["a1", "a2"]


def test_threshold_is_exclusive():
    hits = [_hit("a1", "A", 0.9)]
    result = auto_merge(hits, {"A": _hit("A", None, 0)}, {"A": 2}, threshold=0.5)
    assert [h.id for h in result] == ["a1"]
