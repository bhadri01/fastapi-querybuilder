"""Tests for column type detection helpers in fastapi_querybuilder/builder.py."""

import enum

from sqlalchemy import Boolean, Column, Date, DateTime, Enum, Integer, String
from sqlalchemy.orm import declarative_base

from fastapi_querybuilder.builder import (
    _is_datetime_like_column,
    _is_string_timestamp_like_field,
    is_boolean_column,
    is_enum_column,
    is_integer_column,
    is_string_column,
)

Base = declarative_base()


class StatusEnum(enum.Enum):
    active = "active"
    inactive = "inactive"


class SampleModel(Base):
    __tablename__ = "sample"
    id = Column(Integer, primary_key=True)
    label = Column(String)
    count = Column(Integer)
    is_active = Column(Boolean)
    status = Column(Enum(StatusEnum))
    occurred_at = Column(DateTime)
    event_date = Column(Date)


_str_col = SampleModel.label
_int_col = SampleModel.count
_bool_col = SampleModel.is_active
_enum_col = SampleModel.status
_dt_col = SampleModel.occurred_at
_date_col = SampleModel.event_date


# ---------------------------------------------------------------------------
# is_string_column
# ---------------------------------------------------------------------------


def test_is_string_column_with_string_type():
    assert is_string_column(_str_col) is True


def test_is_string_column_with_integer_type():
    assert is_string_column(_int_col) is False


def test_is_string_column_with_boolean_type():
    assert is_string_column(_bool_col) is False


def test_is_string_column_with_enum_type():
    # SQLAlchemy's Enum type subclasses String, so is_string_column returns True
    # for Enum columns. The caller must check is_enum_column first to distinguish them.
    assert is_string_column(_enum_col) is True


# ---------------------------------------------------------------------------
# is_integer_column
# ---------------------------------------------------------------------------


def test_is_integer_column_with_integer_type():
    assert is_integer_column(_int_col) is True


def test_is_integer_column_with_string_type():
    assert is_integer_column(_str_col) is False


def test_is_integer_column_with_boolean_type():
    # Boolean has python_type bool, not int
    assert is_integer_column(_bool_col) is False


# ---------------------------------------------------------------------------
# is_boolean_column
# ---------------------------------------------------------------------------


def test_is_boolean_column_with_boolean_type():
    assert is_boolean_column(_bool_col) is True


def test_is_boolean_column_with_integer_type():
    assert is_boolean_column(_int_col) is False


def test_is_boolean_column_with_string_type():
    assert is_boolean_column(_str_col) is False


# ---------------------------------------------------------------------------
# is_enum_column
# ---------------------------------------------------------------------------


def test_is_enum_column_with_enum_type():
    assert is_enum_column(_enum_col) is True


def test_is_enum_column_with_string_type():
    assert is_enum_column(_str_col) is False


def test_is_enum_column_with_integer_type():
    assert is_enum_column(_int_col) is False


# ---------------------------------------------------------------------------
# _is_datetime_like_column
# ---------------------------------------------------------------------------


def test_is_datetime_like_column_with_datetime():
    assert _is_datetime_like_column(_dt_col) is True


def test_is_datetime_like_column_with_date():
    assert _is_datetime_like_column(_date_col) is True


def test_is_datetime_like_column_with_string():
    assert _is_datetime_like_column(_str_col) is False


def test_is_datetime_like_column_with_integer():
    assert _is_datetime_like_column(_int_col) is False


# ---------------------------------------------------------------------------
# _is_string_timestamp_like_field
# ---------------------------------------------------------------------------


def test_is_string_timestamp_like_field_ends_with_at():
    assert _is_string_timestamp_like_field(_str_col, ["created_at"]) is True


def test_is_string_timestamp_like_field_ends_with_date():
    assert _is_string_timestamp_like_field(_str_col, ["event_date"]) is True


def test_is_string_timestamp_like_field_ends_with_on():
    assert _is_string_timestamp_like_field(_str_col, ["published_on"]) is True


def test_is_string_timestamp_like_field_named_timestamp():
    assert _is_string_timestamp_like_field(_str_col, ["timestamp"]) is True


def test_is_string_timestamp_like_field_regular_name():
    assert _is_string_timestamp_like_field(_str_col, ["name"]) is False


def test_is_string_timestamp_like_field_not_string_column():
    # Even if the field name looks timestamp-like, must be a String column
    assert _is_string_timestamp_like_field(_int_col, ["created_at"]) is False


def test_is_string_timestamp_like_field_nested_path():
    # Only the last part of the path is checked
    assert _is_string_timestamp_like_field(_str_col, ["role", "created_at"]) is True


def test_is_string_timestamp_like_field_empty_path():
    assert _is_string_timestamp_like_field(_str_col, []) is False


def test_is_string_timestamp_like_field_enum_with_at_suffix_is_false():
    assert _is_string_timestamp_like_field(_enum_col, ["status_at"]) is False


def test_is_string_timestamp_like_field_enum_with_date_suffix_is_false():
    assert _is_string_timestamp_like_field(_enum_col, ["created_date"]) is False


def test_is_string_timestamp_like_field_enum_with_on_suffix_is_false():
    assert _is_string_timestamp_like_field(_enum_col, ["created_on"]) is False
