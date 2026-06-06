import asyncio
import logging
import base64
import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from database import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import os
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_KEY")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "123456789").split(",")))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db = Database()


class AdminStates(StatesGroup):
    waiting_book_name = State()
    waiting_book_info = State()
    waiting_book_image = State()
    waiting_edit_name = State()
    waiting_edit_info = State()


class UserStates(StatesGroup):
    waiting_recommendation_request = State()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def main_menu(user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📝 Kitob nomi bo'yicha qidirish", callback_data="search_name")],
        [InlineKeyboardButton(text="📸 Rasm orqali qidirish", callback_data="search_image")],
        [InlineKeyboardButton(text="💬 Kitob tavsiya olish", callback_data="recommend")],
    ]
    if is_admin(user_id):
        buttons.append([InlineKeyboardButton(text="⚙️ Admin panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Kitob qo'shish", callback_data="add_book")],
        [InlineKeyboardButton(text="📚 Barcha kitoblar", callback_data="list_books")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_main")],
    ])


async def analyze_image_with_gemini(image_data: bytes, mime_type: str = "image/jpeg") -> str:
    image_b64 = base64.standard_b64encode(image_data).decode("utf-8")
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": mime_type, "data": image_b64}},
                {"text": "Bu rasmda kitob bormi? Agar bor bo'lsa, kitob nomini aniq ko'rsating. Faqat kitob nomini yozing. Agar kitob ko'rinmasa, 'kitob_yoq' deb yozing."}
            ]
        }],
        "generationConfig": {"maxOutputTokens": 100, "temperature": 0.1}
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, json=payload)
        result = response.json()
        logger.info(f"Gemini response: {result}")
        return result["candidates"][0]["content"]["parts"][0]["text"].strip()


async def get_recommendation_from_gemini(user_request: str, books_list: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{
            "parts": [{"text": f"Kitoblar:\n{books_list}\n\nSo'rov: {user_request}\n\nO'zbek tilida qisqa tavsiya ber."}]
        }],
        "generationConfig": {"maxOutputTokens": 500, "temperature": 0.7}
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, json=payload)
        result = response.json()
        return result["candidates"][0]["content"]["parts"][0]["text"].strip()


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        f"Salom, {message.from_user.first_name}! 👋\n\n📚 *Kitob Bot*ga xush kelibsiz!\n\nQuyidagilardan birini tanlang:",
        parse_mode="Markdown",
        reply_markup=main_menu(message.from_user.id),
    )


@dp.callback_query(F.data == "back_main")
async def back_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("Asosiy menyu:", reply_markup=main_menu(call.from_user.id))


@dp.callback_query(F.data == "search_name")
async def search_by_name(call: CallbackQuery):
    await call.message.edit_text("📝 Kitob nomini yozing:\n\nMasalan: *Atomic Habits*", parse_mode="Markdown")


@dp.message(F.text, ~F.text.startswith("/"))
async def handle_text(message: Message, state: FSMContext):
    current_state = await state.get_state()

    if current_state == AdminStates.waiting_book_name:
        await state.update_data(book_name=message.text)
        await state.set_state(AdminStates.waiting_book_info)
        await message.answer("📄 Kitob haqida ma'lumot yozing:")
        return

    if current_state == AdminStates.waiting_book_info:
        await state.update_data(book_info=message.text)
        await state.set_state(AdminStates.waiting_book_image)
        await message.answer("🖼 Kitob rasmini yuboring (ixtiyoriy):\nRasm bo'lmasa /skip yozing")
        return

    if current_state == AdminStates.waiting_edit_info:
        data = await state.get_data()
        db.update_book_info(data.get("edit_book_id"), message.text)
        await state.clear()
        await message.answer("✅ Ma'lumot yangilandi!", reply_markup=admin_menu())
        return

    if current_state == UserStates.waiting_recommendation_request:
        books = db.get_all_books()
        if not books:
            await message.answer("😔 Hozircha kitoblar yo'q.", reply_markup=main_menu(message.from_user.id))
            await state.clear()
            return
        books_list = "\n".join([f"- {b['name']}" for b in books])
        await message.answer("🤔 Tavsiya tayyorlanmoqda...")
        try:
            rec = await get_recommendation_from_gemini(message.text, books_list)
            await message.answer(f"💡 *Tavsiya:*\n\n{rec}", parse_mode="Markdown", reply_markup=main_menu(message.from_user.id))
        except Exception as e:
            logger.error(f"Gemini error: {e}")
            await message.answer("❌ Xatolik yuz berdi.", reply_markup=main_menu(message.from_user.id))
        await state.clear()
        return

    book = db.search_book(message.text)
    if book:
        await message.answer(f"📚 *{book['name']}*\n\n{book['info']}", parse_mode="Markdown", reply_markup=main_menu(message.from_user.id))
        if book.get("image_file_id"):
            await message.answer_photo(book["image_file_id"])
    else:
        await message.answer(f"❌ *{message.text}* topilmadi.\n\nBoshqa nom bilan sinab ko'ring.", parse_mode="Markdown", reply_markup=main_menu(message.from_user.id))


