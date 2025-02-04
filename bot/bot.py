import logging
from typing import Literal
import asyncio
import os
import sys

from aiogram import Bot, Dispatcher, filters, types
from aiogram.enums import ParseMode
from aiogram.filters.command import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault
from aiogram.utils.deep_linking import create_start_link
from aiogram.utils.formatting import Text
from custom_types import RegisterStates, TicketStates
from db import (
    add_blocked_user,
    add_ticket,
    all_blocked_users,
    check_blocked,
    edit_ticket_status,
    get_ticket_by_id,
    list_tickets,
    unblock_user,
)
from dotenv import load_dotenv
from utils import active_tickets, answer_register, check_user_registration, new_ticket, raw_reply, reply_list

load_dotenv()
API_TOKEN = os.getenv("API_TOKEN")
_ADMIN_ID = os.getenv("ADMIN_ID")
ACCESS_KEY = os.getenv("ACCESS_KEY")
if not API_TOKEN or not _ADMIN_ID or not ACCESS_KEY:
    logging.error("Отстутствуют переменные ENV.")
    sys.exit(1)

bot = Bot(token=API_TOKEN)
ADMIN_ID = int(_ADMIN_ID)
dispatcher = Dispatcher()


def buttons_keyboard(
    unique_id: int, keyboard_type: Literal["accept", "complete", "reject", "unlock"] = "accept"
) -> types.InlineKeyboardMarkup:
    """
    Формирует клавиатуру в зависимости от нужного варианта.
    'accept' - по умолчанию, кнопки Принять / Отменить.
    'complete' - кнопки Отменить / Закрыть.
    """

    if keyboard_type == "accept":
        buttons = [
            [
                types.InlineKeyboardButton(
                    text="Принять заявку",
                    callback_data=f"ticket_accept_{unique_id}",
                ),
                types.InlineKeyboardButton(
                    text="Отменить заявку",
                    callback_data=f"ticket_canceled_{unique_id}",
                ),
            ],
        ]
    elif keyboard_type == "complete":
        buttons = [
            [
                types.InlineKeyboardButton(
                    text="Отменить заявку",
                    callback_data=f"ticket_canceled_{unique_id}",
                ),
                types.InlineKeyboardButton(
                    text="Закрыть заявку",
                    callback_data=f"ticket_completed_{unique_id}",
                ),
            ],
        ]

    elif keyboard_type == "reject":
        buttons = [
            [
                types.InlineKeyboardButton(
                    text="Отменить заявку",
                    callback_data=f"ticket_usercancel_{unique_id}",
                ),
            ],
        ]
    else:
        buttons = [
            [
                types.InlineKeyboardButton(
                    text="Разблокировать пользователя.",
                    callback_data=f"user_unlock_{unique_id}",
                )
            ]
        ]
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)


async def generate_start_link(our_bot: Bot):
    return await create_start_link(our_bot, ACCESS_KEY)


@dispatcher.callback_query(lambda call: call.data.startswith("user_"))
async def manage_users(callback: types.CallbackQuery):
    if not callback.data:
        return
    _, action, uid = callback.data.split("_")
    if action == "unlock":
        unblock_user(uid)
        till_block_counter.pop(int(uid))
        await callback.message.edit_text(f"Пользователь {uid} разблокирован.")
        await bot.send_message(chat_id=uid, text="Вы были разблокированы администратором бота.")
    await callback.answer()


@dispatcher.callback_query(lambda call: call.data.startswith("ticket_"))
async def send_message_users(callback: types.CallbackQuery):
    if not callback.data:
        return
    _, status, ticket_id = callback.data.split("_")
    if not (ticket := get_ticket_by_id(int(ticket_id))):
        return

    if status == "accept":
        edit_ticket_status(ticket.id, "in_work")
        await bot.send_message(
            chat_id=ticket.user_uid,
            text=f"Ваша заявка: {ticket.id} \nОписание: {ticket.description}\nпринята в работу!",
        )
        await callback.message.edit_text(
            f"Заявка {ticket_id} принята в работу. \nОписание заявки: {ticket.description}",
            reply_markup=buttons_keyboard(ticket_id, "complete"),
        )
    elif status == "canceled":
        edit_ticket_status(
            ticket.id,
            "rejected",
            "Заявка отменена администратором.",
        )
        await bot.send_message(
            chat_id=ticket.user_uid,
            text=f"Ваша заявка {ticket.id} отменена.",
        )
        await callback.message.edit_text(f"Заявка {ticket_id} отменена.")
    elif status == "usercancel":
        edit_ticket_status(
            ticket.id,
            "rejected",
            "Заявка отменена пользователем.",
        )
        await callback.message.edit_text(f"Вы отменили заявку {ticket.id}.")
        await bot.send_message(chat_id=ADMIN_ID, text=f"Заявка {ticket_id} отменена пользователем.")

    elif status == "completed":
        edit_ticket_status(ticket.id, "completed")
        await bot.send_message(
            chat_id=ticket.user_uid,
            text=f"Ваша заявка: {ticket.id} \nОписание: {ticket.description}\nвыполнена!",
        )
        await callback.message.edit_text(f"Заявка {ticket_id} завершена.")

    await callback.answer()


