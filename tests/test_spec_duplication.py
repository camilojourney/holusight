from __future__ import annotations

from pathlib import Path

from holusight.spec_duplication import declared_spec_numbers, nearest_neighbor_specs, run


def test_declared_spec_numbers_single_mention():
    assert declared_spec_numbers("See spec 014 for the taxonomy.") == {"014"}


def test_declared_spec_numbers_range():
    assert declared_spec_numbers("Relationship to specs 011-017") == {
        "011",
        "012",
        "013",
        "014",
        "015",
        "016",
        "017",
    }


def test_declared_spec_numbers_ignores_unrelated_numbers_far_away():
    text = "spec 014 " + ("x" * 100) + " 999"
    assert declared_spec_numbers(text) == {"014"}


def test_declared_spec_numbers_no_mention():
    assert declared_spec_numbers("Nothing relevant here.") == set()


def _write_spec(tmp_path: Path, name: str, body: str) -> Path:
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir(exist_ok=True)
    path = specs_dir / name
    path.write_text(body, encoding="utf-8")
    return path


def _fake_embed(texts: list[str]) -> list[list[float]]:
    # Deterministic toy embedding: bag-of-words over a fixed small vocabulary,
    # so tests don't depend on the real (slow) sentence-transformers model.
    vocab = ["alpha", "beta", "gamma", "delta"]
    vectors = []
    for text in texts:
        lowered = text.lower()
        vectors.append([float(lowered.count(word)) for word in vocab])
    return vectors


def test_nearest_neighbor_specs_ranks_by_similarity(tmp_path):
    _write_spec(tmp_path, "001-alpha-one.md", "alpha alpha alpha beta")
    _write_spec(tmp_path, "002-alpha-two.md", "alpha alpha alpha beta beta")
    _write_spec(tmp_path, "003-gamma.md", "gamma gamma gamma delta")

    neighbors = nearest_neighbor_specs(tmp_path, embed_fn=_fake_embed, top_k=2)

    top_for_001 = neighbors["001-alpha-one.md"][0]
    assert top_for_001["spec"] == "002-alpha-two.md"
    assert top_for_001["similarity"] > 0.9


def test_nearest_neighbor_specs_flags_declared_relationship(tmp_path):
    _write_spec(tmp_path, "001-alpha-one.md", "alpha alpha alpha beta. See spec 002.")
    _write_spec(tmp_path, "002-alpha-two.md", "alpha alpha alpha beta beta")
    _write_spec(tmp_path, "003-gamma.md", "gamma gamma gamma delta")

    neighbors = nearest_neighbor_specs(tmp_path, embed_fn=_fake_embed, top_k=1)

    assert neighbors["001-alpha-one.md"][0]["declared_relationship"] is True


def test_nearest_neighbor_specs_target_filter_scopes_output(tmp_path):
    _write_spec(tmp_path, "001-alpha-one.md", "alpha alpha alpha beta")
    _write_spec(tmp_path, "002-alpha-two.md", "alpha alpha alpha beta beta")
    _write_spec(tmp_path, "003-gamma.md", "gamma gamma gamma delta")

    neighbors = nearest_neighbor_specs(
        tmp_path, embed_fn=_fake_embed, top_k=2, target_specs={"003-gamma.md"}
    )

    assert set(neighbors) == {"003-gamma.md"}


def test_nearest_neighbor_specs_ignores_template(tmp_path):
    _write_spec(tmp_path, "000-template.md", "alpha alpha alpha")
    _write_spec(tmp_path, "001-alpha-one.md", "alpha alpha alpha")
    _write_spec(tmp_path, "002-gamma.md", "gamma gamma gamma")

    neighbors = nearest_neighbor_specs(tmp_path, embed_fn=_fake_embed, top_k=5)

    assert "000-template.md" not in neighbors
    for entries in neighbors.values():
        assert all(n["spec"] != "000-template.md" for n in entries)


def test_run_never_blocks_and_reports_worth_a_look(tmp_path):
    _write_spec(tmp_path, "001-alpha-one.md", "alpha alpha alpha beta")
    _write_spec(tmp_path, "002-alpha-two.md", "alpha alpha alpha beta beta")
    _write_spec(tmp_path, "003-gamma.md", "gamma gamma gamma delta")

    payload = run(tmp_path, top_k=2, embed_fn=_fake_embed)

    assert payload["promotion"]["allowed"] is False
    assert payload["advisory_only"] is True
    assert "001-alpha-one.md" in payload["undeclared_and_worth_a_look"]


def test_run_with_fewer_than_two_specs_reports_empty(tmp_path):
    _write_spec(tmp_path, "001-alpha-one.md", "alpha")

    payload = run(tmp_path, top_k=2, embed_fn=_fake_embed)

    assert payload["nearest_neighbors"] == {}
    assert payload["undeclared_and_worth_a_look"] == {}
