"""Tests for fastapi_querybuilder/utils.py — date parsing and range adjustment."""

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import Column, DateTime, String, Integer
from sqlalchemy.orm import declarative_base

from fastapi_querybuilder.utils import _adjust_date_range, _parse_datetime

Base = declarative_base()


class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    occurred_at = Column(DateTime)
    label = Column(String)


_datetime_col = Event.occurred_at
_string_col = Event.label


# ---------------------------------------------------------------------------
# _parse_datetime
# ---------------------------------------------------------------------------


def test_parse_datetime_date_only():
    dt = _parse_datetime("2024-01-15")
    assert dt == datetime(2024, 1, 15)


def test_parse_datetime_iso_with_T():
    dt = _parse_datetime("2024-01-15T10:30:00")
    assert dt == datetime(2024, 1, 15, 10, 30, 0)


def test_parse_datetime_with_space():
    dt = _parse_datetime("2024-01-15 10:30:00")
    assert dt == datetime(2024, 1, 15, 10, 30, 0)


def test_parse_datetime_with_z_suffix():
    dt = _parse_datetime("2024-01-15T10:30:00Z")
    assert dt == datetime(2024, 1, 15, 10, 30, 0)


def test_parse_datetime_invalid_raises_400():
    with pytest.raises(HTTPException) as exc_info:
        _parse_datetime("not-a-date")
    assert exc_info.value.status_code == 400
    assert "Invalid date format" in exc_info.value.detail


def test_parse_datetime_partial_invalid_raises_400():
    with pytest.raises(HTTPException):
        _parse_datetime("2024/01/15")


# ---------------------------------------------------------------------------
# _adjust_date_range — non-DateTime column passthrough
# ---------------------------------------------------------------------------


def test_adjust_date_range_non_datetime_col_returns_value_unchanged():
    result_value, is_range = _adjust_date_range(_string_col, "hello", "$eq")
    assert result_value == "hello"
    assert is_range is False


def test_adjust_date_range_non_string_value_returns_unchanged():
    result_value, is_range = _adjust_date_range(_datetime_col, 42, "$eq")
    assert result_value == 42
    assert is_range is False


# ---------------------------------------------------------------------------
# _adjust_date_range — full datetime string (no expansion)
# ---------------------------------------------------------------------------


def test_adjust_date_range_full_datetime_no_expansion():
    value = "2024-01-15T10:30:00"
    result_value, is_range = _adjust_date_range(_datetime_col, value, "$eq")
    assert result_value == datetime(2024, 1, 15, 10, 30, 0)
    assert is_range is False


def test_adjust_date_range_full_datetime_with_space_no_expansion():
    value = "2024-01-15 10:30:00"
    result_value, is_range = _adjust_date_range(_datetime_col, value, "$eq")
    assert result_value == datetime(2024, 1, 15, 10, 30, 0)
    assert is_range is False


# ---------------------------------------------------------------------------
# _adjust_date_range — date-only string expansion per operator
# ---------------------------------------------------------------------------


def test_adjust_date_range_eq_date_only_returns_range():
    result_value, is_range = _adjust_date_range(_datetime_col, "2024-01-15", "$eq")
    assert is_range is True
    # The returned expression should be a SQLAlchemy AND clause (not None)
    assert result_value is not None


def test_adjust_date_range_ne_date_only_returns_range():
    result_value, is_range = _adjust_date_range(_datetime_col, "2024-01-15", "$ne")
    assert is_range is True
    assert result_value is not None


def test_adjust_date_range_gt_date_only_advances_by_one_day():
    result_value, is_range = _adjust_date_range(_datetime_col, "2024-01-15", "$gt")
    expected = datetime(2024, 1, 15) + timedelta(days=1)
    assert result_value == expected
    assert is_range is False


def test_adjust_date_range_gte_date_only_returns_exact_day():
    result_value, is_range = _adjust_date_range(_datetime_col, "2024-01-15", "$gte")
    assert result_value == datetime(2024, 1, 15)
    assert is_range is False


def test_adjust_date_range_lt_date_only_returns_exact_day():
    result_value, is_range = _adjust_date_range(_datetime_col, "2024-01-15", "$lt")
    assert result_value == datetime(2024, 1, 15)
    assert is_range is False


def test_adjust_date_range_lte_date_only_advances_by_one_day():
    result_value, is_range = _adjust_date_range(_datetime_col, "2024-01-15", "$lte")
    expected = datetime(2024, 1, 15) + timedelta(days=1)
    assert result_value == expected
    assert is_range is False
