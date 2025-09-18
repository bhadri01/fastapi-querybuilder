from datetime import datetime, timedelta
from typing import Any, Tuple

from fastapi import HTTPException
from sqlalchemy import ColumnElement, DateTime
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql import and_, or_


def _parse_datetime(value: str) -> datetime:
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise HTTPException(status_code=400, detail=f"Invalid date format: {value}")


def _parse_datetime_py11(value: str) -> datetime:
    try:
        # Python 3.11+ has fromisoformat that can handle ISO 8601 directly
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {value}")


def adjust_date_range(
    column: InstrumentedAttribute[Any] | ColumnElement, value: str, operator: str
) -> Tuple[Any, bool]:
    from .operators import Operator

    if not isinstance(column.type, DateTime) or not isinstance(value, str):
        return value, False

    dt = _parse_datetime_py11(value)

    if len(value.split("T")) == 1 and " " not in value:
        if operator is Operator.EQ:
            return and_(column >= dt, column < dt + timedelta(days=1)), True
        elif operator is Operator.NE:
            return or_(column < dt, column >= dt + timedelta(days=1)), True
        elif operator is Operator.GT:
            return dt + timedelta(days=1), False
        elif operator is Operator.GTE:
            return dt, False
        elif operator is Operator.LT:
            return dt, False
        elif operator is Operator.LTE:
            return dt + timedelta(days=1), False
    return dt, False
