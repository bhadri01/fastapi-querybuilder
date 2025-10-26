# FastAPI QueryBuilder

[![PyPI version](https://img.shields.io/pypi/v/fastapi-querybuilder.svg)](https://pypi.org/project/fastapi-querybuilder/)  
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/fastapi-querybuilder?period=total&units=INTERNATIONAL_SYSTEM&left_color=GRAY&right_color=GREEN&left_text=downloads)](https://pepy.tech/projects/fastapi-querybuilder)

**Python 3.10+** | **License: MIT**

A powerful, flexible query builder for FastAPI applications with SQLAlchemy. Easily add filtering, sorting, and searching capabilities to your API endpoints with minimal code.

---

## ✨ Features

- **🔍 Advanced Filtering** — JSON-based filters with 14 comparison and 2 logical operators
- **🔄 Dynamic Sorting** — Sort by any field, including nested relationships
- **🔎 Recursive Global Search** — Intelligent search across all model relationships automatically
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
- [Operator Reference](#operator-reference)
- [Examples](#examples)
- [Developer Guide](#developer-guide)
  - [Running the Example Application](#running-the-example-application)
  - [Contributing](#contributing)
- [License](#license)

---

## 🚀 Installation

```bash
pip install fastapi-querybuilder
```

**Requirements:**

- Python 3.10+
- FastAPI 0.115+
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
    """
    result = await session.execute(query)
    return result.scalars().all()
```

---

### Filtering

#### Basic Filtering

```bash
# Single condition
GET /users?filters={"name": {"$eq": "John Doe"}}

# Multiple conditions (implicit AND)
GET /users?filters={"age": {"$gte": 18}, "is_active": {"$eq": true}}

# Array values
GET /users?filters={"status": {"$in": ["active", "pending"]}}
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

```bash
# Ascending order (default)
GET /users?sort=name:asc
GET /users?sort=name  # :asc is optional

# Descending order
GET /users?sort=created_at:desc
```

#### Relationship Sorting

```bash
# Sort by relationship field
GET /users?sort=role.name:asc

# Deep relationship sorting
GET /users?sort=role.department.name:desc
```

---

### Searching

**Recursive Global Search** — QueryBuilder automatically searches across:
- All fields in the main model
- All fields in related models (recursively)
- Prevents circular references automatically

**Search Behavior by Field Type:**

- **String fields**: Case-insensitive partial matching (`ILIKE '%term%'`)
- **Enum fields**: Matches if any enum value contains the search term
- **Integer fields**: Exact match if search term is a valid number
- **Boolean fields**: Matches if search term is "true" or "false"

```bash
# Simple search - searches across User, Role, and Department models
GET /users?search=john

# Search with other parameters
GET /users?search=admin&filters={"is_active": {"$eq": true}}&sort=name:asc

# Search finds matches in:
# - User: name, email, status (enum), age (if numeric), is_active (if "true"/"false")
# - Role: name
# - Department: name, description
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
| `$eq` | Equal to | `{"age": {"$eq": 25}}` | `age = 25` |
| `$ne` | Not equal to | `{"status": {"$ne": "inactive"}}` | `status != 'inactive'` |
| `$gt` | Greater than | `{"age": {"$gt": 18}}` | `age > 18` |
| `$gte` | Greater than or equal | `{"age": {"$gte": 21}}` | `age >= 21` |
| `$lt` | Less than | `{"age": {"$lt": 65}}` | `age < 65` |
| `$lte` | Less than or equal | `{"age": {"$lte": 64}}` | `age <= 64` |
| `$in` | In array | `{"status": {"$in": ["active", "pending"]}}` | `status IN ('active', 'pending')` |
| `$isanyof` | Is any of (alias for $in) | `{"role": {"$isanyof": ["admin", "user"]}}` | `role IN ('admin', 'user')` |

### String Operators

| Operator | Description | Example | SQL Equivalent |
|----------|-------------|---------|----------------|
| `$contains` | Contains substring | `{"name": {"$contains": "john"}}` | `name ILIKE '%john%'` |
| `$ncontains` | Does not contain | `{"name": {"$ncontains": "test"}}` | `name NOT ILIKE '%test%'` |
| `$startswith` | Starts with | `{"email": {"$startswith": "admin"}}` | `email ILIKE 'admin%'` |
| `$endswith` | Ends with | `{"email": {"$endswith": ".com"}}` | `email ILIKE '%.com'` |

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
pip install -e ".[dev]"
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
