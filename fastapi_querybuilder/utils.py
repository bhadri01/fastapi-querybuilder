from fastapi import HTTPException
from sqlalchemy.sql import and_, or_
from typing import Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy import DateTime
from functools import lru_cache

@lru_cache(maxsize=512)
def _parse_datetime(value: str) -> datetime:
    """
    Parse datetime string with caching (max 512 entries).
    Significantly speeds up repeated date parsing in filters.
    """
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise HTTPException(
        status_code=400, detail=f"Invalid date format: {value}")


def _adjust_date_range(column, value: str, operator: str) -> Tuple[Any, bool]:
    if not isinstance(column.type, DateTime) or not isinstance(value, str):
        return value, False

    dt = _parse_datetime(value)
    if len(value.split("T")) == 1 and " " not in value:
        if operator == "$eq":
            return and_(column >= dt, column < dt + timedelta(days=1)), True
        elif operator == "$ne":
            return or_(column < dt, column >= dt + timedelta(days=1)), True
        elif operator == "$gt":
            return dt + timedelta(days=1), False
        elif operator == "$gte":
            return dt, False
        elif operator == "$lt":
            return dt, False
        elif operator == "$lte":
            return dt + timedelta(days=1), False
    return dt, False