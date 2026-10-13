# fastapi_querybuilder/dependencies.py

from fastapi import Depends, Request
from .params import QueryParams
from .builder import build_query
from typing import Type


def QueryBuilder(model: Type, *, limits=None, policy=None):
    def wrapper(
        request: Request,
        params: QueryParams = Depends()
    ):
        return build_query(model, params, limits=limits, policy=policy)
    return Depends(wrapper)
