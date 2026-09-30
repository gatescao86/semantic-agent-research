from agents.sql_tables import check_domain_scope, referenced_tables


ALLOWED = {
    "SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.GEOGRAPHY_INDEX",
    "SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.GEOGRAPHY_HIERARCHY",
}


def test_referenced_tables_skips_ctes_and_values():
    sql = """
    WITH metro AS (
        SELECT * FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.GEOGRAPHY_INDEX
    ),
    -- counties that roll up into the metro
    children AS (
        SELECT * FROM SNOWFLAKE_PUBLIC_DATA_FREE.PUBLIC_DATA_FREE.GEOGRAPHY_HIERARCHY
    )
    SELECT * FROM metro JOIN children ON 1=1
    UNION ALL
    SELECT * FROM VALUES (1) AS t(x)
    """
    assert referenced_tables(sql) == ALLOWED
    assert check_domain_scope(sql, ALLOWED) is None


def test_unparseable_sql_is_rejected_not_allowed():
    error = check_domain_scope("NOT SQL AT ALL !!!", ALLOWED)
    assert error is not None
    assert "parse" in error.lower()
