"""Tests for fastapi_querybuilder/operators.py — all 14 filter operators."""

import enum

from sqlalchemy import Column, DateTime, Integer, String, select
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects import sqlite
from sqlalchemy.orm import declarative_base

from fastapi_querybuilder.operators import (
    COMPARISON_OPERATORS,
    _eq_operator,
    _ne_operator,
    _gt_operator,
    _gte_operator,
    _lt_operator,
    _lte_operator,
    _isanyof_operator,
    get_comparison_operators,
)

Base = declarative_base()


class StatusEnum(enum.Enum):
    ACCOUNT_SETUP = "accountsetup"
    PROFILE_SETUP = "profilesetup"


class Item(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    age = Column(Integer)
    created_at = Column(DateTime)
    status = Column(SQLEnum(StatusEnum, name="userstatus"))


_name_col = Item.name
_age_col = Item.age
_dt_col = Item.created_at
_status_col = Item.status


def _expr_sql(expr) -> str:
    """Compile a SQLAlchemy expression to SQL string."""
    return str(expr.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))


def _expr_sql_postgres(expr) -> str:
    """Compile a SQLAlchemy expression to PostgreSQL SQL string."""
    return str(expr.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


# ---------------------------------------------------------------------------
# $eq
# ---------------------------------------------------------------------------


def test_eq_operator_string_value():
    expr = COMPARISON_OPERATORS["$eq"](_name_col, "alice")
    sql = _expr_sql(expr)
    assert "lower(items.name) = 'alice'" in sql.lower()


def test_eq_operator_empty_string_becomes_is_null():
    expr = _eq_operator(_name_col, "")
    sql = _expr_sql(expr)
    assert "items.name IS NULL" in sql


def test_eq_operator_integer_value():
    expr = COMPARISON_OPERATORS["$eq"](_age_col, 30)
    sql = _expr_sql(expr)
    assert "items.age = 30" in sql


# ---------------------------------------------------------------------------
# $ne
# ---------------------------------------------------------------------------


def test_ne_operator_string_value():
    expr = COMPARISON_OPERATORS["$ne"](_name_col, "alice")
    sql = _expr_sql(expr)
    assert "lower(items.name) != 'alice'" in sql.lower()


def test_ne_operator_empty_string_becomes_is_not_null():
    expr = _ne_operator(_name_col, "")
    sql = _expr_sql(expr)
    assert "items.name IS NOT NULL" in sql


# ---------------------------------------------------------------------------
# $gt / $gte / $lt / $lte
# ---------------------------------------------------------------------------


def test_gt_operator():
    expr = _gt_operator(_age_col, 18)
    sql = _expr_sql(expr)
    assert "items.age > 18" in sql


def test_gte_operator():
    expr = _gte_operator(_age_col, 18)
    sql = _expr_sql(expr)
    assert "items.age >= 18" in sql


def test_lt_operator():
    expr = _lt_operator(_age_col, 65)
    sql = _expr_sql(expr)
    assert "items.age < 65" in sql


def test_lte_operator():
    expr = _lte_operator(_age_col, 65)
    sql = _expr_sql(expr)
    assert "items.age <= 65" in sql


# ---------------------------------------------------------------------------
# $in
# ---------------------------------------------------------------------------


def test_in_operator():
    expr = COMPARISON_OPERATORS["$in"](_name_col, ["alice", "bob"])
    sql = _expr_sql(expr)
    assert "lower(items.name) in ('alice', 'bob')" in sql.lower()


def test_in_operator_single_value():
    expr = COMPARISON_OPERATORS["$in"](_age_col, [42])
    sql = _expr_sql(expr)
    assert "42" in sql


def test_eq_operator_enum_uses_cast_before_lower_for_postgres():
    expr = COMPARISON_OPERATORS["$eq"](_status_col, "accountsetup")
    sql = _expr_sql_postgres(expr)
    assert "lower(CAST(items.status AS VARCHAR)) = 'accountsetup'" in sql


def test_ne_operator_enum_uses_cast_before_lower_for_postgres():
    expr = COMPARISON_OPERATORS["$ne"](_status_col, "profilesetup")
    sql = _expr_sql_postgres(expr)
    assert "lower(CAST(items.status AS VARCHAR)) != 'profilesetup'" in sql


def test_in_operator_enum_uses_cast_before_lower_for_postgres():
    expr = COMPARISON_OPERATORS["$in"](_status_col, ["accountsetup", "profilesetup"])
    sql = _expr_sql_postgres(expr)
    assert "lower(CAST(items.status AS VARCHAR)) IN ('accountsetup', 'profilesetup')" in sql


def test_eq_operator_enum_member_value_uses_casefolded_value_for_postgres():
    expr = COMPARISON_OPERATORS["$eq"](_status_col, StatusEnum.ACCOUNT_SETUP)
    sql = _expr_sql_postgres(expr)
    assert "lower(CAST(items.status AS VARCHAR)) = 'accountsetup'" in sql


def test_in_operator_enum_member_values_use_casefolded_values_for_postgres():
    expr = COMPARISON_OPERATORS["$in"](_status_col, [StatusEnum.ACCOUNT_SETUP, StatusEnum.PROFILE_SETUP])
    sql = _expr_sql_postgres(expr)
    assert "lower(CAST(items.status AS VARCHAR)) IN ('accountsetup', 'profilesetup')" in sql


def test_legacy_case_sensitive_eq_operator_string_value():
    ops = get_comparison_operators(case_sensitive=True)
    expr = ops["$eq"](_name_col, "alice")
    sql = _expr_sql(expr)
    assert "items.name = 'alice'" in sql


def test_legacy_case_sensitive_sort_ne_operator_string_value():
    ops = get_comparison_operators(case_sensitive=True)
    expr = ops["$ne"](_name_col, "alice")
    sql = _expr_sql(expr)
    assert "items.name != 'alice'" in sql


# ---------------------------------------------------------------------------
# $contains / $ncontains
# ---------------------------------------------------------------------------


def test_contains_operator():
    expr = COMPARISON_OPERATORS["$contains"](_name_col, "lic")
    sql = _expr_sql(expr)
    assert "items.name LIKE '%lic%'" in sql.upper() or "ilike" in sql.lower() or "LIKE" in sql


def test_ncontains_operator():
    expr = COMPARISON_OPERATORS["$ncontains"](_name_col, "lic")
    sql = _expr_sql(expr)
    assert "NOT" in sql.upper()
    assert "lic" in sql


def test_contains_operator_enum_uses_cast_for_postgres():
    expr = COMPARISON_OPERATORS["$contains"](_status_col, "setup")
    sql = _expr_sql_postgres(expr)
    assert "CAST(items.status AS VARCHAR)" in sql
    assert "ILIKE" in sql.upper()


def test_ncontains_operator_enum_uses_cast_for_postgres():
    expr = COMPARISON_OPERATORS["$ncontains"](_status_col, "setup")
    sql = _expr_sql_postgres(expr)
    assert "CAST(items.status AS VARCHAR)" in sql
    assert "NOT" in sql.upper()
    assert "ILIKE" in sql.upper()


# ---------------------------------------------------------------------------
# $startswith / $endswith
# ---------------------------------------------------------------------------


def test_startswith_operator():
    expr = COMPARISON_OPERATORS["$startswith"](_name_col, "al")
    sql = _expr_sql(expr)
    assert "al%" in sql


def test_endswith_operator():
    expr = COMPARISON_OPERATORS["$endswith"](_name_col, "ce")
    sql = _expr_sql(expr)
    assert "%ce" in sql


def test_startswith_operator_enum_uses_cast_for_postgres():
    expr = COMPARISON_OPERATORS["$startswith"](_status_col, "account")
    sql = _expr_sql_postgres(expr)
    assert "CAST(items.status AS VARCHAR)" in sql
    assert "ILIKE" in sql.upper()


def test_endswith_operator_enum_uses_cast_for_postgres():
    expr = COMPARISON_OPERATORS["$endswith"](_status_col, "setup")
    sql = _expr_sql_postgres(expr)
    assert "CAST(items.status AS VARCHAR)" in sql
    assert "ILIKE" in sql.upper()


# ---------------------------------------------------------------------------
# $isempty / $isnotempty
# ---------------------------------------------------------------------------


def test_isempty_operator():
    expr = COMPARISON_OPERATORS["$isempty"](_name_col)
    sql = _expr_sql(expr)
    assert "items.name IS NULL" in sql


def test_isnotempty_operator():
    expr = COMPARISON_OPERATORS["$isnotempty"](_name_col)
    sql = _expr_sql(expr)
    assert "items.name IS NOT NULL" in sql


# ---------------------------------------------------------------------------
# $isanyof
# ---------------------------------------------------------------------------


def test_isanyof_operator_with_integers():
    # Non-string values follow the `column == v` branch directly.
    expr = _isanyof_operator(_age_col, [1, 2, 3])
    sql = _expr_sql(expr)
    assert "1" in sql
    assert "2" in sql
    assert "3" in sql
    assert "OR" in sql.upper()


def test_isanyof_operator_with_date_strings_on_datetime_column():
    # String values on a DateTime column are passed through _adjust_date_range
    # which returns a proper SQLAlchemy expression for date-only strings.
    expr = _isanyof_operator(_dt_col, ["2024-01-15", "2024-06-01"])
    # Result should be a valid SQLAlchemy clause (no raw strings in or_())
    assert expr is not None
    # Both dates should appear as bound parameters in the compiled SQL.
    # SQLite dialect uses positional `?` placeholders; use literal_binds to verify values.
    sql = str(expr.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))
    assert "2024-01-15" in sql
    assert "2024-06-01" in sql


# ---------------------------------------------------------------------------
# COMPARISON_OPERATORS dict completeness
# ---------------------------------------------------------------------------


def test_all_expected_operators_registered():
    expected = {
        "$eq", "$ne", "$gt", "$gte", "$lt", "$lte",
        "$in", "$contains", "$ncontains", "$startswith", "$endswith",
        "$isempty", "$isnotempty", "$isanyof",
    }
    assert expected == set(COMPARISON_OPERATORS.keys())
