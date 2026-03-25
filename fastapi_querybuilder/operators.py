# app/filters/operators.py

from sqlalchemy import Enum, String, and_, cast, func, or_
from sqlalchemy.sql import operators
from .utils import _adjust_date_range

LOGICAL_OPERATORS = {
    "$and": and_,
    "$or": or_
}


def _normalize_string_like_value(value):
    """Normalize plain strings and enum-member string values for insensitive comparisons."""
    if isinstance(value, str):
        return value.casefold()

    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        return enum_value.casefold()

    return None


def _eq_operator(column, value):
    if value == "":
        return column.is_(None)
    adjusted_value, is_range = _adjust_date_range(column, value, "$eq")
    if adjusted_value is not None and is_range is not None:
        return adjusted_value if is_range else column == adjusted_value
    return column == value


def _eq_operator_insensitive(column, value):
    if value == "":
        return column.is_(None)
    normalized = _normalize_string_like_value(value)
    if normalized is not None and _is_string_like_column(column):
        return _to_case_insensitive_expr(column) == normalized
    adjusted_value, is_range = _adjust_date_range(column, value, "$eq")
    if adjusted_value is not None and is_range is not None:
        return adjusted_value if is_range else column == adjusted_value
    return column == value


def _ne_operator(column, value):
    if value == "":
        return column.is_not(None)
    adjusted_value, is_range = _adjust_date_range(column, value, "$ne")
    if adjusted_value is not None and is_range is not None:
        return adjusted_value if is_range else column != adjusted_value
    return column != value


def _ne_operator_insensitive(column, value):
    if value == "":
        return column.is_not(None)
    normalized = _normalize_string_like_value(value)
    if normalized is not None and _is_string_like_column(column):
        return _to_case_insensitive_expr(column) != normalized
    adjusted_value, is_range = _adjust_date_range(column, value, "$ne")
    if adjusted_value is not None and is_range is not None:
        return adjusted_value if is_range else column != adjusted_value
    return column != value


def _gt_operator(column, value):
    return operators.gt(column, _adjust_date_range(column, value, "$gt")[0])


def _gte_operator(column, value):
    return operators.ge(column, _adjust_date_range(column, value, "$gte")[0])


def _lt_operator(column, value):
    return operators.lt(column, _adjust_date_range(column, value, "$lt")[0])


def _lte_operator(column, value):
    return operators.le(column, _adjust_date_range(column, value, "$lte")[0])


def _isanyof_operator(column, value):
    return or_(*[
        _adjust_date_range(column, v, "$eq")[
            0] if isinstance(v, str) else column == v
        for v in value
    ])


def _in_operator_insensitive(column, value):
    if _is_string_like_column(column) and isinstance(value, (list, tuple)):
        normalized = []
        for v in value:
            normalized_value = _normalize_string_like_value(v)
            normalized.append(normalized_value if normalized_value is not None else v)
        return _to_case_insensitive_expr(column).in_(normalized)
    return column.in_(value)


def _contains_operator(column, value):
    return _to_ilike_expr(column).ilike(f"%{value}%")


def _ncontains_operator(column, value):
    return ~_to_ilike_expr(column).ilike(f"%{value}%")


def _startswith_operator(column, value):
    return _to_ilike_expr(column).ilike(f"{value}%")


def _endswith_operator(column, value):
    return _to_ilike_expr(column).ilike(f"%{value}")


def _is_string_column(column):
    col_type = getattr(column, "type", None)
    return isinstance(col_type, String)


def _is_enum_column(column):
    col_type = getattr(column, "type", None)
    return isinstance(col_type, Enum)


def _is_string_like_column(column):
    return _is_string_column(column) or _is_enum_column(column)


def _to_case_insensitive_expr(column):
    if _is_enum_column(column):
        return func.lower(cast(column, String))
    return func.lower(column)


def _to_ilike_expr(column):
    if _is_enum_column(column):
        return cast(column, String)
    return column


def get_comparison_operators(case_sensitive: bool = False):
    eq_op = _eq_operator if case_sensitive else _eq_operator_insensitive
    ne_op = _ne_operator if case_sensitive else _ne_operator_insensitive
    in_op = (lambda column, value: column.in_(value)) if case_sensitive else _in_operator_insensitive

    return {
        "$eq": eq_op,
        "$ne": ne_op,
        "$gt": _gt_operator,
        "$gte": _gte_operator,
        "$lt": _lt_operator,
        "$lte": _lte_operator,
        "$in": in_op,
        "$contains": _contains_operator,
        "$ncontains": _ncontains_operator,
        "$startswith": _startswith_operator,
        "$endswith": _endswith_operator,
        "$isnotempty": lambda column: column.is_not(None),
        "$isempty": lambda column: column.is_(None),
        "$isanyof": _isanyof_operator,
    }


COMPARISON_OPERATORS = get_comparison_operators(case_sensitive=False)
