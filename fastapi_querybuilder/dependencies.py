# fastapi_querybuilder/dependencies.py

from typing import Type

from fastapi import Depends, Request

from fastapi_querybuilder.params import QueryParams

from .builder import build_query


def QueryBuilder(model: Type):
    def wrapper(request: Request, params: QueryParams = Depends()):
        return build_query(model, params)

    return Depends(wrapper)
