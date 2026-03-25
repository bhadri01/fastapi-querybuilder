# Changelog

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
