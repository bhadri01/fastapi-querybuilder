"""Validated filter parsing and mapped-column resolution."""

import json
import math
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import inspect, select, Integer
from sqlalchemy.orm import aliased, ColumnProperty, RelationshipProperty
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import Select, and_

from .operators import LOGICAL_OPERATORS, get_comparison_operators
from .security import QueryBudget, QueryLimits, QueryPolicy, reject


def resolve_and_join_column(model, nested_keys: list[str], query: Select, joins: dict) -> Tuple[Any, Select]:
    """Compatibility entry point; aliases are keyed by path, never just model."""
    return resolve_and_join_column_with_paths(model, nested_keys, query, joins)


def resolve_and_join_column_with_paths(
    model: Any,
    nested_keys: List[str],
    query: Select,
    joins: Dict[Tuple[Tuple[str, ...], type], Any],
    *,
    budget: Optional[QueryBudget] = None,
    operation: str = "filter",
) -> Tuple[Any, Select]:
    budget = budget or QueryBudget(QueryLimits(), QueryPolicy())
    budget.check_path(nested_keys, operation)
    current_model = model
    for i, attr in enumerate(nested_keys):
        mapper = inspect(current_model).mapper
        # Mapped synonyms remain supported; ordinary Python descriptors are never
        # inspected. SQLAlchemy resolves a synonym's property to its mapped target.
        descriptor = getattr(current_model, attr) if attr in mapper.attrs else None
        property_ = getattr(descriptor, "property", None)
        if i == len(nested_keys) - 1:
            if isinstance(property_, ColumnProperty):
                return descriptor, query
        elif isinstance(property_, RelationshipProperty):
            related_model = property_.mapper.class_
            key = (tuple(nested_keys[:i + 1]), related_model)
            if key not in joins:
                budget.add_join()
                joins[key] = aliased(related_model)
                query = query.outerjoin(joins[key], getattr(current_model, attr))
            current_model = joins[key]
            continue
        reject(f"Could not resolve attribute '{attr}' in field path '{'.'.join(nested_keys)}'")
    reject("Field path must end in a mapped column")


def _validate_filters(filters, limits):
    # Iterative traversal rejects oversized/deep programmatic filters before the
    # recursive SQL builder runs. Bound logical groups as well as predicates.
    stack = [(filters, 1)]
    predicates = groups = 0
    operators = get_comparison_operators()
    while stack:
        node, depth = stack.pop()
        groups += 1
        if groups > limits.max_predicates + 1:
            reject("Filters exceed maximum logical groups")
        if depth > limits.max_filter_depth:
            reject("Filters exceed maximum nesting depth")
        if not isinstance(node, dict):
            reject("Filters must be a dictionary")
        for key, value in node.items():
            if not isinstance(key, str):
                reject("Filter keys must be strings")
            if key in LOGICAL_OPERATORS:
                if not isinstance(value, list):
                    reject(f"Logical operator '{key}' must be a list")
                if len(value) > limits.max_predicates:
                    reject("Filters exceed maximum logical groups")
                stack.extend((child, depth + 1) for child in value)
                continue
            if not isinstance(value, dict):
                reject(f"Invalid filter format for key '{key}'")
            for operator, operand in value.items():
                items = operand if isinstance(operand, (list, tuple)) else [operand]
                try:
                    for item in items:
                        if isinstance(item, str):
                            item.encode('utf-8')
                except UnicodeEncodeError as exc:
                    raise HTTPException(status_code=400, detail="Filter strings must be valid UTF-8") from exc
                if any(isinstance(item, float) and not math.isfinite(item) for item in items):
                    reject("Filter numeric values must be finite")
                predicates += 1
                if predicates > limits.max_predicates:
                    reject("Filters exceed maximum predicates")
                if operator not in operators:
                    reject(f"Invalid operator '{operator}' for field '{key}'")
                if operator in {"$in", "$isanyof"}:
                    if not isinstance(operand, (list, tuple)):
                        reject(f"Operator '{operator}' requires a list")
                    if len(operand) > limits.max_in_items:
                        reject("Filter list exceeds maximum items")
                    if any(isinstance(item, (dict, list, tuple)) for item in operand):
                        reject("Filter lists must contain scalar values")
                elif isinstance(operand, (dict, list, tuple)):
                    reject(f"Operator '{operator}' requires a scalar value")


