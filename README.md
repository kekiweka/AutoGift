import re
import time
import requests
import json
import os
import asyncio
from FunPayAPI import Account, Runner, enums
import random
import string
from telegram import Bot
from pyrogram import Client
import threading
import logging
import traceback

                       
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

                                 
FUNPAY_TOKEN = ""      # golden key funpay        
TELEGRAM_BOT_TOKEN = ""    # токен бота тг, куда будут приходить уведомления о заказах                
TELEGRAM_CHAT_ID = ""  # твой айди тг, получить можно @getmyid_bot                    

                    
API_ID = "2040"  # не трогать                       
API_HASH = "b18441a1ff607e10a989891a5462e627"   # не трогать                     
SESSION_NAME = "your_session_name"  # не трогать                      

                                                                    
GIFT_IDS = {
    15: 5170233102089322756,
    25: 5170250947678437525,
    50: 5170144170496491616,
    100: 5170521118301225164
}

HIDE_NAME = True                          
MESSAGE = ""                        

                                                  
telegram_bot = Bot(token=TELEGRAM_BOT_TOKEN)

                                
app = Client(
    SESSION_NAME,
    api_id=API_ID,
    api_hash=API_HASH
)

                    
try:
    acc = Account(FUNPAY_TOKEN).get()
    runner = Runner(acc)
    logger.info("Авторизация на FunPay прошла успешно.")
except Exception:
    logger.error("Ошибка при авторизации на FunPay:")
    logger.error(traceback.format_exc())
    exit(1)

                                                                      
orders = {}

                                                                   
                                                
completed_orders = []

def store_completed_order(order_id, buyer_nick, username, fullname, total_stars, elapsed_time_str):
    completed_orders.append({
        "order_id": order_id,
        "buyer_nick": buyer_nick,                                                                                   
        "username": username,                                      
        "fullname": fullname,                                   
        "total_stars": total_stars,
        "elapsed_time_str": elapsed_time_str,
        "timestamp": time.time()                                            
    })
                                                      
                                       
                                 


def get_last_10_orders():
    if not completed_orders:
        return "Нет данных о выполненных заказах."

                                 
    recent_orders = completed_orders[-10:]
                                                  
    recent_orders = list(reversed(recent_orders))

    lines = ["Последние 10 выполненных заказов:"]
    for i, o in enumerate(recent_orders, start=1):
        lines.append(
            f"{i}) ID={o['order_id']}, "
            f"TGUsername=@{o['username']}, "
            f"Имя='{o['fullname']}', "
            f"Звёзд={o['total_stars']}, "
            f"Время={o['elapsed_time_str']}"
        )

    return "\n".join(lines)


async def send_telegram_notification(message):
    try:
        await telegram_bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.info("Уведомление отправлено в Telegram.")
    except Exception:
        logger.error("Ошибка при отправке уведомления в Telegram:")
        logger.error(traceback.format_exc())


def extract_order_details(order_name, order_id):
    # Приводим строку к нижнему регистру для поиска
    order_name = order_name.lower()

    # Проверяем, есть ли "stars" в названии заказа
    if "stars" not in order_name:
        return "❌ Ошибка: Не удалось распознать количество Stars. Пожалуйста, проверьте описание заказа.", None, None

    # Ищем количество звезд в заказе (число перед словом "stars", с возможными пробелами)
    stars_match = re.search(r'(\d+)\s*stars', order_name)

    # Ищем количество "шт", если указано
    count_match = re.search(r'(\d+)\s*шт', order_name)

    if stars_match:
        quantity = int(stars_match.group(1))
        count = int(count_match.group(1)) if count_match else 1
        total_stars = quantity * count
        return (
            f"🛒 Оплачен заказ #{order_id} на {quantity * count} Telegram Stars.\n🔝 Чтобы доставить Telegram Stars, напишите свой @username", 
            quantity, 
            count
        )
    else:
        logger.warning(f"Не удалось распознать количество Stars для заказа #{order_id}.")
        return "❌ Ошибка: Не удалось распознать количество Stars. Пожалуйста, проверьте описание заказа.", None, None



async def check_username_exists(username):
    try:
        user = await app.get_users(username)
        return True  # Юзернейм существует
    except Exception:
        return False  # Юзернейм не существует

