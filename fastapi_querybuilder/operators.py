# app/filters/operators.py

from sqlalchemy import String, and_, func, or_
from sqlalchemy.sql import operators
from .utils import _adjust_date_range

LOGICAL_OPERATORS = {
    "$and": and_,
    "$or": or_
}


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
    if isinstance(value, str) and _is_string_column(column):
        return func.lower(column) == value.casefold()
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
    if isinstance(value, str) and _is_string_column(column):
        return func.lower(column) != value.casefold()
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
    if _is_string_column(column) and isinstance(value, (list, tuple)):
        normalized = [v.casefold() if isinstance(v, str) else v for v in value]
        return func.lower(column).in_(normalized)
    return column.in_(value)


def _is_string_column(column):
    col_type = getattr(column, "type", None)
    return isinstance(col_type, String)


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
        "$contains": lambda column, value: column.ilike(f"%{value}%"),
        "$ncontains": lambda column, value: ~column.ilike(f"%{value}%"),
        "$startswith": lambda column, value: column.ilike(f"{value}%"),
        "$endswith": lambda column, value: column.ilike(f"%{value}"),
        "$isnotempty": lambda column: column.is_not(None),
        "$isempty": lambda column: column.is_(None),
        "$isanyof": _isanyof_operator,
    }


COMPARISON_OPERATORS = get_comparison_operators(case_sensitive=False)
