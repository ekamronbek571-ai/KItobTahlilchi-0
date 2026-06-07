import asyncio
import logging
import os
import base64
import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from database import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db = Database()


# ─── STATES ────────────────────────────────────────────────────────────────────
class UserStates(StatesGroup):
    waiting_book_name = State()
    waiting_recommendation = State()
    waiting_photo = State()

class AdminStates(StatesGroup):
    waiting_book_name = State()
    waiting_book_info = State()
    waiting_book_photo = State()
    waiting_edit_name = State()
    waiting_edit_field = State()
    waiting_edit_value = State()


# ─── KEYBOARDS ─────────────────────────────────────────────────────────────────
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📚 Kitob ma'lumoti"), KeyboardButton(text="📸 Rasm yuborish")],
            [KeyboardButton(text="💡 Kitob tavsiya"), KeyboardButton(text="ℹ️ Bot haqida")],
        ],
        resize_keyboard=True
    )

def admin_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Kitob qo'shish"), KeyboardButton(text="📋 Kitoblar ro'yxati")],
            [KeyboardButton(text="🔙 Asosiy menyu")],
        ],
        resize_keyboard=True
    )

def cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True
    )


# ─── HELPERS ───────────────────────────────────────────────────────────────────
async def analyze_image_openrouter(image_bytes: bytes) -> str:
    """Rasmni OpenRouter orqali tahlil qiladi va kitob nomini topadi."""
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://kitobtahlilchi.onrender.com",
        "X-Title": "KitobTahlilchi Bot"
    }

    payload = {
        "model": "google/gemini-flash-1.5-8b",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_b64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": (
                            "Bu rasmda kitob muqovasi bor. "
                            "Faqat kitob nomini yoz, boshqa hech narsa yozma. "
                            "Agar kitob nomi ko'rinmasa yoki rasm kitob emas bo'lsa, "
                            "faqat 'TOPILMADI' deb yoz."
                        )
                    }
                ]
            }
        ],
        "max_tokens": 100
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload
        )
        data = response.json()

    if response.status_code != 200:
        logger.error(f"OpenRouter xato: {data}")
        raise Exception(f"OpenRouter API xato: {response.status_code}")

    result = data["choices"][0]["message"]["content"].strip()
    return result