async def admin_to_accept_button(reply_text: Text, ticket_id: int):
    await bot.send_message(
        chat_id=ADMIN_ID,
        text=f"Новая заявка: \n{reply_text.as_html()}\nПод номером {ticket_id} создана.",
        reply_markup=buttons_keyboard(ticket_id),
    )


@dispatcher.message(Command("help"))
async def cmd_help(message: types.Message):
    if check_blocked(message.from_user.id) is True:
        return
    await message.answer(
        "Основные команды для работы:\n"
        "/register - команда для регистрации пользователя. При регистрации возможно указать свои имя/фамилию в формате"
        "\n<pre>/register Имя Фамилия\nВаш отдел</pre>\n"
        "/new_ticket - команда для создания новой заявки.\n"
        "/tickets - команда для проверки ваших заявок.\n"
        "/cancel - команда для отмены заявки <code>/cancel (номер тикета для отмены)</code>.\n"
        "/complete - команда для самостоятельного закрытия заявки "
        "<code>/complete (номер тикета для завершения)</code>.",
        parse_mode=ParseMode.HTML,
    )


till_block_counter = {}


@dispatcher.message(Command("start"))
async def cmd_start(message: types.Message, command: CommandObject):
    if check_blocked(message.from_user.id) is True:
        await message.answer("Вы заблокированы. Обратитесь к администратору.")
        return
    if command.args == ACCESS_KEY:
        is_admin = message.chat.id == ADMIN_ID
        await set_commands(is_admin)
        await message.answer(
            "Добро пожаловать в бот!\nДля продолжения пройдите регистрацию /register или воспользуйтесь "
            "помощью по командам /help."
        )
        return
    if message.chat.id not in till_block_counter:
        till_block_counter[message.from_user.id] = 5
    if till_block_counter[message.from_user.id] > 0:
        await message.answer(
            f"Вы не предоставили ключ доступа к боту или ваш ключ неверен. "
            f"У вас осталось {till_block_counter[message.from_user.id]} попыток до блокировки."
        )
        till_block_counter[message.from_user.id] -= 1
    else:
        add_blocked_user(message.from_user.id, message.from_user.username)
        await message.answer("Вы были заблокированы. Обратитесь к администратору бота для разблокировки.")
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"Пользователь {message.from_user.id} был заблокирован за 5 попыток запуска без ключа.",
            reply_markup=buttons_keyboard(message.from_user.id, "unlock"),
        )


@dispatcher.my_chat_member(filters.ChatMemberUpdatedFilter(member_status_changed=filters.JOIN_TRANSITION))
async def my_chat_member(message: types.Message) -> None:
    await message.answer("Я не работаю в группах.")
    await bot.leave_chat(message.chat.id)


@dispatcher.message(Command("register"))
async def cmd_register(message: types.Message, state: FSMContext) -> None:
    if check_blocked(message.from_user.id) is True:
        await message.answer("Вы заблокированы. Обратитесь к администратору.")
        return

    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    if first_name and last_name:
        await message.reply("Введите ваш отдел.\nНапример: Отдел разработки")
        await state.update_data(first_name=first_name, last_name=last_name)
        await state.set_state(RegisterStates.department)
    else:
        await state.set_state(RegisterStates.first_and_last_name)
        await message.reply("Введите ваши имя и фамилию.\nНапример: Иван Иванов\n")


@dispatcher.message(RegisterStates.first_and_last_name)
async def process_name_and_department(message: types.Message, state: FSMContext) -> None:
    first_and_last_name = message.text
    parts = first_and_last_name.split(" ")
    if len(parts) < 2:
        await message.reply("Неверный формат. Введите имя и фамилию.")
        return
    first_name = parts[0]
    last_name = parts[1]
    await state.update_data(first_name=first_name, last_name=last_name)
    await message.reply("Введите ваш отдел.\nНапример: Отдел разработки")
    await state.set_state(RegisterStates.department)


@dispatcher.message(RegisterStates.department)
async def process_department(message: types.Message, state: FSMContext) -> None:
    department = message.text
    if department is None:
        await message.reply("Неверный формат. Введите отдел.")
        return
    await state.update_data(department=department)
    data = await state.get_data()

    await message.reply(
        "Проверьте данные и подтвердите регистрацию.\n"
        f"Имя: {data.get('first_name')}\n"
        f"Фамилия: {data.get('last_name')}\n"
        f"Отдел: {data.get('department')}\n\n"
        "Нажмите /confirm, чтобы подтвердить,\nили /reject, чтобы отменить."
    )
    await state.set_state(RegisterStates.confirm)


