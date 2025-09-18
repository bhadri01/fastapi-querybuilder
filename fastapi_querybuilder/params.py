from typing import Any, ClassVar, Literal, Optional, TypeAlias

import orjson
from fastapi import Query
from pydantic import (
    BaseModel,
    Field,
    RootModel,
    TypeAdapter,
    ValidationInfo,
    field_validator,
    model_validator,
)
from sqlalchemy import inspect
from sqlalchemy.orm import DeclarativeBase

from .fields import FieldInfo, QueryParamsSchemaResponse, SchemaConfig, SchemaGenerator
from .operators import Operator

LOGICAL_OPERATORS = {Operator.AND, Operator.OR, Operator.NOT}
COMPARISON_OPERATORS = {op for op in Operator if op not in LOGICAL_OPERATORS}
LIST_BASED_OPERATORS = {Operator.IN, Operator.ISANYOF}


def _validate_field_path(model: type[DeclarativeBase], path: str):
    parts = path.split(".")
    current_model = model
    for i, part in enumerate(parts):
        is_last_part = i == len(parts) - 1
        current_inspector = inspect(current_model)
        if part in current_inspector.columns:
            if not is_last_part:
                raise ValueError(
                    f"The field '{part}' in the path '{path}' is a column and cannot have more relationships."
                )
            return True
        elif part in current_inspector.relationships:
            if is_last_part:
                raise ValueError(
                    f"The path '{path}' cannot end in a relationship. It must point to a column (e.g. '{path}.id')."
                )
            current_model = current_inspector.relationships[part].mapper.class_
        else:
            raise ValueError(
                f"The field or relationship '{part}' does not exist in the model '{current_model.__name__}' for the path '{path}'."
            )
    return False


def _recursive_validate_keys(filter_data: dict[str, Any], sqla_model: type[DeclarativeBase], allowed_fields: list[FieldInfo] | None = None):
    if not isinstance(filter_data, dict):
        raise ValueError("Each filter clause must be a dictionary.")

    for key, value in filter_data.items():
        if key in LOGICAL_OPERATORS:
            if key in {Operator.AND, Operator.OR}:
                if not isinstance(value, list):
                    raise ValueError(f"The value for the operator '{key}' must be a list.")
                for sub_filter in value:
                    _recursive_validate_keys(sub_filter, sqla_model)
            elif key == Operator.NOT:
                if not isinstance(value, dict):
                    raise ValueError(f"The value for the operator '{key}' must be a dictionary.")
                _recursive_validate_keys(value, sqla_model)
        else:
            field_info = None
            if allowed_fields is not None:
                field_info = next((f for f in allowed_fields if f.name == key), None)
                if field_info is None:
                    raise ValueError(f"The field '{key}' is not allowed for filtering.")

            _validate_field_path(sqla_model, key)
            if not isinstance(value, dict):
                raise ValueError(
                    f"The value for the field '{key}' must be a comparison dictionary (e.g. {{'$eq': 'value'}})."
                )

            if not value:
                raise ValueError(f"The comparison object for '{key}' cannot be empty.")

            for comp_op_str, comp_val in value.items():
                try:
                    comp_op = Operator(comp_op_str)
                    if comp_op not in COMPARISON_OPERATORS:
                        raise ValueError()
                except ValueError:
                    raise ValueError(f"'{comp_op_str}' is not a valid comparison operator for the field '{key}'.")

                if field_info and comp_op not in {field.name for field in field_info.operators}:
                    raise ValueError(f"'{comp_op_str}' is not a valid comparison operator for the field '{key}'.")
                if comp_op in LIST_BASED_OPERATORS:
                    if not isinstance(comp_val, list):
                        raise ValueError(
                            f"The value for the operator '{comp_op}' in the field '{key}' must be a list."
                        )


ComparisonValue: TypeAlias = str | int | float | bool | list
ComparisonObject: TypeAlias = dict[str, ComparisonValue]
FilterDict: TypeAlias = dict[str, ComparisonObject | list["FilterSchema"]]


