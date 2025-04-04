import json
import os
import asyncio
from telethon import TelegramClient, events
from telethon.tl.types import Channel
from config import API_ID, API_HASH, SESSION_NAME, DATA_DIR

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

broadcasts = {}

# ===== Helpers =====
def save_broadcast(code):
    path = f"{DATA_DIR}/{code}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(broadcasts[code], f, ensure_ascii=False, indent=2)

def load_broadcasts():
    for file in os.listdir(DATA_DIR):
        if file.endswith(".json"):
            with open(f"{DATA_DIR}/{file}", "r", encoding="utf-8") as f:
                code = file.replace(".json", "")
                broadcasts[code] = json.load(f)

async def send_broadcast(code):
    data = broadcasts.get(code)
    if not data:
        return
    data["running"] = True
    save_broadcast(code)

    # Массив для хранения задач отправки сообщений
    tasks = []

    while data["running"]:
        for chat in data["chats"]:
            for msg in data["messages"]:
                task = asyncio.create_task(send_message_to_chat(chat, msg, code))
                tasks.append(task)

        # Ожидаем завершения всех задач
        if tasks:
            await asyncio.gather(*tasks)

        # Пауза между рассылками
        interval = data["interval"]
        await asyncio.sleep(interval)

async def send_message_to_chat(chat, msg, code):
    try:
        # Отправка сообщения в чат
        response = await client.send_message(chat["chat"], msg, reply_to=chat.get("topic_id"))
        # Логируем успешную отправку
        print(f"✅ Сообщение отправлено в {chat['chat']}")
        # Сохраняем успешную отправку в данные рассылки
        log_send_status(code, chat["chat"], "sent")
    except Exception as e:
        # Логируем ошибку отправки
        print(f"❗Ошибка при отправке в {chat['chat']}: {e}")
        # Сохраняем неудачную отправку в данные рассылки
        log_send_status(code, chat["chat"], "failed")

def log_send_status(code, chat, status):
    # Функция для записи статуса отправки
    if "send_status" not in broadcasts[code]:
        broadcasts[code]["send_status"] = {}
    if chat not in broadcasts[code]["send_status"]:
        broadcasts[code]["send_status"][chat] = []
    broadcasts[code]["send_status"][chat].append(status)
    save_broadcast(code)

# ===== Commands =====
@client.on(events.NewMessage(pattern=r'\.b a (\w+)'))
async def add_message(event):
    code = event.pattern_match.group(1)
    if not event.is_reply:
        return await event.reply("Ответь на сообщение для добавления")
    broadcasts.setdefault(code, {"messages": [], "chats": [], "interval": 60, "running": False})
    msg = (await event.get_reply_message()).text
    if msg:
        broadcasts[code]["messages"].append(msg)
        save_broadcast(code)
        await event.reply(f"✅ Сообщение добавлено в {code}")

@client.on(events.NewMessage(pattern=r'\.b r (\w+)'))
async def remove_message(event):
    code = event.pattern_match.group(1)
    if code not in broadcasts:
        return await event.reply("❗Нет такой рассылки")
    if not event.is_reply:
        return await event.reply("Ответь на сообщение для удаления")
    msg = (await event.get_reply_message()).text
    if msg in broadcasts[code]["messages"]:
        broadcasts[code]["messages"].remove(msg)
        save_broadcast(code)
        await event.reply(f"✅ Сообщение удалено из {code}")

@client.on(events.NewMessage(pattern=r'\.b ac (\w+) (@\w+)(?: (\d+))?'))
async def add_chat(event):
    code, chat, topic = event.pattern_match.groups()
    broadcasts.setdefault(code, {"messages": [], "chats": [], "interval": 60, "running": False})
    chats = broadcasts[code]["chats"]
    if any(c["chat"] == chat for c in chats):
        return await event.reply(f"❗{chat} уже добавлен")
    chat_data = {"chat": chat}
    if topic:
        chat_data["topic_id"] = int(topic)
    chats.append(chat_data)
    save_broadcast(code)
    await event.reply(f"✅ Чат {chat} добавлен в {code}")

@client.on(events.NewMessage(pattern=r'\.b rc (\w+) (@\w+)'))
async def remove_chat(event):
    code, chat = event.pattern_match.groups()
    if code not in broadcasts:
        return await event.reply("❗Нет такой рассылки")
    before = len(broadcasts[code]["chats"])
    broadcasts[code]["chats"] = [c for c in broadcasts[code]["chats"] if c["chat"] != chat]
    after = len(broadcasts[code]["chats"])
    save_broadcast(code)
    await event.reply(f"✅ Чат удалён ({before} → {after})")