@dispatcher.message(RegisterStates.confirm)
async def process_confirm(message: types.Message, state: FSMContext) -> None:
    if message.text == "/confirm":
        data = await state.get_data()
        first_name = data.get("first_name")
        last_name = data.get("last_name")
        department = data.get("department")
        is_admin = message.chat.id == ADMIN_ID

        if first_name is None or last_name is None or department is None or is_admin is None:
            await message.reply("Ошибка: Не все данные были получены. Пожалуйста, попробуйте зарегистрироваться заново.")
            await state.set_state(None)
            return

        ans = await answer_register(message, first_name, last_name, department, is_admin)
        if ans:
            await message.reply(ans)
        await state.set_state(None)
    elif message.text == "/reject":
        await message.reply("Регистрация отменена.")
        await state.set_state(None)
    else:
        await message.reply("Неверная команда. Нажмите /confirm, чтобы подтвердить,\nили /reject, чтобы отменить.")


@dispatcher.message(Command("tickets"))
async def cmd_tickets(message: types.Message, command: CommandObject) -> None:
    if check_blocked(message.from_user.id) is True:
        return
    if not check_user_registration(message.chat.id):
        await message.answer("Вы не зарегистрированы.")
        return

    if message.chat.id != ADMIN_ID:
        if command.args is not None:
            await message.answer("! Не пишите лишние аргументы !")
        if not (user_tickets := list_tickets(uid=message.chat.id)):
            await message.answer("Вы ещё не создали ни одного тикета.")
            return
        for user_ticket in user_tickets:
            await message.answer(**reply_list(user_ticket))
        return

    if command.args != "new":
        if not (user_tickets := list_tickets()):
            await message.reply("В базе данных нет тикетов.")
            return
        for user_ticket in user_tickets:
            await message.answer(**reply_list(user_ticket))
        return

    if not (user_tickets := list_tickets(status="new")):
        await message.reply("В базе данных нет тикетов.")
        return
    for user_ticket in user_tickets:
        await message.answer(**reply_list(user_ticket))


@dispatcher.message(Command("new_ticket"))
async def cmd_start_ticket(message: types.Message, state: FSMContext) -> None:
    if check_blocked(message.from_user.id) is True:
        await message.answer("Вы заблокированы. Обратитесь к администратору.")
        return
    if not check_user_registration(message.chat.id) or not message.from_user:
        await message.answer("Вы не зарегистрированы в боте, введите команду /register.")
        return

    await message.reply("Введите кратко суть вашей проблемы:")
    await state.set_state(TicketStates.title)


@dispatcher.message(TicketStates.title)
async def process_title(message: types.Message, state: FSMContext) -> None:
    title = message.text
    await state.update_data(title=title)
    await message.reply("Теперь введите описание вашей проблемы:")
    await state.set_state(TicketStates.description)


@dispatcher.message(TicketStates.description)
async def process_description(message: types.Message, state: FSMContext) -> None:
    description = message.text
    user_id = message.chat.id

    data = await state.get_data()
    title = data.get("title")

    ticket_dict = new_ticket(description, title, user_id)
    reply_text = raw_reply(ticket_dict)
    ticket_id = add_ticket(ticket_dict)

    await admin_to_accept_button(reply_text, ticket_id)
    if user_id != ADMIN_ID:
        await message.reply(reply_text.as_html(), reply_markup=buttons_keyboard(ticket_id, "reject"))

    await state.set_state(None)


@dispatcher.message(Command("cancel"))
async def cmd_cancel_ticket(message: types.Message, command: CommandObject) -> None:
    if check_blocked(message.from_user.id) is True:
        await message.answer("Вы заблокированы. Обратитесь к администратору.")
        return
    if command.args is None:
        await message.reply(
            "Правильный вызов данной команды: */cancel <номер тикета для отмены>*."
            "\nПод отменой подразумевается, что ваша проблема решаться не будет (например, тикет создан по ошибке).",
            parse_mode=ParseMode.MARKDOWN,
        )
        tickets = active_tickets(message.chat.id)
        await message.answer(tickets)
        return
    ticket_id = int(command.args)
    if not get_ticket_by_id(ticket_id):
        await message.reply("Вы не создавали тикета с таким номером.")
        return
    edit_ticket_status(ticket_id, "rejected", "Заявка отменена пользователем.")
    await message.reply(f"Ваш тикет под номером {ticket_id} успешно отменен.")
    await bot.send_message(chat_id=ADMIN_ID, text=f"Заявка {ticket_id} отменена пользователем.")


