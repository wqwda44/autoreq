import contextlib
import asyncio
import logging
import sqlite3
import os
import random
from aiogram import Bot, Dispatcher, types

#БД СОЗДАЕТЬСЯ САМА!
#Рассылка через /send
TOKEN = "here" # токен бота и айди канала, и себя(админа) https://t.me/username_to_id_bot, создай в канале ссылку по принятию и ее распрастраняй
CHANNEL_ID = here
ADMIN_ID = here
DATABASE = 'users.db'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, 'users.db')

def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, passed_captcha BOOLEAN DEFAULT 0, captcha_answer INTEGER)''')
    conn.commit()
    conn.close()

async def add_user(user_id, captcha_answer):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO users (user_id, captcha_answer) VALUES (?, ?)', (user_id, captcha_answer))
    conn.commit()
    conn.close()

async def update_captcha_status(user_id, status):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET passed_captcha = ? WHERE user_id = ?', (status, user_id))
    conn.commit()
    conn.close()

async def get_all_users():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users WHERE passed_captcha = 1')
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

def generate_captcha():
    num1 = random.randint(1, 9)
    num2 = random.randint(1, 9)
    captcha_question = f"{num1} + {num2} = ?"
    captcha_answer = num1 + num2
    return captcha_question, captcha_answer

async def approve_request(chat_join: types.ChatJoinRequest, bot: Bot):
    captcha_question, captcha_answer = generate_captcha()
    await add_user(chat_join.from_user.id, captcha_answer)
    msg = (f"Добро пожаловать! Пожалуйста, решите капчу, чтобы вступить в канал.\n"
           f"Вопрос: {captcha_question}\n"
           "Отправьте ответ командой /answer <ответ>.")
    await bot.send_message(chat_id=chat_join.from_user.id, text=msg)
    asyncio.create_task(send_captcha_reminder(chat_join.from_user.id, bot))

async def send_captcha_reminder(user_id: int, bot: Bot):
    while True:
        await asyncio.sleep(random.randint(28800, 86400)) #время в секундах
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT passed_captcha FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        if result and not result[0]:
            msg = "Напоминаем, пожалуйста, пройдите капчу, ответив на вопрос, отправив команду /answer <ответ>."
            try:
                await bot.send_message(chat_id=user_id, text=msg)
            except Exception as e:
                logging.error(f"Failed to send captcha reminder to {user_id}: {e}")
        else:
            break

async def handle_answer(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    args = message.text.split()[1:]

    if not args:
        await message.reply("Пожалуйста, введите команду в формате: /answer <ответ>")
        return

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT captcha_answer FROM users WHERE user_id = ?', (user_id,))
    captcha_answer = cursor.fetchone()
    conn.close()

    if captcha_answer and int(args[0]) == captcha_answer[0]:
        await update_captcha_status(user_id, 1)
        await bot.send_message(chat_id=user_id, text="Капча пройдена! Добро пожаловать в канал.")
        await bot.approve_chat_join_request(chat_id=CHANNEL_ID, user_id=user_id)
    else:
        await message.reply("Неверный ответ. Пожалуйста, попробуйте снова.")

async def send_universal_message(message: types.Message, bot: Bot):
    if message.from_user.id == ADMIN_ID:
        users = await get_all_users()
        text = message.caption or message.text
        
        # Удаляем команду /send из текста или подписи
        if text and text.startswith('/send'):
            text = text.replace('/send', '').strip()

        if message.photo:
            photo = message.photo[-1].file_id
            for user_id in users:
                try:
                    await bot.send_photo(chat_id=user_id, photo=photo, caption=text)
                except Exception as e:
                    logging.error(f"Failed to send photo with text to {user_id}: {e}")
            await message.reply("Фото с текстом отправлено всем пользователям.")
        elif message.animation:
            gif = message.animation.file_id
            for user_id in users:
                try:
                    await bot.send_animation(chat_id=user_id, animation=gif, caption=text)
                except Exception as e:
                    logging.error(f"Failed to send gif with text to {user_id}: {e}")
            await message.reply("Гифка с текстом отправлена всем пользователям.")
        elif text:
            for user_id in users:
                try:
                    await bot.send_message(chat_id=user_id, text=text)
                except Exception as e:
                    logging.error(f"Failed to send text to {user_id}: {e}")
            await message.reply("Текстовое сообщение отправлено всем пользователям.")
        else:
            await message.reply("Пожалуйста, отправьте текст, фото или гифку с командой /send.")

async def start():
    logging.basicConfig(level=logging.DEBUG,
                        format="%(asctime)s - [%(levelname)s] - %(name)s - (%(filename)s).%(funcName)s(%(lineno)d) - %(message)s")

    init_db()

    bot: Bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.chat_join_request.register(approve_request)
    dp.message.register(handle_answer, lambda message: message.text and message.text.startswith('/answer'))
    dp.message.register(send_universal_message, lambda message: message.text and message.text.startswith('/send') or message.photo or message.animation)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as ex:
        logging.error(f"[Exception] - {ex}", exc_info=True)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt, SystemExit):
        asyncio.run(start())
