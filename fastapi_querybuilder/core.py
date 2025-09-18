# app/filters/core.py

from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import DeclarativeBase, InstrumentedAttribute, RelationshipProperty, aliased
from sqlalchemy.sql import Select, and_

from .operators import COMPARISON_OPERATORS, LOGICAL_OPERATORS, Operator
from .params import FilterSchema


def resolve_and_join_column(
    model: DeclarativeBase, nested_keys: list[str], query: Select, joins: dict
) -> tuple[InstrumentedAttribute[Any], Select]:
    current_model = model
    alias = None

    for i, attr in enumerate(nested_keys):
        relationship: InstrumentedAttribute[Any] = getattr(current_model, attr, None)

        if relationship is not None and isinstance(relationship.property, RelationshipProperty):
            related_model = relationship.property.mapper.class_
            if related_model not in joins:
                alias = aliased(related_model)
                joins[related_model] = alias
                query = query.outerjoin(alias, getattr(current_model, attr))
            else:
                alias = joins[related_model]

            current_model = alias
        else:
            if hasattr(current_model, attr):
                return getattr(current_model, attr), query
            raise HTTPException(
                status_code=400,
                detail=f"Invalid filter key: {'.'.join(nested_keys)}. "
                f"Could not resolve attribute '{attr}' in model '{current_model.__name__}'.",
            )
    raise HTTPException(status_code=400, detail=f"Could not resolve relationship for {'.'.join(nested_keys)}.")


def parse_filters(
    model, filters: FilterSchema, query: Select, allowed_fields: set[str]
) -> tuple[Optional[Any], Select]:
    expressions = []
    joins = {}

    filter_dict = filters.root
    for key, value in filter_dict.items():
        if key in LOGICAL_OPERATORS:
            if not isinstance(value, list):
                raise HTTPException(status_code=400, detail=f"Logical operator '{key}' must be a list")
            sub_expressions = []
            for sub_filter in value:
                sub_expr, query = parse_filters(model, sub_filter, query)
                if sub_expr is not None:
                    sub_expressions.append(sub_expr)
            if sub_expressions:
                expressions.append(LOGICAL_OPERATORS[key](*sub_expressions))

        elif isinstance(value, dict):
            nested_keys = key.split(".")
            column, query = resolve_and_join_column(model, nested_keys, query, joins)
            for operator, operand in value.items():
                if operator not in COMPARISON_OPERATORS:
                    raise HTTPException(status_code=400, detail=f"Invalid operator '{operator}' for field '{key}'")
                try:
                    if operator in {Operator.ISNOTEMPTY, Operator.ISEMPTY}:
                        expressions.append(COMPARISON_OPERATORS[operator](column))
                    else:
                        expressions.append(COMPARISON_OPERATORS[operator](column, operand))
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"Error filtering '{key}': {e}")
        else:
            raise HTTPException(status_code=400, detail=f"Invalid filter format for key '{key}': {value}")

    return and_(*expressions) if expressions else None, query
