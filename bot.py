import telebot
from telebot.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import re
from datetime import datetime
import requests
from PIL import Image, ImageEnhance, ImageFilter
import io
import pytesseract
import os
import platform

# Токен бота
TOKEN = '8654544789:AAFsYNrbCWIoSTHDXvGvi5fqHFfEPpO_sjo'

bot = telebot.TeleBot(TOKEN)

# ID АДМИНИСТРАТОРОВ
ADMIN_IDS = [1732473774]

# Словари для хранения состояний
admin_states = {}
user_states = {}

# Настройка пути к Tesseract
if platform.system() == "Windows":
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
else:
    # Linux / Render / Docker
    possible_paths = ['/usr/bin/tesseract', '/usr/local/bin/tesseract']
    for path in possible_paths:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            break


# === ФУНКЦИЯ ДЛЯ ПОЛУЧЕНИЯ АВАТАРА ИЗ ROBLOX ===

def get_roblox_avatar(username):
    try:
        username = username.strip()
        if username.startswith('@'):
            username = username[1:]

        print(f"🔍 Ищу аватар для: {username}")

        user_url = f"https://api.roblox.com/users/get-by-username?username={username}"
        response = requests.get(user_url, timeout=10)

        user_id = None
        display_name = username

        if response.status_code == 200:
            data = response.json()
            if data and 'Id' in data and data['Id']:
                user_id = data['Id']
                print(f"✅ Найден ID: {user_id}")

                info_url = f"https://users.roblox.com/v1/users/{user_id}"
                info_response = requests.get(info_url, timeout=10)
                if info_response.status_code == 200:
                    info_data = info_response.json()
                    display_name = info_data.get('displayName', username)

        if not user_id:
            search_url = f"https://users.roblox.com/v1/users/search?keyword={username}&limit=5"
            search_response = requests.get(search_url, timeout=10)
            if search_response.status_code == 200:
                data = search_response.json()
                if data.get('data') and len(data['data']) > 0:
                    for user in data['data']:
                        if user['name'].lower() == username.lower():
                            user_id = user['id']
                            display_name = user.get('displayName', user['name'])
                            print(f"✅ Найден через поиск: {user_id}")
                            break

        avatar_url = None
        if user_id:
            avatar_api_url = f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=420x420&format=Png"
            avatar_response = requests.get(avatar_api_url, timeout=10)
            if avatar_response.status_code == 200:
                avatar_data = avatar_response.json()
                if avatar_data.get('data') and len(avatar_data['data']) > 0:
                    avatar_url = avatar_data['data'][0].get('imageUrl')
                    print(f"✅ Аватар получен")

        exists = user_id is not None
        return avatar_url, user_id, display_name, exists

    except Exception as e:
        print(f"Ошибка получения аватара: {e}")
        return None, None, username, False


# === ФУНКЦИИ ДЛЯ РАБОТЫ С ЧЁРНЫМ СПИСКОМ ===

