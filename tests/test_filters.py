"""Tests for fastapi_querybuilder/core.py — filter JSON parsing, filter expression
building, and column/relationship resolution."""

import pytest
from fastapi import HTTPException
from sqlalchemy import Column, ForeignKey, Integer, String, select
from sqlalchemy.dialects import sqlite
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship

from fastapi_querybuilder.core import (
    parse_filter_query,
    parse_filters,
    resolve_and_join_column,
)

Base = declarative_base()


class Department(Base):
    __tablename__ = "depts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    dept_id: Mapped[int] = mapped_column(ForeignKey("depts.id"))
    department: Mapped["Department"] = relationship("Department")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    age: Mapped[int] = mapped_column(Integer)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    role: Mapped["Role"] = relationship("Role")


def _to_sql(query) -> str:
    return str(query.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))


# ---------------------------------------------------------------------------
# parse_filter_query
# ---------------------------------------------------------------------------


def test_parse_filter_query_valid_json():
    result = parse_filter_query('{"name": {"$eq": "alice"}}')
    assert result == {"name": {"$eq": "alice"}}


def test_parse_filter_query_none_returns_none():
    assert parse_filter_query(None) is None


def test_parse_filter_query_empty_string_returns_none():
    assert parse_filter_query("") is None


def test_parse_filter_query_invalid_json_raises_400():
    with pytest.raises(HTTPException) as exc_info:
        parse_filter_query("{not valid json}")
    assert exc_info.value.status_code == 400
    assert "Invalid filter JSON" in exc_info.value.detail


def test_parse_filter_query_non_object_json_raises_400():
    with pytest.raises(HTTPException) as exc_info:
        parse_filter_query("[1, 2, 3]")
    assert exc_info.value.status_code == 400


def test_parse_filter_query_nested_json():
    filters = '{"$and": [{"name": {"$eq": "alice"}}, {"age": {"$gt": 18}}]}'
    result = parse_filter_query(filters)
    assert "$and" in result
    assert len(result["$and"]) == 2


# ---------------------------------------------------------------------------
# parse_filters — simple operators
# ---------------------------------------------------------------------------


def test_parse_filters_simple_eq():
    query = select(User)
    expr, _ = parse_filters(User, {"name": {"$eq": "alice"}}, query)
    assert expr is not None
    sql = str(expr.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))
    assert "lower(users.name) = 'alice'" in sql.lower()


def test_parse_filters_simple_ne():
    query = select(User)
    expr, _ = parse_filters(User, {"name": {"$ne": "alice"}}, query)
    sql = str(expr.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))
    assert "lower(users.name) != 'alice'" in sql.lower()


def test_parse_filters_integer_gt():
    query = select(User)
    expr, _ = parse_filters(User, {"age": {"$gt": 18}}, query)
    sql = str(expr.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))
    assert "users.age > 18" in sql


def test_parse_filters_contains():
    query = select(User)
    expr, _ = parse_filters(User, {"name": {"$contains": "ali"}}, query)
    sql = str(expr.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))
    assert "ali" in sql


def test_parse_filters_isempty():
    query = select(User)
    expr, _ = parse_filters(User, {"name": {"$isempty": None}}, query)
    sql = str(expr.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))
    assert "users.name IS NULL" in sql


def test_parse_filters_isnotempty():
    query = select(User)
    expr, _ = parse_filters(User, {"name": {"$isnotempty": None}}, query)
    sql = str(expr.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))
    assert "users.name IS NOT NULL" in sql


def test_parse_filters_multiple_fields_combined_with_and():
    query = select(User)
    expr, _ = parse_filters(User, {"name": {"$eq": "alice"}, "age": {"$gte": 18}}, query)
    sql = str(expr.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))
    assert "lower(users.name) = 'alice'" in sql.lower()
    assert "users.age >= 18" in sql
    assert "AND" in sql


def test_parse_filters_empty_dict_returns_none_expr():
    query = select(User)
    expr, _ = parse_filters(User, {}, query)
    assert expr is None


# ---------------------------------------------------------------------------
# parse_filters — logical operators
# ---------------------------------------------------------------------------


def test_parse_filters_and_operator():
    query = select(User)
    filters = {"$and": [{"name": {"$eq": "alice"}}, {"age": {"$gt": 18}}]}
    expr, _ = parse_filters(User, filters, query)
    sql = str(expr.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))
    assert "lower(users.name) = 'alice'" in sql.lower()
    assert "users.age > 18" in sql
    assert "AND" in sql


def test_parse_filters_or_operator():
    query = select(User)
    filters = {"$or": [{"name": {"$eq": "alice"}}, {"name": {"$eq": "bob"}}]}
    expr, _ = parse_filters(User, filters, query)
    sql = str(expr.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))
    assert "alice" in sql
    assert "bob" in sql
    assert "OR" in sql


