"""Tests for search functionality, soft delete, circular reference detection,
and search field path parsing in fastapi_querybuilder/builder.py."""

import pytest
from fastapi import HTTPException
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects import sqlite
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship

from fastapi_querybuilder.builder import (
    _check_circular_references,
    _parse_search_field_paths,
    build_query,
)
from fastapi_querybuilder.params import QueryParams

Base = declarative_base()


class Department(Base):
    __tablename__ = "search_depts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)


class Role(Base):
    __tablename__ = "search_roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    dept_id: Mapped[int] = mapped_column(ForeignKey("search_depts.id"))
    department: Mapped["Department"] = relationship("Department")


class User(Base):
    __tablename__ = "search_users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    age: Mapped[int] = mapped_column(Integer)
    role_id: Mapped[int] = mapped_column(ForeignKey("search_roles.id"))
    role: Mapped["Role"] = relationship("Role")


class SoftUser(Base):
    """Model with soft-delete support."""
    __tablename__ = "soft_users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    deleted_at: Mapped[str] = mapped_column(String, nullable=True)


def _to_sql(query) -> str:
    return str(query.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))


def _params(**kwargs) -> QueryParams:
    return QueryParams(
        filters=kwargs.get("filters"),
        sort=kwargs.get("sort"),
        search=kwargs.get("search"),
        search_fields=kwargs.get("search_fields"),
    )


# ---------------------------------------------------------------------------
# Soft delete
# ---------------------------------------------------------------------------


def test_build_query_adds_deleted_at_filter_when_field_exists():
    sql = _to_sql(build_query(SoftUser, _params()))
    assert "deleted_at IS NULL" in sql


def test_build_query_no_deleted_at_filter_when_field_absent():
    sql = _to_sql(build_query(User, _params()))
    assert "deleted_at" not in sql


# ---------------------------------------------------------------------------
# Default search (top-level columns only)
# ---------------------------------------------------------------------------


def test_default_search_adds_where_clause():
    sql = _to_sql(build_query(User, _params(search="alice")))
    assert "WHERE" in sql


def test_default_search_targets_string_column():
    sql = _to_sql(build_query(User, _params(search="alice")))
    # ilike compiles to lower(col) LIKE lower('%value%') in SQLite dialect
    assert "search_users.name" in sql
    assert "alice" in sql
    assert "LIKE" in sql.upper()


def test_default_search_targets_integer_column_when_digit():
    sql = _to_sql(build_query(User, _params(search="42")))
    # Integer 'age' column should be matched when search term is a digit
    assert "search_users.age = 42" in sql


def test_default_search_does_not_add_joins():
    sql = _to_sql(build_query(User, _params(search="alice")))
    # Default search should NOT join related tables
    assert "search_roles" not in sql


def test_default_search_non_digit_does_not_add_integer_condition():
    sql = _to_sql(build_query(User, _params(search="notadigit")))
    # Integer column should not appear in the WHERE/condition part for non-digit search.
    # The column may appear in SELECT but should not be in a comparison in WHERE.
    assert "search_users.age =" not in sql


# ---------------------------------------------------------------------------
# Explicit search via search_fields
# ---------------------------------------------------------------------------


def test_explicit_search_fields_top_level_column():
    sql = _to_sql(build_query(User, _params(search="alice", search_fields="name")))
    assert "search_users.name" in sql
    assert "alice" in sql
    assert "LIKE" in sql.upper()


def test_explicit_search_fields_nested_relationship():
    sql = _to_sql(build_query(User, _params(search="admin", search_fields="role.name")))
    # Should join roles table
    assert "JOIN" in sql.upper()
    assert "search_roles" in sql
    assert "admin" in sql
    assert "LIKE" in sql.upper()


def test_explicit_search_fields_mixed_top_and_nested():
    sql = _to_sql(
        build_query(User, _params(search="eng", search_fields="name,role.department.name"))
    )
    assert "search_users.name" in sql
    assert "eng" in sql
    assert "search_depts" in sql


def test_explicit_search_fields_deeply_nested():
    sql = _to_sql(
        build_query(User, _params(search="eng", search_fields="role.department.name"))
    )
    assert "search_depts" in sql
    assert "eng" in sql
    assert "LIKE" in sql.upper()


def test_explicit_search_fields_with_joins_applies_deduplication():
    sql = _to_sql(
        build_query(User, _params(search="eng", search_fields="role.name"))
    )
    # Subquery-based deduplication should appear (IN subquery)
    assert "IN (" in sql.upper() or "in (" in sql


# ---------------------------------------------------------------------------
# _parse_search_field_paths
# ---------------------------------------------------------------------------