def init_blacklist_db():
    conn = sqlite3.connect('tickets.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blacklist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            roblox_nick TEXT,
            ticket_code TEXT,
            reason TEXT,
            banned_by INTEGER,
            ban_date TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ Таблица чёрного списка готова!")


def add_to_blacklist(user_id=None, roblox_nick=None, ticket_code=None, reason="Нарушение правил", banned_by=None):
    conn = sqlite3.connect('tickets.db')
    cursor = conn.cursor()

    if user_id:
        cursor.execute('SELECT * FROM blacklist WHERE user_id = ?', (user_id,))
        if cursor.fetchone():
            conn.close()
            return False, "Пользователь уже в чёрном списке"

    cursor.execute('''
        INSERT INTO blacklist (user_id, roblox_nick, ticket_code, reason, banned_by, ban_date)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, roblox_nick, ticket_code, reason, banned_by, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    return True, "Добавлен в чёрный список"


def remove_from_blacklist(user_id=None, roblox_nick=None, ticket_code=None):
    conn = sqlite3.connect('tickets.db')
    cursor = conn.cursor()

    if user_id:
        cursor.execute('DELETE FROM blacklist WHERE user_id = ?', (user_id,))
    elif roblox_nick:
        cursor.execute('DELETE FROM blacklist WHERE roblox_nick = ?', (roblox_nick,))
    elif ticket_code:
        cursor.execute('DELETE FROM blacklist WHERE ticket_code = ?', (ticket_code,))
    else:
        conn.close()
        return False

    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted > 0


def is_blacklisted(user_id=None, roblox_nick=None, ticket_code=None):
    conn = sqlite3.connect('tickets.db')
    cursor = conn.cursor()

    if user_id:
        cursor.execute('SELECT * FROM blacklist WHERE user_id = ?', (user_id,))
    elif roblox_nick:
        cursor.execute('SELECT * FROM blacklist WHERE roblox_nick = ?', (roblox_nick,))
    elif ticket_code:
        cursor.execute('SELECT * FROM blacklist WHERE ticket_code = ?', (ticket_code,))
    else:
        conn.close()
        return False

    result = cursor.fetchone()
    conn.close()
    return result is not None


def get_blacklist():
    conn = sqlite3.connect('tickets.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, roblox_nick, ticket_code, reason, ban_date FROM blacklist ORDER BY ban_date DESC')
    blacklist = cursor.fetchall()
    conn.close()
    return blacklist


def search_by_roblox_nick(search_nick):
    """Поиск билетов по Roblox нику"""
    conn = sqlite3.connect('tickets.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT ticket_code, first_name, roblox_nick, check_date FROM used_tickets WHERE roblox_nick LIKE ? ORDER BY check_date DESC',
        (f'%{search_nick}%',))
    tickets = cursor.fetchall()
    conn.close()
    return tickets


# === ФУНКЦИЯ ДЛЯ СОХРАНЕНИЯ НИКОВ В TXT ФАЙЛ ===

def save_nicks_to_txt():
    conn = sqlite3.connect('tickets.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT roblox_nick FROM used_tickets WHERE roblox_nick IS NOT NULL AND roblox_nick != "" ORDER BY check_date DESC')
    nicks = cursor.fetchall()
    conn.close()

    if not nicks:
        return None

    filename = f"nicks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(filename, 'w', encoding='utf-8') as f:
        for nick in nicks:
            f.write(f"{nick[0]}\n")

    return filename


# === ФУНКЦИИ БАЗЫ ДАННЫХ ===

def init_db():
    conn = sqlite3.connect('tickets.db')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS used_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_code TEXT UNIQUE,
            user_id INTEGER,
            username TEXT,
            first_name TEXT,
            roblox_nick TEXT,
            check_date TEXT
        )
    ''')

    conn.commit()
    conn.close()
    print("✅ База данных готова к работе!")
    init_blacklist_db()


def add_ticket_code(ticket_code, user_id, username, first_name, roblox_nick):
    conn = sqlite3.connect('tickets.db')
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO used_tickets (ticket_code, user_id, username, first_name, roblox_nick, check_date)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (ticket_code, user_id, username, first_name, roblox_nick,
              datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def check_ticket_code(ticket_code):
    conn = sqlite3.connect('tickets.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM used_tickets WHERE ticket_code = ?', (ticket_code,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def delete_ticket_by_code(ticket_code):
    conn = sqlite3.connect('tickets.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM used_tickets WHERE ticket_code = ?', (ticket_code,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted > 0


def get_ticket_info(ticket_code):
    conn = sqlite3.connect('tickets.db')
    cursor = conn.cursor()
    cursor.execute('SELECT ticket_code, first_name, roblox_nick, check_date, user_id FROM used_tickets WHERE ticket_code = ?',
                   (ticket_code,))
    ticket = cursor.fetchone()
    conn.close()
    return ticket


def search_tickets_by_code(search_term):
    conn = sqlite3.connect('tickets.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT ticket_code, first_name, roblox_nick, check_date FROM used_tickets WHERE ticket_code LIKE ? ORDER BY check_date DESC',
        (f'%{search_term}%',))
    tickets = cursor.fetchall()
    conn.close()
    return tickets


# === ФУНКЦИИ РАСПОЗНАВАНИЯ БИЛЕТА ===

def extract_last_code_from_text(text):
    all_numbers = re.findall(r'\d+', text)
    print(f"Все найденные коды: {all_numbers}")

    if not all_numbers:
        return None

    last_code = all_numbers[-1]
    if len(last_code) < 8 and len(all_numbers) >= 2:
        last_code = all_numbers[-2]

    print(f"Беру последний код: {last_code}")

    if 8 <= len(last_code) <= 15:
        return last_code
    return None


def preprocess_image(image):
    image = image.convert('L')
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(2.0)
    image = image.filter(ImageFilter.SHARPEN)
    width, height = image.size
    image = image.resize((width * 2, height * 2), Image.Resampling.LANCZOS)
    image = image.point(lambda x: 0 if x < 128 else 255, '1')
    return image


def get_code_from_photo(file_id):
    try:
        file_info = bot.get_file(file_id)
        file_path = file_info.file_path
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
        response = requests.get(file_url)
        image = Image.open(io.BytesIO(response.content))
        image = preprocess_image(image)

        custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789'
        recognized_text = pytesseract.image_to_string(image, config=custom_config)
        recognized_text = recognized_text.strip()

        print(f"Распознанный текст: {recognized_text}")
        ticket_code = extract_last_code_from_text(recognized_text)

        if ticket_code:
            print(f"✅ Найден код билета: {ticket_code}")
        return ticket_code, recognized_text
    except Exception as e:
        print(f"Ошибка распознавания: {e}")
        return None, None


# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

def is_admin(user_id):
    return user_id in ADMIN_IDS


def get_admin_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    btn_list = InlineKeyboardButton("📋 Список билетов", callback_data="admin_list")
    btn_stats = InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")
    btn_delete_one = InlineKeyboardButton("🗑 Удалить 1 билет", callback_data="admin_delete_one")
    btn_clear = InlineKeyboardButton("🗑 Очистить всё", callback_data="admin_clear")
    btn_backup = InlineKeyboardButton("💾 Резервная копия", callback_data="admin_backup")
    btn_search_code = InlineKeyboardButton("🔍 Поиск по коду", callback_data="admin_search_code")
    btn_search_nick = InlineKeyboardButton("🎮 Поиск по нику", callback_data="admin_search_nick")
    btn_blacklist = InlineKeyboardButton("🚫 Чёрный список", callback_data="admin_blacklist")
    btn_export_nicks = InlineKeyboardButton("📝 Экспорт ников", callback_data="admin_export_nicks")
    keyboard.add(btn_list, btn_stats)
    keyboard.add(btn_delete_one, btn_clear)
    keyboard.add(btn_search_code, btn_search_nick)
    keyboard.add(btn_blacklist, btn_export_nicks)
    keyboard.add(btn_backup)
    return keyboard


def get_blacklist_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    btn_add = InlineKeyboardButton("➕ Добавить в ЧС", callback_data="blacklist_add")
    btn_remove = InlineKeyboardButton("➖ Удалить из ЧС", callback_data="blacklist_remove")
    btn_list = InlineKeyboardButton("📋 Список ЧС", callback_data="blacklist_list")
    btn_back = InlineKeyboardButton("🔙 Назад", callback_data="admin_back")
    keyboard.add(btn_add, btn_remove, btn_list, btn_back)
    return keyboard


def get_blacklist_add_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    btn_by_user = InlineKeyboardButton("👤 По Telegram ID", callback_data="blacklist_add_user")
    btn_by_nick = InlineKeyboardButton("🎮 По Roblox нику", callback_data="blacklist_add_nick")
    btn_by_ticket = InlineKeyboardButton("🎫 По коду билета", callback_data="blacklist_add_ticket")
    btn_back = InlineKeyboardButton("🔙 Назад", callback_data="admin_blacklist")
    keyboard.add(btn_by_user, btn_by_nick, btn_by_ticket, btn_back)
    return keyboard


def get_nickname_confirm_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    btn_yes = InlineKeyboardButton("✅ Да, подтверждаю", callback_data="nickname_confirm_yes")
    btn_no = InlineKeyboardButton("❌ Нет, изменить", callback_data="nickname_confirm_no")
    keyboard.add(btn_yes, btn_no)
    return keyboard


def get_back_keyboard():
    keyboard = InlineKeyboardMarkup()
    btn_back = InlineKeyboardButton("🔙 Назад", callback_data="admin_back")
    keyboard.add(btn_back)
    return keyboard


# === ОБРАБОТЧИКИ КОМАНД ===

@bot.message_handler(commands=['start'])
def start(message: Message):
    user_id = message.from_user.id

    # Проверка на чёрный список
    if is_blacklisted(user_id=user_id):
        bot.send_message(message.chat.id, "🚫 *Вам заблокирован доступ к боту!*\n\nОбратитесь к администратору.", parse_mode='Markdown')
        return

    welcome_text = """
🎫 Добро пожаловать в бот проверки билетов!

Я проверяю билеты на концерт Монеточки в Париже.

Как пользоваться:
1. Отправьте мне фото билета
2. Я проверю код
3. Введите ваш Roblox ник
4. Подтвердите ник
5. Вношу вас в базу данных чтобы вы могли попасть на концерт

Важно: Каждый билет можно использовать только один раз!
    """
    bot.send_message(message.chat.id, welcome_text)

    try:
        with open('ticket_sample.jpg', 'rb') as photo:
            bot.send_photo(message.chat.id, photo,
                           caption="Вот так выглядит пример билета.\n\nОтправьте фото вашего билета!")
    except FileNotFoundError:
        bot.send_message(message.chat.id, "Отправьте фото билета для проверки!")

    if is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "🔐 Панель администратора", reply_markup=get_admin_keyboard())


@bot.message_handler(content_types=['photo'])
def handle_ticket_photo(message: Message):
    user_id = message.from_user.id

    # Проверка на чёрный список
    if is_blacklisted(user_id=user_id):
        bot.send_message(message.chat.id, "🚫 *Вам заблокирован доступ!*", parse_mode='Markdown')
        return

    username = message.from_user.username or "Нет username"
    first_name = message.from_user.first_name or ""

    if user_id in user_states:
        bot.send_message(message.chat.id, "Завершите предыдущую проверку или начните заново с /start")
        return

    processing_msg = bot.send_message(message.chat.id, "🔍 Проверяю билет...")

    photo = message.photo[-1]
    ticket_code, _ = get_code_from_photo(photo.file_id)

    if not ticket_code:
        bot.edit_message_text("❌ Не удалось найти код. Отправьте чёткое фото билета.",
                              chat_id=message.chat.id, message_id=processing_msg.message_id)
        return

    # Проверка билета в чёрном списке
    if is_blacklisted(ticket_code=ticket_code):
        bot.edit_message_text("🚫 *Этот билет заблокирован!*\n\nОбратитесь к администратору.",
                              chat_id=message.chat.id, message_id=processing_msg.message_id, parse_mode='Markdown')
        return

    if check_ticket_code(ticket_code):
        bot.edit_message_text(f"❌ Билет {ticket_code} уже использован!",
                              chat_id=message.chat.id, message_id=processing_msg.message_id)
        return

    user_states[user_id] = {
        'ticket_code': ticket_code,
        'username': username,
        'first_name': first_name,
        'awaiting_nickname': True
    }

    bot.edit_message_text(f"✅ Билет {ticket_code} действителен!\n\n🎮 Введите ваш Roblox ник:",
                          chat_id=message.chat.id, message_id=processing_msg.message_id)


@bot.message_handler(
    func=lambda m: m.from_user.id in user_states and user_states[m.from_user.id].get('awaiting_nickname'))
def handle_roblox_nick(message: Message):
    user_id = message.from_user.id
    roblox_nick = message.text.strip()

    if len(roblox_nick) < 2:
        bot.send_message(message.chat.id, "❌ Ник слишком короткий. Введите ещё раз:")
        return

    # Проверка ника в чёрном списке
    if is_blacklisted(roblox_nick=roblox_nick):
        bot.send_message(message.chat.id, "🚫 *Этот Roblox ник заблокирован!*\n\nОбратитесь к администратору.", parse_mode='Markdown')
        del user_states[user_id]
        return

    # === ОТПРАВЛЯЕМ ФОТО-ПРИМЕР (roblox.jpg) ===
    try:
        with open('roblox.jpg', 'rb') as example_photo:
            bot.send_photo(
                message.chat.id,
                example_photo,
                caption="🎮 *ВАЖНО* вводить нужно ваш основной никнейм\n\nСейчас я получу ваш реальный аватар...",
                parse_mode='Markdown'
            )
    except FileNotFoundError:
        bot.send_message(
            message.chat.id,
            "🎮 Сейчас я получу ваш аватар из Roblox..."
        )

    loading_msg = bot.send_message(message.chat.id, "🔍 Получаю аватар из Roblox...")

    avatar_url, user_id_roblox, display_name, exists = get_roblox_avatar(roblox_nick)

    user_states[user_id]['roblox_nick'] = roblox_nick
    user_states[user_id]['awaiting_nickname'] = False

    if avatar_url:
        try:
            if exists:
                caption_text = f"🎮 Ваш аватар в Roblox\n\nНик: *{roblox_nick}*\nОтображаемое имя: *{display_name}*\n\nЭто ваш профиль?"
            else:
                caption_text = f"🎮 Возможно это ваш аватар\n\nНик: *{roblox_nick}*\n\nЕсли это не ваш скин - проверьте правильность написания ника."

            bot.send_photo(message.chat.id, avatar_url, caption=caption_text, parse_mode='Markdown')
        except Exception as e:
            print(f"Ошибка отправки фото: {e}")
            bot.send_message(
                message.chat.id,
                f"🎮 Вы ввели ник: *{roblox_nick}*",
                parse_mode='Markdown'
            )
    else:
        bot.send_message(
            message.chat.id,
            f"🎮 Вы ввели ник: *{roblox_nick}*\n\nНе удалось найти аватар в Roblox.\nПроверьте правильность написания ника.",
            parse_mode='Markdown'
        )

    bot.send_message(
        message.chat.id,
        f"Подтвердите ваш Roblox ник: *{roblox_nick}*",
        parse_mode='Markdown',
        reply_markup=get_nickname_confirm_keyboard()
    )

    bot.delete_message(message.chat.id, loading_msg.message_id)


@bot.callback_query_handler(func=lambda call: call.data in ["nickname_confirm_yes", "nickname_confirm_no"])
def handle_confirmation(call):
    user_id = call.from_user.id

    if user_id not in user_states:
        bot.answer_callback_query(call.id, "❌ Сессия истекла. Начните с /start", show_alert=True)
        return

    data = user_states[user_id]

    if call.data == "nickname_confirm_yes":
        success = add_ticket_code(
            data['ticket_code'], user_id, data['username'], data['first_name'],
            data['roblox_nick']
        )

        if success:
            bot.edit_message_text(
                f"✅ БИЛЕТ ЗАРЕГИСТРИРОВАН!\n\nКод: {data['ticket_code']}\nTelegram: {data['first_name']}\nRoblox: {data['roblox_nick']}\n\n🎉 Добро пожаловать на концерт!\n\nУспешно внесены в белый список\n\nДля лучшей безопасности советуем кинуть в друзья Skjdoemaq",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id
            )
        else:
            bot.edit_message_text(
                f"❌ Ошибка! Билет {data['ticket_code']} уже использован.",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id
            )

        del user_states[user_id]

    else:
        user_states[user_id]['awaiting_nickname'] = True
        bot.edit_message_text(
            "✏️ Введите правильный Roblox ник:",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )

    bot.answer_callback_query(call.id)


# === АДМИН ОБРАБОТЧИКИ ===

@bot.message_handler(func=lambda m: True)
def handle_other(m):
    if is_admin(m.from_user.id) and admin_states.get(m.from_user.id) == 'waiting_for_delete_code':
        ticket_code = m.text.strip()
        admin_states.pop(m.from_user.id, None)

        info = get_ticket_info(ticket_code)
        if not info:
            bot.send_message(m.chat.id, f"❌ Билет с кодом {ticket_code} не найден", reply_markup=get_admin_keyboard())
            return

        if delete_ticket_by_code(ticket_code):
            bot.send_message(
                m.chat.id,
                f"✅ Билет удалён!\n\nКод: {info[0]}\nПользователь: {info[1]}\nRoblox: {info[2] or 'Не указан'}\nДата: {info[3]}",
                reply_markup=get_admin_keyboard()
            )
        else:
            bot.send_message(m.chat.id, "❌ Ошибка при удалении", reply_markup=get_admin_keyboard())
        return

    if is_admin(m.from_user.id) and admin_states.get(m.from_user.id) == 'waiting_for_search_code':
        search_term = m.text.strip()
        admin_states.pop(m.from_user.id, None)

        tickets = search_tickets_by_code(search_term)
        if not tickets:
            bot.send_message(m.chat.id, f"❌ Билеты по запросу '{search_term}' не найдены",
                             reply_markup=get_admin_keyboard())
            return

        result = f"🔍 РЕЗУЛЬТАТЫ ПОИСКА: '{search_term}'\n\nНайдено: {len(tickets)}\n\n"
        for t in tickets[:20]:
            result += f"🎫 Код: {t[0]}\n   👤 {t[1]}\n   🎮 {t[2] or '—'}\n   📅 {t[3]}\n\n"

        bot.send_message(m.chat.id, result[:4000], reply_markup=get_admin_keyboard())
        return

    if is_admin(m.from_user.id) and admin_states.get(m.from_user.id) == 'waiting_for_search_nick':
        search_term = m.text.strip()
        admin_states.pop(m.from_user.id, None)

        tickets = search_by_roblox_nick(search_term)
        if not tickets:
            bot.send_message(m.chat.id, f"❌ Пользователи по нику '{search_term}' не найдены",
                             reply_markup=get_admin_keyboard())
            return

        result = f"🔍 ПОИСК ПО ROBLOX НИКУ: '{search_term}'\n\nНайдено: {len(tickets)}\n\n"
        for t in tickets[:20]:
            result += f"🎫 Код: {t[0]}\n   👤 {t[1]}\n   🎮 {t[2] or '—'}\n   📅 {t[3]}\n\n"

        bot.send_message(m.chat.id, result[:4000], reply_markup=get_admin_keyboard())
        return

    # Обработка добавления в ЧС по Telegram ID
    if is_admin(m.from_user.id) and admin_states.get(m.from_user.id) == 'waiting_blacklist_user':
        try:
            user_id = int(m.text.strip())
            admin_states[m.from_user.id] = {'action': 'blacklist_user_reason', 'user_id': user_id}
            bot.send_message(m.chat.id, "✏️ Введите ПРИЧИНУ блокировки:", reply_markup=get_back_keyboard())
        except:
            bot.send_message(m.chat.id, "❌ Неверный формат. Введите числовой Telegram ID:", reply_markup=get_back_keyboard())
        return

    # Обработка добавления в ЧС по Roblox нику
    if is_admin(m.from_user.id) and admin_states.get(m.from_user.id) == 'waiting_blacklist_nick':
        admin_states[m.from_user.id] = {'action': 'blacklist_nick_reason', 'roblox_nick': m.text.strip()}
        bot.send_message(m.chat.id, "✏️ Введите ПРИЧИНУ блокировки:", reply_markup=get_back_keyboard())
        return

    # Обработка добавления в ЧС по коду билета
    if is_admin(m.from_user.id) and admin_states.get(m.from_user.id) == 'waiting_blacklist_ticket':
        admin_states[m.from_user.id] = {'action': 'blacklist_ticket_reason', 'ticket_code': m.text.strip()}
        bot.send_message(m.chat.id, "✏️ Введите ПРИЧИНУ блокировки:", reply_markup=get_back_keyboard())
        return

    # Обработка причины блокировки
    if is_admin(m.from_user.id) and isinstance(admin_states.get(m.from_user.id), dict) and 'action' in admin_states[m.from_user.id]:
        state = admin_states[m.from_user.id]
        reason = m.text.strip()

        if state['action'] == 'blacklist_user_reason':
            user_id = state['user_id']
            success, msg = add_to_blacklist(user_id=user_id, reason=reason, banned_by=m.from_user.id)
            bot.send_message(m.chat.id, f"{'✅' if success else '❌'} {msg}", reply_markup=get_admin_keyboard())

        elif state['action'] == 'blacklist_nick_reason':
            roblox_nick = state['roblox_nick']
            success, msg = add_to_blacklist(roblox_nick=roblox_nick, reason=reason, banned_by=m.from_user.id)
            bot.send_message(m.chat.id, f"{'✅' if success else '❌'} {msg}", reply_markup=get_admin_keyboard())

        elif state['action'] == 'blacklist_ticket_reason':
            ticket_code = state['ticket_code']
            success, msg = add_to_blacklist(ticket_code=ticket_code, reason=reason, banned_by=m.from_user.id)
            bot.send_message(m.chat.id, f"{'✅' if success else '❌'} {msg}", reply_markup=get_admin_keyboard())

        admin_states.pop(m.from_user.id, None)
        return

    # Обработка удаления из ЧС
    if is_admin(m.from_user.id) and admin_states.get(m.from_user.id) == 'waiting_blacklist_remove':
        remove_by = m.text.strip()
        admin_states.pop(m.from_user.id, None)

        if remove_by.isdigit():
            success = remove_from_blacklist(user_id=int(remove_by))
            msg = f"✅ Пользователь с ID {remove_by} удалён из ЧС" if success else f"❌ Пользователь с ID {remove_by} не найден в ЧС"
        elif remove_by.startswith('@'):
            success = remove_from_blacklist(roblox_nick=remove_by[1:])
            msg = f"✅ Roblox ник {remove_by[1:]} удалён из ЧС" if success else f"❌ Roblox ник {remove_by[1:]} не найден в ЧС"
        else:
            success = remove_from_blacklist(ticket_code=remove_by)
            msg = f"✅ Билет {remove_by} удалён из ЧС" if success else f"❌ Билет {remove_by} не найден в ЧС"

        bot.send_message(m.chat.id, msg, reply_markup=get_admin_keyboard())
        return

    if m.from_user.id in user_states:
        return

    bot.send_message(m.chat.id, "📸 Отправьте ФОТО билета\n\n/start - начать")


# === ОБРАБОТКА КНОПОК ===

@bot.callback_query_handler(func=lambda call: True)
def handle_admin_callback(call):
    user_id = call.from_user.id

    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "❌ Нет доступа!", show_alert=True)
        return

    if call.data == "admin_list":
        conn = sqlite3.connect('tickets.db')
        cur = conn.cursor()
        cur.execute(
            'SELECT ticket_code, first_name, roblox_nick, check_date FROM used_tickets ORDER BY check_date DESC')
        tickets = cur.fetchall()
        conn.close()

        if not tickets:
            bot.edit_message_text("📋 Список билетов пуст", chat_id=call.message.chat.id,
                                  message_id=call.message.message_id, reply_markup=get_admin_keyboard())
            return

        text = "📋 СПИСОК БИЛЕТОВ\n\n"
        for i, t in enumerate(tickets[:30], 1):
            text += f"{i}. 🎫 {t[0]}\n   👤 {t[1]}\n   🎮 {t[2] or '—'}\n   📅 {t[3]}\n\n"

        if len(tickets) > 30:
            text += f"\nВсего: {len(tickets)} билетов"

        bot.edit_message_text(text[:4000], chat_id=call.message.chat.id, message_id=call.message.message_id,
                              reply_markup=get_admin_keyboard())

    elif call.data == "admin_stats":
        conn = sqlite3.connect('tickets.db')
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM used_tickets')
        total = cur.fetchone()[0]
        cur.execute('SELECT COUNT(DISTINCT user_id) FROM used_tickets')
        users = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM used_tickets WHERE roblox_nick IS NOT NULL AND roblox_nick != ""')
        with_nick = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM blacklist')
        blacklist_count = cur.fetchone()[0]
        cur.execute('SELECT check_date FROM used_tickets ORDER BY check_date DESC LIMIT 1')
        last_ticket = cur.fetchone()
        conn.close()

        text = f"📊 СТАТИСТИКА\n\n✅ Всего билетов: {total}\n👥 Пользователей: {users}\n🎮 С указанным ником: {with_nick}\n🚫 В чёрном списке: {blacklist_count}\n"
        if last_ticket:
            text += f"🕐 Последний: {last_ticket[0]}"

        bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id,
                              reply_markup=get_admin_keyboard())

    elif call.data == "admin_delete_one":
        admin_states[user_id] = 'waiting_for_delete_code'
        bot.edit_message_text(
            "🗑 УДАЛЕНИЕ БИЛЕТА\n\nВведите КОД билета который хотите удалить (например: 875808981375):",
            chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=get_back_keyboard())

    elif call.data == "admin_search_code":
        admin_states[user_id] = 'waiting_for_search_code'
        bot.edit_message_text(
            "🔍 ПОИСК ПО КОДУ\n\nВведите КОД или ЧАСТЬ КОДА для поиска (например: 8758 или 981375):",
            chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=get_back_keyboard())

    elif call.data == "admin_search_nick":
        admin_states[user_id] = 'waiting_for_search_nick'
        bot.edit_message_text(
            "🎮 ПОИСК ПО ROBLOX НИКУ\n\nВведите Roblox ник или его часть (например: Miolwer или CoolPlayer):",
            chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=get_back_keyboard())

    elif call.data == "admin_blacklist":
        bot.edit_message_text("🚫 ЧЁРНЫЙ СПИСОК\n\nВыберите действие:",
                              chat_id=call.message.chat.id, message_id=call.message.message_id,
                              reply_markup=get_blacklist_keyboard())

    elif call.data == "blacklist_add":
        bot.edit_message_text("➕ ДОБАВЛЕНИЕ В ЧС\n\nВыберите по чему блокировать:",
                              chat_id=call.message.chat.id, message_id=call.message.message_id,
                              reply_markup=get_blacklist_add_keyboard())

    elif call.data == "blacklist_add_user":
        admin_states[user_id] = 'waiting_blacklist_user'
        bot.edit_message_text(
            "➕ БЛОКИРОВКА ПО TELEGRAM ID\n\nВведите Telegram ID пользователя (число):\n\nПример: 1732473774",
            chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=get_back_keyboard())

    elif call.data == "blacklist_add_nick":
        admin_states[user_id] = 'waiting_blacklist_nick'
        bot.edit_message_text(
            "➕ БЛОКИРОВКА ПО ROBLOX НИКУ\n\nВведите Roblox ник пользователя:\n\nПример: Miolwer12",
            chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=get_back_keyboard())

    elif call.data == "blacklist_add_ticket":
        admin_states[user_id] = 'waiting_blacklist_ticket'
        bot.edit_message_text(
            "➕ БЛОКИРОВКА ПО КОДУ БИЛЕТА\n\nВведите код билета:\n\nПример: 875808981375",
            chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=get_back_keyboard())

    elif call.data == "blacklist_remove":
        admin_states[user_id] = 'waiting_blacklist_remove'
        bot.edit_message_text(
            "➖ УДАЛЕНИЕ ИЗ ЧС\n\nВведите:\n• Telegram ID (число)\n• Roblox ник (@ник)\n• Код билета\n\nПример: 1732473774 или @Miolwer12 или 875808981375",
            chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=get_back_keyboard())

    elif call.data == "blacklist_list":
        blacklist = get_blacklist()
        if not blacklist:
            bot.edit_message_text("📋 ЧЁРНЫЙ СПИСОК ПУСТ",
                                  chat_id=call.message.chat.id, message_id=call.message.message_id,
                                  reply_markup=get_blacklist_keyboard())
            return

        text = "🚫 ЧЁРНЫЙ СПИСОК\n\n"
        for i, item in enumerate(blacklist[:30], 1):
            text += f"{i}. "
            if item[0]:
                text += f"👤 ID: {item[0]}\n"
            elif item[1]:
                text += f"🎮 Ник: {item[1]}\n"
            elif item[2]:
                text += f"🎫 Билет: {item[2]}\n"
            text += f"   📝 Причина: {item[3]}\n"
            text += f"   📅 Дата: {item[4]}\n\n"

        bot.edit_message_text(text[:4000], chat_id=call.message.chat.id, message_id=call.message.message_id,
                              reply_markup=get_blacklist_keyboard())

    elif call.data == "admin_back":
        admin_states.pop(user_id, None)
        bot.edit_message_text("🔐 Панель администратора",
                              chat_id=call.message.chat.id, message_id=call.message.message_id,
                              reply_markup=get_admin_keyboard())

    elif call.data == "admin_clear":
        bot.edit_message_text(
            "⚠️ ОЧИСТИТЬ ВСЕ БИЛЕТЫ?\n\nЭто действие необратимо!",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("✅ ДА, ОЧИСТИТЬ", callback_data="confirm_clear"),
                InlineKeyboardButton("❌ НЕТ, ОТМЕНА", callback_data="admin_back")
            )
        )

    elif call.data == "admin_backup":
        conn = sqlite3.connect('tickets.db')
        cur = conn.cursor()
        cur.execute('SELECT ticket_code, first_name, roblox_nick, check_date FROM used_tickets')
        tickets = cur.fetchall()
        cur.execute('SELECT user_id, roblox_nick, ticket_code, reason, ban_date FROM blacklist')
        blacklist = cur.fetchall()
        conn.close()

        if not tickets:
            bot.answer_callback_query(call.id, "Нет данных для бекапа")
            return

        backup = f"РЕЗЕРВНАЯ КОПИЯ\nДата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        backup += "=== БИЛЕТЫ ===\n"
        for t in tickets:
            backup += f"Код: {t[0]} | Пользователь: {t[1]} | Roblox: {t[2] or '—'} | Дата: {t[3]}\n"
        backup += "\n=== ЧЁРНЫЙ СПИСОК ===\n"
        for b in blacklist:
            backup += f"ID: {b[0] or '—'} | Ник: {b[1] or '—'} | Билет: {b[2] or '—'} | Причина: {b[3]} | Дата: {b[4]}\n"

        with open('backup.txt', 'w', encoding='utf-8') as f:
            f.write(backup)
        with open('backup.txt', 'rb') as f:
            bot.send_document(call.message.chat.id, f, caption="💾 Резервная копия базы данных")
        os.remove('backup.txt')
        bot.answer_callback_query(call.id, "✅ Бекап создан!")

    elif call.data == "admin_export_nicks":
        filename = save_nicks_to_txt()
        if filename:
            with open(filename, 'rb') as f:
                bot.send_document(call.message.chat.id, f,
                                  caption=f"📝 Список Roblox ников\nСгенерировано: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            os.remove(filename)
            bot.answer_callback_query(call.id, "✅ Файл с никами отправлен!")
        else:
            bot.answer_callback_query(call.id, "❌ Нет ников в базе данных", show_alert=True)

        bot.edit_message_text("🔐 Панель администратора",
                              chat_id=call.message.chat.id, message_id=call.message.message_id,
                              reply_markup=get_admin_keyboard())

    elif call.data == "confirm_clear":
        conn = sqlite3.connect('tickets.db')
        cur = conn.cursor()
        cur.execute('DELETE FROM used_tickets')
        conn.commit()
        conn.close()
        bot.edit_message_text("✅ База данных полностью очищена!",
                              chat_id=call.message.chat.id, message_id=call.message.message_id,
                              reply_markup=get_admin_keyboard())


@bot.message_handler(commands=['admin'])
def admin_cmd(m):
    if is_admin(m.from_user.id):
        bot.send_message(m.chat.id, "🔐 Панель администратора", reply_markup=get_admin_keyboard())
    else:
        bot.send_message(m.chat.id, "❌ Нет доступа")


# === ЗАПУСК ===
if __name__ == '__main__':
    init_db()
    print("🤖 Бот запущен!")
    print(f"👑 Администраторы: {ADMIN_IDS}")
    print("✅ Добавлены функции: поиск по нику, чёрный список")
    print("✅ Все фразы из старого бота перенесены")
    bot.infinity_polling()
