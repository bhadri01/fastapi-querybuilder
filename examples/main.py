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
    result = await session.execute(query)
    return result.scalars().all()


@app.get("/users/paginated", response_model=Page[UserResponse])
async def get_users_paginated(query=QueryBuilder(User), session: AsyncSession = Depends(get_db)):
    return await paginate(session, query)


add_pagination(app)

# ───── Run Server ────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