class FilterSchema(RootModel[FilterDict]):
    @model_validator(mode="before")
    @classmethod
    def _validate_with_context(cls, data: Any, info: ValidationInfo) -> Any:
        sqla_model = info.context.get("sqla_model")
        allowed_fields = info.context.get("allowed_fields")
        if not sqla_model:
            raise ValueError("The SQLAlchemy model was not found in the validation context.")
        try:
            if not isinstance(data, dict):
                raise ValueError("The main filter clause must be a dictionary.")
            _recursive_validate_keys(data, sqla_model, allowed_fields)
        except ValueError as e:
            raise ValueError(str(e)) from e
        return data


class SortField(BaseModel):
    field: str = Field(..., description="The field name to sort by.", min_length=1)
    direction: Literal["asc", "desc"] | None = Field(default=None)


class QueryParams(BaseModel):
    SCHEMA: ClassVar[Optional[QueryParamsSchemaResponse]] = None

    filters: Optional[FilterSchema] = Query(default=None, description="Filters in JSON format.")
    sort: list[SortField] = Query(default_factory=list, description="e.g. name:asc,phone:desc or user.email:desc")
    search: Optional[str | None] = Query(default=None, description="A string for global search across string fields.")

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        config = cls.model_config.get("schema_config")
        if config and isinstance(config, SchemaConfig):
            generator = SchemaGenerator(config)
            cls.SCHEMA = generator.generate()

    @classmethod
    def get_schema(cls) -> QueryParamsSchemaResponse:
        if cls.SCHEMA is None:
            raise TypeError(f"The schema has not been generated for the class '{cls.__name__}'.")

        return cls.SCHEMA

    @field_validator("filters", mode="before")
    @classmethod
    def validate_and_parse_filters(cls, v: Any, info: ValidationInfo) -> Optional[dict[str, Any]]:
        if v is None or not isinstance(v, str) or not v.strip():
            return None
        try:
            data = orjson.loads(v)
        except orjson.JSONDecodeError:
            raise ValueError("The JSON provided in 'filters' is invalid.")
        sqla_model = cls.model_config.get("sqla_model") if cls.model_config else None
        query_config = cls.model_config.get("schema_config") if cls.model_config else None

        if not sqla_model:
            if not isinstance(query_config, SchemaConfig):
                raise ValueError("The SQLAlchemy model must be provided in 'model_config' or via 'schema_config'.")
            sqla_model = query_config.model
        if query_config:
            if not isinstance(query_config, SchemaConfig):
                raise ValueError("'schema_config' in 'model_config' must be an instance of SchemaConfig.")
            if sqla_model is not query_config.model:
                raise ValueError("The SQLAlchemy model in 'model_config' must match the one in 'schema_config'.")
        allowed_fields = cls.get_schema().filterable_fields

        validated_filter = TypeAdapter(FilterSchema).validate_python(
            data, context={"sqla_model": sqla_model, "allowed_fields": allowed_fields}
        )
        return validated_filter

    @field_validator("sort", mode="before")
    @classmethod
    def parse_sort_string(cls, v: Any) -> list[dict]:
        if v is None:
            return []
        if isinstance(v, list):
            return v

        if isinstance(v, str):
            allowed_fields = cls.get_schema().sortable_fields
            if not v.strip():
                return []
            sort_fields = []
            sort_string = v.strip()
            fields = [field.strip() for field in sort_string.split(",") if field.strip()]
            for sort_field_expr in fields:
                sort_field = {}
                if ":" in sort_field_expr:
                    field_name, direction = sort_field_expr.split(":", 1)
                    sort_field["field"] = field_name.strip()
                    sort_field["direction"] = direction.strip().lower()
                else:
                    field_name = sort_field_expr.strip()
                    sort_field["field"] = field_name
                    sort_field["direction"] = "asc"
                if sort_field["field"] not in allowed_fields:
                    raise ValueError(f"Field '{sort_field['field']}' is not sortable.")
                sort_fields.append(sort_field)
            return sort_fields
        raise ValueError(f"Invalid sort type: {type(v)}. Expected string or list.")
