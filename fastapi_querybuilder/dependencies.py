# fastapi_querybuilder/dependencies.py

from fastapi import Depends, HTTPException, Query, Request
from pydantic import ValidationError

from .fields import SchemaConfig
from .params import QueryParams

from .builder import build_query


def _parse_errors(e: ValidationError):
    # Ensure the error structure is compatible with FastAPI's expected format
    return [
        {"type": error.type, "loc": error.loc, "msg": error.msg}
        for error in e.errors(include_context=False, include_url=False, include_input=False)
    ]


def filter_params(cls: type[QueryParams]):
    def get(
        filters: str | None = Query(
            default=None,
            description="Filtro en formato de string JSON.",
            example='{"$and": [{"active": {"$eq": true}}, {"role": {"$eq": "admin"}}, {"age": {"$gte": 30, "$lt": 50}}]}',
        ),
        sort: str | None = Query(
            default=None,
            description="e.g. name:asc,phone:desc or user.email:desc",
            example="name:asc,age:desc",
        ),
        search: str | None = Query(
            default=None,
            description="Una cadena para búsqueda global a través de campos de cadena.",
            example="developer",
        ),
    ) -> type[QueryParams]:
        try:
            return cls(filters=filters, sort=sort, search=search)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=_parse_errors(e))

    return get


def QueryBuilder(query_params: type[QueryParams] = QueryParams):
    def wrapper(request: Request, params: QueryParams = Depends(filter_params(query_params))):
        schema_config: SchemaConfig = query_params.model_config.get("schema_config")
        model = query_params.model_config.get("model")
        return build_query(
            model or schema_config.model,
            params,
        )

    return Depends(wrapper)
