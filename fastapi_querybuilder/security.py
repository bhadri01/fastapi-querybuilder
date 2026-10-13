"""Server-owned query budgets and field policies (never HTTP parameters)."""

from dataclasses import dataclass, fields
from typing import FrozenSet, Optional, NoReturn

from fastapi import HTTPException


@dataclass(frozen=True)
class QueryLimits:
    """Finite per-request budgets. Raise limits deliberately for trusted workloads."""

    max_filter_bytes: int = 16_384
    max_filter_depth: int = 8
    max_predicates: int = 100
    max_in_items: int = 100
    max_relationship_depth: int = 4
    max_joins: int = 8
    max_search_length: int = 256
    max_search_fields: int = 20
    max_sort_fields: int = 10
    max_field_length: int = 256

    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field.name} must be a non-negative integer")


@dataclass(frozen=True)
class QueryPolicy:
    """Exact dotted allowlists. None allows mapped fields; an empty set allows none.

    Relationships lists allowed relationship prefixes, for example both ``role``
    and ``role.department`` for the field ``role.department.name``.
    """

    filter_fields: Optional[FrozenSet[str]] = None
    search_fields: Optional[FrozenSet[str]] = None
    sort_fields: Optional[FrozenSet[str]] = None
    relationships: Optional[FrozenSet[str]] = None

    def __post_init__(self):
        for field in fields(self):
            values = getattr(self, field.name)
            if values is not None:
                if isinstance(values, str):
                    raise ValueError(f"{field.name} must be a collection of paths")
                values = frozenset(values)
                if any(not isinstance(path, str) or not path or
                       any(not part.isidentifier() or part.startswith('_')
                           for part in path.split('.')) for path in values):
                    raise ValueError(f"{field.name} must contain exact dotted paths")
                object.__setattr__(self, field.name, values)


class QueryBudget:
    def __init__(self, limits: QueryLimits, policy: QueryPolicy):
        self.limits = limits
        self.policy = policy
        self.joins = 0

    def add_join(self):
        self.joins += 1
        if self.joins > self.limits.max_joins:
            reject("Query exceeds maximum relationship joins")

    def check_path(self, parts, operation):
        path = '.'.join(parts)
        if (not parts or len(path) > self.limits.max_field_length or
                any(not part.isidentifier() or part.startswith('_') for part in parts)):
            reject("Invalid field path")
        if len(parts) - 1 > self.limits.max_relationship_depth:
            reject("Query exceeds maximum relationship depth")
        allowed = getattr(self.policy, f"{operation}_fields")
        if allowed is not None and path not in allowed:
            reject(f"Field is not allowed for {operation}")
        relationships = self.policy.relationships
        if relationships is not None:
            for i in range(1, len(parts)):
                if '.'.join(parts[:i]) not in relationships:
                    reject("Relationship is not allowed")


def reject(detail) -> NoReturn:
    raise HTTPException(status_code=400, detail=detail)