async def wait_for_user_reply(chat_id, order_id):
    last_processed_message_id = None

    # Проверка и создание записи, если её нет
    if order_id not in orders:
        orders[order_id] = {}

    while True:
        try:
            chat = acc.get_chat(chat_id)
            if chat and chat.messages:
                for message in reversed(chat.messages):
                    if last_processed_message_id is None or message.id > last_processed_message_id:
                        last_processed_message_id = message.id
                        text = message.text.strip()

                        if text.startswith("@") and len(text) > 1:
                            username = text.strip("@")
                            logger.info(f"Получен корректный @username от пользователя: {username}")

                            # Проверяем, существует ли этот юзернейм
                            if await check_username_exists(username):
                                # Записываем юзернейм в словарь
                                orders[order_id]["username"] = username
                                return username  # Возвращаем правильный юзернейм
                            else:
                                acc.send_message(chat_id, f"❌ Ошибка: Пользователь @{username} не найден. Пожалуйста, введите правильный @username.")
                                continue

        except Exception as e:
            logger.error("Ошибка при ожидании ответа от пользователя (username):")
            logger.error(traceback.format_exc())

        await asyncio.sleep(2)





async def wait_for_plus(chat_id, order_id, buyer_funpay_username, quantity, count):
    last_processed_message_id = None

    # Проверка и создание записи, если её нет
    if order_id not in orders:
        orders[order_id] = {}

    user_reply = orders[order_id].get("username", "???")
    total_stars = quantity * count

    fullname = "Неизвестно"

    try:
        t_user = await app.get_users(user_reply)  # Получаем информацию о пользователе через Pyrogram
        first_name = t_user.first_name or ""
        last_name = t_user.last_name or ""
        fullname = (f"{first_name} {last_name}").strip()
    except Exception as e:
        logger.warning(f"Не удалось получить имя/фамилию через Pyrogram для @{user_reply}: {e}")
        acc.send_message(chat_id, f"❌ Ошибка: Пользователь @{user_reply} не найден. Пожалуйста, проверьте правильность ввода и отправьте новый юзернейм.")
        orders[order_id]["username"] = "???"  # Сбрасываем текущий юзернейм
        user_reply = await wait_for_user_reply(chat_id, order_id)  # Запрашиваем новый юзернейм

        # Обновляем юзернейм в словаре после получения нового значения
        orders[order_id]["username"] = user_reply  # Сохраняем правильный юзернейм
        confirm = await wait_for_plus(chat_id, order_id, buyer_funpay_username, quantity, count)  # Повторно подтверждаем данные
        return confirm  # Рекурсивный вызов, чтобы подтвердить данные заново

    orders[order_id]["fullname"] = fullname

    summary = (
        f"⭐ 𝐚𝐮𝐭𝐨𝐬𝐭𝐚𝐫𝐬 𝐛𝐲 𝐤𝐤𝐞𝐲𝐱𝐳 ⭐\n\n"
        f"👤 Юзернейм: @{user_reply}\n"
        f"✍️ Ник: {fullname}\n"
        f"🌟 Количество звёзд: {total_stars}\n\n"
        f"✅ ЕСЛИ ДАННЫЕ ВЕРНЫ, ОТПРАВЬТЕ «+».\n"
        f"❌ ЕСЛИ ДАННЫЕ НЕВЕРНЫ, ОТПРАВЬТЕ «-»."
    )
    acc.send_message(chat_id, summary)

    while True:
        try:
            chat = acc.get_chat(chat_id)
            if chat and chat.messages:
                for message in reversed(chat.messages):
                    if last_processed_message_id is None or message.id > last_processed_message_id:
                        last_processed_message_id = message.id
                        text = message.text.strip()

                        if text.lower() == "#orders":
                            logger.info("Пользователь запросил список последних заказов (#orders).")
                            acc.send_message(chat_id, get_last_10_orders())
                            continue

                        if text == "+":
                            logger.info("Пользователь подтвердил данные (+).")
                            return True  # Данные подтверждены

                        if text == "-":
                            logger.info("Пользователь хочет изменить данные (-).")
                            # Если данные неверные, снова запросим правильные данные
                            acc.send_message(chat_id, f"⏳ Ожидаем новый юзернейм. Пожалуйста, введите правильный @username.")
                            orders[order_id]["username"] = "???"  # Сбрасываем текущий юзернейм
                            user_reply = await wait_for_user_reply(chat_id, order_id)  # Запрашиваем новый юзернейм
                            orders[order_id]["username"] = user_reply  # Сохраняем правильный юзернейм
                            confirm = await wait_for_plus(chat_id, order_id, buyer_funpay_username, quantity, count)  # Повторно подтверждаем данные
                            if confirm:
                                return True  # Если данные подтверждены, возвращаем True
                            else:
                                return False  # Если данные не подтверждены, завершаем процесс

        except Exception:
            logger.error("Ошибка при ожидании подтверждения (+ или -):")
            logger.error(traceback.format_exc())

        await asyncio.sleep(2)





