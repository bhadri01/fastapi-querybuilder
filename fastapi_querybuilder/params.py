# fastapi_querybuilder/params.py

from typing import Optional
from fastapi import Query


class QueryParams:
    def __init__(
        self,
        filters: Optional[str] = Query(None, description="A JSON string representing filter conditions."),
        sort: Optional[str] = Query(
            None,
            description="e.g. name:asc, role.name:desc, role__department__name:asc"
        ),
        search: Optional[str] = Query(None, description="A string for global search. Searches only the root model's string/enum columns. To search related models, use search_fields parameter."),
        search_fields: Optional[str] = Query(
            None,
            description="Comma-separated field names and nested paths to search (e.g., name,email,role.name,role.department.name). "
            "If specified, only these exact fields are searched (can include nested relationships). "
            "If not specified, only the root model's string/enum columns are searched (no relationships)."
        ),
        case_sensitive: bool = Query(
            False,
            description="When true, uses legacy case-sensitive behavior for string filters and string sorting. "
            "Default false applies case-insensitive behavior."
        )
    ):
        self.filters = filters
        self.search = search
        self.sort = sort
        self.search_fields = search_fields
        self.case_sensitive = case_sensitive if isinstance(case_sensitive, bool) else False
