# app/filters/core.py

from fastapi import HTTPException
from sqlalchemy.orm import RelationshipProperty, aliased
from sqlalchemy.sql import Select, and_
from typing import Any, Optional, Dict, Tuple, List
import json
from functools import lru_cache
from .operators import LOGICAL_OPERATORS, get_comparison_operators

def resolve_and_join_column(model, nested_keys: list[str], query: Select, joins: dict) -> Tuple[Any, Select]:
    current_model = model
    alias = None

    for i, attr in enumerate(nested_keys):
        relationship = getattr(current_model, attr, None)

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
                f"Could not resolve attribute '{attr}' in model '{current_model.__name__}'."
            )
    raise HTTPException(
        status_code=400,
        detail=f"Could not resolve relationship for {'.'.join(nested_keys)}."
    )


def resolve_and_join_column_with_paths(
    model: Any,
    nested_keys: List[str],
    query: Select,
    joins: Dict[Tuple[Tuple[str, ...], type], Any]
) -> Tuple[Any, Select]:
    """
    Enhanced version of resolve_and_join_column that supports path-aware joins.
    
    This allows multiple joins to the same model if they come via different relationship paths.
    
    Args:
        model: Root model class
        nested_keys: List of attribute names to traverse (e.g., ['role', 'department', 'name'])
        query: SQLAlchemy Select query
        joins: Dictionary with key format: (tuple_of_relationship_keys, model_class) -> alias
        
    Returns:
        Tuple of (column_expression, modified_query)
    """
    current_model = model
    alias = None
    relationship_path = []  # Track the path of relationship keys traversed

    for i, attr in enumerate(nested_keys):
        relationship = getattr(current_model, attr, None)

        if relationship is not None and isinstance(relationship.property, RelationshipProperty):
            related_model = relationship.property.mapper.class_
            
            # Create path-aware key: (tuple of rel keys, model class)
            relationship_path.append(attr)
            path_key = (tuple(relationship_path), related_model)
            
            # Check if we've already joined this relationship path
            if path_key not in joins:
                alias = aliased(related_model)
                joins[path_key] = alias
                query = query.outerjoin(alias, getattr(current_model, attr))
            else:
                alias = joins[path_key]

            current_model = alias
        else:
            # This should be the final column attribute
            if hasattr(current_model, attr):
                return getattr(current_model, attr), query
            raise HTTPException(
                status_code=400,
                detail=f"Invalid filter key: {'.'.join(nested_keys)}. "
                f"Could not resolve attribute '{attr}' in model '{current_model.__name__}'."
            )
    
    raise HTTPException(
        status_code=400,
        detail=f"Could not resolve relationship for {'.'.join(nested_keys)}."
    )


def parse_filters(
    model,
    filters: dict,
    query: Select,
    case_sensitive: bool = False,
) -> Tuple[Optional[Any], Select]:
    expressions = []
    joins = {}
    comparison_operators = get_comparison_operators(case_sensitive=case_sensitive)

    if not isinstance(filters, dict):
        raise HTTPException(
            status_code=400, detail="Filters must be a dictionary")

    for key, value in filters.items():
        if key in LOGICAL_OPERATORS:
            if not isinstance(value, list):
                raise HTTPException(
                    status_code=400, detail=f"Logical operator '{key}' must be a list")
            sub_expressions = []
            for sub_filter in value:
                sub_expr, query = parse_filters(
                    model,
                    sub_filter,
                    query,
                    case_sensitive=case_sensitive,
                )
                if sub_expr is not None:
                    sub_expressions.append(sub_expr)
            if sub_expressions:
                expressions.append(LOGICAL_OPERATORS[key](*sub_expressions))

        elif isinstance(value, dict):
            nested_keys = key.split(".")
            column, query = resolve_and_join_column(
                model, nested_keys, query, joins)
            for operator, operand in value.items():
                if operator not in comparison_operators:
                    raise HTTPException(
                        status_code=400, detail=f"Invalid operator '{operator}' for field '{key}'")
                try:
                    if operator in ["$isempty", "$isnotempty"]:
                        expressions.append(
                            comparison_operators[operator](column))
                    else:
                        expressions.append(
                            comparison_operators[operator](column, operand))
                except Exception as e:
                    raise HTTPException(
                        status_code=400, detail=f"Error filtering '{key}': {e}")
        else:
            raise HTTPException(
                status_code=400, detail=f"Invalid filter format for key '{key}': {value}")

    return and_(*expressions) if expressions else None, query


@lru_cache(maxsize=1024)
def parse_filter_query(filters: Optional[str]) -> Optional[Dict]:
    """
    Parse JSON filter string with LRU caching (max 1024 entries).
    Significantly speeds up repeated filter queries.
    
    IMPORTANT: Returns dict, but since dicts are mutable, cache key should only
    be the string. The @lru_cache ensures identical filter strings don't re-parse.
    """
    if not filters:
        return None
    try:
        parsed = json.loads(filters)
        if not isinstance(parsed, dict):
            raise ValueError("Filters must be a JSON object")
        return parsed
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid filter JSON: {e}")