def test_parse_search_field_paths_single_field():
    result = _parse_search_field_paths("name")
    assert result == [([], "name")]


def test_parse_search_field_paths_multiple_fields():
    result = _parse_search_field_paths("name,email")
    assert ([], "name") in result
    assert ([], "email") in result


def test_parse_search_field_paths_nested():
    result = _parse_search_field_paths("role.name")
    assert result == [(["role"], "name")]


def test_parse_search_field_paths_deeply_nested():
    result = _parse_search_field_paths("role.department.name")
    assert result == [(["role", "department"], "name")]


def test_parse_search_field_paths_mixed():
    result = _parse_search_field_paths("name,role.name,role.department.name")
    assert ([], "name") in result
    assert (["role"], "name") in result
    assert (["role", "department"], "name") in result


def test_parse_search_field_paths_deduplicates():
    result = _parse_search_field_paths("name,name,role.name,role.name")
    # Duplicates removed
    assert len(result) == 2


def test_parse_search_field_paths_double_dot_raises_400():
    with pytest.raises(HTTPException) as exc_info:
        _parse_search_field_paths("role..name")
    assert exc_info.value.status_code == 400
    assert "empty parts" in exc_info.value.detail


def test_parse_search_field_paths_leading_dot_raises_400():
    with pytest.raises(HTTPException) as exc_info:
        _parse_search_field_paths(".name")
    assert exc_info.value.status_code == 400


def test_parse_search_field_paths_empty_string_returns_empty():
    result = _parse_search_field_paths("")
    assert result == []


def test_parse_search_field_paths_whitespace_only_returns_empty():
    result = _parse_search_field_paths("   ")
    assert result == []


# ---------------------------------------------------------------------------
# _check_circular_references
# ---------------------------------------------------------------------------


def test_check_circular_refs_top_level_passes():
    # Top-level columns have no circular reference risk
    paths = [([], "name"), ([], "age")]
    _check_circular_references(paths, User)  # should not raise


def test_check_circular_refs_valid_nested_passes():
    paths = [(["role"], "name"), (["role", "department"], "name")]
    _check_circular_references(paths, User)  # should not raise


def test_check_circular_refs_detects_cycle_raises_400():
    # Create a self-referential model to force a circular reference
    CircBase = declarative_base()

    class Node(CircBase):
        __tablename__ = "nodes"
        id: Mapped[int] = mapped_column(primary_key=True)
        name: Mapped[str] = mapped_column(String)
        parent_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), nullable=True)
        parent: Mapped["Node"] = relationship("Node", remote_side="Node.id")

    # path: node -> parent -> (back to Node) — circular
    paths = [(["parent", "parent"], "name")]
    with pytest.raises(HTTPException) as exc_info:
        _check_circular_references(paths, Node)
    assert exc_info.value.status_code == 400
    assert "Circular reference" in exc_info.value.detail


# ---------------------------------------------------------------------------
# build_query — no params (no-op path)
# ---------------------------------------------------------------------------


def test_build_query_no_params_returns_simple_select():
    sql = _to_sql(build_query(User, _params()))
    assert "SELECT" in sql.upper()
    assert "search_users" in sql
    assert "WHERE" not in sql
    assert "ORDER BY" not in sql


# ---------------------------------------------------------------------------
# build_query — combined params integration
# ---------------------------------------------------------------------------


def test_build_query_filters_and_sort_combined():
    sql = _to_sql(
        build_query(
            User,
            _params(filters='{"name": {"$eq": "alice"}}', sort="name:asc"),
        )
    )
    assert "lower(search_users.name) = 'alice'" in sql.lower()
    assert "order by lower(search_users.name) asc" in sql.lower()


def test_build_query_search_and_sort_combined():
    sql = _to_sql(
        build_query(User, _params(search="alice", sort="age:desc"))
    )
    assert "alice" in sql
    assert "LIKE" in sql.upper()
    assert "ORDER BY" in sql
    assert "DESC" in sql


def test_build_query_filters_search_and_sort_all_combined():
    sql = _to_sql(
        build_query(
            User,
            _params(
                filters='{"age": {"$gte": 18}}',
                search="alice",
                sort="name:asc",
            ),
        )
    )
    assert "search_users.age >= 18" in sql
    assert "alice" in sql
    assert "order by lower(search_users.name) asc" in sql.lower()


def test_build_query_legacy_case_sensitive_sort_and_filter():
    sql = _to_sql(
        build_query(
            User,
            QueryParams(
                filters='{"name": {"$eq": "alice"}}',
                sort="name:asc",
                search=None,
                search_fields=None,
                case_sensitive=True,
            ),
        )
    )
    assert "search_users.name = 'alice'" in sql
    assert "ORDER BY search_users.name ASC" in sql
