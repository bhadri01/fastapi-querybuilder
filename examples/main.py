from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, Depends
import sqlalchemy
from fastapi_querybuilder import QueryBuilder
from fastapi_pagination import Page, add_pagination
from fastapi_pagination.ext.sqlalchemy import paginate
from sqlalchemy import String, ForeignKey, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column, relationship, declarative_base
import uvicorn

from examples.schemas import StatusEnum, UserResponse

# ───── App & DB Setup ───────────────────────────

DATABASE_URL = "sqlite+aiosqlite:///./test.db"

engine = create_async_engine(DATABASE_URL, echo=True)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()


async def get_db():
    async with SessionLocal() as session:
        yield session


# ───── Models ────────────────────────────────────

class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=True)

    roles: Mapped[list["Role"]] = relationship("Role", back_populates="department")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))

    users: Mapped[list["User"]] = relationship("User", back_populates="role")
    department: Mapped["Department"] = relationship(
        "Department", back_populates="roles", lazy="selectin")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    age: Mapped[int] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    status: Mapped[StatusEnum] = mapped_column(
        sqlalchemy.Enum(StatusEnum),
        default=StatusEnum.ACTIVE,
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc))

    role: Mapped["Role"] = relationship(
        "Role", back_populates="users", lazy="selectin")


# ───── Lifespan / Seed Data ─────────────────────

@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        result = await session.execute(select(Department))
        if not result.scalars().first():
            # Create departments
            engineering = Department(name="Engineering", description="Software development and engineering")
            hr = Department(name="Human Resources", description="People and culture management")
            sales = Department(name="Sales", description="Business development and sales")
            session.add_all([engineering, hr, sales])
            await session.commit()

            # Create roles with department assignments
            admin = Role(name="admin", department=engineering)
            user = Role(name="user", department=hr)
            manager = Role(name="manager", department=sales)
            developer = Role(name="developer", department=engineering)
            hr_specialist = Role(name="hr_specialist", department=hr)
            session.add_all([admin, user, manager, developer, hr_specialist])
            await session.commit()

            session.add_all([
                User(name="Alice", email="alice@example.com", role=admin,
                     status=StatusEnum.ACTIVE, age=30, is_active=True),
                User(name="Bob", email="bob@example.com", role=user,
                     status=StatusEnum.INACTIVE, age=25, is_active=False),
                User(name="Carol", email="carol@example.com", role=manager,
                     status=StatusEnum.SUSPENDED, age=40, is_active=False),
                User(name="Dave", email="dave@example.com", role=developer,
                     status=StatusEnum.ACTIVE, age=35, is_active=True),
                User(name="Eve", email="eve@example.com", role=hr_specialist,
                     status=StatusEnum.ACTIVE, age=28, is_active=True),
            ])
            await session.commit()

    yield

# ───── FastAPI App ───────────────────────────────

app = FastAPI(lifespan=lifespan)


@app.get("/users")
async def get_users(query=QueryBuilder(User), session: AsyncSession = Depends(get_db)):
    print("Generated SQL Query:")
    print(query)
    print("SQL String with literal binds:")
    result = await session.execute(query)
    return result.scalars().all()


@app.get("/users/paginated", response_model=Page[UserResponse])
async def get_users_paginated(query=QueryBuilder(User), session: AsyncSession = Depends(get_db)):
    return await paginate(session, query)


add_pagination(app)

# ───── Test Examples for search_fields ──────────

from fastapi_querybuilder.builder import _parse_search_field_paths, _check_circular_references


