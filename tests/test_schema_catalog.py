from pathlib import Path

from semantic_models.schema import DOMAINS_DIR, load_semantic_model, study_tables

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = REPO_ROOT / "semantic_models" / "raw" / "schema_catalog.md"


def _catalog_module():
    import importlib.util
    import sys

    path = REPO_ROOT / "scripts" / "generate_schema_catalog.py"
    spec = importlib.util.spec_from_file_location("generate_schema_catalog", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_study_tables_covers_every_entity_table():
    expected = set()
    for path in sorted(DOMAINS_DIR.glob("*.yaml")):
        model = load_semantic_model(path)
        for entity in model.entities:
            expected.add(entity.table)
    cataloged = {fqdn for fqdn, _domains in study_tables()}
    assert cataloged == expected
    assert cataloged, "no study tables found"


def test_schema_catalog_lists_every_study_table_and_no_glossary():
    assert CATALOG_PATH.is_file(), (
        "schema_catalog.md is missing — run "
        "`python scripts/generate_schema_catalog.py --from-yaml`"
    )
    text = CATALOG_PATH.read_text()
    for fqdn, _domains in study_tables():
        assert f"## {fqdn}" in text, fqdn
    lowered = text.lower()
    assert "cross_domain_keys" not in lowered
    assert "\nmetrics:" not in lowered


def test_snowflake_type_codes_map_to_names():
    gsc = _catalog_module()
    assert gsc._snowflake_type_name("2") == "TEXT"
    assert gsc._snowflake_type_name("3") == "DATE"
    assert gsc._snowflake_type_name("13") == "BOOLEAN"
    assert gsc._snowflake_type_name("TEXT") == "TEXT"
    assert gsc._snowflake_type_name("") == ""


def test_render_schema_catalog_format():
    gsc = _catalog_module()
    tables = [
        gsc.CatalogTable(
            fqdn="DB.SCHEMA.T1",
            domains=("geography",),
            columns=(gsc.CatalogColumn(name="GEO_ID", type="VARCHAR"),),
        )
    ]
    rendered = gsc.render_schema_catalog(tables, gsc.YAML_HEADER)
    assert rendered.startswith("# GENERATED FILE")
    assert "## DB.SCHEMA.T1" in rendered
    assert "domains: geography" in rendered
    assert "- GEO_ID VARCHAR" in rendered
    assert "no metrics" in rendered.lower()