def test_parse_filters_nested_and_or():
    query = select(User)
    filters = {
        "$and": [
            {"$or": [{"name": {"$eq": "alice"}}, {"name": {"$eq": "bob"}}]},
            {"age": {"$gte": 18}},
        ]
    }
    expr, _ = parse_filters(User, filters, query)
    sql = str(expr.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))
    assert "alice" in sql
    assert "bob" in sql
    assert "OR" in sql
    assert "AND" in sql
    assert "18" in sql


def test_parse_filters_and_requires_list_raises_400():
    query = select(User)
    with pytest.raises(HTTPException) as exc_info:
        parse_filters(User, {"$and": "not-a-list"}, query)
    assert exc_info.value.status_code == 400
    assert "must be a list" in exc_info.value.detail


def test_parse_filters_or_requires_list_raises_400():
    query = select(User)
    with pytest.raises(HTTPException) as exc_info:
        parse_filters(User, {"$or": {"name": {"$eq": "x"}}}, query)
    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# parse_filters — error cases
# ---------------------------------------------------------------------------


def test_parse_filters_invalid_operator_raises_400():
    query = select(User)
    with pytest.raises(HTTPException) as exc_info:
        parse_filters(User, {"name": {"$unknown": "x"}}, query)
    assert exc_info.value.status_code == 400
    assert "Invalid operator" in exc_info.value.detail


def test_parse_filters_non_dict_value_raises_400():
    query = select(User)
    with pytest.raises(HTTPException) as exc_info:
        parse_filters(User, {"name": "not-a-dict"}, query)
    assert exc_info.value.status_code == 400
    assert "Invalid filter format" in exc_info.value.detail


def test_parse_filters_non_dict_root_raises_400():
    query = select(User)
    with pytest.raises(HTTPException) as exc_info:
        parse_filters(User, ["not", "a", "dict"], query)
    assert exc_info.value.status_code == 400
    assert "Filters must be a dictionary" in exc_info.value.detail


# ---------------------------------------------------------------------------
# parse_filters — nested relationship path
# ---------------------------------------------------------------------------


def test_parse_filters_nested_relationship_generates_join():
    query = select(User)
    filters = {"role.name": {"$eq": "admin"}}
    _, modified_query = parse_filters(User, filters, query)
    sql = _to_sql(modified_query)
    # An OUTER JOIN to roles should be present
    assert "JOIN" in sql.upper()
    assert "roles" in sql


def test_parse_filters_deeply_nested_relationship():
    query = select(User)
    filters = {"role.department.name": {"$eq": "Engineering"}}
    expr, modified_query = parse_filters(User, filters, query)
    sql = _to_sql(modified_query)
    assert "JOIN" in sql.upper()
    assert "depts" in sql
    assert "engineering" in _to_sql(modified_query.where(expr)).lower()


def test_parse_filters_legacy_case_sensitive_eq():
    query = select(User)
    expr, _ = parse_filters(User, {"name": {"$eq": "alice"}}, query, case_sensitive=True)
    sql = str(expr.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))
    assert "users.name = 'alice'" in sql


# ---------------------------------------------------------------------------
# resolve_and_join_column
# ---------------------------------------------------------------------------


def test_resolve_and_join_column_direct_attribute():
    query = select(User)
    col, _ = resolve_and_join_column(User, ["name"], query, {})
    assert col is not None


def test_resolve_and_join_column_one_level_relationship():
    query = select(User)
    col, modified_query = resolve_and_join_column(User, ["role", "name"], query, {})
    sql = _to_sql(modified_query)
    assert "JOIN" in sql.upper()
    assert "roles" in sql


def test_resolve_and_join_column_reuses_existing_join():
    query = select(User)
    joins = {}
    _, query = resolve_and_join_column(User, ["role", "name"], query, joins)
    # Second resolution on the same relationship should reuse the alias, not add another JOIN
    col2, query2 = resolve_and_join_column(User, ["role", "id"], query, joins)
    sql = _to_sql(query2)
    # Only one JOIN to roles
    assert sql.count("JOIN") == 1


def test_resolve_and_join_column_invalid_attribute_raises_400():
    query = select(User)
    with pytest.raises(HTTPException) as exc_info:
        resolve_and_join_column(User, ["nonexistent_field"], query, {})
    assert exc_info.value.status_code == 400
    assert "Could not resolve attribute" in exc_info.value.detail


def test_resolve_and_join_column_invalid_nested_attribute_raises_400():
    query = select(User)
    with pytest.raises(HTTPException) as exc_info:
        resolve_and_join_column(User, ["role", "nonexistent"], query, {})
    assert exc_info.value.status_code == 400
