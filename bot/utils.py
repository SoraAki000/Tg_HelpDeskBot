from aiogram.types import Message
from aiogram.utils.formatting import Text, as_list
from custom_types import TicketDict, UserDTO
from db import User, add_user, get_user_by_uid, list_ticket_ids


async def answer_register(
        message: Message, first_name: str, last_name: str, department: str, is_admin: bool = False) -> str:
    user_uid = message.chat.id
    user = check_user_registration(user_uid)
    if not user:
        if not is_admin:
            user_dict = new_user(user_uid, first_name, last_name, department)
        else:
            user_dict = UserDTO(
                user_uid=user_uid, first_name=first_name, last_name=last_name, department="Admin", is_priority=99
            )
        add_user(user_dict)
        answer = "Вы успешно зарегистрировались!"
    else:
        answer = "Вы уже зарегистрированы!"
    return f"{first_name}, добро пожаловать в бот!\n{answer}"


def check_user_registration(user_uid: int) -> User | None:
    return get_user_by_uid(user_uid)


def new_ticket(description: str, title: str, user_id: int) -> TicketDict:
    return TicketDict(user_uid=user_id, title=title, description=description)


def new_user(user_uid: int, first_name: str, last_name: str, department: str) -> UserDTO:
    return UserDTO(user_uid=user_uid, first_name=first_name, last_name=last_name, department=department)


def raw_reply(item: TicketDict) -> Text:
    user = get_user_by_uid(item.user_uid)
    return as_list(
        f"От пользователя: {user.first_name} {user.last_name}",
        f"Отдел: {user.department}",
        f"Приоритет: {user.is_priority}",
        f"Заголовок: {item.title}",
        f"Описание: {item.description}",
        f"Статус: {item.status}",
        sep="\n",
    )


def reply_list(item: TicketDict) -> dict:
    return raw_reply(item).as_kwargs()


def active_tickets(chat_id: int) -> str:
    tickets = list_ticket_ids(chat_id)
    string_ticket = "Список ваших активных тикетов:"
    inactive = 0
    for ticket in tickets:
        if ticket.status not in ("completed", "rejected"):
            string_ticket += f"\n{ticket.id}: {ticket.description}. Статус: {ticket.status}"
        else:
            inactive += 1
    if not tickets or inactive == len(tickets):
        return "У вас нет активных тикетов."
    return string_ticket
