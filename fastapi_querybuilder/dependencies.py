# fastapi_querybuilder/dependencies.py

from fastapi import Depends, HTTPException, Query, Request
from pydantic import ValidationError

from fastapi_querybuilder.params import QueryParams

from .builder import build_query


def filter_params(cls: type[QueryParams]):
    def get(
        filters: str | None = Query(
            default=None,
            description="Filtro en formato de string JSON.",
            example="{'$and': [{{'is_active': {{'$eq': true}}}}, {{'role': {{'$eq': 'admin'}}}}, {{'age': {{'$gte': 30, '$lt': 50}}}}]}",
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
            raise HTTPException(status_code=422, detail=e.errors())

    return get


def QueryBuilder(query_params: type[QueryParams] = QueryParams):
    def wrapper(request: Request, params: QueryParams = Depends(filter_params(query_params))):
        return build_query(
            query_params.model_config.get("model") or query_params.model_config.get("schema_config").model, params
        )

    return Depends(wrapper)
