from sqlalchemy import cast, select, or_, asc, desc, String, Enum
from sqlalchemy.orm import RelationshipProperty
from fastapi import HTTPException
from .core import parse_filter_query, parse_filters, resolve_and_join_column_with_paths
from typing import List, Tuple, Dict, Any

# Performance optimization: Cache for column metadata (type info per model)
_COLUMN_METADATA_CACHE: Dict[int, Dict[str, Tuple[str, bool]]] = {}
# Format: model_id -> {column_name: (column_type_name, is_searchable)}


def build_query(cls, params):
    if hasattr(cls, 'deleted_at'):
        query = select(cls).where(cls.deleted_at.is_(None))
    else:
        query = select(cls)

    # Filters
    parsed_filters = parse_filter_query(params.filters)
    if parsed_filters:
        filter_expr, query = parse_filters(cls, parsed_filters, query)
        if filter_expr is not None:
            query = query.where(filter_expr)

    # Search - DEFAULT: Top-level model only, or EXPLICIT FIELDS
    if params.search:
        search_expr = []
        
        if params.search_fields:
            # EXPLICIT: Use specified field paths (can include nested relationships)
            try:
                parsed_paths = _parse_search_field_paths(params.search_fields)
                
                # Validate circular references
                _check_circular_references(parsed_paths, cls)
                
                # Build search expressions for explicit fields
                search_expr, query = _build_search_for_explicit_fields(
                    model_cls=cls,
                    parsed_paths=parsed_paths,
                    search_term=params.search,
                    query=query
                )
                
                # Apply optimized deduplication instead of DISTINCT for better performance
                has_joins = any(len(rel_path) > 0 for rel_path, _ in parsed_paths)
                if has_joins and search_expr:
                    # Use subquery deduplication instead of DISTINCT to avoid O(n log n) sort
                    query = _apply_optimized_deduplication(query, cls)
                    
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Error processing search_fields: {str(e)}"
                )
        else:
            # DEFAULT: Search only top-level model columns (no relationships)
            search_expr = _get_search_expressions_for_model(cls, params.search)
            
            # No DISTINCT needed for top-level search (no joins)
            # No joins are created, so we don't need DISTINCT

        if search_expr:
            query = query.where(or_(*search_expr))

    # Sorting
    if params.sort:
        sort_clauses = _parse_sort_clauses(params.sort)
        query = _apply_sorting(cls, query, sort_clauses)

    return query


def _apply_optimized_deduplication(query, model_cls):
    """
    Optimized deduplication using subquery instead of DISTINCT.
    Avoids expensive O(n log n) sorting for large result sets.
    """
    from sqlalchemy import select as sa_select
    
    # Get distinct IDs via subquery
    distinct_ids_subquery = sa_select(model_cls.id).distinct().subquery()
    
    # Filter to those IDs
    return query.where(model_cls.id.in_(sa_select(distinct_ids_subquery.c.id)))


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


def _apply_sorting(model_cls: Any, query: Any, sort_clauses: List[Tuple[List[str], str]]) -> Any:
    """Apply validated sort clauses to query with path-aware relationship joins."""
    if not sort_clauses:
        return query

    joins: Dict[Tuple[Tuple[str, ...], type], Any] = {}
    order_expressions = []

    for field_path, sort_dir in sort_clauses:
        try:
            column, query = resolve_and_join_column_with_paths(model_cls, field_path, query, joins)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Error resolving sort field '{'.'.join(field_path)}': {str(e)}",
            )

        order_expressions.append(asc(column) if sort_dir == "asc" else desc(column))

    return query.order_by(*order_expressions)


def _get_column_metadata(model_class) -> Dict[str, Tuple[str, bool]]:
    """
    Get cached column metadata for a model.
    Caches column type information to avoid repeated introspection.
    
    Returns: {column_name: (column_type_name, is_searchable)}
    """
    model_id = id(model_class)
    
    # Check cache first
    if model_id in _COLUMN_METADATA_CACHE:
        return _COLUMN_METADATA_CACHE[model_id]
    
    # Build metadata for all columns
    metadata = {}
    for column in model_class.__table__.columns:
        is_enum = isinstance(column.type, Enum)
        is_string = isinstance(column.type, String)
        is_integer = hasattr(column.type, "python_type") and column.type.python_type is int
        is_boolean = hasattr(column.type, "python_type") and column.type.python_type is bool
        
        is_searchable = is_enum or is_string or is_integer or is_boolean
        type_name = "enum" if is_enum else "string" if is_string else "integer" if is_integer else "boolean" if is_boolean else "other"
        
        metadata[column.name] = (type_name, is_searchable)
    
    # Cache the metadata
    _COLUMN_METADATA_CACHE[model_id] = metadata
    return metadata


def _get_search_expressions_for_model(model_class, search_term: str):
    """
    Helper function to get search expressions for a single model's columns.
    Uses cached column metadata for better performance.
    """
    expressions = []
    metadata = _get_column_metadata(model_class)  # Uses cache
    
    for column_name, (type_name, is_searchable) in metadata.items():
        if not is_searchable:
            continue
        
        column = getattr(model_class, column_name)
        
        if type_name == "enum":
            expressions.append(cast(column, String).ilike(f"%{search_term}%"))
        elif type_name == "string":
            expressions.append(column.ilike(f"%{search_term}%"))
        elif type_name == "integer":
            if search_term.isdigit():
                expressions.append(column == int(search_term))
        elif type_name == "boolean":
            if search_term.lower() in ("true", "false"):
                expressions.append(column == (search_term.lower() == "true"))
    
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
            rel_attr = getattr(current_model, rel_key, None)
            
            if rel_attr is None or not isinstance(rel_attr.property, RelationshipProperty):
                # Invalid relationship, will be caught later
                break
            
            next_model = rel_attr.property.mapper.class_
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
    query: Any
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
    joins = {}  # Use path-aware joins: (rel_path_tuple, model_class) -> alias
    
    for rel_path, col_name in parsed_paths:
        full_path = rel_path + [col_name]
        
        try:
            # Resolve the column with path-aware joining
            column, query = resolve_and_join_column_with_paths(
                model_cls,
                full_path,
                query,
                joins
            )
            
            # Generate search expression for the column
            col_type = column.type
            
            if is_enum_column(column):
                search_expressions.append(cast(column, String).ilike(f"%{search_term}%"))
            elif is_string_column(column):
                search_expressions.append(column.ilike(f"%{search_term}%"))
            elif is_integer_column(column):
                if search_term.isdigit():
                    search_expressions.append(column == int(search_term))
            elif is_boolean_column(column):
                if search_term.lower() in ("true", "false"):
                    search_expressions.append(column == (search_term.lower() == "true"))
            
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
    return hasattr(column.type, "python_type") and column.type.python_type is int


def is_boolean_column(column):
    """Check if a column is a boolean type"""
    return hasattr(column.type, "python_type") and column.type.python_type is bool