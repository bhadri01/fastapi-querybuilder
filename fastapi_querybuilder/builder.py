from sqlalchemy import cast, select, or_, asc, desc, String, Enum, Date, DateTime, func, inspect, false, and_
from sqlalchemy.orm import aliased, RelationshipProperty
from fastapi import HTTPException
from .core import parse_filter_query, build_filter_expression, resolve_and_join_column_with_paths
from .security import QueryBudget, QueryLimits, QueryPolicy, reject
from typing import List, Tuple, Dict, Any
from weakref import WeakKeyDictionary

# Performance optimization: Cache for column metadata (type info per model)
_COLUMN_METADATA_CACHE: Any = WeakKeyDictionary()
# Format: model_id -> {column_name: (column_type_name, is_searchable)}


def build_query(cls, params, *, limits=None, policy=None):
    """Build a bounded query using trusted server-side limits and allowlists."""
    budget = QueryBudget(limits or QueryLimits(), policy or QueryPolicy())
    limits = budget.limits
    for name, maximum in (("search", limits.max_search_length),
                          ("search_fields", limits.max_search_fields * (limits.max_field_length + 1)),
                          ("sort", limits.max_sort_fields * (limits.max_field_length + 6))):
        value = getattr(params, name)
        if value is not None and (not isinstance(value, str) or len(value) > maximum):
            reject(f"Query {name} exceeds maximum length")
        if value is not None:
            try:
                value.encode('utf-8')
            except UnicodeEncodeError as exc:
                raise HTTPException(status_code=400, detail=f"Query {name} must be valid UTF-8") from exc

    query = select(cls)
    # This fixed server-owned attribute may be a mapped synonym or hybrid.
    if hasattr(cls, 'deleted_at'):
        query = query.where(cls.deleted_at.is_(None))

    parsed_filters = parse_filter_query(params.filters, limits=limits)
    if parsed_filters:
        expression = build_filter_expression(cls, parsed_filters, params.case_sensitive, budget)
        if expression is not None:
            query = query.where(expression)

    if params.search:
        if params.search_fields:
            if len(params.search_fields.split(',')) > limits.max_search_fields:
                reject("Query exceeds maximum search fields")
            paths = _parse_search_field_paths(params.search_fields)
            _check_circular_references(paths, cls)
            for relationships, column_name in paths:
                budget.check_path(relationships + [column_name], "search")
            # OR independent paths as separate EXISTS expressions. A no-match
            # search must not enumerate products of unrelated to-many collections.
            groups = {}
            for relationships, column_name in paths:
                groups.setdefault(tuple(relationships), []).append((relationships, column_name))
            all_expressions = []
            for relationships, group in groups.items():
                source = aliased(cls) if relationships else cls
                search_query = select(1).select_from(source)
                expressions, search_query = _build_search_for_explicit_fields(
                    source, group, params.search, search_query, budget=budget)
                if relationships and expressions:
                    mapper = inspect(cls).mapper
                    correlation = [getattr(source, mapper.get_property_by_column(pk).key) ==
                                   getattr(cls, mapper.get_property_by_column(pk).key)
                                   for pk in mapper.primary_key]
                    all_expressions.append(search_query.where(
                        *correlation, or_(*expressions)
                    ).correlate(cls).exists())
                else:
                    all_expressions.extend(expressions)
            query = query.where(or_(*all_expressions) if all_expressions else false())
        else:
            allowed = budget.policy.search_fields
            if allowed is None:
                candidates = [key for key, (_, searchable) in _get_column_metadata(cls).items()
                              if searchable]
            else:
                # Policies may name mapped synonyms as well as original columns.
                candidates = sorted(key for key in allowed if '.' not in key)
            if len(candidates) > limits.max_search_fields:
                reject("Query exceeds maximum search fields; configure explicit searchable fields")
            if allowed is None:
                expressions = _get_search_expressions_for_model(cls, params.search)
            else:
                expressions, _ = _build_search_for_explicit_fields(
                    cls, [([], key) for key in candidates], params.search,
                    select(1).select_from(cls), budget=budget)
            query = query.where(or_(*expressions) if expressions else false())

    if params.sort:
        if len(params.sort.split(',')) > limits.max_sort_fields:
            reject("Query exceeds maximum sort fields")
        clauses = _parse_sort_clauses(params.sort)
        sort_keys = []
        query = _apply_sorting(cls, query, clauses, case_sensitive=params.case_sensitive,
                               budget=budget, sort_keys=sort_keys)
        if any(len(path) > 1 for path, _ in clauses):
            query = _apply_optimized_deduplication(query, cls, sort_keys)
    return query


