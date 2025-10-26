from pydantic import BaseModel
from typing import Optional
import datetime
from enum import Enum


class StatusEnum(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


# -------------------
# Department Schemas
# -------------------

class DepartmentBase(BaseModel):
    name: str
    description: Optional[str] = None


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(DepartmentBase):
    pass


class DepartmentResponse(DepartmentBase):
    id: int

    class Config:
        from_attributes = True


# -------------------
# Role Schemas
# -------------------

class RoleBase(BaseModel):
    name: str


class RoleCreate(RoleBase):
    department_id: int


class RoleUpdate(RoleBase):
    department_id: Optional[int] = None


class RoleResponse(RoleBase):
    id: int
    department: Optional[DepartmentResponse]

    class Config:
        from_attributes = True


# -------------------
# User Schemas
# -------------------

class UserBase(BaseModel):
    name: str
    email: str
    age: Optional[int] = None
    is_active: Optional[bool] = True
    status: Optional[StatusEnum] = None
    role_id: int


class UserCreate(UserBase):
    pass


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    age: Optional[int] = None
    is_active: Optional[bool] = None
    status: Optional[StatusEnum] = None
    role_id: Optional[int] = None


class UserResponse(UserBase):
    id: int
    created_at: datetime.datetime
    role: Optional[RoleResponse]

    class Config:
        from_attributes = True
