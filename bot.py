import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters, ConversationHandler

from config import settings_manager, BOT_TOKEN
from core.sources import add_source, remove_source, get_sources, clear_sources
from core.logger import get_logger

logger = get_logger("BOT")

# تعريف حالات معالج المحادثة
AWAIT_TARGET_CHANNEL, AWAIT_ADD_SOURCE, AWAIT_MAX_MESSAGES, AWAIT_HEADER_TEXT, AWAIT_BLACKLIST_WORD, AWAIT_SOURCE_LABEL, AWAIT_SENDER_LABEL, AWAIT_INDEX_THRESHOLD = range(8)


# =========================
# الواجهات (Keyboards)
# =========================
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("⚙️ إدارة المصادر والوجهات", callback_data="menu_sources")],
        [InlineKeyboardButton("🎛 خيارات وتفاصيل النقل", callback_data="menu_mechanics")],
        [InlineKeyboardButton("📊 حالة البوت", callback_data="status")],
        [InlineKeyboardButton("ℹ️ مساعدة", callback_data="help")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_sources_keyboard():
    keyboard = [
        [InlineKeyboardButton("🎯 تحديد الوجهة الأساسية", callback_data="set_target_channel")],
        [InlineKeyboardButton("➕ إضافة مصدر جديد", callback_data="add_source")],
        [InlineKeyboardButton("🔎 إدارة وحذف المصادر الحالية", callback_data="manage_sources_0")],
        [InlineKeyboardButton("🗑 مسح الكل", callback_data="clear_sources")],
        [InlineKeyboardButton("🔄 جلب أحدث الملفات الآن!", callback_data="trigger_fetch_all")],
        [InlineKeyboardButton("⬅️ عودة للرئيسية", callback_data="menu_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_sources_manage_keyboard(page: int = 0):
    source_ids = settings_manager.get("ALLOWED_SOURCE_CHAT_IDS") or []
    titles = settings_manager.get("SOURCE_TITLES") or {}
    
    items_per_page = 8
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    
    current_ids = source_ids[start_idx:end_idx]
    
    keyboard = []
    for chat_id in current_ids:
        title = titles.get(str(chat_id)) or f"ID: {chat_id}"
        keyboard.append([
            InlineKeyboardButton(f"🗑 {title}", callback_data=f"del_source_{chat_id}_{page}")
        ])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"manage_sources_{page-1}"))
    
    total_pages = (len(source_ids) + items_per_page - 1) // items_per_page
    if len(source_ids) > 0:
        nav_buttons.append(InlineKeyboardButton(f"صفحة {page+1}/{max(1, total_pages)}", callback_data="noop"))
        
    if end_idx < len(source_ids):
        nav_buttons.append(InlineKeyboardButton("التالي ➡️", callback_data=f"manage_sources_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
        
    keyboard.append([InlineKeyboardButton("🔙 رجوع لقائمة المصادر", callback_data="menu_sources")])
    return InlineKeyboardMarkup(keyboard)

def get_mechanics_keyboard():
    status = lambda k: "✅" if settings_manager.get(k) else "❌"
    max_msgs = settings_manager.get("MAX_LAST_MESSAGES") or 5
    
    keyboard = [
        [InlineKeyboardButton(f"🔢 عدد الملفات/الدفعة: {max_msgs}", callback_data="set_max_messages")],
        [InlineKeyboardButton(f"📁 فلترة أنواع الوسائط المنقولة", callback_data="menu_types")],
        [InlineKeyboardButton(f"🚫 القائمة السوداء (الكلمات المحظورة)", callback_data="menu_blacklist")],
        [InlineKeyboardButton(f"✏️ نص الترويسة الرئيسي", callback_data="edit_header_text")],
        [
            InlineKeyboardButton(f"✏️ تسمية المصدر", callback_data="edit_source_label"),
            InlineKeyboardButton(f"👤 تسمية المرسل", callback_data="edit_sender_label")
        ],
        [InlineKeyboardButton(f"🔄 نوع النقل بالنسخ: {status('USE_COPY_INSTEAD_OF_FORWARD')}", callback_data="toggle_copy")],
        [InlineKeyboardButton(f"📝 ترويسة مع النص: {status('ADD_HEADER')}", callback_data="toggle_header")],
        [InlineKeyboardButton(f"📑 نظام الفهرسة الآلي", callback_data="menu_index")],
        [InlineKeyboardButton(f"🏷 فلتر الهاشتاق: {status('REQUIRE_HASHTAG')}", callback_data="toggle_hashtag")],
        [InlineKeyboardButton("⬅️ عودة للرئيسية", callback_data="menu_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_types_keyboard():
    status = lambda k: "✅" if settings_manager.get(k) else "❌"
    keyboard = [
        [
            InlineKeyboardButton(f"نصوص {status('ALLOW_TEXT')}", callback_data="toggle_type_ALLOW_TEXT"),
            InlineKeyboardButton(f"صور {status('ALLOW_PHOTO')}", callback_data="toggle_type_ALLOW_PHOTO")
        ],
        [
            InlineKeyboardButton(f"مستندات {status('ALLOW_DOCUMENT')}", callback_data="toggle_type_ALLOW_DOCUMENT"),
            InlineKeyboardButton(f"فيديو {status('ALLOW_VIDEO')}", callback_data="toggle_type_ALLOW_VIDEO")
        ],
        [
            InlineKeyboardButton(f"بصمات {status('ALLOW_VOICE')}", callback_data="toggle_type_ALLOW_VOICE"),
            InlineKeyboardButton(f"صوتيات {status('ALLOW_AUDIO')}", callback_data="toggle_type_ALLOW_AUDIO")
        ],
        [
            InlineKeyboardButton(f"متحركة {status('ALLOW_ANIMATION')}", callback_data="toggle_type_ALLOW_ANIMATION")
        ],
        [InlineKeyboardButton("⬅️ رجوع للخيارات", callback_data="menu_mechanics")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_index_keyboard():
    status = lambda k: "✅" if settings_manager.get(k) else "❌"
    threshold = settings_manager.get("INDEX_THRESHOLD") or 50
    keyboard = [
        [InlineKeyboardButton(f"نظام الفهرسة: {status('ENABLE_INDEXING')}", callback_data="toggle_indexing")],
        [InlineKeyboardButton(f"نشر فهرس كل: {threshold} ملف", callback_data="set_index_threshold")],
        [InlineKeyboardButton("⬅️ رجوع للخيارات", callback_data="menu_mechanics")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_blacklist_keyboard():
    words = settings_manager.get("BLACKLIST_WORDS") or []
    keyboard = []
    
    # عرض الكلمات مع زر حذف بجانب كل واحدة
    for word in words:
        keyboard.append([
            InlineKeyboardButton(f"🗑 {word}", callback_data=f"del_word_{word}"),
        ])
    
    keyboard.append([InlineKeyboardButton("➕ إضافة كلمة محظورة", callback_data="add_blacklist_word")])
    keyboard.append([InlineKeyboardButton("⬅️ رجوع للخيارات", callback_data="menu_mechanics")])
    return InlineKeyboardMarkup(keyboard)


# =========================
# الأزرار التفاعلية
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔘 **القائمة الرئيسية**\nمرحباً بك! اختر القسم الذي تود تعديله:", reply_markup=get_main_keyboard(), parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_main":
        await query.edit_message_text("🔘 **القائمة الرئيسية:**", reply_markup=get_main_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END
    elif data == "menu_sources":
        await query.edit_message_text("💾 **إدارة المصادر والوجهات:**", reply_markup=get_sources_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END
    elif data.startswith("manage_sources_"):
        page = int(data.split("_")[-1])
        await query.edit_message_text("📋 **إدارة وحذف المصادر:**\nاختر المصدر الذي تود حذفه:", reply_markup=get_sources_manage_keyboard(page), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END
    elif data.startswith("del_source_"):
        parts = data.split("_")
        chat_id = int(parts[2])
        page = int(parts[3])
        from core.sources import remove_source
        if remove_source(chat_id):
            await query.answer(f"✅ تم حذف المصدر بنجاح")
        else:
            await query.answer("⚠️ فشل حذف المصدر")
        await query.edit_message_reply_markup(reply_markup=get_sources_manage_keyboard(page))
        return ConversationHandler.END
    elif data == "menu_mechanics":
        await query.edit_message_text("▶️ **خيارات النقل:**", reply_markup=get_mechanics_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END
    elif data == "menu_types":
        await query.edit_message_text("📂 **فلترة أنواع الوسائط:**\nاختر الأنواع التي تود السماح بنقلها:", reply_markup=get_types_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END
    elif data == "menu_blacklist":
        await query.edit_message_text("🚫 **قائمة الكلمات المحظورة:**\nاضغط على الكلمة لحذفها، أو أضف كلمة جديدة:", reply_markup=get_blacklist_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END
    elif data == "menu_index":
        await query.edit_message_text("📑 **نظام الفهرسة التلقائية:**\nيسمح هذا النظام بنشر رسائل مجمعة بروابط الملفات لتسهيل البحث عنها.", reply_markup=get_index_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END
    
    elif data == "toggle_indexing":
        settings_manager.set("ENABLE_INDEXING", not settings_manager.get("ENABLE_INDEXING"))
        await query.edit_message_reply_markup(reply_markup=get_index_keyboard())
        return ConversationHandler.END

    elif data == "set_index_threshold":
        current = settings_manager.get("INDEX_THRESHOLD") or 50
        await query.edit_message_text(f"🔢 **تعديل حد الفهرسة:**\nالحالي: `{current}` ملف.\n\nأرسل **عدد الملفات الجديد** الذي تريد أن ينشر البوت الفهرس بعد وصوله:", parse_mode=ParseMode.MARKDOWN)
        return AWAIT_INDEX_THRESHOLD

    elif data.startswith("del_word_"):
        word_to_del = data.replace("del_word_", "")
        words = settings_manager.get("BLACKLIST_WORDS") or []
        if word_to_del in words:
            words.remove(word_to_del)
            settings_manager.set("BLACKLIST_WORDS", words)
        await query.edit_message_reply_markup(reply_markup=get_blacklist_keyboard())
        return ConversationHandler.END

    elif data.startswith("toggle_type_"):
        key = data.replace("toggle_type_", "")
        settings_manager.set(key, not settings_manager.get(key))
        await query.edit_message_reply_markup(reply_markup=get_types_keyboard())
        settings_manager.set("USE_COPY_INSTEAD_OF_FORWARD", not settings_manager.get("USE_COPY_INSTEAD_OF_FORWARD"))
        await query.edit_message_reply_markup(reply_markup=get_mechanics_keyboard())
    elif data == "toggle_header":
        settings_manager.set("ADD_HEADER", not settings_manager.get("ADD_HEADER"))
        await query.edit_message_reply_markup(reply_markup=get_mechanics_keyboard())
    elif data == "toggle_hashtag":
        settings_manager.set("REQUIRE_HASHTAG", not settings_manager.get("REQUIRE_HASHTAG"))
        await query.edit_message_reply_markup(reply_markup=get_mechanics_keyboard())

    elif data == "help":
        await query.edit_message_text(
            "ℹ️ هذا البوت مسؤول عن إدارة الإعدادات فقط. عند إضافة مصدر للقائمة سيقوم حساب الـ Userbot المرافق بالنقل التلقائي منه للوجهة المطلوبة فوراً وبدون تعارض.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ عودة للرئيسية", callback_data="menu_main")]])
        )
    elif data == "status":
        target = settings_manager.get("TARGET_CHANNEL_ID")
        groups = get_sources()
        await query.edit_message_text(
            f"📊 **حالة البوت:**\nالحالة: يعمل\nمعرف القناة الوجهة: `{target}`\nعدد المصادر المراقبة: {len(groups) if isinstance(groups, list) else 0}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ عودة للرئيسية", callback_data="menu_main")]]),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "show_sources":
        groups = get_sources()
        text_groups = "\n".join([f"- `{g}`" for g in groups]) if groups else "لا توجد مصادر حالياً."
        await query.edit_message_text(
            f"📋 **المصادر المراقبة:**\n{text_groups}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع للمصادر", callback_data="menu_sources")]]),
            parse_mode=ParseMode.MARKDOWN
        )
    elif data == "clear_sources":
        clear_sources()
        await query.edit_message_text(
            "🗑 **تم مسح جميع المصادر بنجاح!**",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع للمصادر", callback_data="menu_sources")]]),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "trigger_fetch_all":
        settings_manager.set("TRIGGER_FETCH_ALL", True)
        await query.answer("⏳ تم إصدار أمر لـ UserBot ببدء سحب الملفات للتو!", show_alert=True)
        return ConversationHandler.END

    elif data == "set_max_messages":
        await query.edit_message_text(
            "أرسل **العدد المطلوب** للملفات التي تريد سحبها من كل مصدر بأثر رجعي (مثال: `5` أو `10`):",
            parse_mode=ParseMode.MARKDOWN
        )
        return AWAIT_MAX_MESSAGES

    elif data == "edit_header_text":
        current = settings_manager.get("HEADER_TEXT")
        await query.edit_message_text(
            f"📝 **نص الترويسة العلوي الحالي:**\n`{current}`\n\nأرسل **النص الجديد** الذي تريده أن يظهر كعنوان رئيسي:\nلإلغاء العملية أرسل /cancel",
            parse_mode=ParseMode.MARKDOWN
        )
        return AWAIT_HEADER_TEXT

    elif data == "edit_source_label":
        current = settings_manager.get("SOURCE_LABEL")
        await query.edit_message_text(
            f"✏️ **تسمية المصدر الحالية:** `{current}`\n\nأرسل **التسمية الجديدة** (مثال: `من قناة` أو `المصدر`):",
            parse_mode=ParseMode.MARKDOWN
        )
        return AWAIT_SOURCE_LABEL

    elif data == "edit_sender_label":
        current = settings_manager.get("SENDER_LABEL")
        await query.edit_message_text(
            f"👤 **تسمية المرسل الحالية:** `{current}`\n\nأرسل **التسمية الجديدة** (مثال: `بواسطة` أو `الناشر`):",
            parse_mode=ParseMode.MARKDOWN
        )
        return AWAIT_SENDER_LABEL

    elif data == "add_blacklist_word":
        await query.edit_message_text(
            "🚫 أرسل **الكلمة أو العبارة** التي تريد حظر نقلها (سيتم حظر أي رسالة أو ملف يحتوي على هذه الكلمة):\nلإلغاء العملية أرسل /cancel",
            parse_mode=ParseMode.MARKDOWN
        )
        return AWAIT_BLACKLIST_WORD

    elif data == "set_target_channel":
        await query.edit_message_text(
            "🎯 أرسل **معرف القناة الأساسية الجديدة** الآن (مثال: -100123... أو المعرف @channel):\n\nلإلغاء العملية أرسل /cancel",
            parse_mode=ParseMode.MARKDOWN
        )
        return AWAIT_TARGET_CHANNEL
    elif data == "add_source":
        await query.edit_message_text(
            "➕ أرسل **معرف (رقمي أو يوزر)** للمصدر الجديد:\nسيعتمد فوراً للنقل.\nملاحظة: الروابط الطويلة ستُضاف للانضمام التلقائي من قبل الـ Userbot.\n\nلإلغاء العملية أرسل /cancel",
            parse_mode=ParseMode.MARKDOWN
        )
        return AWAIT_ADD_SOURCE

    return ConversationHandler.END


# =========================
# معالجات الحالات (States Handlers)
# =========================
async def receive_target_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "/cancel":
        await update.message.reply_text("✅ تم إلغاء المهمة.", reply_markup=get_sources_keyboard())
        return ConversationHandler.END

    try:
        channel_id = int(text)
    except ValueError:
        try:
            chat = await context.bot.get_chat(text)
            channel_id = chat.id
        except Exception:
            await update.message.reply_text("❌ **فشل في تحديد المعرف!**\nجرب مرة أخرى أو أرسل /cancel")
            return AWAIT_TARGET_CHANNEL

    settings_manager.set("TARGET_CHANNEL_ID", channel_id)
    await update.message.reply_text(f"✅ تم حفظ القناة الأساسية بنجاح: `{channel_id}`", reply_markup=get_sources_keyboard(), parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END


async def receive_add_source(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("✅ تم إلغاء المهمة.", reply_markup=get_sources_keyboard())
        return ConversationHandler.END

    pending = settings_manager.get("PENDING_JOINS")
    if text not in pending:
        pending.append(text)
        settings_manager.set("PENDING_JOINS", pending)
        logger.info(f"تمت إضافة مصدر للطابور: {text}")
        await update.message.reply_text(
            "✅ تم تحويل المصدر لمحرك النقل (UserBot).\n"
            "سيقوم الحساب تلقائياً الآن بالدخول، الاعتماد، ونقل أحدث الملفات فوراً!", 
            reply_markup=get_sources_keyboard()
        )
    else:
        await update.message.reply_text("⚠️ هذا المصدر موجود بالفعل في طابور المعالجة.", reply_markup=get_sources_keyboard())
        
    return ConversationHandler.END


async def receive_max_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("✅ تم إلغاء المهمة.", reply_markup=get_mechanics_keyboard())
        return ConversationHandler.END

    try:
        max_msgs = int(text)
        if max_msgs <= 0 or max_msgs > 50:
            await update.message.reply_text("❌ العدد غير منطقي، أرسل رقماً بين 1 و 50.")
            return AWAIT_MAX_MESSAGES
    except ValueError:
        await update.message.reply_text("❌ يرجى إرسال أرقام فقط (مثال: 5).\nلإلغاء: /cancel")
        return AWAIT_MAX_MESSAGES

    settings_manager.set("MAX_LAST_MESSAGES", max_msgs)
    await update.message.reply_text(f"✅ تم حفظ الحد الأقصى لسحب الملفات بأثر رجعي: `{max_msgs}`", reply_markup=get_mechanics_keyboard(), parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END


async def receive_header_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("✅ تم إلغاء المهمة.", reply_markup=get_mechanics_keyboard())
        return ConversationHandler.END

    settings_manager.set("HEADER_TEXT", text)
    await update.message.reply_text(f"✅ تم تحديث نص الترويسة بنجاح إلى:\n`{text}`", reply_markup=get_mechanics_keyboard(), parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END


async def receive_blacklist_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    word = update.message.text.strip()
    if word == "/cancel":
        await update.message.reply_text("✅ تم إلغاء المهمة.", reply_markup=get_mechanics_keyboard())
        return ConversationHandler.END

    words = settings_manager.get("BLACKLIST_WORDS") or []
    if word not in words:
        words.append(word)
        settings_manager.set("BLACKLIST_WORDS", words)
        await update.message.reply_text(f"✅ تمت إضافة الكلمة ` {word} ` إلى القائمة السوداء.", reply_markup=get_blacklist_keyboard(), parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("⚠️ هذه الكلمة موجودة بالفعل في القائمة.", reply_markup=get_blacklist_keyboard())
    
    return ConversationHandler.END


async def receive_source_label(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("✅ تم إلغاء المهمة.", reply_markup=get_mechanics_keyboard())
        return ConversationHandler.END

    settings_manager.set("SOURCE_LABEL", text)
    await update.message.reply_text(f"✅ تم تحديث تسمية المصدر إلى: `{text}`", reply_markup=get_mechanics_keyboard(), parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END


async def receive_sender_label(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("✅ تم إلغاء المهمة.", reply_markup=get_mechanics_keyboard())
        return ConversationHandler.END

    settings_manager.set("SENDER_LABEL", text)
    await update.message.reply_text(f"✅ تم تحديث تسمية المرسل إلى: `{text}`", reply_markup=get_mechanics_keyboard(), parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END


async def receive_index_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("✅ تم إلغاء المهمة.", reply_markup=get_index_keyboard())
        return ConversationHandler.END

    if not text.isdigit():
        await update.message.reply_text("⚠️ يرجى إرسال رقم صحيح.")
        return AWAIT_INDEX_THRESHOLD

    val = int(text)
    if val < 1:
        await update.message.reply_text("⚠️ الحد الأدنى هو 1 ملف.")
        return AWAIT_INDEX_THRESHOLD

    settings_manager.set("INDEX_THRESHOLD", val)
    await update.message.reply_text(f"✅ تم ضبط حد الفهرسة على: `{val}` ملف.", reply_markup=get_index_keyboard(), parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END


async def cancel_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم الإلغاء.", reply_markup=get_main_keyboard())
    return ConversationHandler.END


def main():
    if not BOT_TOKEN or BOT_TOKEN == "PUT_YOUR_BOT_TOKEN":
        logger.error("BOT_TOKEN is missing or invalid in .env")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    setup_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_callback, pattern="^(set_target_channel|add_source|set_max_messages|edit_header_text|add_blacklist_word|edit_source_label|edit_sender_label|set_index_threshold)$")],
        states={
            AWAIT_TARGET_CHANNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_target_channel)],
            AWAIT_ADD_SOURCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_add_source)],
            AWAIT_MAX_MESSAGES: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_max_messages)],
            AWAIT_HEADER_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_header_text)],
            AWAIT_BLACKLIST_WORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_blacklist_word)],
            AWAIT_SOURCE_LABEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_source_label)],
            AWAIT_SENDER_LABEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_sender_label)],
            AWAIT_INDEX_THRESHOLD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_index_threshold)],
        },
        fallbacks=[CommandHandler("cancel", cancel_setup)]
    )

    app.add_handler(setup_conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    # تمت إزالة file_router بالكامل لمنع الازدواجية والتضارب

    logger.info("تم تشغيل لوحة تحكم البوت (Dashboard) بنجاح.")
    app.run_polling()

if __name__ == "__main__":
    main()