def _apply_optimized_deduplication(query, model_cls, sort_keys=None):
    """Select one ordered joined row per complete mapped primary key.

    Windowing deduplicates before caller LIMIT/OFFSET without DISTINCT on JSON or
    PostgreSQL's DISTINCT/ORDER BY restrictions. A to-many sort uses its first row
    in the requested lexicographic ordering (minimum for ASC, maximum for DESC).
    """
    sort_keys = sort_keys or []
    mapper = inspect(model_cls).mapper
    primary_keys = [getattr(model_cls, mapper.get_property_by_column(pk).key)
                    for pk in mapper.primary_key]
    order = [asc(expr) if direction == "asc" else desc(expr)
             for expr, direction in sort_keys]
    row_number = func.row_number().over(partition_by=primary_keys,
                                        order_by=order or primary_keys).label(None)
    labels = [expr.label(None) for expr, _ in sort_keys]
    rows = query.order_by(None).add_columns(row_number, *labels).subquery()
    # Keep the original mapped entity in the outer SELECT so callers may append
    # tenant/authorization WHERE clauses using Model.column without a cartesian join.
    identity = and_(*[column == rows.corresponding_column(column) for column in primary_keys])
    result = select(model_cls).join(rows, identity).where(rows.corresponding_column(row_number) == 1)
    for label, (_, direction) in zip(labels, sort_keys):
        column = rows.corresponding_column(label)
        result = result.order_by(asc(column) if direction == "asc" else desc(column))
    return result


def _parse_sort_clauses(sort_value: str) -> List[Tuple[List[str], str]]:
    """
    Parse sort query string into sort clauses.

    Supports:
    - single field: "name" or "name:desc"
    - nested field: "role.name:asc" or "role__name:asc"
    - multi-sort: "name:asc,created_at:desc"

    Returns:
        List of tuples: [([path_parts], direction), ...]
    """
    if not sort_value or not sort_value.strip():
        return []

    parsed: List[Tuple[List[str], str]] = []
    clauses = [clause.strip() for clause in sort_value.split(",") if clause.strip()]

    if not clauses:
        raise HTTPException(status_code=400, detail="Sort value cannot be empty")

    for clause in clauses:
        if ":" in clause:
            parts = clause.split(":", 1)
            raw_field = parts[0].strip()
            raw_dir = parts[1].strip().lower() or "asc"
        else:
            raw_field = clause.strip()
            raw_dir = "asc"

        if not raw_field:
            raise HTTPException(status_code=400, detail=f"Invalid sort clause: '{clause}'")

        if raw_dir not in {"asc", "desc"}:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid sort direction '{raw_dir}' for field '{raw_field}'. Use 'asc' or 'desc'.",
            )

        # Support both dot and double-underscore notation for relationships.
        normalized_field = raw_field.replace("__", ".")
        path_parts = [part.strip() for part in normalized_field.split(".")]

        if any(not part for part in path_parts):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid sort field path '{raw_field}'",
            )

        parsed.append((path_parts, raw_dir))

    return parsed


def _apply_sorting(
    model_cls: Any,
    query: Any,
    sort_clauses: List[Tuple[List[str], str]],
    case_sensitive: bool = False,
    *,
    budget=None,
    sort_keys=None,
) -> Any:
    """Apply validated sort clauses to query with path-aware relationship joins."""
    if not sort_clauses:
        return query

    joins: Dict[Tuple[Tuple[str, ...], type], Any] = {}
    order_expressions = []

    for field_path, sort_dir in sort_clauses:
        try:
            column, query = resolve_and_join_column_with_paths(model_cls, field_path, query, joins,
                                                            budget=budget, operation="sort")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Error resolving sort field '{'.'.join(field_path)}': {str(e)}",
            )

        sort_expression = _get_sort_expression(column, field_path, case_sensitive=case_sensitive)
        if sort_keys is not None:
            sort_keys.append((sort_expression, sort_dir))
        order_expressions.append(asc(sort_expression) if sort_dir == "asc" else desc(sort_expression))

    return query.order_by(*order_expressions)


def _get_sort_expression(column: Any, field_path: List[str], case_sensitive: bool = False) -> Any:
    """
    Return a DB expression suitable for sorting.

    Date/time columns are sorted directly.
    For string timestamp-like fields (e.g. created_at, updated_at), use a
    datetime expression to avoid lexicographic mis-ordering across months/years.
    """
    if _is_datetime_like_column(column):
        return column

    if _is_string_timestamp_like_field(column, field_path):
        return cast(column, DateTime)

    if not case_sensitive:
        if is_enum_column(column):
            return func.lower(cast(column, String))
        if is_string_column(column):
            return func.lower(column)

    return column


