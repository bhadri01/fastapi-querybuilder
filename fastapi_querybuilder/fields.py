from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import ColumnElement, inspect
from sqlalchemy.orm import DeclarativeBase, DeclarativeMeta
from sqlalchemy.types import Boolean, Date, DateTime, Float, Integer, Numeric, String, Text

from .operators import Operator


class OperatorInfo(BaseModel):
    name: Operator = Field(..., description="The comparison operator, e.g., '$eq'")
    description: str = Field(..., description="A human-readable description.")


class FieldInfo(BaseModel):
    name: str = Field(..., description="The name of the field.")
    type: str = Field(..., description="The general data type (string, number, boolean, datetime).")
    operators: list[OperatorInfo] = Field(..., description="List of valid operators for this field.")


class QueryParamsSchemaResponse(BaseModel):
    filterable_fields: list[FieldInfo] = Field(..., description="Fields that can be used in filters.")
    sortable_fields: list[str] = Field(..., description="Fields that can be sorted.")
    searchable_fields: list[str] = Field(..., description="Text fields that can be searched.")


@dataclass
class SchemaConfig:
    model: type[DeclarativeMeta | DeclarativeBase]  # Should be a SQLAlchemy DeclarativeBase subclass
    only: Optional[Sequence[str]] = None
    exclude: Optional[Sequence[str]] = None


class ColumnTypeCategory(StrEnum):
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATETIME = "datetime"


OPERATORS = {
    ColumnTypeCategory.STRING: [
        OperatorInfo(name=Operator.EQ, description="Equal to"),
        OperatorInfo(name=Operator.NE, description="Not equal to"),
        OperatorInfo(name=Operator.IN, description="Is in the list"),
        OperatorInfo(name=Operator.CONTAINS, description="Contains the text"),
        OperatorInfo(name=Operator.STARTSWITH, description="Starts with"),
        OperatorInfo(name=Operator.ENDSWITH, description="Ends with"),
    ],
    ColumnTypeCategory.NUMBER: [
        OperatorInfo(name=Operator.EQ, description="Equal to"),
        OperatorInfo(name=Operator.NE, description="Not equal to"),
        OperatorInfo(name=Operator.GT, description="Greater than"),
        OperatorInfo(name=Operator.GTE, description="Greater than or equal to"),
        OperatorInfo(name=Operator.LT, description="Less than"),
        OperatorInfo(name=Operator.LTE, description="Less than or equal to"),
        OperatorInfo(name=Operator.IN, description="Is in the list"),
    ],
    ColumnTypeCategory.BOOLEAN: [
        OperatorInfo(name=Operator.EQ, description="Equal to"),
        OperatorInfo(name=Operator.NE, description="Not equal to"),
    ],
    ColumnTypeCategory.DATETIME: [
        OperatorInfo(name=Operator.EQ, description="Exact date"),
        OperatorInfo(name=Operator.NE, description="Not the exact date"),
        OperatorInfo(name=Operator.GT, description="After"),
        OperatorInfo(name=Operator.GTE, description="Greater than or equal to"),
        OperatorInfo(name=Operator.LT, description="Before"),
        OperatorInfo(name=Operator.LTE, description="Until"),
    ],
}


class SchemaGenerator:
    def __init__(self, config: SchemaConfig):
        self.config = config
        self.inspector = inspect(self.config.model)

    @staticmethod
    def _parse_scoped_list(items: Optional[list[str]]) -> dict[str, set[str]]:
        """Parse a list of strings that may contain scoped prefixes.

        Supported prefixes (case-insensitive):
          - filter:field
          - search:field
          - sort:field (alias: order:field)

        Items without a prefix apply globally to all capabilities.
        Returns a dict with keys: 'global', 'filter', 'sort', 'search'.
        """
        scopes = {"global": set(), "filter": set(), "sort": set(), "search": set()}
        if not items:
            return scopes
        for raw in items:
            if not isinstance(raw, str):
                continue
            s = raw.strip()
            if ":" in s:
                prefix, name = s.split(":", 1)
                field = name.strip()
                p = prefix.strip().lower()
                if p == "order":
                    p = "sort"
                if p in {"filter", "sort", "search"} and field:
                    scopes[p].add(field)
                else:
                    # Unrecognized prefix -> treat whole item as a global field name
                    scopes["global"].add(s)
            elif s:
                scopes["global"].add(s)
        return scopes

    def _get_column_type_category(self, column: ColumnElement) -> Optional[ColumnTypeCategory]:
        if isinstance(column.type, (String, Text)):
            return ColumnTypeCategory.STRING
        if isinstance(column.type, (Integer, Float, Numeric)):
            return ColumnTypeCategory.NUMBER
        if isinstance(column.type, Boolean):
            return ColumnTypeCategory.BOOLEAN
        if isinstance(column.type, (Date, DateTime)):
            return ColumnTypeCategory.DATETIME
        return None

    def _get_fields_to_process(self) -> set[str]:
        all_columns = {c.name for c in self.inspector.columns}
        all_columns |= {r.key for r in self.inspector.relationships}

        only_scoped = self._parse_scoped_list(self.config.only)
        exclude_scoped = self._parse_scoped_list(self.config.exclude)

        # Apply ONLY and EXCLUDE at the global level first
        fields = set(all_columns)
        if only_scoped["global"]:
            fields &= only_scoped["global"]
        if exclude_scoped["global"]:
            fields -= exclude_scoped["global"]
        return fields

    @staticmethod
    def _apply_only_exclude(base: set[str], only: set[str] | None, exclude: set[str] | None) -> set[str]:
        fields = set(base)
        if only:
            fields &= set(only)
        if exclude:
            fields -= set(exclude)
        return fields

    def generate(self) -> QueryParamsSchemaResponse:
        # Base fields after applying global scoped only/exclude
        base_fields = self._get_fields_to_process()

        # Scoped controls
        only_scoped = self._parse_scoped_list(self.config.only)
        exclude_scoped = self._parse_scoped_list(self.config.exclude)

        filter_names = self._apply_only_exclude(
            base_fields, only_scoped["filter"], exclude_scoped["filter"]
        )
        sort_names = self._apply_only_exclude(
            base_fields, only_scoped["sort"], exclude_scoped["sort"]
        )
        search_names = self._apply_only_exclude(
            base_fields, only_scoped["search"], exclude_scoped["search"]
        )
        search_scoped = bool(only_scoped["search"] or exclude_scoped["search"])  # Did user provide scoped search?

        filterable_fields: list[FieldInfo] = []
        sortable_fields: list[str] = []
        searchable_fields: list[str] = []

        for field_name in sorted(list(base_fields)):
            if field_name not in self.inspector.columns:
                continue

            column = self.inspector.columns[field_name]
            type_category = self._get_column_type_category(column)

            if not type_category:
                continue

            if field_name in filter_names:
                available_operators = OPERATORS.get(type_category, [])
                filterable_fields.append(
                    FieldInfo(name=field_name, type=type_category, operators=available_operators)
                )
            if field_name in sort_names:
                sortable_fields.append(field_name)
            # Search list:
            # - If user provided scoped search, honor it for any column type.
            # - If not, include all columns and let the query builder decide
            #   which types are safe to search (string/enum/int/bool).
            if search_scoped:
                if field_name in search_names:
                    searchable_fields.append(field_name)
            else:
                searchable_fields.append(field_name)

        return QueryParamsSchemaResponse(
            filterable_fields=filterable_fields,
            sortable_fields=sortable_fields,
            searchable_fields=searchable_fields,
        )
