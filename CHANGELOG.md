# Changelog

## [0.1.18] - 2026-03-25

### Fixed
- PostgreSQL enum compatibility for case-insensitive filtering (`$eq`, `$ne`, `$in`) by using enum-safe text casting in generated SQL expressions
- Enum-safe case-insensitive string operators (`$contains`, `$ncontains`, `$startswith`, `$endswith`) to avoid enum type errors on PostgreSQL
- Enum columns are now excluded from timestamp-like string detection in sorting, preventing incorrect datetime casting based on field-name suffixes (`_at`, `_date`, `_on`)
- Release pipeline tag verification no longer fetches all tags in tag-triggered runs, preventing `would clobber existing tag` failures

### Added
- Regression tests for enum-safe filter operators on PostgreSQL SQL generation
- Regression tests for enum-safe sorting behavior and enum timestamp-like field guard
- Regression tests for enum-member input normalization in case-insensitive comparisons

### Documentation
- Updated README and HTML docs to document enum-safe case-insensitive behavior, sorting safeguards, and SQL examples with enum casting

## [0.1.17] - 2026-03-25

### Changed
- String filtering is now case-insensitive by default for `$eq`, `$ne`, and `$in`
- String sorting is now case-insensitive by default across root and nested relationship fields
- Added `case_sensitive` query parameter to restore legacy case-sensitive behavior when needed

### Improved
- Unified boolean search-term normalization using robust case folding

### Added
- Compatibility coverage tests for legacy case-sensitive mode
- SQL behavior tests for case-insensitive filter and sorting defaults

### Documentation
- Updated README with default case-insensitive behavior and `case_sensitive=true` examples
- Updated HTML docs (`docs/index.html`) with filtering/sorting compatibility guidance

## [0.1.16] - 2026-03-09

### Fixed
- Global date sorting correctness for timestamp-like fields (`created_at`, `updated_at`) when values are stored as strings
- Prevented lexicographic date ordering issues across months/years by applying datetime casting for timestamp-like string sort fields

### Added
- Regression tests for date-based sorting behavior:
	- Verifies timestamp-like string fields are sorted using datetime casting
	- Verifies regular string fields are not cast to datetime

### Documentation
- Updated README sorting examples with date-aware sorting usage
- Updated docs/index.html sorting section to document chronological sorting for timestamp-like fields

## [0.1.15] - 2026-03-09

### Added
- Multi-field sorting support with comma-separated sort clauses
- Double-underscore notation support for nested relationship sorting (for example `role__department__name:asc`)
- Strict sort direction validation with clear error messages
- Comprehensive test suite for sorting functionality (`tests/test_sorting.py`)
- LRU caching for performance optimization:
	- Column metadata caching (`_get_column_metadata`)
	- Filter query parsing cache (maxsize=1024)
	- Datetime parsing cache (maxsize=512)

### Changed
- Sorting parameter now strictly validates direction values (`asc`/`desc`)
- Refactored sorting implementation with dedicated parsing and apply helpers
- Optimized circular reference detection from O(n) to O(1) using sets
- Replaced DISTINCT with optimized subquery deduplication for better performance

### Fixed
- Sorting now properly handles multiple fields (for example `?sort=status:asc,created_at:desc`)
- Fixed nested relationship sorting to use path-aware joins preventing duplicate join errors

### Documentation
- Updated README with multi-sort examples and double-underscore notation
- Enhanced docs/index.html with expanded sorting examples and guidance

## [0.1.14] - 2026-02-17

### Added
- Smart filtering, sorting, and searching capabilities for FastAPI
- SQLAlchemy integration for query building
- Support for pagination with fastapi_pagination
- Type hints and `py.typed` marker for IDE/type-checker support
- Initial comprehensive documentation and examples

## [0.1.13] - 2025-11-05

### Changed
- Historical release tag present in repository.
- Detailed release notes were not preserved in the current changelog format.

## [0.1.12] - 2025-10-26

### Changed
- Historical release tag present in repository.
- Detailed release notes were not preserved in the current changelog format.

## [0.1.11] - 2025-09-18

### Changed
- Historical release tag present in repository.
- Detailed release notes were not preserved in the current changelog format.

## [0.1.10] - 2025-08-30

### Changed
- Historical release tag present in repository.
- Detailed release notes were not preserved in the current changelog format.

## [0.1.9] - 2025-06-09

### Changed
- Historical release tag present in repository.
- Detailed release notes were not preserved in the current changelog format.

## [0.1.8] - 2025-06-09

### Changed
- Historical release tag present in repository.
- Detailed release notes were not preserved in the current changelog format.

## [0.1.7] - 2025-06-08

### Changed
- Historical release tag present in repository.
- Detailed release notes were not preserved in the current changelog format.

## [0.1.6] - 2025-06-08

### Changed
- Historical release tag present in repository.
- Detailed release notes were not preserved in the current changelog format.

## [0.1.5] - 2025-06-08

### Changed
- Historical release tag present in repository.
- Detailed release notes were not preserved in the current changelog format.

## [0.1.4] - 2025-03-25

### Changed
- Historical release tag present in repository.
- Detailed release notes were not preserved in the current changelog format.