@dispatcher.message(Command("complete"))
async def cmd_complete_ticket(message: types.Message, command: CommandObject) -> None:
    if check_blocked(message.from_user.id) is True:
        await message.answer("Вы заблокированы. Обратитесь к администратору.")
        return
    if command.args is None:
        await message.reply(
            "Правильный вызов данной команды: */complete <номер тикета для завершения>*"
            "\nИспользовать, если проблема решена.",
            parse_mode=ParseMode.MARKDOWN,
        )
        tickets = active_tickets(message.chat.id)
        await message.answer(tickets)
        return
    ticket_id = int(command.args)
    if not get_ticket_by_id(ticket_id):
        await message.reply("Вы не создавали тикета с таким номером.")
        return
    edit_ticket_status(ticket_id, "completed", "Заявка завершена пользователем.")
    await message.reply(f"Ваш тикет под номером {ticket_id} успешно завершен.")
    await bot.send_message(chat_id=ADMIN_ID, text=f"Заявка {ticket_id} завершена пользователем.")


@dispatcher.message(Command("check_admin"))
async def cmd_check_authority(message: types.Message) -> None:
    if check_blocked(message.from_user.id) is True:
        await message.answer("Вы заблокированы. Обратитесь к администратору.")
        return
    if message.chat.id != ADMIN_ID:
        await message.reply("Нет прав администратора.")
        return

    await message.reply("Права администратора подтверждены.")
    # Регистрация администратора в таблице Users если он не записан в базе.
    if check_user_registration(message.chat.id) or not message.chat.first_name or not message.chat.last_name:
        return
    await answer_register(message, message.chat.first_name, message.chat.last_name, "Admin", True)


@dispatcher.message(Command("block"))
async def cmd_block_user(message: types.Message, command: CommandObject) -> None:
    if message.chat.id != ADMIN_ID:
        return
    if command.args is None:
        await message.reply("Укажите UID пользователя для блокировки.")
    add_blocked_user(int(command.args), "Added by admin.")
    await bot.send_message(chat_id=int(command.args), text="Вы были заблокированы администратором бота.")
    if check_blocked(int(command.args)):
        await message.answer(f"Пользователь {int(command.args)} заблокирован.")


@dispatcher.message(Command("unblock"))
async def cmd_unblock_user(message: types.Message, command: CommandObject) -> None:
    if message.chat.id != ADMIN_ID:
        return
    if command.args is None:
        await message.reply("Укажите UID пользователя для разблокировки.")
        if blocklist := all_blocked_users():
            for user in blocklist:
                await message.answer(f"{user[0]}: {user[1]}", reply_markup=buttons_keyboard(user[0], "unlock"))
        else:
            await message.answer("На данный момент нет заблокированных пользователей.")
    unblock_user(int(command.args))
    till_block_counter.pop(int(command.args))
    await bot.send_message(chat_id=int(command.args), text="Вы были разблокированы администратором бота.")
    if not check_blocked(int(command.args)):
        await message.answer(f"Пользователь {int(command.args)} разблокирован.")


async def set_commands(is_admin):
    if is_admin:
        commands = [
            BotCommand(command="register", description="Команда для регистрации пользователя"),
            BotCommand(command="new_ticket", description="Команда для создания новой заявки"),
            BotCommand(command="tickets", description="Команда для проверки ваших заявок"),
            BotCommand(command="cancel", description="Команда для отмены заявки"),
            BotCommand(command="complete", description="Команда для самостоятельного закрытия заявки"),
            BotCommand(command="help", description="Справка по командам"),
            BotCommand(command="tickets", description="Команда для создания новой заявки"),
            BotCommand(command="check_admin", description="Команда для проверки статуса Admin"),
            BotCommand(command="block", description="Команда для блокировки пользователя"),
            BotCommand(command="unblock", description="Команда для разблокировки пользователя"),
        ]
        await bot.set_my_commands(commands, BotCommandScopeChat(chat_id=ADMIN_ID))

    else:
        commands = [
            BotCommand(command="register", description="Команда для регистрации пользователя"),
            BotCommand(command="new_ticket", description="Команда для создания новой заявки"),
            BotCommand(command="tickets", description="Команда для проверки ваших заявок"),
            BotCommand(command="cancel", description="Команда для отмены заявки"),
            BotCommand(command="complete", description="Команда для самостоятельного закрытия заявки"),
            BotCommand(command="help", description="Справка по командам"),
        ]
        await bot.set_my_commands(commands, BotCommandScopeDefault())


async def main():
    await bot.send_message(
        chat_id=ADMIN_ID,
        text=f"Бот запущен, приглашение работает по ссылке {await generate_start_link(bot)}",
    )
    await dispatcher.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] - %(filename)s:%(lineno)d #%(levelname)-s - %(name)s - %(message)s",
        filename="bot.log",
        filemode="w",
    )
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Остановка сервера!")
