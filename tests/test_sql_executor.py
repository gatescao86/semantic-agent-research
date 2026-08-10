import pytest

from agents.sql_executor import UnsafeSqlError, check_sql_is_read_only


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "  select * from foo",
        "WITH x AS (SELECT 1) SELECT * FROM x",
        "SELECT * FROM foo;",
    ],
)
def test_allows_single_select(sql):
    check_sql_is_read_only(sql)  # should not raise


@pytest.mark.parametrize(
    "sql,expected_message_fragment",
    [
        ("DROP TABLE foo", "Only SELECT"),
        ("SELECT * FROM foo; DROP TABLE foo;", "Multiple statements"),
        ("INSERT INTO foo VALUES (1)", "Only SELECT"),
        ("UPDATE foo SET x = 1", "Only SELECT"),
        ("", "Empty SQL"),
        ("USE DATABASE x", "Only SELECT"),
        ("select * from foo where x = 'a'; select * from bar", "Multiple statements"),
        # Documented limitation: the keyword check is not string-literal-aware,
        # so a disallowed word inside a quoted value is rejected too (a false
        # positive we accept for a defense-in-depth check — see module docstring).
        ("select * from foo where x = 'DROP me'", "Disallowed keyword"),
    ],
)
def test_rejects_unsafe_sql(sql, expected_message_fragment):
    with pytest.raises(UnsafeSqlError, match=expected_message_fragment):
        check_sql_is_read_only(sql)