async def send_stars(recipient_username, quantity, gift_id, order_id):
    try:
        if not await check_username_exists(recipient_username):
            logger.error(f"Юзернейм @{recipient_username} не существует.")
            return False  # Возвращаем False, если юзернейм не существует

        logger.info(f"Попытка отправить {quantity} Stars пользователю '@{recipient_username}' (gift_id={gift_id})...")
        gift_text = f"#{order_id}"
        await app.send_gift(
            chat_id=recipient_username,
            gift_id=gift_id,
            text=gift_text,
            hide_my_name=HIDE_NAME
        )
        logger.info("Stars успешно отправлены!")
        return True
    except Exception as e:
        logger.error(f"Ошибка при отправке Stars пользователю @{recipient_username}: {e}")
        logger.error(traceback.format_exc())
    return False


async def handle_new_order(event):                            
    order_name = event.order.description
    buyer_funpay_username = event.order.buyer_username                            
    order_id = event.order.id

    logger.info(f"Обработка нового заказа: ID={order_id}, Покупатель=@{buyer_funpay_username}, Описание='{order_name}'")

                                                            
    response_message, quantity, count = extract_order_details(order_name, order_id)
    if quantity is None or count is None:
                                             
        logger.warning("Не распознано количество Stars. Отправляем покупателю сообщение об ошибке.")
                                         
        chat = acc.get_chat_by_name(buyer_funpay_username)
        if chat:
            acc.send_message(chat.id, response_message)
        else:
            logger.warning(f"Чат с пользователем @{buyer_funpay_username} не найден. Сообщение отправить не удалось.")
                                                  
        await send_telegram_notification(
            f"❌ Некорректный заказ: ID={order_id}, Покупатель=@{buyer_funpay_username}, Описание='{order_name}'"
        )
        return

                                                      
    telegram_message = (
        f"❗ Новый заказ на FunPay\n"
        f"Покупатель: @{buyer_funpay_username}\n"
        f"ID заказа: {order_id}\n"
        f"Количество Stars: {quantity} x {count} = {quantity * count}"
    )
    await send_telegram_notification(telegram_message)

                                                                          
    chat = acc.get_chat_by_name(buyer_funpay_username)
    if not chat:
        logger.warning(f"Чат с покупателем @{buyer_funpay_username} не найден. Невозможно отправить сообщение.")
        return
                                          
    acc.send_message(chat.id, response_message)
    logger.info(f"Сообщение покупателю в чат {chat.id}: {response_message}")

                                                                      
                                                                               
    
    user_reply = await wait_for_user_reply(chat.id, order_id)
    if not user_reply:
        logger.info("Пользователь не ввёл username, прерываем процесс.")
        return

                                  
    confirm = await wait_for_plus(chat.id, order_id, buyer_funpay_username, quantity, count)
    if not confirm:
        logger.info("Пользователь НЕ подтвердил данные, прерываем процесс.")
        return

                                                                         
    gift_id = GIFT_IDS.get(quantity)
    if not gift_id:
        logger.error(f"Не найден GIFT_ID для {quantity} Stars.")
        await send_telegram_notification(
            f"❌ GIFT_ID не найден для {quantity} Stars. Заказ {order_id}."
        )
        acc.send_message(chat.id, "Произошла ошибка, обратитесь в поддержку.")
        return

                                   
    start_time = time.time()
    for i in range(count):
        success = await send_stars(user_reply, quantity, gift_id, order_id)
        if not success:
            logger.warning(f"Не удалось отправить {quantity} Stars на итерации {i+1}/{count} пользователю @{user_reply}")

    end_time = time.time()
    elapsed = end_time - start_time
    minutes, seconds = divmod(int(elapsed), 60)
    total_stars = quantity * count
    elapsed_time_str = f"{minutes} м. {seconds} с."

                                                               
    completion_message = (
        f"⭐ 𝐚𝐮𝐭𝐨𝐬𝐭𝐚𝐫𝐬 𝐛𝐲 𝐤𝐤𝐞𝐲𝐱𝐳 ⭐\n\n"
        f"💸 Ваш подарок был отправлен ({total_stars})\n"
        f"🗨️ Комментарий к транзакции: {order_id}\n"
        f"👌 НЕ ЗАБУДЬТЕ подтвердить заказ и оставить отзыв, как только звезды придут."
    )
    acc.send_message(chat.id, completion_message)

                            
    total_stars = quantity * count
    telegram_message = (
        f"✅ Заказ ID={order_id} выполнен.\n"
        f"Покупатель (TG): @{user_reply}\n"
        f"Количество Stars: {total_stars} ({quantity} x {count})\n"
        f"Время выполнения: {elapsed_time_str}"
    )
    await send_telegram_notification(telegram_message)

                                                            
    store_completed_order(
        order_id=order_id,
        buyer_nick=buyer_funpay_username,
        username=user_reply,
        total_stars=total_stars,
        elapsed_time_str=elapsed_time_str
    )