def _is_datetime_like_column(column: Any) -> bool:
    col_type = getattr(column, "type", None)
    return isinstance(col_type, (Date, DateTime))


def _is_string_timestamp_like_field(column: Any, field_path: List[str]) -> bool:
    # Enum can subclass String, but enum values must not be cast as datetime.
    if is_enum_column(column):
        return False

    col_type = getattr(column, "type", None)
    if not isinstance(col_type, String):
        return False

    field_name = field_path[-1].lower() if field_path else ""
    return (
        field_name.endswith("_at")
        or field_name.endswith("_date")
        or field_name.endswith("_on")
        or field_name in {"date", "datetime", "timestamp"}
    )


def _get_column_metadata(model_class) -> Dict[str, Tuple[str, bool]]:
    """
    Get cached column metadata for a model.
    Caches column type information to avoid repeated introspection.
    
    Returns: {column_name: (column_type_name, is_searchable)}
    """
    model_id = inspect(model_class).mapper.class_
    
    # Check cache first
    if model_id in _COLUMN_METADATA_CACHE:
        return _COLUMN_METADATA_CACHE[model_id]
    
    # Build metadata for all columns
    metadata = {}
    for property_ in inspect(model_class).mapper.column_attrs:
        column = getattr(model_class, property_.key)
        is_enum = isinstance(column.type, Enum)
        is_string = isinstance(column.type, String)
        is_integer = is_integer_column(column)
        is_boolean = is_boolean_column(column)
        
        is_searchable = is_enum or is_string or is_integer or is_boolean
        type_name = "enum" if is_enum else "string" if is_string else "integer" if is_integer else "boolean" if is_boolean else "other"
        
        metadata[property_.key] = (type_name, is_searchable)
    
    # Cache the metadata
    _COLUMN_METADATA_CACHE[model_id] = metadata
    return metadata


def _get_search_expressions_for_model(model_class, search_term: str, *, allowed_fields=None):
    """
    Helper function to get search expressions for a single model's columns.
    Uses cached column metadata for better performance.
    """
    expressions = []
    metadata = _get_column_metadata(model_class)  # Uses cache
    
    for column_name, (type_name, is_searchable) in metadata.items():
        if not is_searchable or (allowed_fields is not None and column_name not in allowed_fields):
            continue
        
        column = getattr(model_class, column_name)
        
        if type_name == "enum":
            expressions.append(cast(column, String).ilike(f"%{search_term}%"))
        elif type_name == "string":
            expressions.append(column.ilike(f"%{search_term}%"))
        elif type_name == "integer":
            value = _integer_search_value(search_term)
            if value is not None:
                expressions.append(column == value)
        elif type_name == "boolean":
            if _is_boolean_search_term(search_term):
                expressions.append(column == (_normalize_boolean_search_term(search_term) == "true"))
    
    return expressions


def _parse_search_field_paths(search_fields_str: str) -> List[Tuple[List[str], str]]:
    """
    Parse comma-separated search field paths into structured format.
    
    Args:
        search_fields_str: e.g., "name,email,role.name,role.department.name"
        
    Returns:
        List of tuples: [(relationship_path, column_name), ...]
        e.g., [([], 'name'), ([], 'email'), (['role'], 'name'), (['role', 'department'], 'name')]
        
    Raises:
        HTTPException(400) if format is invalid
    """
    if not search_fields_str or not search_fields_str.strip():
        return []
    
    parsed_paths = []
    seen_paths = set()  # For deduplication
    
    fields = [f.strip() for f in search_fields_str.split(",") if f.strip()]
    
    for field in fields:
        parts = field.split(".")
        
        if not parts or not parts[-1]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid search field path: '{field}' - must contain a column name"
            )
        
        # Last part is the column name, everything else is the relationship path
        relationship_path = parts[:-1]
        column_name = parts[-1]
        
        # Check for empty parts (e.g., "role..name" or ".name")
        if any(not part for part in parts):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid search field path: '{field}' - contains empty parts"
            )
        
        # Deduplicate
        path_key = (tuple(relationship_path), column_name)
        if path_key in seen_paths:
            continue
        seen_paths.add(path_key)
        
        parsed_paths.append((relationship_path, column_name))
    
    return parsed_paths