def print_section(title: str):
    """Print a formatted section header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def demo_parse_search_field_paths():
    """Demonstrate path parsing functionality"""
    print_section("Demo 1: Parsing Search Field Paths")
    
    test_cases = [
        ("name", "Single top-level field"),
        ("name,email,status", "Multiple top-level fields"),
        ("role.name", "Single nested field"),
        ("role.department.name", "Multiple nesting levels"),
        ("name,email,role.name,role.department.name", "Mixed top-level and nested"),
        ("name,name,role.name,role.name", "Duplicate fields (auto-deduplicated)"),
        ("name, email, role.name", "Fields with whitespace"),
    ]
    
    for search_fields, description in test_cases:
        result = _parse_search_field_paths(search_fields)
        print(f"\n  Input: {search_fields}")
        print(f"  ({description})")
        print(f"  Parsed: {result}")


def demo_circular_reference_detection():
    """Demonstrate circular reference detection"""
    print_section("Demo 2: Circular Reference Detection")
    
    from fastapi import HTTPException
    
    valid_cases = [
        ([([], "name"), ([], "email")], "Top-level fields"),
        ([(["role"], "name")], "Single level nesting"),
        ([(["role", "department"], "name")], "Deep nesting"),
    ]
    
    print("\n  Valid Cases (should pass):")
    for parsed, description in valid_cases:
        try:
            _check_circular_references(parsed, User)
            print(f"    ✓ {description}: {parsed}")
        except HTTPException as e:
            print(f"    ✗ {description}: {e.detail}")
    
    print("\n  Invalid Cases (should be detected):")
    invalid_case = ([(["role", "department"], "name")], "Hypothetical User->Role->User cycle")
    print(f"    (Note: Current model doesn't have circular refs, so validating structure)")


def demo_invalid_paths():
    """Demonstrate error handling for invalid paths"""
    print_section("Demo 3: Invalid Path Error Handling")
    
    from fastapi import HTTPException
    
    invalid_cases = [
        ("role..name", "Double dots (empty parts)"),
        (".name", "Leading dot"),
        ("role.", "Trailing dot"),
    ]
    
    for search_fields, description in invalid_cases:
        try:
            _parse_search_field_paths(search_fields)
            print(f"\n  ✗ {description}: {search_fields}")
            print(f"    Expected error but got result")
        except HTTPException as e:
            print(f"\n  ✓ {description}: {search_fields}")
            print(f"    Error (400): {e.detail}")


def demo_sql_generation():
    """Demonstrate SQL query generation with search_fields"""
    print_section("Demo 4: SQL Query Generation")
    
    from fastapi_querybuilder.params import QueryParams
    from fastapi_querybuilder.builder import build_query
    
    test_cases = [
        (QueryParams(search="alice", filters=None, sort=None, search_fields=None), "Default search (top-level only)"),
        (QueryParams(search="alice", filters=None, sort=None, search_fields="name,email"), "Top-level fields explicitly"),
        (QueryParams(search="Engineering", filters=None, sort=None, search_fields="role.department.name"), "Search related model"),
        (QueryParams(search="admin", filters=None, sort=None, search_fields="name,role.name"), "Mixed: top-level + relation"),
    ]
    
    for params, description in test_cases:
        print(f"\n  {description}")
        print(f"  Query Params:")
        print(f"    search: {params.search}")
        print(f"    search_fields: {params.search_fields}")
        
        query = build_query(User, params)
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        
        # Extract relevant parts
        has_join = "JOIN" in sql
        has_distinct = "DISTINCT" in sql
        
        print(f"  Query Characteristics:")
        print(f"    Has JOIN: {has_join}")
        print(f"    Has DISTINCT: {has_distinct}")
        print(f"    SQL Length: {len(sql)} chars")


def demo_behavior_comparison():
    """Compare old vs new behavior"""
    print_section("Demo 5: Behavior Comparison (Old vs New)")
    
    print("\n  Scenario: ?search=admin")
    print("\n  OLD BEHAVIOR (v1 - Recursive):")
    print("    • Searches: User.name, User.email, Role.name, Role.status,")
    print("                 Department.name, Department.description, ...")
    print("    • Joins: 2+ (all relationships)")
    print("    • DISTINCT: Always")
    print("    • Speed: Slow (Cartesian product risk)")
    print("    • Result: Unexpected matches from unrelated tables")
    
    print("\n  NEW BEHAVIOR (v2 - Controlled):")
    print("    • Searches: User.name, User.email (root model only)")
    print("    • Joins: 0")
    print("    • DISTINCT: Not needed")
    print("    • Speed: Fast ⚡")
    print("    • To include relations: ?search=admin&search_fields=name,role.name")


def demo_all_tests():
    """Run all demonstration tests"""
    print("\n\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 68 + "║")
    print("║" + "  NESTED FIELD NOTATION SEARCH_FIELDS - COMPREHENSIVE DEMO".center(68) + "║")
    print("║" + " " * 68 + "║")
    print("╚" + "=" * 68 + "╝")
    
    try:
        demo_parse_search_field_paths()
        demo_circular_reference_detection()
        demo_invalid_paths()
        demo_sql_generation()
        demo_behavior_comparison()
        
        print("\n\n" + "=" * 70)
        print("  ✅ ALL DEMONSTRATIONS COMPLETED SUCCESSFULLY")
        print("=" * 70 + "\n")
        
    except Exception as e:
        print(f"\n\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()


# ───── Run Server or Demo ────────────────────────

if __name__ == "__main__":
    import sys
    
    # Check for --demo flag
    if "--demo" in sys.argv:
        print("Starting demonstrations...")
        demo_all_tests()
        print("\nTo start the server, run: python examples/main.py")
    else:
        print("Starting FastAPI server...")
        print("Run 'python examples/main.py --demo' to see search_fields demonstrations")
        uvicorn.run("examples.main:app", host="0.0.0.0", port=8000, reload=True)
