import telebot
from telebot.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import re
from datetime import datetime
import requests
import os
import platform

# ------------------------------
# 1. ТОКЕН и АДМИНЫ (из переменных окружения)
# ------------------------------
TOKEN = os.environ.get('BOT_TOKEN', '8654544789:AAFsYNrbCWIoSTHDXvGvi5fqHFfEPpO_sjo')
ADMIN_IDS = [1732473774]

bot = telebot.TeleBot(TOKEN)

# ------------------------------
# 2. ЛЁГКАЯ НАСТРОЙКА TESSERACT (если отсутствует – просто не используем OCR)
# ------------------------------
HAS_TESSERACT = False
try:
    import pytesseract
    from PIL import Image, ImageEnhance, ImageFilter
    import io

    # Пытаемся найти tesseract в системе
    if platform.system() == "Windows":
        tesseract_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        if os.path.exists(tesseract_path):
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
            HAS_TESSERACT = True
    else:
        # Linux / Render
        possible_paths = ['/usr/bin/tesseract', '/usr/local/bin/tesseract']
        for path in possible_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                HAS_TESSERACT = True
                break
    if HAS_TESSERACT:
        print("✅ Tesseract найден, OCR будет работать")
    else:
        print("⚠️ Tesseract НЕ найден, распознавание кода недоступно. Будет работать ручной ввод кода.")
except ImportError:
    print("⚠️ Библиотеки OCR не установлены. Бот будет работать без распознавания фото.")
except Exception as e:
    print(f"⚠️ Ошибка инициализации Tesseract: {e}")

