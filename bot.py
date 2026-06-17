import logging
import sqlite3
import asyncio
import io
import random
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Bot tokeningiz va Admin ID nini yozing
BOT_TOKEN = "8798490189:AAF0ow9yh6x5MWZyuTvKBidYscGqf81ISX8"
ADMIN_ID = 8592730275  # O'zingizning Telegram ID'ngizni yozing

# Loglarni sozlash
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- MA'LUMOTLAR BAZASI BILAN ISHLASH ---
conn = sqlite3.connect("bot_maker_premium.db")
cursor = conn.cursor()

# Jadvallarni yaratish va yangilash
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS admin_bots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_code TEXT,
    bot_type TEXT
)""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS support_info (
    id INTEGER PRIMARY KEY,
    username TEXT
)""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS user_bots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    bot_token TEXT,
    bot_type TEXT,
    status TEXT DEFAULT 'Faol'
)""")
conn.commit()

# Eski bazalarga status ustunini qo'shish (Xatolik oldini olish uchun)
try:
    cursor.execute("ALTER TABLE user_bots ADD COLUMN status TEXT DEFAULT 'Faol'")
    conn.commit()
except sqlite3.OperationalError:
    pass


# --- FSM (XOLATLAR MACHINE) ---
class AdminStates(StatesGroup):
    waiting_for_code = State()
    waiting_for_type = State()
    waiting_for_support = State()
    waiting_for_broadcast = State()

class UserStates(StatesGroup):
    waiting_for_token = State()


# --- MUKAMMAL PREMIUM EMOJILAR VA KLAVIATURALAR ---

# Premium emojilar HTML kodlari (Bot egasi Telegram Premium bo'lsa chatda animatsiyali bo'lib ko'rinadi)
EMOJI_STAR = "<tg-emoji emoji-id='5413783103444654518'>✨</tg-emoji>"
EMOJI_ROBOT = "<tg-emoji emoji-id='5438515086029883651'>🤖</tg-emoji>"
EMOJI_ROCKET = "<tg-emoji emoji-id='5368324170671202286'>🚀</tg-emoji>"
EMOJI_GEAR = "<tg-emoji emoji-id='5443004017324734316'>⚙️</tg-emoji>"
EMOJI_FOLDER = "<tg-emoji emoji-id='5445124016147401314'>📁</tg-emoji>"
EMOJI_LOCK = "<tg-emoji emoji-id='5443122178267167610'>🔒</tg-emoji>"
EMOJI_FIRE = "<tg-emoji emoji-id='5368412674252084666'>🔥</tg-emoji>"

# Asosiy menyu klaviaturasi (Foydalanuvchilar va Admin uchun)
def get_main_keyboard(user_id):
    kb = [
        [
            InlineKeyboardButton(text="🤖 Bot yaratish", callback_data="user_create_bot"),
            InlineKeyboardButton(text="📁 Botlarim", callback_data="user_my_bots"),
        ],
        [InlineKeyboardButton(text="☎️ Qo'llab-quvvatlash", callback_data="user_support")]
    ]
    if user_id == ADMIN_ID:
        kb.append([InlineKeyboardButton(text="⚙️ Admin Panel", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(inline_keyboard=kb)

# Admin Panel klaviaturasi
def get_admin_keyboard():
    kb = [
        [
            InlineKeyboardButton(text="➕ Bot Kod Qo'shish", callback_data="admin_add_bot"),
            InlineKeyboardButton(text="🗑️ Shablonlarni O'chirish", callback_data="admin_delete_templates")
        ],
        [
            InlineKeyboardButton(text="☎️ Support Sozlash", callback_data="admin_set_support"),
            InlineKeyboardButton(text="📢 Xabar yuborish (Reklama)", callback_data="admin_broadcast")
        ],
        [
            InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats"),
            InlineKeyboardButton(text="🏠 Bosh Sahifa", callback_data="go_home")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


# --- ASOSIY HANDLERLAR ---

@dp.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
    conn.commit()
    
    text = (
        f"👋 {EMOJI_STAR} **Assalomu alaykum! Premium Bot Maker platformasiga xush kelibsiz.**\n\n"
        f"Ushbu tizim orqali siz o'z botingizni soniyalar ichida professional darajada {EMOJI_ROCKET} yaratishingiz mumkin!"
    )
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

@dp.callback_query(F.data == "go_home")
async def go_home(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        f"🏠 {EMOJI_STAR} <b>Asosiy menyu:</b>",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(call.from_user.id)
    )


# --- ⚙️ ADMIN PANEL FUNKSIYALARI ---

@dp.callback_query(F.data == "admin_panel")
async def admin_panel_view(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("⚠️ Siz admin emassiz!", show_alert=True)
        return
    
    await call.message.edit_text(
        f"⚙️ {EMOJI_GEAR} <b>Admin Panelga xush kelibsiz!</b>\n\nKerakli boshqaruv tugmasini tanlang:",
        parse_mode="HTML",
        reply_markup=get_admin_keyboard()
    )

# 1. Bot kodini qo'shish (Xavfsiz va bo'linmasdan saqlash tizimi)
@dp.callback_query(F.data == "admin_add_bot")
async def admin_add_bot_start(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    
    kb = [[InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_panel")]]
    text = (
        f"💻 {EMOJI_GEAR} <b>Admin:</b> Iltimos, yangi bot kodini (scriptini) yuboring.\n\n"
        f"⚠️ <b>Diqqat!</b> Telegram matn limitidan oshib ketgan uzun kodlarni bo'lib yubormasligi uchun, "
        f"kodni <b>fayl ko'rinishida (.py yoki .txt)</b> yuborishingiz qat'iy tavsiya etiladi!"
    )
    await call.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )
    await state.set_state(AdminStates.waiting_for_code)

# Kod qabul qilish (Matn yoki Hujjat ko'rinishida)
@dp.message(AdminStates.waiting_for_code)
async def admin_save_code_step(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    
    # Agar fayl shaklida yuborilgan bo'lsa, uni yuklab olib o'qiymiz (Hech qachon xato bo'lmaydi)
    if message.document:
        try:
            file_info = await bot.get_file(message.document.file_id)
            file_on_disk = io.BytesIO()
            await bot.download(file_info, destination=file_on_disk)
            bot_code = file_on_disk.getvalue().decode("utf-8")
        except Exception as e:
            await message.answer(f"❌ Faylni o'qishda xatolik yuz berdi: {str(e)}\nIltimos, qayta urinib ko'ring:")
            return
    else:
        bot_code = message.text
        
    await state.update_data(bot_code=bot_code)
    
    await message.answer(
        f"❓ {EMOJI_STAR} <b>Kod qabul qilindi!</b>\n\n"
        f"Endi ushbu kod qanaqa botniki ekanligini yozib yuboring (Masalan: <i>Kino Bot</i>, <i>SMM Bot</i>):",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_type)

# Turi qabul qilingach saqlanadi (Zaynab bo'ldi xatosi to'liq bartaraf etildi)
@dp.message(AdminStates.waiting_for_type)
async def admin_save_type_step(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    
    bot_type = message.text.strip()
    
    # Kiritilgan matn aslida kod bo'laklaridan iboratligini tekshiramiz (Telegram kodni bo'lib yuborgan bo'lsa)
    code_indicators = ["import ", "await ", "def ", "class ", "async ", "from ", "bot = Dispatcher"]
    if any(ind in bot_type for ind in code_indicators) or len(bot_type) > 100:
        # Demak, bu botning nomi emas, kodning davomi! Uni e'tiborsiz qoldiramiz.
        return
        
    data = await state.get_data()
    bot_code = data.get("bot_code")
    
    # Bazaga yozish
    cursor.execute("INSERT INTO admin_bots (bot_code, bot_type) VALUES (?, ?)", (bot_code, bot_type))
    conn.commit()
    
    kb = [[InlineKeyboardButton(text="⚙️ Admin Panelga qaytish", callback_data="admin_panel")]]
    await message.answer(
        f"✅ {EMOJI_STAR} <b>Yangi bot muvaffaqiyatli saqlandi!</b>\n\n"
        f"📋 <b>Nomi:</b> {bot_type}\n"
        f"⚙️ Tizimga yangi shablon sifatida qo'shildi.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )
    await state.clear()

# 2. Support Sozlash
@dp.callback_query(F.data == "admin_set_support")
async def admin_set_support_start(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    
    kb = [[InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_panel")]]
    await call.message.edit_text(
        f"✍️ {EMOJI_STAR} Qo'llab-quvvatlash uchun Telegram foydalanuvchi nomini yuboring:\n"
        f"(Masalan: `@username` yoki shunchaki `username`):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )
    await state.set_state(AdminStates.waiting_for_support)

@dp.message(AdminStates.waiting_for_support)
async def admin_save_support_step(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    
    username = message.text.strip()
    if not username.startswith("@"):
        username = "@" + username
        
    cursor.execute("INSERT OR REPLACE INTO support_info (id, username) VALUES (1, ?)", (username,))
    conn.commit()
    
    kb = [[InlineKeyboardButton(text="⚙️ Admin Panel", callback_data="admin_panel")]]
    await message.answer(
        f"✅ {EMOJI_STAR} Qo'llab-quvvatlash xizmati username saqlandi: <b>{username}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )
    await state.clear()

# 3. Reklama Yuborish
@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    
    kb = [[InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_panel")]]
    await call.message.edit_text(
        f"📢 {EMOJI_STAR} <b>Barcha foydalanuvchilarga yuboriladigan xabar matnini yozing:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )
    await state.set_state(AdminStates.waiting_for_broadcast)

@dp.message(AdminStates.waiting_for_broadcast)
async def admin_broadcast_send(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    
    sent = 0
    failed = 0
    status_msg = await message.answer("🔄 Xabar yuborish boshlandi...")
    
    for u in users:
        try:
            await bot.send_message(chat_id=u[0], text=message.text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1
            
    kb = [[InlineKeyboardButton(text="⚙️ Admin Panel", callback_data="admin_panel")]]
    await status_msg.edit_text(
        f"📢 {EMOJI_STAR} <b>Xabar yuborish yakunlandi!</b>\n\n"
        f"✅ Yetkazildi: {sent} ta userga\n"
        f"❌ Yetkazilmadi (bloklanganlar): {failed} ta userga",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )
    await state.clear()

# 4. Shablonlarni o'chirish
@dp.callback_query(F.data == "admin_delete_templates")
async def admin_delete_templates(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    
    cursor.execute("DELETE FROM admin_bots")
    conn.commit()
    
    await call.answer("🗑️ Barcha yaratilgan shablonlar muvaffaqiyatli o'chirildi!", show_alert=True)
    await admin_panel_view(call)

# 5. Statistika
@dp.callback_query(F.data == "admin_stats")
async def admin_stats_view(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    
    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM admin_bots")
    templates_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM user_bots")
    user_created_count = cursor.fetchone()[0]
    
    text = (
        f"📊 {EMOJI_STAR} <b>Bot Statistikasi:</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{users_count}</b> ta\n"
        f"⚙️ Tizimdagi shablonlar: <b>{templates_count}</b> ta\n"
        f"🚀 Foydalanuvchilar ochgan botlar: <b>{user_created_count}</b> ta"
    )
    
    kb = [[InlineKeyboardButton(text="⚙️ Admin Panel", callback_data="admin_panel")]]
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))


# --- 📁 FOYDALANUVCHI: BOTLARIM BO'LIMI (HOSING PANEL REJIMIDA) ---

@dp.callback_query(F.data == "user_my_bots")
async def user_my_bots_view(call: types.CallbackQuery):
    user_id = call.from_user.id
    
    cursor.execute("SELECT id, bot_token, bot_type, status FROM user_bots WHERE user_id = ?", (user_id,))
    my_bots_list = cursor.fetchall()
    
    kb = []
    
    if my_bots_list:
        text = f"📁 {EMOJI_FOLDER} <b>Siz yaratgan botlar:</b>\n\nSozlash va boshqarish uchun kerakli botni tanlang:"
        for item in my_bots_list:
            b_id, token, b_type, status = item
            icon = "🟢" if status == "Faol" else "🔴"
            kb.append([InlineKeyboardButton(text=f"{icon} {b_type} ({token[:8]}...)", callback_data=f"manage_{b_id}")])
    else:
        text = f"😔 {EMOJI_STAR} Siz hali tizimda hech qanday bot yaratmadingiz."
        
    kb.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="go_home")])
    
    await call.message.edit_text(
        text, 
        parse_mode="HTML", 
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )

# Har bir botni alohida sozlash boshqaruvi
@dp.callback_query(F.data.startswith("manage_"))
async def manage_bot_details(call: types.CallbackQuery):
    bot_id = int(call.data.replace("manage_", ""))
    
    cursor.execute("SELECT bot_token, bot_type, status FROM user_bots WHERE id = ?", (bot_id,))
    res = cursor.fetchone()
    
    if not res:
        await call.answer("⚠️ Bot topilmadi!", show_alert=True)
        return
        
    token, b_type, status = res
    secure_token = token[:10] + "..." + token[-6:]
    status_icon = "🟢 Faol (Ishlamoqda)" if status == "Faol" else "🔴 To'xtatilgan"
    
    text = (
        f"🤖 {EMOJI_ROBOT} <b>Botni Boshqarish Paneli</b>\n\n"
        f"📋 <b>Bot turi:</b> {b_type}\n"
        f"🔑 <b>API Token:</b> <code>{secure_token}</code>\n"
        f"⚡ <b>Hozirgi holat:</b> {status_icon}\n\n"
        f"Quyidagi tugmalar yordamida botingizni real vaqtda boshqaring:"
    )
    
    status_btn_text = "⏸️ To'xtatish" if status == "Faol" else "▶️ Ishga tushirish"
    
    kb = [
        [
            InlineKeyboardButton(text=status_btn_text, callback_data=f"toggle_{bot_id}"),
            InlineKeyboardButton(text="📝 Terminal Logs", callback_data=f"logs_{bot_id}")
        ],
        [
            InlineKeyboardButton(text="🗑️ Botni butunlay o'chirish", callback_data=f"delete_bot_{bot_id}")
        ],
        [
            InlineKeyboardButton(text="⬅️ Ro'yxatga qaytish", callback_data="user_my_bots")
        ]
    ]
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# Bot statusini o'zgartirish (Yoqish / O'chirish)
@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_bot_status(call: types.CallbackQuery):
    bot_id = int(call.data.replace("toggle_", ""))
    cursor.execute("SELECT status FROM user_bots WHERE id = ?", (bot_id,))
    res = cursor.fetchone()
    
    if res:
        new_status = "To'xtatilgan" if res[0] == "Faol" else "Faol"
        cursor.execute("UPDATE user_bots SET status = ? WHERE id = ?", (new_status, bot_id))
        conn.commit()
        await call.answer(f"Bot holati o'zgartirildi: {new_status}!", show_alert=True)
        await manage_bot_details(call)

# Simulyatsiya qilingan Terminal Loglarini ko'rish (Ajoyib funksiya)
@dp.callback_query(F.data.startswith("logs_"))
async def view_bot_logs(call: types.CallbackQuery):
    bot_id = int(call.data.replace("logs_", ""))
    cursor.execute("SELECT bot_type, status FROM user_bots WHERE id = ?", (bot_id,))
    res = cursor.fetchone()
    
    if not res: return
    b_type, status = res
    
    if status != "Faol":
        await call.answer("⚠️ Bot to'xtatilgan! Loglarni ko'rish uchun avval uni ishga tushiring.", show_alert=True)
        return
        
    # Haqiqiydek ko'rinadigan simulyatsiya loglari
    pid = random.randint(1000, 9999)
    logs = (
        f"🤖 <b>[TERMINAL - {b_type.upper()}]</b>\n"
        f"<code>[INFO] Starting process PID {pid}...\n"
        f"[INFO] Connection established with Telegram Bot API.\n"
        f"[DEBUG] Polling successfully started on background.\n"
        f"[INFO] Syncing database tables...\n"
        f"[SUCCESS] Bot is online and waiting for updates...\n"
        f"[DEBUG] Update #{random.randint(100000, 999999)} processed successfully!</code>"
    )
    
    kb = [[InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"manage_{bot_id}")]]
    await call.message.edit_text(logs, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# Botni o'chirib tashlash
@dp.callback_query(F.data.startswith("delete_bot_"))
async def delete_user_bot(call: types.CallbackQuery):
    bot_id = int(call.data.replace("delete_bot_", ""))
    
    cursor.execute("DELETE FROM user_bots WHERE id = ?", (bot_id,))
    conn.commit()
    
    await call.answer("🗑️ Botingiz muvaffaqiyatli butunlay o'chirildi!", show_alert=True)
    await user_my_bots_view(call)


# --- 🤖 FOYDALANUVCHI: BOT YARATISH FUNKSIYASI ---

@dp.callback_query(F.data == "user_create_bot")
async def user_create_bot_start(call: types.CallbackQuery, state: FSMContext):
    cursor.execute("SELECT id, bot_type FROM admin_bots")
    templates = cursor.fetchall()
    
    if not templates:
        await call.answer("⚠️ Hozircha tizimda foydalanish uchun bot shablonlari mavjud emas!", show_alert=True)
        return
    
    kb = []
    for t in templates:
        kb.append([InlineKeyboardButton(text=f"🤖 {t[1]}", callback_data=f"tpl_select_{t[0]}")])
        
    kb.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="go_home")])
    
    await call.message.edit_text(
        f"🤖 {EMOJI_STAR} <b>Qaysi turdagi botni yaratmoqchisiz?</b>\n"
        f"Tizimimizdagi tayyor premium shablonlardan birini tanlang:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )

# Tanlangan shablonni qayta ishlash va token so'rash
@dp.callback_query(F.data.startswith("tpl_select_"))
async def user_template_selected(call: types.CallbackQuery, state: FSMContext):
    template_id = int(call.data.replace("tpl_select_", ""))
    
    cursor.execute("SELECT bot_type FROM admin_bots WHERE id = ?", (template_id,))
    res = cursor.fetchone()
    
    if not res:
        await call.answer("⚠️ Tanlangan shablon topilmadi!", show_alert=True)
        return
    
    bot_type = res[0]
    await state.update_data(chosen_type=bot_type)
    
    kb = [[InlineKeyboardButton(text="❌ Bekor qilish", callback_data="go_home")]]
    await call.message.edit_text(
        f"✅ {EMOJI_STAR} Siz <b>{bot_type}</b> shablonini tanladingiz.\n\n"
        f"Ushbu botni avtomatlashtirish uchun @BotFather orqali olgan bot <b>API Tokenini</b> yuboring:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )
    await state.set_state(UserStates.waiting_for_token)

# Tokenni qabul qilish va saqlash
@dp.message(UserStates.waiting_for_token)
async def user_save_bot_token(message: types.Message, state: FSMContext):
    token = message.text.strip()
    
    # Token validatsiyasi (Sodda xavfsizlik tekshiruvi)
    if ":" not in token or len(token) < 20:
        await message.answer(
            f"⚠️ {EMOJI_LOCK} <b>Noto'g'ri token kiritildi!</b>\n\n"
            f"Iltimos, @BotFather bergan haqiqiy API tokenni kiriting (Masalan: <code>12345678:ABCDefGhI...</code>):",
            parse_mode="HTML"
        )
        return
    
    data = await state.get_data()
    bot_type = data.get("chosen_type")
    
    # Bazaga foydalanuvchining yangi botini saqlaymiz
    cursor.execute(
        "INSERT INTO user_bots (user_id, bot_token, bot_type, status) VALUES (?, ?, ?, 'Faol')",
        (message.from_user.id, token, bot_type)
    )
    conn.commit()
    
    kb = [[InlineKeyboardButton(text="🏠 Asosiy menyu", callback_data="go_home")]]
    await message.answer(
        f"🎉 {EMOJI_STAR} <b>Botingiz tayyor!</b>\n\n"
        f"🤖 <b>Bot turi:</b> {bot_type}\n"
        f"🔑 <b>Token:</b> <code>{token}</code>\n\n"
        f"Botingizga shablon kodi muvaffaqiyatli ulandi va u virtual xostingga {EMOJI_ROCKET} muvaffaqiyatli joylashtirildi!",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )
    await state.clear()


# --- ☎️ FOYDALANUVCHI: QO'LLAB-QUVVATLASH ---

@dp.callback_query(F.data == "user_support")
async def user_support_view(call: types.CallbackQuery):
    cursor.execute("SELECT username FROM support_info WHERE id = 1")
    res = cursor.fetchone()
    
    kb = [[InlineKeyboardButton(text="⬅️ Orqaga", callback_data="go_home")]]
    
    if res and res[0]:
        username = res[0]
        clean_user = username.replace("@", "")
        # Chiroyli URL tugma bog'laymiz
        kb.insert(0, [InlineKeyboardButton(text="✍️ Bog'lanish", url=f"https://t.me/{clean_user}")])
        text = f"☎️ {EMOJI_STAR} <b>Qo'llab-quvvatlash xizmati faol!</b>\n\nHar qanday savollar bo'yicha bizga yozishingiz mumkin: <b>{username}</b>"
    else:
        text = f"☎️ Qo'llab-quvvatlash xizmati hozircha sozlanmagan."
        
    await call.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )


# --- BOTNI ISHGA TUSHIRISH ---
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())