def _comparison_expressions(column, comparisons, operators, key):
    result = []
    for operator, operand in comparisons.items():
        items = operand if isinstance(operand, (list, tuple)) else [operand]
        if isinstance(column.type, Integer) and any(
            isinstance(item, int) and not -(2**63) <= item <= 2**63 - 1
            for item in items
        ):
            reject("Integer filter value is outside the signed 64-bit range")
        try:
            if operator in {"$isempty", "$isnotempty"}:
                result.append(operators[operator](column))
            else:
                result.append(operators[operator](column, operand))
        except HTTPException:
            raise
        except (TypeError, ValueError, AttributeError, OverflowError, SQLAlchemyError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid operand for '{key}'") from exc
    return result


def parse_filters(
    model,
    filters: dict,
    query: Select,
    case_sensitive: bool = False,
    *,
    limits: Optional[QueryLimits] = None,
    policy: Optional[QueryPolicy] = None,
    _budget: Optional[QueryBudget] = None,
) -> Tuple[Optional[Any], Select]:
    """Build filter expressions with bounded, path-aware joins.

    This low-level API returns joins. ``build_query`` uses correlated EXISTS so
    relationship filters cannot multiply outer result rows.
    """
    budget = _budget or QueryBudget(limits or QueryLimits(), policy or QueryPolicy())
    _validate_filters(filters, budget.limits)
    operators = get_comparison_operators(case_sensitive=case_sensitive)

    def visit(node, current_query):
        expressions = []
        # Each dictionary is a separate existential scope. Reusing aliases across
        # logical branches would change which related rows may satisfy AND.
        joins = {}
        for key, value in node.items():
            if key in LOGICAL_OPERATORS:
                children = []
                for child in value:
                    expression, current_query = visit(child, current_query)
                    if expression is not None:
                        children.append(expression)
                if children:
                    expressions.append(LOGICAL_OPERATORS[key](*children))
            else:
                column, current_query = resolve_and_join_column_with_paths(
                    model, key.split('.'), current_query, joins, budget=budget)
                expressions.extend(_comparison_expressions(column, value, operators, key))
        return and_(*expressions) if expressions else None, current_query

    return visit(filters, query)


def build_filter_expression(model, filters, case_sensitive, budget):
    """Correlate each relationship filter scope independently to its root row.

    Outer joins inside EXISTS preserve legacy null/missing-relationship matches.
    Unlike sharing aliases or flattening AND, separate child-row matches survive.
    """
    _validate_filters(filters, budget.limits)
    operators = get_comparison_operators(case_sensitive=case_sensitive)

    def visit(node):
        expressions = []
        local = {key: value for key, value in node.items() if key not in LOGICAL_OPERATORS}
        if local:
            has_relationships = any('.' in key for key in local)
            source = aliased(model) if has_relationships else model
            query = select(1).select_from(source)
            joins = {}
            local_expressions = []
            for key, value in local.items():
                column, query = resolve_and_join_column_with_paths(
                    source, key.split('.'), query, joins, budget=budget)
                local_expressions.extend(_comparison_expressions(column, value, operators, key))
            if local_expressions:
                if has_relationships:
                    mapper = inspect(model).mapper
                    correlation = [getattr(source, mapper.get_property_by_column(pk).key) ==
                                   getattr(model, mapper.get_property_by_column(pk).key)
                                   for pk in mapper.primary_key]
                    expressions.append(query.where(*correlation, *local_expressions).correlate(model).exists())
                else:
                    expressions.extend(local_expressions)
        for key, value in node.items():
            if key in LOGICAL_OPERATORS:
                children = [expr for child in value if (expr := visit(child)) is not None]
                if children:
                    expressions.append(LOGICAL_OPERATORS[key](*children))
        return and_(*expressions) if expressions else None

    return visit(filters)


def parse_filter_query(filters: Optional[str], *, limits: Optional[QueryLimits] = None) -> Optional[Dict]:
    """Parse bounded JSON without retaining client strings or mutable results."""
    if not filters:
        return None
    limits = limits or QueryLimits()
    if not isinstance(filters, str):
        reject("Filters must be a JSON string")
    # The cheap character check avoids allocating a large encoded copy.
    if len(filters) > limits.max_filter_bytes:
        reject("Filter JSON exceeds maximum bytes")
    try:
        encoded_length = len(filters.encode('utf-8'))
    except UnicodeEncodeError as exc:
        raise HTTPException(status_code=400, detail="Filter JSON must be valid UTF-8") from exc
    if encoded_length > limits.max_filter_bytes:
        reject("Filter JSON exceeds maximum bytes")
    # Bound lexical nesting before json.loads can recurse; ignore quoted braces.
    depth = 0
    quoted = escaped = False
    for char in filters:
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in '[{':
            depth += 1
            if depth > 2 * limits.max_filter_depth + 2:
                reject("Filters exceed maximum nesting depth")
        elif char in ']}':
            depth -= 1
    try:
        parsed = json.loads(filters, parse_constant=lambda value: reject("Invalid filter JSON constant"))
    except (ValueError, RecursionError) as exc:
        raise HTTPException(status_code=400, detail="Invalid filter JSON") from exc
    if not isinstance(parsed, dict):
        reject("Invalid filter JSON: Filters must be a JSON object")
    _validate_filters(parsed, limits)
    return parsed
