from sqlalchemy import cast, select, or_, asc, desc, String, Enum, inspect
from fastapi import HTTPException
from .core import parse_filter_query, parse_filters, resolve_and_join_column


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

    # Search - NOW RECURSIVE (with loop prevention)
    if params.search:
        search_expr = []
        
        globally_processed_models = set()

        # Call the new recursive helper
        query = _apply_recursive_search(
            model_cls=cls,
            query=query,
            search_term=params.search,
            search_expr_list=search_expr,
            globally_processed_models=globally_processed_models,
            # Pass a frozenset of models in the *current* recursive path
            ancestry=frozenset() 
        )

        if search_expr:
            # Apply the combined OR conditions from all models
            query = query.where(or_(*search_expr))
            
            # Add DISTINCT to avoid duplicates
            query = query.distinct()

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