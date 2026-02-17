from sqlalchemy import cast, select, or_, asc, desc, String, Enum, inspect
from sqlalchemy.orm import RelationshipProperty
from fastapi import HTTPException
from .core import parse_filter_query, parse_filters, resolve_and_join_column, resolve_and_join_column_with_paths
from typing import List, Tuple, Set, Dict, Any


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
                
                # Apply DISTINCT only if joins were created (i.e., if any relationship path exists)
                has_joins = any(len(rel_path) > 0 for rel_path, _ in parsed_paths)
                if has_joins and search_expr:
                    query = query.distinct()
                    
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
        try:
            sort_field, sort_dir = params.sort.split(":")
        except ValueError:
            sort_field, sort_dir = params.sort, "asc"

        column = getattr(cls, sort_field, None)
        if column is None:
            nested_keys = sort_field.split(".")
            if len(nested_keys) > 1:
                joins = {}
                column, query = resolve_and_join_column(
                    cls, nested_keys, query, joins)
            else:
                raise HTTPException(
                    status_code=400, detail=f"Invalid sort field: {sort_field}")

        query = query.order_by(
            asc(column) if sort_dir.lower() == "asc" else desc(column))

    return query


def _apply_recursive_search(
    model_cls, 
    query, 
    search_term: str, 
    search_expr_list: list, 
    globally_processed_models: set,
    ancestry: frozenset, # A set of models in the path *above* this call
    joined_tables: set = None, # Track which tables have been joined globally
):
    """
    Recursively applies search logic to a model and its relationships,
    preventing circular recursion and duplicate joins.
    """
    
    # Initialize joined_tables set on first call
    if joined_tables is None:
        joined_tables = set()
    
    # --- 1. RECURSION PREVENTION (Top-level) ---
    # This check is technically redundant with the
    # check inside the loop, but good for safety.
    if model_cls in ancestry:
        return query
    
    # Add this model to the ancestry for *this branch's* recursive calls
    new_ancestry = ancestry | {model_cls}
    
    # --- 2. ADD SEARCH EXPRESSIONS ---
    # We only add expressions the *first* time we process a model.
    if model_cls not in globally_processed_models:
        search_expr_list.extend(
            _get_search_expressions_for_model(model_cls, search_term)
        )
        globally_processed_models.add(model_cls)


    # --- 3. INSPECT & RECURSE ---
    mapper = inspect(model_cls)
    
    for rel in mapper.relationships:
        
        related_model_class = rel.mapper.class_
        
        # --- CIRCULAR REFERENCE CHECK ---
        # Before joining, check if the model we are about to
        # join is already in our ancestry. If it is,
        # we are following a back-reference and must skip it.
        if related_model_class in ancestry:
            continue # Skip this relationship
        
        # --- DUPLICATE JOIN CHECK ---
        # Check if we've already joined to this related table
        # This prevents the "table name specified more than once" error
        # We use the related table name as the key since that's what 
        # SQL cares about when checking for duplicate table references
        related_table_name = related_model_class.__tablename__
        if related_table_name in joined_tables:
            # We've already joined this table from another path
            # Add search expressions for this model if not done yet
            # but skip the join to avoid duplicates
            if related_model_class not in globally_processed_models:
                search_expr_list.extend(
                    _get_search_expressions_for_model(related_model_class, search_term)
                )
                globally_processed_models.add(related_model_class)
            continue # Skip this join
        # --- END FIX ---

        # Get the relationship attribute from the current model
        rel_attr = getattr(model_cls, rel.key)
        
        # Add the JOIN
        query = query.join(rel_attr, isouter=True)
        joined_tables.add(related_table_name)

        # 4. Recurse into the related model
        query = _apply_recursive_search(
            model_cls=related_model_class, # The related model class
            query=query,
            search_term=search_term,
            search_expr_list=search_expr_list,
            globally_processed_models=globally_processed_models,
            ancestry=new_ancestry, # Pass the new ancestry down
            joined_tables=joined_tables, # Pass the joined tables set
        )
    
    # Return the modified query
    return query


def _get_search_expressions_for_model(model_class, search_term: str):
    """
    Helper function to get search expressions for a single model's columns.
    """
    expressions = []
    for column in model_class.__table__.columns:
        if is_enum_column(column):
            expressions.append(cast(column, String).ilike(f"%{search_term}%"))
        elif is_string_column(column):
            expressions.append(column.ilike(f"%{search_term}%"))
        elif is_integer_column(column):
            if search_term.isdigit():
                expressions.append(column == int(search_term))
        elif is_boolean_column(column):
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
    
    Args:
        parsed_paths: List of (relationship_path, column_name) tuples
        root_model: Root model class
        
    Raises:
        HTTPException(400) if circular reference detected
    """
    for rel_path, col_name in parsed_paths:
        if not rel_path:
            continue  # Top-level columns have no circular risk
        
        # Traverse the path and collect all models
        current_model = root_model
        models_in_path = [root_model]
        
        for rel_key in rel_path:
            rel_attr = getattr(current_model, rel_key, None)
            
            if rel_attr is None or not isinstance(rel_attr.property, RelationshipProperty):
                # Invalid relationship, will be caught later
                break
            
            next_model = rel_attr.property.mapper.class_
            
            # Check for circular reference
            if next_model in models_in_path:
                path_str = ".".join(rel_path + [col_name])
                raise HTTPException(
                    status_code=400,
                    detail=f"Circular reference in search_fields path: '{path_str}' - "
                    f"Model {next_model.__name__} appears multiple times in traversal path"
                )
            
            models_in_path.append(next_model)
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