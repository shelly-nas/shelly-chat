from app.retrieval import Hit, auto_merge, diverse, fuse, relevant


def _hit(id: str, parent: str | None, score: float, rank: float = 0.0, embedding=None) -> Hit:
    return Hit(
        id=id, parent_id=parent, content=id, metadata={}, file_path="f.md",
        file_name="f.md", source_url="", score=score, rank=rank, embedding=embedding,
    )


def test_merges_into_parent_above_threshold():
    hits = [_hit("a1", "A", 0.9, 0.03), _hit("b1", "B", 0.75, 0.025), _hit("a2", "A", 0.7, 0.02)]
    parents = {"A": _hit("A", None, 0), "B": _hit("B", None, 0)}
    result = auto_merge(hits, parents, {"A": 3, "B": 4}, threshold=0.5)

    # 2 of 3 leaves of A were found: A replaces them. 1 of 4 leaves of B is not enough.
    assert [(h.id, h.chunk_type) for h in result] == [("A", "parent"), ("b1", "child")]
    assert result[0].merged_ids == ["a1", "a2"]
    # A section ranks as its best leaf plus a bonus for the others, never below that leaf;
    # its relevance is that of its best leaf.
    assert result[0].rank == 0.03 + 0.5 * 0.02
    assert result[0].score == 0.9


def test_threshold_is_exclusive():
    hits = [_hit("a1", "A", 0.9)]
    result = auto_merge(hits, {"A": _hit("A", None, 0)}, {"A": 2}, threshold=0.5)
    assert [h.id for h in result] == ["a1"]


def test_fusion_puts_what_both_searches_found_first():
    vector = [_hit("x", None, 0.8), _hit("y", None, 0.7)]
    keyword = [_hit("z", None, 0.4), _hit("y", None, 0.7)]
    assert [h.id for h in fuse(vector, keyword)] == ["y", "x", "z"]
    # Without keywords the order is the cosine order.
    assert [h.id for h in fuse([_hit("x", None, 0.8), _hit("y", None, 0.7)])] == ["x", "y"]


def test_relevance_has_a_floor_and_a_relative_limit():
    hits = [_hit("a", None, 0.72), _hit("b", None, 0.6), _hit("c", None, 0.55), _hit("d", None, 0.4)]
    assert [h.id for h in relevant(hits, 0.5, 0)] == ["a", "b", "c"]
    assert [h.id for h in relevant(hits, 0.5, 0.15)] == ["a", "b"]
    assert relevant(hits, 0.8, 0.15) == []


def test_diversity_skips_near_duplicates():
    same, other = [1.0, 0.0], [0.0, 1.0]
    hits = [_hit("a", None, 0.9, 0.05, same), _hit("a2", None, 0.89, 0.049, same), _hit("b", None, 0.8, 0.04, other)]
    # a2 says what a says: b, a little less relevant but different, comes second.
    assert [h.id for h in diverse(hits, 2, 0.7)] == ["a", "b"]
    assert [h.id for h in diverse(hits, 2, 1.0)] == ["a", "a2"]
