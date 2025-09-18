from fastapi import HTTPException
from sqlalchemy import Enum, String, asc, cast, desc, or_, select
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql.elements import KeyedColumnElement

from .core import parse_filters, resolve_and_join_column
from .params import QueryParams


def build_query(cls: type[DeclarativeBase], params: QueryParams):
    if hasattr(cls, "deleted_at"):
        query = select(cls).where(cls.deleted_at.is_(None))
    else:
        query = select(cls)

    # Filters
    if params.filters:
        filter_expr, query = parse_filters(cls, params.filters, query, params.get_schema().filterable_fields)
        if filter_expr is not None:
            query = query.where(filter_expr)

    # Search - restricted to schema.searchable_fields
    if params.search:
        search_expr = []
        allowed_search = set(params.get_schema().searchable_fields)

        for column in cls.__table__.columns:
            if column.key not in allowed_search:
                continue
            if is_enum_column(column):
                search_expr.append(cast(column, String).ilike(f"%{params.search}%"))
            elif is_string_column(column):
                search_expr.append(column.ilike(f"%{params.search}%"))
            elif is_integer_column(column):
                if params.search.isdigit():
                    search_expr.append(column == int(params.search))
            elif is_boolean_column(column):
                if params.search.lower() in ("true", "false"):
                    search_expr.append(column == (params.search.lower() == "true"))

        if search_expr:
            query = query.where(or_(*search_expr))

    # Sorting
    if params.sort:
        for sort_field in params.sort:
            column = getattr(cls, sort_field.field, None)
            if column is None:
                nested_keys = sort_field.field.split(".")
                if len(nested_keys) > 1:
                    joins = {}
                    column, query = resolve_and_join_column(cls, nested_keys, query, joins)
                else:
                    raise HTTPException(status_code=400, detail=f"Invalid sort field: {sort_field}")

            query = query.order_by(asc(column) if sort_field.direction.lower() == "asc" else desc(column))

    return query


def is_enum_column(column: KeyedColumnElement):
    """Check if a column is an enum type"""
    return isinstance(column.type, Enum)


def is_string_column(column: KeyedColumnElement):
    """Check if a column is a string type"""
    return isinstance(column.type, String)


def is_integer_column(column: KeyedColumnElement):
    """Check if a column is an integer type"""
    return hasattr(column.type, "python_type") and column.type.python_type is int


def is_boolean_column(column: KeyedColumnElement):
    """Check if a column is a boolean type"""
    return hasattr(column.type, "python_type") and column.type.python_type is bool