def _check_circular_references(parsed_paths: List[Tuple[List[str], str]], root_model: Any) -> None:
    """
    Validate that no parsed path contains circular references.
    Optimized to use sets for O(1) lookup instead of lists (O(n)).
    
    Args:
        parsed_paths: List of (relationship_path, column_name) tuples
        root_model: Root model class
        
    Raises:
        HTTPException(400) if circular reference detected
    """
    for rel_path, col_name in parsed_paths:
        if not rel_path:
            continue  # Top-level columns have no circular risk
        
        # Traverse the path and collect all model IDs (set for O(1) lookup)
        current_model = root_model
        model_ids_in_path = {id(root_model)}  # Use set of model IDs (much faster)
        
        for rel_key in rel_path:
            mapper = inspect(current_model).mapper
            descriptor = getattr(current_model, rel_key) if rel_key in mapper.attrs else None
            relationship = getattr(descriptor, 'property', None)

            if not isinstance(relationship, RelationshipProperty):
                # Invalid relationship, will be caught later
                break
            
            next_model = relationship.mapper.class_
            model_id = id(next_model)
            
            # Check for circular reference (O(1) with set)
            if model_id in model_ids_in_path:
                path_str = ".".join(rel_path + [col_name])
                raise HTTPException(
                    status_code=400,
                    detail=f"Circular reference in search_fields path: '{path_str}' - "
                    f"Model {next_model.__name__} appears multiple times in traversal path"
                )
            
            model_ids_in_path.add(model_id)
            current_model = next_model


def _build_search_for_explicit_fields(
    model_cls: Any,
    parsed_paths: List[Tuple[List[str], str]],
    search_term: str,
    query: Any,
    *,
    budget=None,
) -> Tuple[Any, Any]:
    """
    Build search expressions for explicitly specified field paths.
    
    Args:
        model_cls: Root model class
        parsed_paths: List of (relationship_path, column_name) tuples from _parse_search_field_paths
        search_term: Search term string
        query: SQLAlchemy Select query
        
    Returns:
        Tuple of (search_expression_list, modified_query)
    """
    search_expressions = []
    joins: Dict[Tuple[Tuple[str, ...], type], Any] = {}  # Use path-aware joins: (rel_path_tuple, model_class) -> alias
    
    for rel_path, col_name in parsed_paths:
        full_path = rel_path + [col_name]
        
        try:
            # Resolve the column with path-aware joining
            column, query = resolve_and_join_column_with_paths(
                model_cls,
                full_path,
                query,
                joins,
                budget=budget,
                operation="search",
            )
            
            # Generate search expression for the column
            if is_enum_column(column):
                search_expressions.append(cast(column, String).ilike(f"%{search_term}%"))
            elif is_string_column(column):
                search_expressions.append(column.ilike(f"%{search_term}%"))
            elif is_integer_column(column):
                value = _integer_search_value(search_term)
                if value is not None:
                    search_expressions.append(column == value)
            elif is_boolean_column(column):
                if _is_boolean_search_term(search_term):
                    search_expressions.append(column == (_normalize_boolean_search_term(search_term) == "true"))
            
        except HTTPException:
            # Re-raise invalid column/relationship errors
            raise
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Error resolving search field '{'.'.join(full_path)}': {str(e)}"
            )
    
    return search_expressions, query


def is_enum_column(column):
    """Check if a column is an enum type"""
    return isinstance(column.type, Enum)


def is_string_column(column):
    """Check if a column is a string type"""
    return isinstance(column.type, String)


def is_integer_column(column):
    """Check if a column is an integer type"""
    return _python_type(column) is int


def is_boolean_column(column):
    """Check if a column is a boolean type"""
    return _python_type(column) is bool


def _normalize_boolean_search_term(search_term: str) -> str:
    return search_term.casefold()


def _is_boolean_search_term(search_term: str) -> bool:
    return _normalize_boolean_search_term(search_term) in ("true", "false")

def _python_type(column):
    try:
        return column.type.python_type
    except (AttributeError, NotImplementedError):
        return None


def _integer_search_value(search_term):
    # Common SQL integer binders accept signed 64-bit values. Longer numeric
    # text may still match string columns but must not overflow an integer bind.
    if not search_term.isdecimal():
        return None
    # Unicode decimal digits are valid Python integer input too. Normalization
    # keeps zero-padded values compatible without parsing arbitrarily long ints.
    import unicodedata
    digits = "".join(str(unicodedata.decimal(char)) for char in search_term).lstrip("0") or "0"
    if len(digits) > 19:
        return None
    value = int(digits)
    return value if value <= 2**63 - 1 else None
