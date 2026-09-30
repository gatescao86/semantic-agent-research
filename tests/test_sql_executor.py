import pytest

from agents.sql_executor import UnsafeSqlError, check_sql_is_read_only, strip_sql_comments


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


@pytest.mark.parametrize(
    "sql",
    [
        # A `;` inside a comment is not a statement separator. Found authoring
        # eval/ground_truth/ex-001-deposits.sql, whose header comment contains
        # "geoId/C21780; Gibson County ...".
        "-- geoId/C21780; Gibson County is not in this CBSA\nSELECT 1",
        # A query may legitimately open with a comment.
        "-- ground truth: deposit market\nWITH x AS (SELECT 1) SELECT * FROM x",
        # A disallowed keyword inside a comment is not a disallowed statement.
        "/* do not CREATE anything */ SELECT 1",
        "SELECT 1 -- DROP TABLE foo",
    ],
)
def test_comments_do_not_trigger_false_rejections(sql):
    check_sql_is_read_only(sql)  # should not raise


def test_strip_sql_comments_preserves_string_literals():
    sql = "SELECT '-- not a comment' AS a, 'a''b' AS b -- real comment\nFROM t"
    assert strip_sql_comments(sql) == "SELECT '-- not a comment' AS a, 'a''b' AS b \nFROM t"


def test_statement_separator_outside_comment_still_rejected():
    with pytest.raises(UnsafeSqlError, match="Multiple statements"):
        check_sql_is_read_only("-- a comment\nSELECT 1; SELECT 2")
