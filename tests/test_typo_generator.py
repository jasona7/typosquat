from find_domains.typos.generator import (
    TypoCandidate,
    generate_typos,
    _omissions,
    _doublings,
    _transpositions,
    _adjacent_keys,
    _homoglyph_subs,
)


class TestOmissions:
    def test_basic(self):
        results = _omissions("google")
        typos = [t for t, _ in results]
        assert "oogle" in typos  # drop 'g'
        assert "gogle" in typos  # drop 'o'
        assert "googl" in typos  # drop 'e'

    def test_all_are_omissions(self):
        for _, typo_type in _omissions("test"):
            assert typo_type == "omission"

    def test_length(self):
        results = _omissions("hello")
        # Each char can be dropped, all produce unique results minus degenerate cases
        assert len(results) == 5


class TestDoublings:
    def test_basic(self):
        results = _doublings("test")
        typos = [t for t, _ in results]
        assert "ttest" in typos
        assert "teest" in typos
        assert "tesst" in typos
        assert "testt" in typos

    def test_already_doubled(self):
        # "tt" -> doubling 't' at position 0 gives "ttt"est which is still different
        results = _doublings("tt")
        assert len(results) > 0


class TestTranspositions:
    def test_basic(self):
        results = _transpositions("google")
        typos = [t for t, _ in results]
        assert "ogogle" in typos  # swap g,o
        assert "goole" not in typos  # this would be an omission

    def test_count(self):
        # n-1 adjacent pairs
        results = _transpositions("abcd")
        assert len(results) == 3  # ab->ba, bc->cb, cd->dc


class TestAdjacentKeys:
    def test_basic(self):
        results = _adjacent_keys("a")
        typos = [t for t, _ in results]
        # 'a' neighbors: q, w, s, z
        assert "q" in typos
        assert "w" in typos
        assert "s" in typos
        assert "z" in typos

    def test_produces_valid_typos(self):
        results = _adjacent_keys("test")
        for typo, typo_type in results:
            assert typo_type == "adjacent_key"
            assert len(typo) == 4  # same length as original


class TestHomoglyphs:
    def test_single_char(self):
        results = _homoglyph_subs("lo")
        typos = [t for t, _ in results]
        assert "1o" in typos  # l -> 1
        assert "io" in typos  # l -> i
        assert "l0" in typos  # o -> 0

    def test_multi_char(self):
        results = _homoglyph_subs("burn")
        typos = [t for t, _ in results]
        assert "bum" in typos  # rn -> m


class TestGenerateTypos:
    def test_returns_candidates(self):
        candidates = generate_typos("google", [".com", ".net"])
        assert len(candidates) > 0
        assert all(isinstance(c, TypoCandidate) for c in candidates)

    def test_includes_tld_variants(self):
        candidates = generate_typos("test", [".com", ".io"])
        domains = {c.domain for c in candidates}
        # Should have candidates on both TLDs
        com_count = sum(1 for d in domains if d.endswith(".com"))
        io_count = sum(1 for d in domains if d.endswith(".io"))
        assert com_count > 0
        assert io_count > 0

    def test_no_duplicates(self):
        candidates = generate_typos("perplexity", [".com", ".net", ".org"])
        domains = [c.domain for c in candidates]
        assert len(domains) == len(set(domains))

    def test_includes_tld_swap(self):
        candidates = generate_typos("example", [".com", ".net", ".org"])
        tld_swaps = [c for c in candidates if c.typo_type == "tld_swap"]
        assert len(tld_swaps) > 0

    def test_confidence_scores_valid(self):
        candidates = generate_typos("amazon", [".com"])
        for c in candidates:
            assert 0.0 <= c.confidence <= 1.0

    def test_original_preserved(self):
        candidates = generate_typos("Stripe", [".com"])
        for c in candidates:
            assert c.original == "Stripe"