# ------------------------------
# 3. РАБОТА С БАЗОЙ ДАННЫХ (SQLite)
# ------------------------------
def init_db():
    conn = sqlite3.connect('tickets.db')
    c = conn.cursor()
    c.execute('''
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
    c.execute('''
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

def add_ticket_code(ticket_code, user_id, username, first_name, roblox_nick):
    conn = sqlite3.connect('tickets.db')
    c = conn.cursor()
    try:
        c.execute('''
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
    c = conn.cursor()
    c.execute('SELECT 1 FROM used_tickets WHERE ticket_code = ?', (ticket_code,))
    result = c.fetchone()
    conn.close()
    return result is not None

def delete_ticket_by_code(ticket_code):
    conn = sqlite3.connect('tickets.db')
    c = conn.cursor()
    c.execute('DELETE FROM used_tickets WHERE ticket_code = ?', (ticket_code,))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted > 0

def get_ticket_info(ticket_code):
    conn = sqlite3.connect('tickets.db')
    c = conn.cursor()
    c.execute('SELECT ticket_code, first_name, roblox_nick, check_date FROM used_tickets WHERE ticket_code = ?', (ticket_code,))
    ticket = c.fetchone()
    conn.close()
    return ticket

def search_tickets_by_code(search_term):
    conn = sqlite3.connect('tickets.db')
    c = conn.cursor()
    c.execute('SELECT ticket_code, first_name, roblox_nick, check_date FROM used_tickets WHERE ticket_code LIKE ? ORDER BY check_date DESC', (f'%{search_term}%',))
    tickets = c.fetchall()
    conn.close()
    return tickets

def search_by_roblox_nick(nick):
    conn = sqlite3.connect('tickets.db')
    c = conn.cursor()
    c.execute('SELECT ticket_code, first_name, roblox_nick, check_date FROM used_tickets WHERE roblox_nick LIKE ? ORDER BY check_date DESC', (f'%{nick}%',))
    rows = c.fetchall()
    conn.close()
    return rows

def is_blacklisted(user_id=None, roblox_nick=None, ticket_code=None):
    conn = sqlite3.connect('tickets.db')
    c = conn.cursor()
    if user_id:
        c.execute('SELECT 1 FROM blacklist WHERE user_id = ?', (user_id,))
    elif roblox_nick:
        c.execute('SELECT 1 FROM blacklist WHERE roblox_nick = ?', (roblox_nick,))
    elif ticket_code:
        c.execute('SELECT 1 FROM blacklist WHERE ticket_code = ?', (ticket_code,))
    else:
        conn.close()
        return False
    result = c.fetchone()
    conn.close()
    return result is not None

def get_blacklist():
    conn = sqlite3.connect('tickets.db')
    c = conn.cursor()
    c.execute('SELECT user_id, roblox_nick, ticket_code, reason, ban_date FROM blacklist ORDER BY ban_date DESC')
    data = c.fetchall()
    conn.close()
    return data

def add_to_blacklist(user_id=None, roblox_nick=None, ticket_code=None, reason="Нарушение", banned_by=None):
    conn = sqlite3.connect('tickets.db')
    c = conn.cursor()
    if user_id:
        c.execute('SELECT 1 FROM blacklist WHERE user_id = ?', (user_id,))
        if c.fetchone():
            conn.close()
            return False, "Уже в ЧС"
    c.execute('INSERT INTO blacklist (user_id, roblox_nick, ticket_code, reason, banned_by, ban_date) VALUES (?, ?, ?, ?, ?, ?)',
              (user_id, roblox_nick, ticket_code, reason, banned_by, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    return True, "Добавлен в ЧС"

def remove_from_blacklist(user_id=None, roblox_nick=None, ticket_code=None):
    conn = sqlite3.connect('tickets.db')
    c = conn.cursor()
    if user_id:
        c.execute('DELETE FROM blacklist WHERE user_id = ?', (user_id,))
    elif roblox_nick:
        c.execute('DELETE FROM blacklist WHERE roblox_nick = ?', (roblox_nick,))
    elif ticket_code:
        c.execute('DELETE FROM blacklist WHERE ticket_code = ?', (ticket_code,))
    else:
        conn.close()
        return False
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted > 0

# ------------------------------
# 4. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ И КЛАВИАТУРЫ
# ------------------------------
def is_admin(user_id):
    return user_id in ADMIN_IDS

def get_admin_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📋 Список билетов", callback_data="admin_list"),
        InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
        InlineKeyboardButton("🗑 Удалить 1 билет", callback_data="admin_delete_one"),
        InlineKeyboardButton("🗑 Очистить всё", callback_data="admin_clear"),
        InlineKeyboardButton("🔍 Поиск по коду", callback_data="admin_search_code"),
        InlineKeyboardButton("🎮 Поиск по нику", callback_data="admin_search_nick"),
        InlineKeyboardButton("🚫 Чёрный список", callback_data="admin_blacklist"),
        InlineKeyboardButton("📝 Экспорт ников", callback_data="admin_export_nicks"),
        InlineKeyboardButton("💾 Резервная копия", callback_data="admin_backup")
    )
    return kb

def get_nickname_confirm_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Да, подтверждаю", callback_data="nickname_confirm_yes"),
        InlineKeyboardButton("❌ Нет, изменить", callback_data="nickname_confirm_no")
    )
    return kb

def get_back_keyboard():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="admin_back"))
    return kb

def get_blacklist_keyboard():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("➕ Добавить в ЧС", callback_data="blacklist_add"),
        InlineKeyboardButton("➖ Удалить из ЧС", callback_data="blacklist_remove"),
        InlineKeyboardButton("📋 Список ЧС", callback_data="blacklist_list"),
        InlineKeyboardButton("🔙 Назад", callback_data="admin_back")
    )
    return kb

def get_blacklist_add_keyboard():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("👤 По Telegram ID", callback_data="blacklist_add_user"),
        InlineKeyboardButton("🎮 По Roblox нику", callback_data="blacklist_add_nick"),
        InlineKeyboardButton("🎫 По коду билета", callback_data="blacklist_add_ticket"),
        InlineKeyboardButton("🔙 Назад", callback_data="admin_blacklist")
    )
    return kb

def save_nicks_to_txt():
    conn = sqlite3.connect('tickets.db')
    c = conn.cursor()
    c.execute('SELECT roblox_nick FROM used_tickets WHERE roblox_nick IS NOT NULL AND roblox_nick != "" ORDER BY check_date DESC')
    nicks = c.fetchall()
    conn.close()
    if not nicks:
        return None
    filename = f"nicks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(filename, 'w', encoding='utf-8') as f:
        for nick in nicks:
            f.write(f"{nick[0]}\n")
    return filename

# ------------------------------
# 5. ОСНОВНЫЕ ОБРАБОТЧИКИ
# ------------------------------
user_states = {}
admin_states = {}

@bot.message_handler(commands=['start'])
def start(message: Message):
    uid = message.from_user.id
    if is_blacklisted(user_id=uid):
        bot.send_message(uid, "🚫 *Доступ заблокирован!* Обратитесь к администратору.", parse_mode='Markdown')
        return
    bot.send_message(uid, "🎫 Добро пожаловать в бот проверки билетов!\nОтправьте мне *фото билета* или просто *введите код билета* вручную.", parse_mode='Markdown')
    if is_admin(uid):
        bot.send_message(uid, "🔐 Панель администратора", reply_markup=get_admin_keyboard())

@bot.message_handler(content_types=['photo'])
def handle_photo(message: Message):
    uid = message.from_user.id
    if is_blacklisted(user_id=uid):
        bot.send_message(uid, "🚫 Доступ заблокирован.")
        return
    if HAS_TESSERACT:
        # Если есть OCR – пытаемся распознать код
        file_id = message.photo[-1].file_id
        # Здесь должна быть логика распознавания через get_code_from_photo
        # Для простоты – заглушка: просим ввести код вручную
        bot.reply_to(message, "🔍 Распознавание временно отключено. Пожалуйста, *введите код билета* текстом.", parse_mode='Markdown')
    else:
        bot.reply_to(message, "📸 Распознавание фото недоступно. *Введите код билета* вручную.", parse_mode='Markdown')

@bot.message_handler(func=lambda m: True)
def handle_text(message: Message):
    uid = message.from_user.id
    if is_blacklisted(user_id=uid):
        bot.send_message(uid, "🚫 Доступ заблокирован.")
        return

    # Если админ в режиме ожидания – пропускаем (обрабатывается отдельно)
    if is_admin(uid) and admin_states.get(uid) in ['waiting_for_delete_code', 'waiting_for_search_code', 'waiting_for_search_nick']:
        return

    # Обычный пользователь: вводит код билета
    code = message.text.strip()
    if re.fullmatch(r'\d{8,15}', code):
        if check_ticket_code(code):
            bot.reply_to(message, f"❌ Билет {code} уже использован.")
        else:
            user_states[uid] = {'ticket_code': code, 'username': message.from_user.username or "", 'first_name': message.from_user.first_name or "", 'awaiting_nickname': True}
            bot.reply_to(message, f"✅ Билет {code} действителен!\nТеперь введите ваш *Roblox ник*:", parse_mode='Markdown')
    else:
        if uid in user_states and user_states[uid].get('awaiting_nickname'):
            nick = message.text.strip()
            if is_blacklisted(roblox_nick=nick):
                bot.reply_to(message, "🚫 Этот Roblox ник заблокирован.")
                user_states.pop(uid, None)
                return
            user_states[uid]['roblox_nick'] = nick
            user_states[uid]['awaiting_nickname'] = False
            bot.reply_to(message, f"🎮 Вы ввели ник: *{nick}*\nЭто ваш Roblox ник?", parse_mode='Markdown', reply_markup=get_nickname_confirm_keyboard())
        else:
            bot.reply_to(message, "📸 Отправьте фото билета или введите код билета (8–15 цифр).")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    uid = call.from_user.id
    if not is_admin(uid):
        bot.answer_callback_query(call.id, "Нет доступа", show_alert=True)
        return

    # ---------- АДМИН-КОМАНДЫ ----------
    if call.data == "admin_list":
        conn = sqlite3.connect('tickets.db')
        c = conn.cursor()
        c.execute('SELECT ticket_code, first_name, roblox_nick, check_date FROM used_tickets ORDER BY check_date DESC')
        tickets = c.fetchall()
        conn.close()
        if not tickets:
            bot.edit_message_text("📋 Список пуст", call.message.chat.id, call.message.message_id, reply_markup=get_admin_keyboard())
            return
        text = "📋 СПИСОК БИЛЕТОВ\n\n"
        for i, t in enumerate(tickets[:30], 1):
            text += f"{i}. 🎫 {t[0]}\n   👤 {t[1]}\n   🎮 {t[2] or '—'}\n   📅 {t[3]}\n\n"
        if len(tickets) > 30:
            text += f"\nВсего: {len(tickets)}"
        bot.edit_message_text(text[:4000], call.message.chat.id, call.message.message_id, reply_markup=get_admin_keyboard())

    elif call.data == "admin_stats":
        conn = sqlite3.connect('tickets.db')
        c = conn.cursor()
        total = c.execute('SELECT COUNT(*) FROM used_tickets').fetchone()[0]
        users = c.execute('SELECT COUNT(DISTINCT user_id) FROM used_tickets').fetchone()[0]
        with_nick = c.execute('SELECT COUNT(*) FROM used_tickets WHERE roblox_nick IS NOT NULL').fetchone()[0]
        black = c.execute('SELECT COUNT(*) FROM blacklist').fetchone()[0]
        last = c.execute('SELECT check_date FROM used_tickets ORDER BY check_date DESC LIMIT 1').fetchone()
        conn.close()
        text = f"📊 СТАТИСТИКА\n✅ Билетов: {total}\n👥 Пользователей: {users}\n🎮 С ником: {with_nick}\n🚫 В ЧС: {black}\n🕐 Последний: {last[0] if last else '—'}"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=get_admin_keyboard())

    elif call.data == "admin_delete_one":
        admin_states[uid] = 'waiting_for_delete_code'
        bot.edit_message_text("🗑 Введите код билета для удаления:", call.message.chat.id, call.message.message_id, reply_markup=get_back_keyboard())

    elif call.data == "admin_search_code":
        admin_states[uid] = 'waiting_for_search_code'
        bot.edit_message_text("🔍 Введите код или часть кода:", call.message.chat.id, call.message.message_id, reply_markup=get_back_keyboard())

    elif call.data == "admin_search_nick":
        admin_states[uid] = 'waiting_for_search_nick'
        bot.edit_message_text("🎮 Введите Roblox ник или его часть:", call.message.chat.id, call.message.message_id, reply_markup=get_back_keyboard())

    elif call.data == "admin_blacklist":
        bot.edit_message_text("🚫 Чёрный список", call.message.chat.id, call.message.message_id, reply_markup=get_blacklist_keyboard())

    elif call.data == "blacklist_add":
        bot.edit_message_text("➕ Добавление в ЧС", call.message.chat.id, call.message.message_id, reply_markup=get_blacklist_add_keyboard())

    elif call.data == "blacklist_add_user":
        admin_states[uid] = 'waiting_blacklist_user'
        bot.edit_message_text("Введите Telegram ID (число):", call.message.chat.id, call.message.message_id, reply_markup=get_back_keyboard())

    elif call.data == "blacklist_add_nick":
        admin_states[uid] = 'waiting_blacklist_nick'
        bot.edit_message_text("Введите Roblox ник:", call.message.chat.id, call.message.message_id, reply_markup=get_back_keyboard())

    elif call.data == "blacklist_add_ticket":
        admin_states[uid] = 'waiting_blacklist_ticket'
        bot.edit_message_text("Введите код билета:", call.message.chat.id, call.message.message_id, reply_markup=get_back_keyboard())

    elif call.data == "blacklist_remove":
        admin_states[uid] = 'waiting_blacklist_remove'
        bot.edit_message_text("Введите ID, @ник или код билета:", call.message.chat.id, call.message.message_id, reply_markup=get_back_keyboard())

    elif call.data == "blacklist_list":
        blacklist = get_blacklist()
        if not blacklist:
            bot.edit_message_text("📋 ЧС пуст", call.message.chat.id, call.message.message_id, reply_markup=get_blacklist_keyboard())
            return
        text = "🚫 ЧЁРНЫЙ СПИСОК\n"
        for i, item in enumerate(blacklist[:30], 1):
            text += f"{i}. "
            if item[0]: text += f"👤 {item[0]}"
            elif item[1]: text += f"🎮 {item[1]}"
            elif item[2]: text += f"🎫 {item[2]}"
            text += f" | {item[3]}\n   📅 {item[4]}\n\n"
        bot.edit_message_text(text[:4000], call.message.chat.id, call.message.message_id, reply_markup=get_blacklist_keyboard())

    elif call.data == "admin_export_nicks":
        fname = save_nicks_to_txt()
        if fname:
            with open(fname, 'rb') as f:
                bot.send_document(call.message.chat.id, f, caption="📝 Список Roblox ников")
            os.remove(fname)
        else:
            bot.answer_callback_query(call.id, "Нет ников", show_alert=True)
        bot.edit_message_text("🔐 Админ-панель", call.message.chat.id, call.message.message_id, reply_markup=get_admin_keyboard())

    elif call.data == "admin_backup":
        conn = sqlite3.connect('tickets.db')
        c = conn.cursor()
        tickets = c.execute('SELECT ticket_code, first_name, roblox_nick, check_date FROM used_tickets').fetchall()
        black = c.execute('SELECT user_id, roblox_nick, ticket_code, reason, ban_date FROM blacklist').fetchall()
        conn.close()
        with open('backup.txt', 'w', encoding='utf-8') as f:
            f.write(f"Бекап {datetime.now()}\n===Билеты===\n")
            for t in tickets:
                f.write(f"{t[0]} | {t[1]} | {t[2] or '—'} | {t[3]}\n")
            f.write("\n===ЧС===\n")
            for b in black:
                f.write(f"{b[0] or '—'} | {b[1] or '—'} | {b[2] or '—'} | {b[3]} | {b[4]}\n")
        with open('backup.txt', 'rb') as f:
            bot.send_document(call.message.chat.id, f, caption="💾 Бекап БД")
        os.remove('backup.txt')
        bot.answer_callback_query(call.id, "Бекап создан")

    elif call.data == "admin_clear":
        bot.edit_message_text("⚠️ Очистить ВСЕ билеты? Необратимо!", call.message.chat.id, call.message.message_id,
                              reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("✅ ДА", callback_data="confirm_clear"), InlineKeyboardButton("❌ НЕТ", callback_data="admin_back")))

    elif call.data == "confirm_clear":
        conn = sqlite3.connect('tickets.db')
        conn.execute('DELETE FROM used_tickets')
        conn.commit()
        conn.close()
        bot.edit_message_text("✅ База очищена", call.message.chat.id, call.message.message_id, reply_markup=get_admin_keyboard())

    elif call.data == "admin_back":
        admin_states.pop(uid, None)
        bot.edit_message_text("🔐 Админ-панель", call.message.chat.id, call.message.message_id, reply_markup=get_admin_keyboard())

    # ---------- ПОДТВЕРЖДЕНИЕ НИКА ----------
    elif call.data == "nickname_confirm_yes":
        data = user_states.get(uid)
        if data:
            ok = add_ticket_code(data['ticket_code'], uid, data['username'], data['first_name'], data['roblox_nick'])
            bot.edit_message_text("✅ БИЛЕТ ЗАРЕГИСТРИРОВАН!" if ok else "❌ Ошибка! Билет уже использован.", call.message.chat.id, call.message.message_id)
            user_states.pop(uid, None)
        else:
            bot.answer_callback_query(call.id, "Сессия истекла")
    elif call.data == "nickname_confirm_no":
        if uid in user_states:
            user_states[uid]['awaiting_nickname'] = True
            bot.edit_message_text("✏️ Введите правильный Roblox ник:", call.message.chat.id, call.message.message_id)
        else:
            bot.answer_callback_query(call.id, "Сессия истекла")

    bot.answer_callback_query(call.id)

# ------------------------------
# 6. ЗАПУСК
# ------------------------------
if __name__ == "__main__":
    init_db()
    print("🤖 Бот запущен!")
    bot.infinity_polling()
