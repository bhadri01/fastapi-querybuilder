from enum import StrEnum
from typing import Any

from sqlalchemy import ColumnElement, ColumnExpressionArgument, and_, or_
from sqlalchemy.sql import operators

from .utils import adjust_date_range


class Operator(StrEnum):
    # Logical Operators
    AND = "$and"
    OR = "$or"
    NOT = "$not"
    # Comparison Operators
    EQ = "$eq"
    NE = "$ne"
    GT = "$gt"
    GTE = "$gte"
    LT = "$lt"
    LTE = "$lte"
    IN = "$in"
    CONTAINS = "$contains"
    NCONTAINS = "$ncontains"
    STARTSWITH = "$startswith"
    ENDSWITH = "$endswith"
    ISNOTEMPTY = "$isnotempty"
    ISEMPTY = "$isempty"
    ISANYOF = "$isanyof"


def _not_operator(column: ColumnExpressionArgument):
    return ~column


def _eq_operator(column: ColumnElement[Any], value):
    if value == "":
        return column.is_(None)
    adjusted_value, is_range = adjust_date_range(column, value, Operator.EQ)
    if adjusted_value is not None and is_range is not None:
        return adjusted_value if is_range else column == adjusted_value
    return column == value


def _ne_operator(column: ColumnElement[Any], value):
    if value == "":
        return column.is_not(None)
    adjusted_value, is_range = adjust_date_range(column, value, Operator.NE)
    if adjusted_value is not None and is_range is not None:
        return adjusted_value if is_range else column != adjusted_value
    return column != value


def _gt_operator(column: ColumnElement[Any], value):
    return operators.gt(column, adjust_date_range(column, value, Operator.GT)[0])


def _gte_operator(column: ColumnElement[Any], value):
    return operators.ge(column, adjust_date_range(column, value, Operator.GTE)[0])


def _lt_operator(column: ColumnElement[Any], value):
    return operators.lt(column, adjust_date_range(column, value, Operator.LT)[0])


def _lte_operator(column: ColumnElement[Any], value):
    return operators.le(column, adjust_date_range(column, value, Operator.LTE)[0])


def _isanyof_operator(column: ColumnElement[Any], value: list):
    return or_(*[adjust_date_range(column, v, Operator.EQ)[0] if isinstance(v, str) else column == v for v in value])


def _in_operator(column: ColumnElement[Any], value: list):
    return column.in_(value)


def _contains_operator(column: ColumnElement[Any], value):
    return column.ilike(f"%{value}%")


def _ncontains_operator(column: ColumnElement[Any], value):
    return ~column.ilike(f"%{value}%")


def _startswith_operator(column: ColumnElement[Any], value):
    return column.ilike(f"{value}%")


def _endswith_operator(column: ColumnElement[Any], value):
    return column.ilike(f"%{value}")


def _isnotempty_operator(column: ColumnElement[Any]):
    return column.is_not(None)


def _isempty_operator(column: ColumnElement[Any]):
    return column.is_(None)


LOGICAL_OPERATORS = {
    Operator.AND: and_,
    Operator.OR: or_,
    Operator.NOT: _not_operator,
}

COMPARISON_OPERATORS = {
    Operator.EQ: _eq_operator,
    Operator.NE: _ne_operator,
    Operator.GT: _gt_operator,
    Operator.GTE: _gte_operator,
    Operator.LT: _lt_operator,
    Operator.LTE: _lte_operator,
    Operator.IN: _in_operator,
    Operator.CONTAINS: _contains_operator,
    Operator.NCONTAINS: _ncontains_operator,
    Operator.STARTSWITH: _startswith_operator,
    Operator.ENDSWITH: _endswith_operator,
    Operator.ISNOTEMPTY: _isnotempty_operator,
    Operator.ISEMPTY: _isempty_operator,
    Operator.ISANYOF: _isanyof_operator,
}