@dp.callback_query(F.data == "search_image")
async def search_by_image(call: CallbackQuery):
    await call.message.edit_text("📸 Kitob rasmini yuboring.\n\nGemini AI rasmni tahlil qiladi!")


@dp.message(F.photo)
async def handle_photo(message: Message, state: FSMContext):
    current_state = await state.get_state()

    if current_state == AdminStates.waiting_book_image:
        data = await state.get_data()
        db.add_book(data["book_name"], data["book_info"], message.photo[-1].file_id)
        await state.clear()
        await message.answer(f"✅ *{data['book_name']}* qo'shildi!", parse_mode="Markdown", reply_markup=admin_menu())
        return

    await message.answer("🔍 Gemini AI rasmni tahlil qilmoqda...")
    try:
        file = await bot.get_file(message.photo[-1].file_id)
        file_bytes = await bot.download_file(file.file_path)
        detected_name = await analyze_image_with_gemini(file_bytes.read())

        if detected_name.lower() == "kitob_yoq":
            await message.answer("😕 Rasmda kitob aniqlanmadi.", reply_markup=main_menu(message.from_user.id))
            return

        await message.answer(f"🔎 Aniqlangan: *{detected_name}*", parse_mode="Markdown")
        book = db.search_book(detected_name)
        if book:
            await message.answer(f"📚 *{book['name']}*\n\n{book['info']}", parse_mode="Markdown", reply_markup=main_menu(message.from_user.id))
            if book.get("image_file_id"):
                await message.answer_photo(book["image_file_id"])
        else:
            await message.answer(f"📖 *{detected_name}* haqida ma'lumot yo'q.\n\nTez orada qo'shamiz! 🙏", parse_mode="Markdown", reply_markup=main_menu(message.from_user.id))
    except Exception as e:
        logger.error(f"Image error: {e}")
        await message.answer("❌ Xatolik. Qayta urinib ko'ring.", reply_markup=main_menu(message.from_user.id))


@dp.message(Command("skip"))
async def skip_image(message: Message, state: FSMContext):
    if await state.get_state() == AdminStates.waiting_book_image:
        data = await state.get_data()
        db.add_book(data["book_name"], data["book_info"], None)
        await state.clear()
        await message.answer(f"✅ *{data['book_name']}* qo'shildi (rasmsiz)!", parse_mode="Markdown", reply_markup=admin_menu())


@dp.callback_query(F.data == "recommend")
async def recommend(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.waiting_recommendation_request)
    await call.message.edit_text("💬 Qanday kitob qidirmoqdasiz?\n\n• Motivatsiya\n• Biznes\n• O'zini rivojlantirish", parse_mode="Markdown")


@dp.callback_query(F.data == "admin_panel")
async def admin_panel(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await call.message.edit_text("⚙️ *Admin panel*", parse_mode="Markdown", reply_markup=admin_menu())


@dp.callback_query(F.data == "add_book")
async def add_book(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_book_name)
    await call.message.edit_text("➕ Yangi kitob nomi:")


@dp.callback_query(F.data == "list_books")
async def list_books(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    books = db.get_all_books()
    if not books:
        await call.message.edit_text("📚 Hozircha kitob yo'q.", reply_markup=admin_menu())
        return
    buttons = [[InlineKeyboardButton(text=f"📖 {b['name']}", callback_data=f"book_{b['id']}")] for b in books]
    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_panel")])
    await call.message.edit_text(f"📚 Jami {len(books)} ta kitob:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@dp.callback_query(F.data.startswith("book_"))
async def book_detail_admin(call: CallbackQuery):
    book_id = int(call.data.split("_")[1])
    book = db.get_book_by_id(book_id)
    if not book:
        await call.answer("Kitob topilmadi!")
        return
    await call.message.edit_text(
        f"📖 *{book['name']}*\n\n{book['info']}", parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=f"edit_{book_id}")],
            [InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"delete_{book_id}")],
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data="list_books")],
        ])
    )


@dp.callback_query(F.data.startswith("edit_"))
async def edit_book(call: CallbackQuery, state: FSMContext):
    book_id = int(call.data.split("_")[1])
    await state.set_state(AdminStates.waiting_edit_info)
    await state.update_data(edit_book_id=book_id)
    await call.message.edit_text("✏️ Yangi ma'lumot yozing:")


@dp.callback_query(F.data.startswith("delete_"))
async def delete_book(call: CallbackQuery):
    db.delete_book(int(call.data.split("_")[1]))
    await call.message.edit_text("🗑 Kitob o'chirildi!", reply_markup=admin_menu())


async def web_server():
    from aiohttp import web
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="Bot ishlayapti!"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8080)))
    await site.start()


async def main():
    db.init()
    await web_server()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