@client.on(events.NewMessage(pattern=r'\.b i (\w+) (\d+) (\d+)'))
async def set_interval(event):
    code, min_sec, max_sec = event.pattern_match.groups()
    if code not in broadcasts:
        return await event.reply("❗Нет такой рассылки")
    interval = (int(min_sec) + int(max_sec)) // 2
    broadcasts[code]["interval"] = interval * 60  # Конвертируем в секунды
    save_broadcast(code)
    await event.reply(f"✅ Интервал {min_sec}-{max_sec} минут установлен")

@client.on(events.NewMessage(pattern=r'\.b s (\w+)'))
async def start_broadcast(event):
    code = event.pattern_match.group(1)
    if code not in broadcasts:
        return await event.reply("❗Нет такой рассылки")
    if broadcasts[code]["running"]:
        return await event.reply("❗Уже запущено")
    asyncio.create_task(send_broadcast(code))
    await event.reply(f"🚀 Рассылка {code} запущена")

@client.on(events.NewMessage(pattern=r'\.b x (\w+)'))
async def stop_broadcast(event):
    code = event.pattern_match.group(1)
    if code not in broadcasts:
        return await event.reply("❗Нет такой рассылки")
    broadcasts[code]["running"] = False
    save_broadcast(code)
    await event.reply(f"🛑 Рассылка {code} остановлена")

@client.on(events.NewMessage(pattern=r'\.b d (\w+)'))
async def delete_broadcast(event):
    code = event.pattern_match.group(1)
    if code in broadcasts:
        os.remove(f"{DATA_DIR}/{code}.json")
        del broadcasts[code]
        await event.reply(f"❌ Рассылка {code} удалена")
    else:
        await event.reply("❗Нет такой рассылки")

@client.on(events.NewMessage(pattern=r'\.b l'))
async def list_broadcasts(event):
    if not broadcasts:
        return await event.reply("📭 Нет рассылок")
    text = "📄 Список рассылок:\n\n"
    for code, data in broadcasts.items():
        text += f"🔹 {code} | сообщений: {len(data['messages'])} | чатов: {len(data['chats'])} | интервал: {data['interval']//60} мин | статус: {'🟢' if data['running'] else '🔴'}\n"
    await event.reply(text)

@client.on(events.NewMessage(pattern=r'\.b auto (\w+)'))
async def auto_add_chats(event):
    code = event.pattern_match.group(1)
    broadcasts.setdefault(code, {"messages": [], "chats": [], "interval": 60, "running": False})
    existing = {c["chat"] for c in broadcasts[code]["chats"]}

    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if isinstance(entity, Channel) and entity.megagroup:
            username = f"@{entity.username}" if entity.username else None
            if username and username not in existing:
                broadcasts[code]["chats"].append({"chat": username})
                existing.add(username)
    save_broadcast(code)
    await event.reply(f"✅ Группы добавлены в {code}")

@client.on(events.NewMessage(pattern=r'\.b edit (\w+) (@\w+) (\d+)'))
async def edit_topic(event):
    code, chatname, topic_id = event.pattern_match.groups()
    if code not in broadcasts:
        return await event.reply("❗Нет такой рассылки")
    updated = False
    for chat in broadcasts[code]["chats"]:
        if chat["chat"] == chatname:
            chat["topic_id"] = int(topic_id)
            updated = True
            break
    if updated:
        save_broadcast(code)
        await event.reply(f"✅ В {chatname} установлен topic_id {topic_id} для {code}")
    else:
        await event.reply("❗Чат не найден в этой рассылке")

@client.on(events.NewMessage(pattern=r'\.b chats (\w+)'))
async def list_chats(event):
    code = event.pattern_match.group(1)
    if code not in broadcasts:
        return await event.reply("❗Нет такой рассылки")
    text = f"📄 Чаты рассылки {code}:\n\n"
    for chat in broadcasts[code]["chats"]:
        line = f"🔹 {chat['chat']}"
        if "topic_id" in chat and chat["topic_id"]:
            line += f" 🧩 (topic_id: {chat['topic_id']})"
        text += line + "\n"
    await event.reply(text)

@client.on(events.NewMessage(pattern=r'\.b commands'))
async def send_commands(event):
    text = """
📄 Команды Userbot:

.b a CODE — добавить сообщение в рассылку
.b r CODE — удалить сообщение
.b ac CODE @chat (topic_id) — добавить чат
.b rc CODE @chat — удалить чат
.b i CODE min max — интервал (в минутах)
.b s CODE — старт рассылки
.b x CODE — стоп рассылки
.b d CODE — удалить рассылку
.b l — список рассылок
.b auto CODE — авто-добавление групп
.b edit CODE @chat topic_id — установить topic_id
.b chats CODE — список чатов
.b commands — список команд
"""
    await event.reply(text)

# ===== Запуск =====
load_broadcasts()

client.start()
print("Bot is running...")
client.run_until_disconnected()
