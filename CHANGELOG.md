# Changelog

## [0.1.15] - 2026-03-09

### Added
- Multi-field sorting support with comma-separated sort clauses
- Double-underscore notation support for nested relationship sorting (e.g., `role__department__name:asc`)
- Strict sort direction validation with clear error messages
- Comprehensive test suite for sorting functionality (`tests/test_sorting.py`)
- LRU caching for performance optimization:
  - Column metadata caching (`_get_column_metadata`)
  - Filter query parsing cache (maxsize=1024)
  - Datetime parsing cache (maxsize=512)

### Changed
- **Breaking improvement**: Sort parameter now strictly validates direction values (`asc`/`desc`)
- Refactored sorting implementation with dedicated `_parse_sort_clauses()` and `_apply_sorting()` functions
- Optimized circular reference detection from O(n) to O(1) using sets
- Replaced DISTINCT with optimized subquery deduplication for better performance
- Updated search deduplication to use optimized subquery approach

### Fixed
- **Major fix**: Sorting now properly handles multiple fields (e.g., `?sort=status:asc,created_at:desc`)
- Fixed nested relationship sorting to use path-aware joins preventing duplicate join errors
- Improved error messages for invalid sort fields and directions

### Documentation
- Updated README.md with multi-sort examples and double-underscore notation
- Enhanced docs/index.html with 6 sorting examples (was 4) and detailed info cards
- Updated API parameter descriptions to reflect new sorting capabilities
- Added sorting best practices and usage examples

## [0.1.14] - 2026-02-17

### Added
- Smart filtering, sorting, and searching capabilities for FastAPI
- SQLAlchemy integration for query building
- Support for pagination with fastapi_pagination
- Type hints and py.typed marker for better IDE support
- Comprehensive documentation with examples
- Support for Python 3.10, 3.11, and 3.12

### Features
- Query parameter extraction and validation
- Dynamic filter operators (equality, comparison, range, text search)
- Flexible sorting with multiple columns
- Chainable query builder API
- REST API compatibility

### Changed
- Version bumped from 0.1.13 to 0.1.14

## [0.1.0] - Initial Release

### Added
- Initial release of fastapi-querybuilder
- Core query building functionality
- Basic filter and sort support
- REST API integration examples
