# FastAPI QueryBuilder

[![PyPI version](https://img.shields.io/pypi/v/fastapi-querybuilder.svg)](https://pypi.org/project/fastapi-querybuilder/)  [![PyPI Downloads](https://static.pepy.tech/personalized-badge/fastapi-querybuilder?period=total&units=INTERNATIONAL_SYSTEM&left_color=GRAY&right_color=GREEN&left_text=downloads)](https://pepy.tech/projects/fastapi-querybuilder)

**Python 3.10+** | **License: MIT**

A powerful, flexible query builder for FastAPI applications with SQLAlchemy. Easily add filtering, sorting, and searching capabilities to your API endpoints with minimal code.

---

## ✨ Features

- **🔍 Advanced Filtering** — JSON-based filters with 14 comparison and 2 logical operators
- **🔄 Dynamic Sorting** — Sort by any field, including nested relationships
- **🔎 Controlled Search** — Root-model search with explicit related fields and server allowlists
- **🔗 Relationship Support** — Query nested relationships with automatic joins
- **📄 Pagination Ready** — Works seamlessly with [fastapi-pagination](https://github.com/uriyyo/fastapi-pagination)
- **🗑️ Soft Delete Support** — Automatically excludes soft-deleted records with `deleted_at` field
- **📅 Smart Date Handling** — Automatic date range processing for date-only strings
- **⚡ High Performance** — Efficient SQLAlchemy query generation with optimized joins

---

## 📋 Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage Guide](#usage-guide)
  - [Basic Setup](#basic-setup)
  - [Filtering](#filtering)
  - [Sorting](#sorting)
  - [Searching](#searching)
  - [Pagination](#pagination)
- [Security and Query Limits](#security-and-query-limits)
- [Operator Reference](#operator-reference)
- [Examples](#examples)
- [Developer Guide](#developer-guide)
  - [Running the Example Application](#running-the-example-application)
  - [Contributing](#contributing)
- [License](#license)

---

## Security and Query Limits

Treat client query strings as untrusted. Every `QueryBuilder`/`build_query` call
has finite defaults, including calls made outside FastAPI. Rejected paths,
malformed filter structures, disallowed fields, and over-budget queries raise HTTP 400.
Database-specific value/type constraints still belong in application validation.

Pass limits and allowlists from application code, never from request parameters:

```python
from fastapi_querybuilder import QueryBuilder, QueryLimits, QueryPolicy

USER_QUERY_POLICY = QueryPolicy(
    filter_fields={"name", "age", "role.name"},
    search_fields={"name", "role.name"},
    sort_fields={"name", "created_at"},
    relationships={"role"},
)

@app.get("/users")
async def users(
    query=QueryBuilder(
        User,
        policy=USER_QUERY_POLICY,
        limits=QueryLimits(max_predicates=30, max_joins=4),
    ),
    session: AsyncSession = Depends(get_db),
):
    # Authentication and tenant/row authorization remain your responsibility.
    query = query.where(User.tenant_id == current_tenant_id)
    return (await session.execute(query.limit(50))).scalars().all()
```

`build_query(User, params, policy=..., limits=...)` accepts the same options.
Each optional allowlist defaults to `None` for backward-compatible mapped-field
access; an empty collection permits no fields/relationships. Allowlists contain
exact, case-sensitive dotted paths, with no wildcard expansion. Every traversed
relationship prefix must be listed: `role.department.name` needs both `role`
and `role.department`. Sort `role__name` is normalized to `role.name`. Default
search uses only allowed root fields; an empty or inapplicable search allowlist
matches no rows. Explicit disallowed fields raise HTTP 400. These policies do
not redact returned model columns or replace row-level authorization.

| Budget | Default |
| --- | ---: |
| UTF-8 filter JSON bytes (`max_filter_bytes`) | 16,384 |
| Filter dictionary depth (`max_filter_depth`, root is 1) | 8 |
| Comparison predicates (`max_predicates`) | 100 |
| Items per `$in` / `$isanyof` list (`max_in_items`) | 100 |
| Relationships in one field path (`max_relationship_depth`) | 4 |
| Total relationship joins across filters/search/sort (`max_joins`) | 8 |
| Search characters (`max_search_length`) | 256 |
| Search fields (`max_search_fields`) | 20 |
| Sort fields (`max_sort_fields`) | 10 |
| Characters in a field path (`max_field_length`) | 256 |

Logical group counts are bounded alongside predicates. Membership operands must
be flat lists of scalar values. Integer-column operands must fit signed 64-bit
integers; larger numeric search terms only participate in string searches. Limits can be raised deliberately with a
`QueryLimits` instance; they cannot be disabled by a client. Applications with
more than 20 default-searchable columns should configure a narrower search
allowlist or explicitly raise the budget.

Relationship filters keep each logical dictionary's scope: two conditions in
one dictionary refer to the same joined child, while separate `$and` branches
may match different children. Correlated EXISTS avoids multiplying outer rows.
Relationship sorting uses SQL window functions to choose the first related row
in the requested lexicographic order (minimum for ascending, maximum for
descending), returning one root before LIMIT/OFFSET/count. Composite and non-`id`
primary keys are supported. Root-model `.where(...)` clauses remain composable.
Sorting requires a database with window-function support (SQLite 3.25+,
PostgreSQL, MySQL 8+); NULL ordering follows the database. Use a root primary-key
sort as a final tie-breaker for stable pagination.

These are query-construction limits, not a database execution-time guarantee.
Add authentication, tenant/row authorization, response pagination, rate limits,
request-size limits at your gateway, appropriate indexes, and database statement
timeouts. Substring searches can still scan large tables. Protect sensitive
columns with explicit allowlists even if they are not returned in responses.
The example app is for local demonstrations, not an authenticated production API.

### Compatibility notes

Oversized queries previously accepted now return HTTP 400; mapped columns are
required at the end of every field path. Invalid suffixes and Python attributes
are no longer silently accepted. Searches with no applicable expression now
match no rows rather than returning an unfiltered result. Relationship queries
return unique roots; consumers should not rely on duplicate rows. Poetry is a
development/build tool only and is no longer installed with the runtime package.
This unreleased change updates dependency security floors; review the lockfile
and run integration tests in your application before upgrading.

### Verification

```bash
pipx install poetry==2.5.1
poetry sync --with dev
poetry run pytest
poetry run ruff check fastapi_querybuilder
poetry run mypy
poetry run python -m build
poetry run pip-audit --skip-editable
```

The PR workflow runs tests on Python 3.10–3.14, plus lint, typing, build, and
dependency auditing. The release workflow still requires a separately pushed
version tag; this change does not publish a release.

---

## 🚀 Installation

```bash
pip install fastapi-querybuilder
```

**Requirements:**

- Python 3.10+
- FastAPI 0.135.2+ (with compatible Starlette 1.3.1+)
- SQLAlchemy 2.0+
- fastapi-pagination 0.13.2+

---

## ⚡ Quick Start

### Basic Endpoint with QueryBuilder

```python
from fastapi import FastAPI, Depends
from fastapi_querybuilder import QueryBuilder
from sqlalchemy.ext.asyncio import AsyncSession

app = FastAPI()

@app.get("/users")
async def get_users(
    query=QueryBuilder(User),
    session: AsyncSession = Depends(get_db)
):
    result = await session.execute(query)
    return result.scalars().all()
```

### Your endpoint now supports:

```bash
# Advanced filtering
GET /users?filters={"name": {"$eq": "John"}, "age": {"$gte": 18}}

# Dynamic sorting
GET /users?sort=name:asc

# Global search across all fields and relationships
GET /users?search=john

# Combined usage
GET /users?filters={"is_active": {"$eq": true}}&search=admin&sort=created_at:desc
```

---

## 📚 Usage Guide

### Basic Setup

#### 1. Define Your Models

```python
from sqlalchemy import String, ForeignKey, DateTime, Boolean, Integer, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship, declarative_base
from datetime import datetime, timezone
from enum import Enum as PyEnum

Base = declarative_base()

class StatusEnum(str, PyEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"

class Department(Base):
    __tablename__ = "departments"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    
    roles: Mapped[list["Role"]] = relationship("Role", back_populates="department")

class Role(Base):
    __tablename__ = "roles"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    
    users: Mapped[list["User"]] = relationship("User", back_populates="role")
    department: Mapped["Department"] = relationship("Department", back_populates="roles", lazy="selectin")

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    age: Mapped[int] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[StatusEnum] = mapped_column(SQLEnum(StatusEnum), default=StatusEnum.ACTIVE)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    deleted_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)  # Soft delete support
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    
    role: Mapped["Role"] = relationship("Role", back_populates="users", lazy="selectin")
```

**Note:** If your model has a `deleted_at` field, QueryBuilder automatically excludes soft-deleted records (`WHERE deleted_at IS NULL`).

#### 2. Create Your Endpoints

```python
from fastapi import FastAPI, Depends
from fastapi_querybuilder import QueryBuilder
from sqlalchemy.ext.asyncio import AsyncSession

app = FastAPI()

@app.get("/users")
async def get_users(
    query=QueryBuilder(User),
    session: AsyncSession = Depends(get_db)
):
    """
    Get users with advanced filtering, sorting, and searching.
    
    Query Parameters:
    - filters: JSON string for filtering (e.g., {"name": {"$eq": "John"}})
    - sort: Sort field and direction (e.g., "name:asc" or "role.name:desc")
    - search: Global search term across all fields and relationships
    - case_sensitive: Set to true to use legacy case-sensitive string filters/sorting
    """
    result = await session.execute(query)
    return result.scalars().all()
```

---

### Filtering

#### Basic Filtering

String filters are case-insensitive by default for `$eq`, `$ne`, and `$in`.
Set `case_sensitive=true` to use legacy case-sensitive string filtering.

For SQL enum columns (common in PostgreSQL), case-insensitive comparisons are enum-safe:
- `$eq`, `$ne`, `$in` cast enum fields to text before case-insensitive comparison
- enum-member values (not just plain strings) are normalized correctly

```bash
# Single condition
GET /users?filters={"name": {"$eq": "John Doe"}}

# Multiple conditions (implicit AND)
GET /users?filters={"age": {"$gte": 18}, "is_active": {"$eq": true}}

# Array values
GET /users?filters={"status": {"$in": ["active", "pending"]}}

# Legacy case-sensitive filtering
GET /users?filters={"name": {"$eq": "John"}}&case_sensitive=true
```

#### Logical Operators

```bash
# OR condition
GET /users?filters={"$or": [{"name": {"$contains": "john"}}, {"email": {"$contains": "john"}}]}

# Complex AND/OR combinations
GET /users?filters={
  "$and": [
    {"age": {"$gte": 18}},
    {
      "$or": [
        {"status": {"$eq": "active"}},
        {"status": {"$eq": "pending"}}
      ]
    }
  ]
}
```

#### Nested Relationship Filtering

```bash
# Filter by relationship field
GET /users?filters={"role.name": {"$eq": "admin"}}

# Deep nesting
GET /users?filters={"role.department.name": {"$contains": "Engineering"}}

# Multiple relationship conditions
GET /users?filters={
  "role.name": {"$eq": "admin"},
  "role.department.name": {"$contains": "Engineering"}
}
```

#### Date Filtering

```bash
# Date-only string (matches entire day)
GET /users?filters={"created_at": {"$eq": "2023-12-01"}}
# Equivalent to: created_at >= '2023-12-01 00:00:00' AND created_at < '2023-12-02 00:00:00'

# Exact datetime
GET /users?filters={"created_at": {"$eq": "2023-12-01T10:30:00"}}

# Date ranges
GET /users?filters={"created_at": {"$gte": "2023-01-01", "$lt": "2024-01-01"}}

# Supported date formats:
# - "2023-12-01" (YYYY-MM-DD)
# - "2023-12-01T10:30:00" (ISO format)
# - "2023-12-01 10:30:00" (Space separated)
# - "2023-12-01T10:30:00Z" (UTC)
```

---

### Sorting

#### Basic Sorting

String sorting is case-insensitive by default.
Set `case_sensitive=true` to use legacy case-sensitive text ordering.

Enum sorting is also handled safely in case-insensitive mode by casting enum values to text first.
Enum fields are never treated as timestamp-like string fields, even if their names end with `_at`, `_date`, or `_on`.

```bash
# Ascending order (default)
GET /users?sort=name:asc
GET /users?sort=name  # :asc is optional

# Descending order
GET /users?sort=created_at:desc

# Legacy case-sensitive string sort
GET /users?sort=name:asc&case_sensitive=true

# Multiple sort clauses (applied left to right)
GET /users?sort=status:asc,created_at:desc

# Date-aware sorting for timestamp-like string fields
# (e.g., created_at/updated_at stored as strings)
GET /users?sort=created_at:desc,updated_at:asc
```

#### Relationship Sorting

```bash
# Sort by relationship field
GET /users?sort=role.name:asc

# Deep relationship sorting
GET /users?sort=role.department.name:desc

# Double-underscore notation is also supported
GET /users?sort=role__department__name:desc
```

---

### Searching

**Smart Search with Explicit Field Control** — QueryBuilder provides powerful search capabilities with performance optimization:

#### Default Search Behavior (Top-Level Only)

By default, search **only searches the root model's fields** for optimal performance:

```bash
# Searches only User model fields (name, email, status, age, is_active)
GET /users?search=john

# Fast and predictable - no joins, no DISTINCT overhead
# 5-100x faster than recursive search
```

#### Explicit Field Search with `search_fields`

Use the `search_fields` parameter to control exactly which fields to search, including nested relationships:

```bash
# Search only specific top-level fields
GET /users?search=john&search_fields=name,email

# Search in related models using dot notation
GET /users?search=admin&search_fields=name,role.name

# Search deeply nested relationships
GET /users?search=Engineering&search_fields=role.department.name

# Mix top-level and nested fields
GET /users?search=dev&search_fields=name,email,role.name,role.department.name
```

**Nested Field Notation:**
- Use dots (`.`) to traverse relationships: `role.name`, `role.department.name`
- Automatically creates necessary joins only for specified paths
- Uses correlated EXISTS for relationship search so each root appears once
- Supports multiple paths to the same model
- Prevents circular references

**Search Behavior by Field Type:**

- **String fields**: Case-insensitive partial matching (`ILIKE '%term%'`)
- **Enum fields**: Matches if any enum value contains the search term
- **Integer fields**: Exact match if search term is a valid number
- **Boolean fields**: Matches if search term is "true" or "false"

**Performance Benefits:**

- **Default behavior**: root-model search avoids relationship joins
- **Explicit fields**: Only creates joins for specified nested paths
- **Predictable results**: relationship filters/search use correlated EXISTS; related sorting deduplicates before pagination
- **Predictable results**: Know exactly which fields are being searched

```bash
# Examples with filtering and sorting
GET /users?search=admin&search_fields=name,role.name&filters={"is_active": {"$eq": true}}&sort=created_at:desc

# Search in department names only
GET /users?search=Engineering&search_fields=role.department.name

# Complex multi-field search
GET /users?search=tech&search_fields=name,email,role.name,role.department.name,role.department.description
```

---

### Pagination

#### With fastapi-pagination

```python
from fastapi_pagination import Page, add_pagination
from fastapi_pagination.ext.sqlalchemy import paginate

@app.get("/users/paginated", response_model=Page[UserResponse])
async def get_users_paginated(
    query=QueryBuilder(User),
    session: AsyncSession = Depends(get_db)
):
    return await paginate(session, query)

# Add pagination to your app
add_pagination(app)
```

#### Usage with Pagination

```bash
# Basic pagination
GET /users/paginated?page=1&size=10

# With filtering and sorting
GET /users/paginated?page=2&size=20&filters={"is_active": {"$eq": true}}&sort=name:asc

# With search
GET /users/paginated?page=1&size=50&search=john&sort=created_at:desc
```

---

## 🔧 Operator Reference

### Comparison Operators

| Operator | Description | Example | SQL Equivalent |
|----------|-------------|---------|----------------|
| `$eq` | Equal to | `{"age": {"$eq": 25}}` | `LOWER(name) = 'john'` / `LOWER(CAST(status AS VARCHAR)) = 'active'` |
| `$ne` | Not equal to | `{"status": {"$ne": "inactive"}}` | `LOWER(name) != 'inactive'` / `LOWER(CAST(status AS VARCHAR)) != 'inactive'` |
| `$gt` | Greater than | `{"age": {"$gt": 18}}` | `age > 18` |
| `$gte` | Greater than or equal | `{"age": {"$gte": 21}}` | `age >= 21` |
| `$lt` | Less than | `{"age": {"$lt": 65}}` | `age < 65` |
| `$lte` | Less than or equal | `{"age": {"$lte": 64}}` | `age <= 64` |
| `$in` | In array | `{"status": {"$in": ["active", "pending"]}}` | `LOWER(name) IN (...)` / `LOWER(CAST(status AS VARCHAR)) IN (...)` |
| `$isanyof` | Is any of (alias for $in) | `{"role": {"$isanyof": ["admin", "user"]}}` | `role IN ('admin', 'user')` |

### String Operators

| Operator | Description | Example | SQL Equivalent |
|----------|-------------|---------|----------------|
| `$contains` | Contains substring | `{"name": {"$contains": "john"}}` | `name ILIKE '%john%'` / `CAST(status AS VARCHAR) ILIKE '%john%'` |
| `$ncontains` | Does not contain | `{"name": {"$ncontains": "test"}}` | `name NOT ILIKE '%test%'` / `CAST(status AS VARCHAR) NOT ILIKE '%test%'` |
| `$startswith` | Starts with | `{"email": {"$startswith": "admin"}}` | `email ILIKE 'admin%'` / `CAST(status AS VARCHAR) ILIKE 'admin%'` |
| `$endswith` | Ends with | `{"email": {"$endswith": ".com"}}` | `email ILIKE '%.com'` / `CAST(status AS VARCHAR) ILIKE '%.com'` |

### Null/Empty Operators

| Operator | Description | Example | SQL Equivalent |
|----------|-------------|---------|----------------|
| `$isempty` | Is null | `{"description": {"$isempty": true}}` | `description IS NULL` |
| `$isnotempty` | Is not null | `{"description": {"$isnotempty": true}}` | `description IS NOT NULL` |

### Logical Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `$and` | Logical AND | `{"$and": [{"age": {"$gte": 18}}, {"is_active": {"$eq": true}}]}` |
| `$or` | Logical OR | `{"$or": [{"name": {"$contains": "john"}}, {"email": {"$contains": "john"}}]}` |

### Special Cases

**Empty String Handling:**
```bash
# Empty string is treated as NULL
GET /users?filters={"description": {"$eq": ""}}
# Equivalent to: description IS NULL
```

**Date Range Processing:**
```bash
# Date-only strings automatically expand to day ranges
GET /users?filters={"created_at": {"$eq": "2023-12-01"}}
# Becomes: created_at >= '2023-12-01 00:00:00' AND created_at < '2023-12-02 00:00:00'

# Time-specific dates are exact matches
GET /users?filters={"created_at": {"$eq": "2023-12-01T10:30:00"}}
# Becomes: created_at = '2023-12-01 10:30:00'
```

---

## 🌟 Examples

### Basic Examples

```bash
# Find active users
GET /users?filters={"is_active": {"$eq": true}}

# Find users by email domain
GET /users?filters={"email": {"$endswith": "@company.com"}}

# Find users with age between 25 and 40
GET /users?filters={"age": {"$gte": 25, "$lte": 40}}

# Search for "john" across all fields and relationships
GET /users?search=john
```

### Advanced Examples

```bash
# Find active admin users in Engineering department
GET /users?filters={
  "is_active": {"$eq": true},
  "role.name": {"$eq": "admin"},
  "role.department.name": {"$eq": "Engineering"}
}

# Find users with specific roles OR specific statuses
GET /users?filters={
  "$or": [
    {"role.name": {"$in": ["admin", "manager"]}},
    {"status": {"$eq": "active"}}
  ]
}

# Complex query with filtering, sorting, and search
GET /users?filters={
  "age": {"$gte": 25},
  "role.department.name": {"$contains": "Tech"}
}&sort=created_at:desc&search=engineer

# Find users created in December 2023
GET /users?filters={
  "created_at": {"$gte": "2023-12-01", "$lt": "2024-01-01"}
}
```

---

## �‍💻 Developer Guide

### Running the Example Application

The project includes a complete example application demonstrating all features.

#### 1. Clone the Repository

```bash
git clone https://github.com/bhadri01/fastapi-querybuilder.git
cd fastapi-querybuilder
```

#### 2. Set Up Development Environment

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Linux/Mac:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Install dependencies
pip install -e .
```

#### 3. Run the Example Server

```bash
# Navigate to examples directory
cd examples

# Run the server
python main.py
```

The server will start at `http://localhost:8000`. The example includes:
- **Auto-seeded database** with sample data (users, roles, departments)
- **Interactive API docs** at `http://localhost:8000/docs`
- **Two endpoints**:
  - `/users` - Basic endpoint with QueryBuilder
  - `/users/paginated` - Paginated endpoint

#### 4. Try It Out

Open `http://localhost:8000/docs` and try these examples:

```bash
# Find all active users
GET /users?filters={"is_active": {"$eq": true}}

# Search across all models
GET /users?search=engineering

# Filter by department through relationships
GET /users?filters={"role.department.name": {"$eq": "Engineering"}}

# Paginated results
GET /users/paginated?page=1&size=2&sort=name:asc
```

---

### Contributing

We welcome contributions! Here's how to get started:

#### Development Setup

```bash
# Fork the repository on GitHub, then clone your fork
git clone https://github.com/YOUR_USERNAME/fastapi-querybuilder.git
cd fastapi-querybuilder

# Add upstream remote
git remote add upstream https://github.com/bhadri01/fastapi-querybuilder.git

# Create virtual environment and install dependencies
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install poetry==2.5.1
poetry sync --with dev
```

#### Making Changes

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Follow the existing code style
   - Add type hints for all functions
   - Keep changes focused and atomic

3. **Test your changes**
   ```bash
   # Run the example to ensure it works
   cd examples
   python main.py
   
   # Test different query combinations at http://localhost:8000/docs
   ```

4. **Commit your changes**
   ```bash
   git add .
   git commit -m "feat: add your feature description"
   ```
   
   Use conventional commits:
   - `feat:` - New feature
   - `fix:` - Bug fix
   - `docs:` - Documentation changes
   - `refactor:` - Code refactoring
   - `test:` - Adding tests
   - `chore:` - Maintenance tasks

5. **Push and create Pull Request**
   ```bash
   git push origin feature/your-feature-name
   ```
   Then create a Pull Request on GitHub.

#### Contribution Guidelines

- **Code Quality**
  - Follow PEP 8 style guidelines
  - Use type hints throughout
  - Keep functions small and focused
  - Add docstrings for public APIs

- **Documentation**
  - Update README.md for user-facing changes
  - Add code comments for complex logic
  - Include examples for new features

- **Testing**
  - Test your changes with the example application
  - Ensure existing functionality still works
  - Test edge cases and error conditions

- **Pull Request Guidelines**
  - Provide a clear description of changes
  - Reference related issues
  - Keep PRs focused on a single feature/fix
  - Be responsive to review feedback

#### Project Structure

```
fastapi-querybuilder/
├── fastapi_querybuilder/    # Main package
│   ├── __init__.py          # Package exports
│   ├── builder.py           # Query building logic
│   ├── core.py              # Filter parsing and column resolution
│   ├── dependencies.py      # FastAPI dependency
│   ├── operators.py         # Filter operators
│   ├── params.py            # Query parameters
│   └── utils.py             # Utility functions
├── examples/                 # Example application
│   ├── main.py              # FastAPI app with examples
│   └── schemas.py           # Pydantic schemas and models
├── docs/                     # Documentation website
├── pyproject.toml           # Project metadata and dependencies
└── README.md                # This file
```

#### Areas for Contribution

We're looking for help with:

- 🐛 **Bug Fixes** - Report or fix issues
- ✨ **New Features** - Propose and implement new operators or capabilities
- 📚 **Documentation** - Improve docs, add examples, fix typos
- 🧪 **Testing** - Add test coverage
- 🎨 **Examples** - Add more real-world example use cases
- 🌐 **Localization** - Translate documentation

#### Getting Help

- 💬 **Questions?** Open a [Discussion](https://github.com/bhadri01/fastapi-querybuilder/discussions)
- 🐛 **Found a bug?** Open an [Issue](https://github.com/bhadri01/fastapi-querybuilder/issues)
- 💡 **Have an idea?** Start a [Discussion](https://github.com/bhadri01/fastapi-querybuilder/discussions) first

---

## �📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

```
MIT License

Copyright (c) 2024 FastAPI QueryBuilder

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 🙏 Acknowledgments

- **[FastAPI](https://fastapi.tiangolo.com/)** - The amazing web framework
- **[SQLAlchemy](https://www.sqlalchemy.org/)** - The powerful ORM
- **[fastapi-pagination](https://github.com/uriyyo/fastapi-pagination)** - Seamless pagination integration

---

## 📞 Support

- 🐛 **Bug Reports**: [GitHub Issues](https://github.com/bhadri01/fastapi-querybuilder/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/bhadri01/fastapi-querybuilder/discussions)

---

**Made with ❤️ for the FastAPI community**

*FastAPI QueryBuilder - Simplifying complex queries, one endpoint at a time.*
