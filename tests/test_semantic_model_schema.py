from pathlib import Path

import pytest

from semantic_models.schema import (
    load_semantic_model,
    merge_domain_models,
    validate_references,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DOMAINS_DIR = REPO_ROOT / "semantic_models" / "domains"
UNIFIED_PATH = REPO_ROOT / "semantic_models" / "unified" / "unified_model.yaml"

DOMAIN_FILES = sorted(DOMAINS_DIR.glob("*.yaml"))


@pytest.mark.parametrize("path", DOMAIN_FILES, ids=lambda p: p.stem)
def test_domain_model_loads_and_validates(path):
    model = load_semantic_model(path)
    assert model.entities, f"{path} has no entities"
    assert validate_references(model) == []


def test_unified_model_is_up_to_date_with_domain_models():
    """Enforces the plan's "generated, not hand-authored" rule for the unified model."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "generate_unified_model.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"unified_model.yaml is stale — run scripts/generate_unified_model.py.\n{result.stderr}"
    )


def test_unified_model_contains_promoted_cross_domain_relationships():
    model = load_semantic_model(UNIFIED_PATH)
    assert model.cross_domain_keys == []
    rel_pairs = {(r.from_, r.to) for r in model.relationships}
    assert ("company.hq_geo_id", "geography.geo_id") in rel_pairs
    assert ("indicator_timeseries.geo_id", "geography.geo_id") in rel_pairs
    assert ("acs_timeseries.geo_id", "geography.geo_id") in rel_pairs


def test_merge_domain_models_promotes_relationship_when_both_domains_present():
    merged, unavailable = merge_domain_models(["competitor_intelligence", "geography"])
    assert unavailable == []
    rel_pairs = {(r["from"], r["to"]) for r in merged["relationships"]}
    assert ("company.hq_geo_id", "geography.geo_id") in rel_pairs


def test_merge_domain_models_drops_relationship_when_target_domain_missing():
    merged, unavailable = merge_domain_models(["competitor_intelligence"])
    assert len(unavailable) == 1
    assert "geography" in unavailable[0]
    rel_froms = {r["from"] for r in merged["relationships"]}
    assert "company.hq_geo_id" not in rel_froms


def test_generate_unified_model_rejects_entity_name_collision(tmp_path, monkeypatch):
    import importlib

    domains_dir = tmp_path / "domains"
    domains_dir.mkdir()
    (domains_dir / "a.yaml").write_text(
        "domain: a\ndescription: d\nentities:\n"
        "  - name: shared\n    table: T_A\n    primary_key: id\n"
    )
    (domains_dir / "b.yaml").write_text(
        "domain: b\ndescription: d\nentities:\n"
        "  - name: shared\n    table: T_B\n    primary_key: id\n"
    )

    import scripts.generate_unified_model as gen

    monkeypatch.setattr(gen, "DOMAINS_DIR", domains_dir)
    with pytest.raises(SystemExit):
        gen.build_unified_model(gen.load_domain_models())