def queue_putter(runner, loop, queue):
    try:
        logger.info("Запуск слушателя событий FunPay...")
        for event in runner.listen(requests_delay=1):
            if event:
                logger.info(f"Получено событие: {event.type}")
                asyncio.run_coroutine_threadsafe(queue.put(event), loop)
    except Exception:
        logger.error("Ошибка в queue_putter:")
        logger.error(traceback.format_exc())


async def process_events(queue):
    while True:
        event = await queue.get()
        try:
            if event.type == enums.EventTypes.NEW_ORDER:
                                                   
                asyncio.create_task(handle_new_order(event))
            elif event.type == enums.EventTypes.NEW_MESSAGE:
                asyncio.create_task(handle_new_message(event))
        except Exception:
            logger.error("Ошибка при обработке события из очереди:", exc_info=True)
        finally:
            queue.task_done()


async def main():                 
    try:
        await app.start()
        logger.info("Pyrogram клиент запущен и авторизован.")
    except Exception:
        logger.error("Ошибка при запуске Pyrogram клиента:")
        logger.error(traceback.format_exc())
        return

                                  
    queue = asyncio.Queue()

                                      
    loop = asyncio.get_running_loop()

                                                 
    listener_thread = threading.Thread(target=queue_putter, args=(runner, loop, queue), daemon=True)
    listener_thread.start()
    logger.info("Слушатель событий запущен в отдельном потоке.")

                                
    await process_events(queue)

async def process_events(queue):
    while True:
        event = await queue.get()
        try:
            if event.type == enums.EventTypes.NEW_ORDER:
                asyncio.create_task(handle_new_order(event))
            
            elif event.type == enums.EventTypes.NEW_MESSAGE:
                asyncio.create_task(handle_new_message(event))                      
                
        except Exception:
            logger.error("Ошибка при обработке события из очереди:")
            logger.error(traceback.format_exc())
        finally:
            queue.task_done()

async def handle_new_message(event):                                                
    msg_text = (event.message.text or "").strip()
                                                                      
                                                                              
    chat_name = event.message.chat_name                      
    
                                       
    if msg_text.lower() == "#orders":
        logger.info(f"Пользователь @{chat_name} запросил #orders (глобально).")
        
                                        
                                    
        chat = acc.get_chat_by_name(chat_name)
        if chat:
            acc.send_message(chat.id, get_last_10_orders())
        else:
            logger.warning(f"Не найден чат с @{chat_name}, не можем отправить #orders")



if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Программа остановлена пользователем.")
    except Exception:
        logger.error("Непредвиденная ошибка в главном цикле:")
        logger.error(traceback.format_exc())
