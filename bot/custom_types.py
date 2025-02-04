from typing import Literal, TypeAlias
from enum import Enum

from pydantic import BaseModel

from aiogram.fsm.state import StatesGroup, State

status_type: TypeAlias = Literal["new", "in_work", "completed", "rejected"]


class StatusEnum(Enum):
    new = "new"
    in_work = "in_work"
    completed = "completed"
    rejected = "rejected"


class UserDTO(BaseModel):
    user_uid: int
    first_name: str
    last_name: str
    department: str = ""
    is_priority: int = 0


class TicketDict(BaseModel):
    user_uid: int
    title: str
    description: str
    status: status_type = "new"


class TicketDictID(TicketDict):
    id: int


class TicketStates(StatesGroup):
    title = State()
    description = State()


class RegisterStates(StatesGroup):
    first_and_last_name = State()
    department = State()
    confirm = State()
