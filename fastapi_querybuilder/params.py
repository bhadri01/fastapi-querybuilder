# fastapi_querybuilder/params.py

from typing import Optional
from fastapi import Query


class QueryParams:
    def __init__(
        self,
        filters: Optional[str] = Query(None, description="A JSON string representing filter conditions."),
        sort: Optional[str] = Query(None, description="e.g. name:asc or user__email:desc"),
        search: Optional[str] = Query(None, description="A string for global search. Searches only the root model's string/enum columns. To search related models, use search_fields parameter."),
        search_fields: Optional[str] = Query(
            None,
            description="Comma-separated field names and nested paths to search (e.g., name,email,role.name,role.department.name). "
            "If specified, only these exact fields are searched (can include nested relationships). "
            "If not specified, only the root model's string/enum columns are searched (no relationships)."
        )
    ):
        self.filters = filters
        self.search = search
        self.sort = sort
        self.search_fields = search_fields
