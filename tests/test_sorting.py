from fastapi import HTTPException
import enum
from sqlalchemy import ForeignKey, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects import sqlite
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship

from fastapi_querybuilder.builder import _parse_sort_clauses, build_query
from fastapi_querybuilder.params import QueryParams


Base = declarative_base()


class UserStatus(enum.Enum):
    ACCOUNT_SETUP = "accountsetup"
    PROFILE_SETUP = "profilesetup"


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))

    department: Mapped["Department"] = relationship("Department")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)
    updated_at: Mapped[str] = mapped_column(String)
    status: Mapped[UserStatus] = mapped_column(SQLEnum(UserStatus, name="userstatus"))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))

    role: Mapped["Role"] = relationship("Role")


def _to_sql(query) -> str:
    return str(query.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))


def _to_postgres_sql(query) -> str:
    return str(query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_parse_sort_clauses_supports_multi_and_nested_formats():
    parsed = _parse_sort_clauses("name:asc, role.name:desc, role__department__name:asc")

    assert parsed == [
        (["name"], "asc"),
        (["role", "name"], "desc"),
        (["role", "department", "name"], "asc"),
    ]


def test_parse_sort_clauses_rejects_invalid_direction():
    try:
        _parse_sort_clauses("name:up")
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "Invalid sort direction" in exc.detail
    else:
        raise AssertionError("Expected HTTPException for invalid sort direction")


def test_build_query_supports_multi_sort_and_nested_paths():
    params = QueryParams(
        filters=None,
        search=None,
        sort="name:asc,role__name:desc,role.department.name:asc",
        search_fields=None,
    )

    sql = _to_sql(build_query(User, params))

    assert "ORDER BY" in sql
    assert "lower(users.name) asc" in sql.lower()
    assert "lower(roles_1.name) desc" in sql.lower()
    assert "lower(departments_1.name) asc" in sql.lower()


def test_build_query_rejects_invalid_sort_field():
    params = QueryParams(filters=None, search=None, sort="unknown_field:asc", search_fields=None)

    try:
        build_query(User, params)
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "Could not resolve attribute" in exc.detail
    else:
        raise AssertionError("Expected HTTPException for invalid sort field")


def test_build_query_uses_datetime_expression_for_timestamp_like_string_fields():
    params = QueryParams(filters=None, search=None, sort="created_at:desc,updated_at:asc", search_fields=None)

    sql = _to_sql(build_query(User, params))

    assert "ORDER BY" in sql
    assert "CAST(users.created_at AS DATETIME) DESC" in sql
    assert "CAST(users.updated_at AS DATETIME) ASC" in sql


def test_build_query_keeps_regular_string_sort_unchanged():
    params = QueryParams(filters=None, search=None, sort="name:asc", search_fields=None)

    sql = _to_sql(build_query(User, params))

    assert "order by lower(users.name) asc" in sql.lower()
    assert "CAST(users.name AS DATETIME)" not in sql


def test_build_query_legacy_case_sensitive_sorting():
    params = QueryParams(
        filters=None,
        search=None,
        sort="name:asc",
        search_fields=None,
        case_sensitive=True,
    )

    sql = _to_sql(build_query(User, params))

    assert "ORDER BY users.name ASC" in sql
    assert "lower(users.name)" not in sql.lower()


def test_build_query_enum_sort_uses_cast_before_lower_for_postgres():
    params = QueryParams(filters=None, search=None, sort="status:asc", search_fields=None)

    sql = _to_postgres_sql(build_query(User, params))

    assert "ORDER BY lower(CAST(users.status AS VARCHAR)) ASC" in sql