async def get_recommendation_openrouter(user_request: str, books_list: str) -> str:
    """Foydalanuvchi so'roviga qarab kitob tavsiya beradi."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://kitobtahlilchi.onrender.com",
        "X-Title": "KitobTahlilchi Bot"
    }

    payload = {
        "model": "google/gemini-flash-1.5-8b",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Sen kitob do'konidagi yordamchisan. "
                    "Foydalanuvchi so'roviga qarab quyidagi kitoblar ro'yxatidan tavsiya ber. "
                    "Javobni o'zbek tilida yoz. Qisqa va aniq bo'l.\n\n"
                    f"Mavjud kitoblar:\n{books_list}"
                )
            },
            {
                "role": "user",
                "content": user_request
            }
        ],
        "max_tokens": 500
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload
        )
        data = response.json()

    if response.status_code != 200:
        raise Exception(f"OpenRouter API xato: {response.status_code}")

    return data["choices"][0]["message"]["content"].strip()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ─── /start ────────────────────────────────────────────────────────────────────
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    name = message.from_user.first_name
    await message.answer(
        f"Salom, {name}! 👋\n\n"
        "📚 *KitobTahlilchi* botiga xush kelibsiz!\n\n"
        "Quyidagi xizmatlardan foydalaning:",
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )


# ─── /admin ────────────────────────────────────────────────────────────────────
@dp.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Sizda admin huquqi yo'q.", reply_markup=main_menu())
        return
    await state.clear()
    await message.answer("🔐 Admin paneliga xush kelibsiz!", reply_markup=admin_menu())


# ─── BEKOR QILISH ──────────────────────────────────────────────────────────────
@dp.message(F.text == "❌ Bekor qilish")
async def cancel_action(message: Message, state: FSMContext):
    await state.clear()
    if is_admin(message.from_user.id):
        await message.answer("Bekor qilindi.", reply_markup=admin_menu())
    else:
        await message.answer("Bekor qilindi.", reply_markup=main_menu())


# ─── ASOSIY MENYU ──────────────────────────────────────────────────────────────
@dp.message(F.text == "🔙 Asosiy menyu")
async def back_to_main(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=main_menu())


@dp.message(F.text == "ℹ️ Bot haqida")
async def about_bot(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "📚 *KitobTahlilchi Bot*\n\n"
        "Bu bot sizga:\n"
        "• Kitob nomi bo'yicha ma'lumot beradi\n"
        "• Kitob rasmini tahlil qilib, ma'lumot chiqaradi\n"
        "• Sizga mos kitob tavsiya qiladi\n\n"
        "Kitob do'konlari uchun QR kod orqali ishlaydi! 🏪",
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )


# ─── KITOB MA'LUMOTI (nom bo'yicha) ────────────────────────────────────────────
@dp.message(F.text == "📚 Kitob ma'lumoti")
async def book_info_start(message: Message, state: FSMContext):
    await state.set_state(UserStates.waiting_book_name)
    await message.answer(
        "📝 Kitob nomini yozing:",
        reply_markup=cancel_keyboard()
    )


@dp.message(UserStates.waiting_book_name)
async def book_info_search(message: Message, state: FSMContext):
    book_name = message.text.strip()
    book = db.get_book_by_name(book_name)

    if book:
        await state.clear()
        text = (
            f"📖 *{book['name']}*\n\n"
            f"{book['info']}"
        )
        if book.get("photo"):
            await message.answer_photo(
                photo=book["photo"],
                caption=text,
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
        else:
            await message.answer(text, parse_mode="Markdown", reply_markup=main_menu())
    else:
        # Qisman qidirish
        books = db.search_books(book_name)
        if books:
            inline_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=b["name"], callback_data=f"book_{b['id']}")]
                for b in books[:5]
            ])
            await message.answer(
                f"🔍 '{book_name}' bo'yicha natijalar:",
                reply_markup=inline_kb
            )
        else:
            await message.answer(
                "❌ Kitob topilmadi.\n\nBoshqa nom yozing yoki bekor qiling.",
                reply_markup=cancel_keyboard()
            )


@dp.callback_query(F.data.startswith("book_"))
async def book_callback(callback: CallbackQuery, state: FSMContext):
    book_id = int(callback.data.split("_")[1])
    book = db.get_book_by_id(book_id)
    await state.clear()

    if book:
        text = f"📖 *{book['name']}*\n\n{book['info']}"
        if book.get("photo"):
            await callback.message.answer_photo(
                photo=book["photo"],
                caption=text,
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
        else:
            await callback.message.answer(text, parse_mode="Markdown", reply_markup=main_menu())
    await callback.answer()


# ─── RASM YUBORISH ─────────────────────────────────────────────────────────────
@dp.message(F.text == "📸 Rasm yuborish")
async def photo_start(message: Message, state: FSMContext):
    await state.set_state(UserStates.waiting_photo)
    await message.answer(
        "📸 Kitob muqovasini rasm yuboring:\n"
        "(Galereadan yoki kamera orqali)",
        reply_markup=cancel_keyboard()
    )


@dp.message(UserStates.waiting_photo, F.photo)
async def photo_received(message: Message, state: FSMContext):
    await state.clear()
    processing_msg = await message.answer(
        "🔍 Rasm tahlil qilinmoqda...",
        reply_markup=ReplyKeyboardRemove()
    )

    try:
        # Rasmni yuklab olish
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_bytes = await bot.download_file(file.file_path)
        image_data = file_bytes.read()

        # OpenRouter orqali tahlil
        book_name_found = await analyze_image_openrouter(image_data)

        await bot.delete_message(message.chat.id, processing_msg.message_id)

        if book_name_found == "TOPILMADI" or not book_name_found:
            await message.answer(
                "❌ Rasmdan kitob nomi aniqlanmadi.\n"
                "Iltimos, aniqroq rasm yuboring yoki nom bo'yicha qidiring.",
                reply_markup=main_menu()
            )
            return

        # Bazadan qidirish
        book = db.get_book_by_name(book_name_found)
        if not book:
            book_list = db.search_books(book_name_found)
            if book_list:
                book = book_list[0]

        if book:
            text = (
                f"✅ Kitob topildi!\n\n"
                f"📖 *{book['name']}*\n\n"
                f"{book['info']}"
            )
            if book.get("photo"):
                await message.answer_photo(
                    photo=book["photo"],
                    caption=text,
                    parse_mode="Markdown",
                    reply_markup=main_menu()
                )
            else:
                await message.answer(text, parse_mode="Markdown", reply_markup=main_menu())
        else:
            await message.answer(
                f"🔍 Rasm tahlilida *'{book_name_found}'* topildi.\n\n"
                "❌ Lekin bu kitob bazamizda yo'q.\n"
                "Boshqa kitoblarni ko'rish uchun menyu tugmalaridan foydalaning.",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )

    except Exception as e:
        logger.error(f"Rasm tahlil xato: {e}")
        await bot.delete_message(message.chat.id, processing_msg.message_id)
        await message.answer(
            "⚠️ Rasm tahlilida xato yuz berdi. Qayta urinib ko'ring.",
            reply_markup=main_menu()
        )


# ─── KITOB TAVSIYA ─────────────────────────────────────────────────────────────
@dp.message(F.text == "💡 Kitob tavsiya")
async def recommendation_start(message: Message, state: FSMContext):
    await state.set_state(UserStates.waiting_recommendation)
    await message.answer(
        "💬 Qanday kitob qidiraysiz? Xohishingizni yozing:\n\n"
        "Misol: *'motivatsiya kitoblari'* yoki *'bolalar uchun'*",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown"
    )


@dp.message(UserStates.waiting_recommendation)
async def recommendation_answer(message: Message, state: FSMContext):
    await state.clear()
    user_request = message.text.strip()

    processing_msg = await message.answer(
        "⏳ Tavsiya tayyorlanmoqda...",
        reply_markup=ReplyKeyboardRemove()
    )

    books = db.get_all_books()
    if not books:
        await bot.delete_message(message.chat.id, processing_msg.message_id)
        await message.answer(
            "❌ Hozircha bazada kitob yo'q.",
            reply_markup=main_menu()
        )
        return

    books_list = "\n".join([f"- {b['name']}: {b['info'][:80]}..." for b in books])

    try:
        recommendation = await get_recommendation_openrouter(user_request, books_list)
        await bot.delete_message(message.chat.id, processing_msg.message_id)
        await message.answer(
            f"💡 *Tavsiya:*\n\n{recommendation}",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
    except Exception as e:
        logger.error(f"Tavsiya xato: {e}")
        await bot.delete_message(message.chat.id, processing_msg.message_id)
        await message.answer(
            "⚠️ Tavsiya berishda xato. Qayta urinib ko'ring.",
            reply_markup=main_menu()
        )


# ─── ADMIN: KITOB QO'SHISH ─────────────────────────────────────────────────────
@dp.message(F.text == "➕ Kitob qo'shish")
async def admin_add_book(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(AdminStates.waiting_book_name)
    await message.answer("📝 Kitob nomini yozing:", reply_markup=cancel_keyboard())


@dp.message(AdminStates.waiting_book_name)
async def admin_book_name(message: Message, state: FSMContext):
    await state.update_data(book_name=message.text.strip())
    await state.set_state(AdminStates.waiting_book_info)
    await message.answer(
        "📄 Kitob haqida ma'lumot yozing:\n(Muallif, mavzu, yosh chegarasi va h.k.)",
        reply_markup=cancel_keyboard()
    )


@dp.message(AdminStates.waiting_book_info)
async def admin_book_info(message: Message, state: FSMContext):
    await state.update_data(book_info=message.text.strip())
    await state.set_state(AdminStates.waiting_book_photo)
    await message.answer(
        "🖼 Kitob rasmini yuboring yoki o'tkazib yuborish uchun '➡️ O'tkazib yuborish' bosing:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="➡️ O'tkazib yuborish")], [KeyboardButton(text="❌ Bekor qilish")]],
            resize_keyboard=True
        )
    )


@dp.message(AdminStates.waiting_book_photo, F.photo)
async def admin_book_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photo_id = message.photo[-1].file_id
    db.add_book(data["book_name"], data["book_info"], photo_id)
    await state.clear()
    await message.answer(
        f"✅ *{data['book_name']}* kitob qo'shildi!",
        parse_mode="Markdown",
        reply_markup=admin_menu()
    )


@dp.message(AdminStates.waiting_book_photo, F.text == "➡️ O'tkazib yuborish")
async def admin_book_no_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    db.add_book(data["book_name"], data["book_info"], None)
    await state.clear()
    await message.answer(
        f"✅ *{data['book_name']}* kitob qo'shildi (rasmsiz)!",
        parse_mode="Markdown",
        reply_markup=admin_menu()
    )


# ─── ADMIN: KITOBLAR RO'YXATI ──────────────────────────────────────────────────
@dp.message(F.text == "📋 Kitoblar ro'yxati")
async def admin_book_list(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    books = db.get_all_books()
    if not books:
        await message.answer("📭 Hozircha kitob yo'q.", reply_markup=admin_menu())
        return

    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"📖 {b['name']}", callback_data=f"admin_book_{b['id']}"),
            InlineKeyboardButton(text="🗑", callback_data=f"delete_book_{b['id']}")
        ]
        for b in books
    ])
    await message.answer(f"📚 Jami: {len(books)} ta kitob", reply_markup=inline_kb)


@dp.callback_query(F.data.startswith("admin_book_"))
async def admin_view_book(callback: CallbackQuery, state: FSMContext):
    book_id = int(callback.data.split("_")[2])
    book = db.get_book_by_id(book_id)
    if book:
        text = f"📖 *{book['name']}*\n\n{book['info']}"
        await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()


@dp.callback_query(F.data.startswith("delete_book_"))
async def delete_book(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Ruxsat yo'q!")
        return
    book_id = int(callback.data.split("_")[2])
    book = db.get_book_by_id(book_id)
    if book:
        db.delete_book(book_id)
        await callback.message.answer(
            f"🗑 *{book['name']}* o'chirildi.",
            parse_mode="Markdown",
            reply_markup=admin_menu()
        )
    await callback.answer()


# ─── NOTO'G'RI XABAR ───────────────────────────────────────────────────────────
@dp.message()
async def unknown_message(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        return  # State kutayotgan bo'lsa, ignore qil
    await message.answer(
        "❓ Tushunmadim. Menyu tugmalaridan foydalaning.",
        reply_markup=main_menu()
    )


# ─── MAIN ──────────────────────────────────────────────────────────────────────
async def main():
    db.init_db()
    logger.info("Bot ishga tushmoqda...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
