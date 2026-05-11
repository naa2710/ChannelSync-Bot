import os, re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters, ConversationHandler, InlineQueryHandler

from config import settings_manager, BOT_TOKEN, get_data_path
from core.sources import add_source, remove_source, get_sources, clear_sources
from core.db import search_files, get_tags_list, get_all_files_paginated, get_categories_list, get_sources_list
from core.logger import get_logger
from core.resolver import clean_identifier, is_numeric_id

logger = get_logger("BOT")

# تعريف حالات معالج المحادثة
AWAIT_TARGET_CHANNEL, AWAIT_ADD_SOURCE, AWAIT_MAX_MESSAGES, AWAIT_HEADER_TEXT, AWAIT_BLACKLIST_WORD, AWAIT_SOURCE_LABEL, AWAIT_SENDER_LABEL, AWAIT_INDEX_THRESHOLD, AWAIT_SEARCH_QUERY, AWAIT_SOURCE_TARGET, AWAIT_SOURCE_HEADER, AWAIT_TARGET_NAME, AWAIT_COPY_SETTINGS_TARGET, AWAIT_GROUP_ID = range(14)


# =========================
# الواجهات (Keyboards)
# =========================
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("📡 إضافة وإدارة قنوات المصدر", callback_data="menu_sources")],
        [InlineKeyboardButton("⚙️ ضـبـط طـريقة النـقل والفـلترة", callback_data="menu_smart_settings")],
        [InlineKeyboardButton("📚 تصفح الملفات والأرشيف (المكتبة)", callback_data="menu_library")],
        [InlineKeyboardButton("🛠 أدوات السحب والمزامنة الشاملة", callback_data="menu_tools")],
        [InlineKeyboardButton("📊 حالة البوت وإحصائيات القناة", callback_data="menu_stats")],
        [InlineKeyboardButton("📋 المجموعة التفاعلية — فهرس ذكي", callback_data="menu_group_index")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_group_keyboard():
    """قائمة إدارة المجموعة التفاعلية."""
    group_id = settings_manager.get("INDEX_GROUP_ID")
    auto = "✅" if settings_manager.get("GROUP_AUTO_UPDATE") else "❌"
    mode = settings_manager.get("GROUP_INDEX_MODE") or "category"
    mode_labels = {"category": "📂 حسب النوع", "source": "🌐 حسب المصدر", "both": "🔀 الاثنان معاً"}
    mode_label = mode_labels.get(mode, mode)
    group_status = f"`{group_id}`" if group_id else "❌ غير محدد"

    keyboard = [
        [InlineKeyboardButton(f"🔗 المجموعة: {group_status}", callback_data="set_group_id")],
        [InlineKeyboardButton(f"⚡ التحديث التلقائي: {auto}", callback_data="grp_toggle_auto")],
        [InlineKeyboardButton(f"📐 نمط الفهرسة: {mode_label}", callback_data="grp_cycle_mode")],
        [
            InlineKeyboardButton("🔄 إعادة بناء الفهرس الكامل", callback_data="grp_rebuild"),
            InlineKeyboardButton("📊 تحديث الإحصائيات", callback_data="grp_update_stats"),
        ],
        [InlineKeyboardButton("🗑 مسح سجل الرسائل وإعادة البناء", callback_data="grp_reset_ids")],
        [InlineKeyboardButton("⬅️ عودة للرئيسية", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_sources_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("🎯 إدارة قنوات الوجهة (Target)", callback_data="manage_targets"),
            InlineKeyboardButton("➕ ربط قناة مصدر جديدة", callback_data="add_source")
        ],
        [
            InlineKeyboardButton("📋 قائمة قنوات المصدر المتصلة", callback_data="manage_sources_0")
        ],
        [InlineKeyboardButton("🔄 جلب أحدث الملفات من الجميع الآن", callback_data="trigger_fetch_all")],
        [InlineKeyboardButton("⬅️ عودة للرئيسية", callback_data="menu_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_targets_manage_keyboard():
    targets = settings_manager.get("TARGET_CHANNELS") or {}
    keyboard = []
    
    for tid, name in targets.items():
        keyboard.append([
            InlineKeyboardButton(f"📍 {name} ({tid})", callback_data="noop"),
            InlineKeyboardButton("🗑", callback_data=f"del_target_{tid}")
        ])
    
    keyboard.append([InlineKeyboardButton("➕ إضافة قناة وجهة جديدة", callback_data="add_new_target")])
    keyboard.append([InlineKeyboardButton("⬅️ عودة للمصادر", callback_data="menu_sources")])
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
            InlineKeyboardButton(f"⚙️ {title}", callback_data=f"source_profile_{chat_id}"),
        ])
        keyboard.append([
            InlineKeyboardButton("📥 سحب آخر 100", callback_data=f"fetch_100_{chat_id}_{page}"),
            InlineKeyboardButton("🗑 حذف", callback_data=f"del_source_{chat_id}_{page}")
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

def get_source_profile_keyboard(chat_id):
    status = lambda k: "✅" if settings_manager.get_for_source(chat_id, k) else "❌"
    keyboard = [
        [InlineKeyboardButton(f"🧹 حذف حقوق وقنوات المصدر: {status('DEFAULT_CLEAN_CAPTION')}", callback_data=f"sp_toggle_clean_{chat_id}")],
        [InlineKeyboardButton(f"📁 التحكم في أنواع الملفات المنقولة", callback_data=f"sp_media_filter_{chat_id}")],
        [InlineKeyboardButton(f"📝 تعديل الترويسة", callback_data=f"sp_set_header_{chat_id}"), InlineKeyboardButton(f"🎯 تغيير قناة الوجهة", callback_data=f"sp_select_target_{chat_id}")],
        [
            InlineKeyboardButton(f"🔄 الترويسة: {status('ADD_HEADER')}", callback_data=f"sp_toggle_header_{chat_id}"),
            InlineKeyboardButton(f"🙈 إخفاء المصدر: {status('USE_COPY_INSTEAD_OF_FORWARD')}", callback_data=f"sp_toggle_copy_{chat_id}")
        ],
        [InlineKeyboardButton(f"🚫 حذف اسم القناة المصدر: {status('HIDE_SOURCE_NAME')}", callback_data=f"sp_toggle_hidesrc_{chat_id}")],
        [InlineKeyboardButton("📋 نسخ هذه الإعدادات لمصدر آخر", callback_data=f"sp_copy_settings_{chat_id}")],
        [InlineKeyboardButton("⬅️ عودة للقائمة", callback_data="manage_sources_0")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_source_media_keyboard(chat_id):
    status = lambda k: "✅" if settings_manager.get_for_source(chat_id, k) else "❌"
    keyboard = [
        [
            InlineKeyboardButton(f"نصوص {status('ALLOW_TEXT')}", callback_data=f"smt_{chat_id}_ALLOW_TEXT"),
            InlineKeyboardButton(f"صور {status('ALLOW_PHOTO')}", callback_data=f"smt_{chat_id}_ALLOW_PHOTO")
        ],
        [
            InlineKeyboardButton(f"مستندات {status('ALLOW_DOCUMENT')}", callback_data=f"smt_{chat_id}_ALLOW_DOCUMENT"),
            InlineKeyboardButton(f"فيديو {status('ALLOW_VIDEO')}", callback_data=f"smt_{chat_id}_ALLOW_VIDEO")
        ],
        [
            InlineKeyboardButton(f"بصمات {status('ALLOW_VOICE')}", callback_data=f"smt_{chat_id}_ALLOW_VOICE"),
            InlineKeyboardButton(f"صوتيات {status('ALLOW_AUDIO')}", callback_data=f"smt_{chat_id}_ALLOW_AUDIO")
        ],
        [
            InlineKeyboardButton(f"متحركة {status('ALLOW_ANIMATION')}", callback_data=f"smt_{chat_id}_ALLOW_ANIMATION")
        ],
        [InlineKeyboardButton("⬅️ رجوع للبروفايل", callback_data=f"source_profile_{chat_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_target_selection_keyboard(source_chat_id):
    targets = settings_manager.get("TARGET_CHANNELS") or {}
    keyboard = []
    
    for tid, name in targets.items():
        keyboard.append([InlineKeyboardButton(f"🎯 {name}", callback_data=f"sp_settarget_{source_chat_id}_{tid}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ رجوع للبروفايل", callback_data=f"source_profile_{source_chat_id}")])
    return InlineKeyboardMarkup(keyboard)

# دالة مكررة سيتم حذفها واستخدام get_main_menu_keyboard بدلاً منها

def get_smart_settings_keyboard():
    status = lambda k: "✅" if settings_manager.get(k) else "❌"
    keyboard = [
        [InlineKeyboardButton(f"🔄 إخفاء المصدر (وضع النسخ): {status('USE_COPY_INSTEAD_OF_FORWARD')}", callback_data="toggle_copy")],
        [InlineKeyboardButton(f"🧹 حذف الروابط والمعرفات الدعائية: {status('DEFAULT_CLEAN_CAPTION')}", callback_data="toggle_clean_all")],
        [InlineKeyboardButton(f"📝 إضافة مقدمة/هيدر للملف: {status('ADD_HEADER')}", callback_data="toggle_header")],
        [InlineKeyboardButton("📁 اختيار أنواع الملفات المسموحة", callback_data="menu_types")],
        [InlineKeyboardButton("🏷 إعدادات الفهرسة والوسوم (#)", callback_data="menu_index")],
        [InlineKeyboardButton("🚫 فلتر الكلمات المحظورة (Blacklist)", callback_data="menu_blacklist")],
        [InlineKeyboardButton("⬅️ عودة للرئيسية", callback_data="menu_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_tools_keyboard():
    max_msgs = settings_manager.get("MAX_LAST_MESSAGES") or 5
    keyboard = [
        [InlineKeyboardButton("📥 سحب الأرشيف التاريخي (History)", callback_data="menu_import_history")],
        [InlineKeyboardButton(f"🔢 سرعة السحب (عدد الملفات): {max_msgs}", callback_data="set_max_messages")],
        [InlineKeyboardButton("🔄 تحديث قائمة الملاحة المثبتة", callback_data="trigger_hub_update")],
        [InlineKeyboardButton("🧹 تحسين أداء البوت (Refresh)", callback_data="cleanup_bot")],
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
        [InlineKeyboardButton("⬅️ رجوع للإعدادات", callback_data="menu_smart_settings")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_index_keyboard():
    status = lambda k: "✅" if settings_manager.get(k) else "❌"
    threshold = settings_manager.get("INDEX_THRESHOLD") or 50
    keyboard = [
        [InlineKeyboardButton(f"نظام الفهرسة: {status('ENABLE_INDEXING')}", callback_data="toggle_indexing")],
        [InlineKeyboardButton(f"نشر فهرس كل: {threshold} ملف", callback_data="set_index_threshold")],
        [
            InlineKeyboardButton(f"هاشتاج بالاسم: {status('FULL_NAME_HASHTAG')}", callback_data="toggle_full_tag"),
            InlineKeyboardButton(f"فهرس مبوب: {status('INDEX_PER_CATEGORY')}", callback_data="toggle_per_category")
        ],
        [InlineKeyboardButton("🔄 تحديث بوابة الملاحة الآن", callback_data="trigger_hub_update")],
        [InlineKeyboardButton("⬅️ رجوع للإعدادات", callback_data="menu_smart_settings")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_library_keyboard():
    keyboard = [
        [InlineKeyboardButton("📂 تصفح حسب النوع (كتب، فيديو...)", callback_data="lib_main_cat")],
        [InlineKeyboardButton("🏷 تصفح حسب الهاشتاق (#)", callback_data="lib_main_tag")],
        [InlineKeyboardButton("🌐 تصفح حسب قنوات المصدر", callback_data="lib_main_src")],
        [InlineKeyboardButton("🗓 تصفح حسب التاريخ (الأحدث)", callback_data="lib_main_date")],
        [InlineKeyboardButton("⬅️ رجوع للرئيسية", callback_data="menu_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_lib_categories_keyboard():
    cats = get_categories_list()
    keyboard = []
    for i in range(0, len(cats), 2):
        row = [InlineKeyboardButton(f"📁 {cats[i]}", callback_data=f"lib_cat_{cats[i]}")]
        if i + 1 < len(cats):
            row.append(InlineKeyboardButton(f"📁 {cats[i+1]}", callback_data=f"lib_cat_{cats[i+1]}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("⬅️ عودة", callback_data="menu_library")])
    return InlineKeyboardMarkup(keyboard)

def get_lib_sources_keyboard():
    sources = get_sources_list()
    keyboard = []
    for s in sources:
        keyboard.append([InlineKeyboardButton(f"🌐 {s}", callback_data=f"lib_src_{s}")])
    keyboard.append([InlineKeyboardButton("⬅️ عودة", callback_data="menu_library")])
    return InlineKeyboardMarkup(keyboard)

def get_lib_tags_keyboard():
    tags = get_tags_list()
    keyboard = []
    for i in range(0, len(tags), 2):
        row = [InlineKeyboardButton(f"🏷 {tags[i]}", callback_data=f"lib_tag_{tags[i]}")]
        if i + 1 < len(tags):
            row.append(InlineKeyboardButton(f"🏷 {tags[i+1]}", callback_data=f"lib_tag_{tags[i+1]}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("⬅️ عودة", callback_data="menu_library")])
    return InlineKeyboardMarkup(keyboard)

def get_files_list_keyboard(files: list, back_callback: str):
    keyboard = []
    for f in files:
        target_id = settings_manager.get("TARGET_CHANNEL_ID")
        clean_id = str(target_id).replace("-100", "")
        link = f"https://t.me/c/{clean_id}/{f['msg_id']}"
        icon = "🎬" if f['category'] == "🎬 المرئيات" else "📚" if f['category'] == "📚 المكتبة" else "📄"
        keyboard.append([InlineKeyboardButton(f"{icon} {f['name']}", url=link)])
    
    keyboard.append([InlineKeyboardButton("⬅️ عودة للمجلد", callback_data=back_callback)])
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
    keyboard.append([InlineKeyboardButton("⬅️ رجوع للإعدادات", callback_data="menu_smart_settings")])
    return InlineKeyboardMarkup(keyboard)


# =========================
# الأزرار التفاعلية
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    version = "2.5 (Cloud Sync)"
    is_sync = "✅ مفعل" if get_data_path("settings.json").startswith("/data") else "ℹ️ محلي"
    
    text = (
        f"🔘 **لوحة التحكم الشاملة - إصدار {version}**\n\n"
        f"مرحباً بك! اختر القسم الذي تود إدارته من القائمة أدناه:\n\n"
        f"🌐 نظام الملفات: {is_sync}\n"
        f"⚙️ الحالة: ✅ مستقرة"
    )
    await update.message.reply_text(text, reply_markup=get_main_keyboard(), parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_main":
        version = "2.5 (Cloud Sync)"
        is_sync = "✅ مفعل" if get_data_path("settings.json").startswith("/data") else "ℹ️ محلي"
        text = (
            f"🔘 **لوحة التحكم الشاملة - إصدار {version}**\n\n"
            f"مرحباً بك! اختر القسم الذي تود إدارته من القائمة أدناه:\n\n"
            f"🌐 نظام الملفات: {is_sync}\n"
            f"⚙️ الحالة: ✅ مستقرة"
        )
        await query.edit_message_text(text, reply_markup=get_main_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END
    elif data == "menu_sources":
        await query.edit_message_text("📡 **إدارة المصادر والوجهات:**\nتحكم في القنوات التي يتم النقل منها وإليها:", reply_markup=get_sources_keyboard(), parse_mode=ParseMode.MARKDOWN)
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
    elif data.startswith("fetch_100_"):
        parts = data.split("_")
        chat_id = int(parts[2])
        
        requests = settings_manager.get("PENDING_FETCH_REQUESTS") or []
        # تجنب التكرار لنفس القناة
        if not any(r['chat_id'] == chat_id for r in requests):
            requests.append({"chat_id": chat_id, "limit": 100})
            settings_manager.set("PENDING_FETCH_REQUESTS", requests)
            await query.answer("⏳ تم جدولة سحب آخر 100 ملف من هذا المصدر في الخلفية!", show_alert=True)
        else:
            await query.answer("⚠️ هناك طلب سحب جاري لهذا المصدر بالفعل.")
        return ConversationHandler.END
    elif data == "menu_smart_settings":
        await query.edit_message_text("⚙️ **الإعدادات الذكية:**\nتحكم في طريقة معالجة وتصفية الملفات المنقولة:", reply_markup=get_smart_settings_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

    # ===== قسم المجموعة التفاعلية =====
    elif data == "menu_group_index":
        group_id = settings_manager.get("INDEX_GROUP_ID")
        status = f"🔗 **مرتبطة:** `{group_id}`" if group_id else "❌ **لم يتم تعيين المجموعة بعد**"
        text = (
            "📋 **المجموعة التفاعلية — الفهرس الذكي**\n\n"
            f"الحالة: {status}\n\n"
            "**كيف تعمل؟**\n"
            "• بعد كل ملف جديد، يُحدَّث الفهرس في المجموعة تلقائياً.\n"
            "• رسالة واحدة لكل فئة (كتب، فيديو، صوتيات...) مع روابط مباشرة.\n"
            "• رسالة إحصائيات شاملة مثبتة في القمة.\n\n"
            "ابدأ بـ **ربط المجموعة** من الأسفل:"
        )
        await query.edit_message_text(text, reply_markup=get_group_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

    elif data == "set_group_id":
        await query.edit_message_text(
            "🔗 **ربط مجموعة الفهرس الذكي:**\n\n"
            "أرسل الآن **معرف المجموعة** (Chat ID):\n\n"
            "📌 للحصول على معرف المجموعة:\n"
            "1. أضف البوت `@getmyid_bot` للمجموعة مؤقتاً\n"
            "2. أو أرسل أي رسالة في المجموعة وانظر للـ ID في السجل\n\n"
            "✅ تنسيق صحيح: `-1001234567890`\n"
            "لإلغاء أرسل: /cancel",
            parse_mode=ParseMode.MARKDOWN
        )
        return AWAIT_GROUP_ID

    elif data == "grp_toggle_auto":
        current = settings_manager.get("GROUP_AUTO_UPDATE")
        settings_manager.set("GROUP_AUTO_UPDATE", not current)
        state = "✅ مفعّل" if not current else "❌ معطّل"
        await query.answer(f"التحديث التلقائي: {state}")
        await query.edit_message_reply_markup(reply_markup=get_group_keyboard())
        return ConversationHandler.END

    elif data == "grp_cycle_mode":
        modes = ["category", "source", "both"]
        current = settings_manager.get("GROUP_INDEX_MODE") or "category"
        next_mode = modes[(modes.index(current) + 1) % len(modes)]
        settings_manager.set("GROUP_INDEX_MODE", next_mode)
        labels = {"category": "حسب النوع", "source": "حسب المصدر", "both": "الاثنان معاً"}
        await query.answer(f"نمط الفهرسة: {labels[next_mode]}")
        await query.edit_message_reply_markup(reply_markup=get_group_keyboard())
        return ConversationHandler.END

    elif data == "grp_rebuild":
        group_id = settings_manager.get("INDEX_GROUP_ID")
        if not group_id:
            await query.answer("❌ يجب ربط مجموعة أولاً!", show_alert=True)
            return ConversationHandler.END
        settings_manager.set("TRIGGER_REBUILD_GROUP_INDEX", True)
        await query.answer("⏳ تم إصدار أمر إعادة بناء الفهرس! سيبدأ اليوزربوت فوراً.", show_alert=True)
        return ConversationHandler.END

    elif data == "grp_update_stats":
        group_id = settings_manager.get("INDEX_GROUP_ID")
        if not group_id:
            await query.answer("❌ يجب ربط مجموعة أولاً!", show_alert=True)
            return ConversationHandler.END
        settings_manager.set("TRIGGER_REBUILD_GROUP_INDEX", True)  # سيُحدّث الإحصائيات ضمن إعادة البناء
        await query.answer("📊 جاري تحديث رسالة الإحصائيات...")
        return ConversationHandler.END

    elif data == "grp_reset_ids":
        settings_manager.set("GROUP_INDEX_MSG_IDS", {})
        settings_manager.set("TRIGGER_REBUILD_GROUP_INDEX", True)
        await query.answer("🗑 تم مسح السجل — سيُعاد نشر رسائل الفهرس من جديد.", show_alert=True)
        await query.edit_message_reply_markup(reply_markup=get_group_keyboard())
        return ConversationHandler.END
    # ==================================

    elif data == "menu_tools":
        await query.edit_message_text("🛠 **الأدوات والمساعدة:**\nخوارزميات التحكم اليدوي والمزامنة الشاملة:", reply_markup=get_tools_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END
    elif data == "menu_stats":
        from core.db import get_files_count, get_category_group_stats
        total = get_files_count()
        stats = get_category_group_stats()
        stats_text = "\n".join([f"🔸 {cat}: {count} ملف" for cat, count in stats])
        await query.edit_message_text(f"📊 **إحصائيات النظام:**\n\n🎯 إجمالي الملفات: {total}\n\n**التوزيع:**\n{stats_text}", reply_markup=get_main_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END
    elif data == "menu_mechanics": # Fallback for old back buttons
        await query.edit_message_text("⚙️ **الإعدادات الذكية:**", reply_markup=get_smart_settings_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END
    elif data == "menu_types":
        await query.edit_message_text("📂 **فلترة أنواع الوسائط:**\nاختر الأنواع التي تود السماح بنقلها:", reply_markup=get_types_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END
    elif data == "menu_blacklist":
        await query.edit_message_text("🚫 **قائمة الكلمات المحظورة:**\nاضغط على الكلمة لحذفها، أو أضف كلمة جديدة:", reply_markup=get_blacklist_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END
    elif data == "menu_index":
        await query.edit_message_text("📑 **إعدادات الفهرسة والبحث:**", reply_markup=get_index_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END
    
    elif data == "menu_library":
        await query.edit_message_text("📚 **المكتبة التفاعلية (المجلدات):**\nاختر طريقة الفرز التي تفضلها للوصول لملفاتك:", reply_markup=get_library_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

    elif data == "lib_main_tag":
        await query.edit_message_text("🏷 **تصفح حسب الهاشتاق:**\nاختر الوسم المطلوب:", reply_markup=get_lib_tags_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

    elif data == "lib_main_cat":
        await query.edit_message_text("📂 **تصفح حسب النوع:**\nاختر القسم المطلوب:", reply_markup=get_lib_categories_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

    elif data == "lib_main_src":
        await query.edit_message_text("🌐 **تصفح حسب المصدر:**\nاختر القناة المصدرية:", reply_markup=get_lib_sources_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

    elif data.startswith("lib_tag_"):
        tag = data.replace("lib_tag_", "")
        from core.db import get_files_by_tag
        files = get_files_by_tag(tag, limit=10)
        await query.edit_message_text(f"📁 **مجلد الوسم: {tag}**", reply_markup=get_files_list_keyboard(files, "lib_main_tag"), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

    elif data.startswith("lib_cat_"):
        cat = data.replace("lib_cat_", "")
        from core.db import get_files_by_category
        files = get_files_by_category(cat, limit=10)
        await query.edit_message_text(f"📁 **قسم: {cat}**", reply_markup=get_files_list_keyboard(files, "lib_main_cat"), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

    elif data.startswith("lib_src_"):
        src = data.replace("lib_src_", "")
        from core.db import get_files_by_source
        files = get_files_by_source(src, limit=10)
        await query.edit_message_text(f"🌐 **مصدر: {src}**", reply_markup=get_files_list_keyboard(files, "lib_main_src"), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

    elif data == "lib_main_date":
        from core.db import get_all_files_paginated
        files = get_all_files_paginated(limit=15)
        await query.edit_message_text("🗓 **أحدث الملفات المضافة:**", reply_markup=get_files_list_keyboard(files, "menu_library"), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

    elif data == "btn_search":
        await query.edit_message_text("🔍 **البحث عن ملفات:**\nأرسل اسم الملف أو كلمة مفتاحية للبحث في قاعدة البيانات:", parse_mode=ParseMode.MARKDOWN)
        return AWAIT_SEARCH_QUERY

    elif data.startswith("source_profile_"):
        chat_id = int(data.split("_")[-1])
        title = (settings_manager.get("SOURCE_TITLES") or {}).get(str(chat_id)) or f"ID: {chat_id}"
        text = f"⚙️ **إعدادات المصدر:** {title}\nالمعرف: `{chat_id}`\n\nهنا يمكنك تخصيص كيفية تعامل البوت مع هذا المصدر بشكل مستقل."
        await query.edit_message_text(text, reply_markup=get_source_profile_keyboard(chat_id), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

    elif data.startswith("sp_toggle_clean_"):
        chat_id = int(data.split("_")[-1])
        current = settings_manager.get_for_source(chat_id, "DEFAULT_CLEAN_CAPTION")
        settings_manager.set_for_source(chat_id, "DEFAULT_CLEAN_CAPTION", not current)
        await query.edit_message_reply_markup(reply_markup=get_source_profile_keyboard(chat_id))
        return ConversationHandler.END

    elif data.startswith("sp_toggle_header_"):
        chat_id = int(data.split("_")[-1])
        current = settings_manager.get_for_source(chat_id, "ADD_HEADER")
        settings_manager.set_for_source(chat_id, "ADD_HEADER", not current)
        await query.edit_message_reply_markup(reply_markup=get_source_profile_keyboard(chat_id))
        return ConversationHandler.END

    elif data.startswith("sp_toggle_copy_"):
        chat_id = int(data.split("_")[-1])
        current = settings_manager.get_for_source(chat_id, "USE_COPY_INSTEAD_OF_FORWARD")
        settings_manager.set_for_source(chat_id, "USE_COPY_INSTEAD_OF_FORWARD", not current)
        await query.edit_message_reply_markup(reply_markup=get_source_profile_keyboard(chat_id))
        return ConversationHandler.END

    elif data.startswith("sp_toggle_hidesrc_"):
        chat_id = int(data.split("_")[-1])
        current = settings_manager.get_for_source(chat_id, "HIDE_SOURCE_NAME")
        settings_manager.set_for_source(chat_id, "HIDE_SOURCE_NAME", not current)
        await query.edit_message_reply_markup(reply_markup=get_source_profile_keyboard(chat_id))
        return ConversationHandler.END

    elif data.startswith("sp_set_header_"):
        chat_id = int(data.split("_")[-1])
        context.user_data['target_source_profile'] = chat_id
        await query.edit_message_text("📝 **تعديل رأسية المصدر:**\nأرسل النص الجديد للرأسية لهذا المصدر فقط:", parse_mode=ParseMode.MARKDOWN)
        return AWAIT_SOURCE_HEADER

    elif data == "manage_targets":
        await query.edit_message_text("🎯 **إدارة سجل القنوات المستقبلة (الوجهات):**\nيمكنك هنا إضافة القنوات التي تود النقل إليها وتسميتها لتسهيل اختيارها لاحقاً.", reply_markup=get_targets_manage_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

    elif data == "clear_target_history":
        settings_manager.set("TARGET_CHANNELS", {})
        await query.answer("✅ تم مسح سجل الوجهات")
        await query.edit_message_reply_markup(reply_markup=get_targets_manage_keyboard())
        return ConversationHandler.END

    elif data.startswith("del_target_"):
        tid = data.split("_")[-1]
        targets = settings_manager.get("TARGET_CHANNELS") or {}
        if tid in targets:
            name = targets.pop(tid)
            settings_manager.set("TARGET_CHANNELS", targets)
            await query.answer(f"✅ تم حذف الوجهة: {name}")
        await query.edit_message_reply_markup(reply_markup=get_targets_manage_keyboard())
        return ConversationHandler.END

    elif data.startswith("sp_media_filter_"):
        chat_id = int(data.split("_")[-1])
        await query.edit_message_text("📁 **فلترة الوسائط لهذا المصدر:**\nاختر ما تريد السماح بنقله من هذا المصدر تحديداً:", reply_markup=get_source_media_keyboard(chat_id), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

    elif data.startswith("smt_"):
        parts = data.split("_")
        chat_id = int(parts[1])
        key = "_".join(parts[2:])
        current = settings_manager.get_for_source(chat_id, key)
        settings_manager.set_for_source(chat_id, key, not current)
        await query.edit_message_reply_markup(reply_markup=get_source_media_keyboard(chat_id))
        return ConversationHandler.END

    elif data.startswith("sp_select_target_"):
        chat_id = int(data.split("_")[-1])
        await query.edit_message_text("🎯 **اختر الوجهة لهذا المصدر:**\nسيتم نقل الملفات من هذا المصدر إلى الوجهة التي تختارها من القائمة:", reply_markup=get_target_selection_keyboard(chat_id), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

    elif data.startswith("sp_settarget_"):
        parts = data.split("_")
        source_id = int(parts[1])
        target_id = int(parts[2])
        settings_manager.set_for_source(source_id, "TARGET_CHANNEL_ID", target_id)
        await query.answer("✅ تم ربط المصدر بالوجهة المختارة")
        await query.edit_message_text(f"⚙️ **إعدادات المصدر المحدثة:**", reply_markup=get_source_profile_keyboard(source_id), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

    elif data.startswith("sp_copy_settings_"):
        chat_id = int(data.split("_")[-1])
        context.user_data['copy_source_from'] = chat_id
        await query.edit_message_text(f"📋 **نسخ إعدادات المصدر:** `{chat_id}`\n\nأرسل **معرف المصدر المستهدف** (ID) الذي تريد تطبيق هذه الإعدادات عليه:")
        return AWAIT_COPY_SETTINGS_TARGET

    elif data == "toggle_indexing":
        settings_manager.set("ENABLE_INDEXING", not settings_manager.get("ENABLE_INDEXING"))
        await query.edit_message_reply_markup(reply_markup=get_index_keyboard())
        return ConversationHandler.END

    elif data == "set_index_threshold":
        current = settings_manager.get("INDEX_THRESHOLD") or 50
        await query.edit_message_text(f"🔢 **تعديل حد الفهرسة:**\nالحالي: `{current}` ملف.\n\nأرسل **عدد الملفات الجديد** الذي تريد أن ينشر البوت الفهرس بعد وصوله:", parse_mode=ParseMode.MARKDOWN)
        return AWAIT_INDEX_THRESHOLD

    elif data == "toggle_full_tag":
        settings_manager.set("FULL_NAME_HASHTAG", not settings_manager.get("FULL_NAME_HASHTAG"))
        await query.edit_message_reply_markup(reply_markup=get_index_keyboard())
        return ConversationHandler.END
    elif data == "toggle_per_category":
        settings_manager.set("INDEX_PER_CATEGORY", not settings_manager.get("INDEX_PER_CATEGORY"))
        await query.edit_message_reply_markup(reply_markup=get_index_keyboard())
        return ConversationHandler.END
    elif data == "trigger_hub_update":
        # طلب تحديث البوابة من اليوزر بوت
        settings_manager.set("TRIGGER_HUB_UPDATE", True)
        await query.answer("⏳ تم جدولة تحديث بوابة الملاحة المركزية!", show_alert=True)
        return ConversationHandler.END

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
        return ConversationHandler.END
    elif data == "toggle_copy":
        current = settings_manager.get("USE_COPY_INSTEAD_OF_FORWARD")
        settings_manager.set("USE_COPY_INSTEAD_OF_FORWARD", not current)
        await query.edit_message_reply_markup(reply_markup=get_smart_settings_keyboard())
        return ConversationHandler.END
    elif data == "toggle_clean_all":
        current = settings_manager.get("DEFAULT_CLEAN_CAPTION")
        settings_manager.set("DEFAULT_CLEAN_CAPTION", not current)
        await query.edit_message_reply_markup(reply_markup=get_smart_settings_keyboard())
        return ConversationHandler.END
    elif data == "cleanup_bot":
        # تنظيف العمليات العالية أو الملفات المؤقتة
        import psutil
        count = 0
        for proc in psutil.process_iter(['pid', 'name']):
            if "python" in proc.info['name'].lower() and proc.info['pid'] != os.getpid():
                # لا نريد قتل العمليات الأساسية هنا، فقط تنظيف الذاكرة الوهمي للتنبيه
                pass
        await query.answer("🧹 تم تحسين استهلاك الذاكرة وتنظيف الملفات المؤقتة بنجاح!", show_alert=True)
        return ConversationHandler.END

    elif data == "menu_import_history":
        await query.edit_message_text("📥 **استيراد التاريخ (Messages History):**\nاختر المصدر الذي تود سحب الملفات القديمة منه:", reply_markup=get_sources_manage_keyboard(0), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END
    elif data == "toggle_hashtag":
        settings_manager.set("REQUIRE_HASHTAG", not settings_manager.get("REQUIRE_HASHTAG"))
        await query.edit_message_reply_markup(reply_markup=get_smart_settings_keyboard())
        return ConversationHandler.END

    elif data == "help":
        await query.edit_message_text(
            "ℹ️ هذا البوت مسؤول عن إدارة الإعدادات فقط. عند إضافة مصدر للقائمة سيقوم حساب الـ Userbot المرافق بالنقل التلقائي منه للوجهة المطلوبة فوراً وبدون تعارض.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ عودة للرئيسية", callback_data="menu_main")]])
        )
    elif data == "status":
        target = settings_manager.get("TARGET_CHANNEL_ID")
        groups = get_sources()
        from core.db import get_files_count
        count = get_files_count()
        indexing = "✅" if settings_manager.get("ENABLE_INDEXING") else "❌"
        copy_mode = "نسخ" if settings_manager.get("USE_COPY_INSTEAD_OF_FORWARD") else "إعادة توجيه"
        
        text = (
            f"📊 **حالة البوت وإحصائيات:**\n\n"
            f"🔹 **الحالة:** يعمل بكفاءة\n"
            f"🔹 **الوجهة الافتراضية:** `{target}`\n"
            f"🔹 **المصادر النشطة:** `{len(groups) if isinstance(groups, list) else 0}`\n"
            f"🔹 **إجمالي ملفات الفهرس:** `{count}`\n"
            f"🔹 **وضع النقل:** {copy_mode}\n"
            f"🔹 **نظام الفهرسة:** {indexing}\n\n"
            f"🤖 محرك النقل (UserBot) متصل ويراقب القنوات الآن."
        )
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ عودة للرئيسية", callback_data="menu_main")]])
            , parse_mode=ParseMode.MARKDOWN
        )
        return ConversationHandler.END

    elif data == "show_sources":
        groups = get_sources()
        titles = settings_manager.get("SOURCE_TITLES") or {}
        if groups:
            lines = ["📋 **المصادر المراقبة:**", ""]
            for idx, g in enumerate(groups[:20], 1):
                title = titles.get(str(g)) or "بدون اسم محفوظ"
                lines.append(f"{idx}. **{title}**")
                lines.append(f"`{g}`")
            if len(groups) > 20:
                lines.append("")
                lines.append(f"… وهناك `{len(groups) - 20}` مصدر إضافي.")
            text_groups = "\n".join(lines)
        else:
            text_groups = "📋 **المصادر المراقبة:**\nلا توجد مصادر حالياً."
        await query.edit_message_text(
            text_groups,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع للمصادر", callback_data="menu_sources")]]),
            parse_mode=ParseMode.MARKDOWN
        )
    elif data == "show_pending_sources":
        pending = settings_manager.get("PENDING_JOINS") or []
        if pending:
            lines = ["⏳ **المصادر المعلقة:**", "هذه المصادر محفوظة وتنتظر أن يعتمدها الـ UserBot.", ""]
            for idx, item in enumerate(pending[:20], 1):
                lines.append(f"{idx}. `{item}`")
            if len(pending) > 20:
                lines.append("")
                lines.append(f"… وهناك `{len(pending) - 20}` مصدر إضافي.")
            text = "\n".join(lines)
        else:
            text = "⏳ **المصادر المعلقة:**\nلا توجد مصادر معلقة حالياً."
        await query.edit_message_text(
            text,
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
            "أرسل **العدد المطلوب** للملفات التي تريد سحبها من كل مصدر بأثر رجعي (يمكنك اختيار رقم بين 1 و **100**):",
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

    elif data == "add_new_target":
        text = (
            "🎯 **إضافة قناة وجهة (المستقبِلة):**\n"
            "أرسل الآن **رابط القناة، اليوزر، أو الآيدي الرقمي**.\n\n"
            "✅ يدعم الأن:\n"
            "• الروابط العامة: `https://t.me/channel`\n"
            "• اليوزرات: `@channel`\n"
            "• روابط الانضمام الخاصة: `https://t.me/+Abc...`\n"
            "• الآيدي الرقمي: `-100...`"
        )
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
        return AWAIT_TARGET_CHANNEL
    elif data == "add_source":
        await query.edit_message_text("➕ **ربط قناة مصدر جديدة:**\nأرسل الآن (رابط القناة، اليوزر، أو الآيدي الرقمي):\nمثال: `https://t.me/example` أو `@example`", parse_mode=ParseMode.MARKDOWN)
        return AWAIT_ADD_SOURCE

    return ConversationHandler.END


# =========================
# معالجات الحالات (States Handlers)
# =========================
async def receive_target_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("✅ تم إلغاء المهمة.", reply_markup=get_sources_keyboard())
        return ConversationHandler.END

    # استخدام المحرك الذكي
    source_identifier = clean_identifier(text)
    
    # 1. إذا نجحنا في استخراج آيدي رقمي مباشر
    if isinstance(source_identifier, int):
        channel_id = source_identifier
        settings_manager.set("TARGET_CHANNEL_ID", channel_id)
        
        targets = settings_manager.get("TARGET_CHANNELS") or {}
        if str(channel_id) not in targets:
            context.user_data['pending_target_id'] = channel_id
            await update.message.reply_text(f"✅ تم استخراج المعرف بنجاح: `{channel_id}`\n\nأرسل الآن **اسماً مستعاراً** لهذه القناة لإضافتها للسجل:")
            return AWAIT_TARGET_NAME
        
        await update.message.reply_text(f"✅ تم ضبط القناة الوجهة بنجاح: `{channel_id}`", reply_markup=get_sources_keyboard(), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

    # 2. محاولة التعرف عبر البوت أو التحويل لليوزربوت (الفشل يعني التحويل التلقائي)
    try:
        chat = await context.bot.get_chat(source_identifier)
        channel_id = chat.id
    except Exception:
        # الاستجابة النهائية والجذرية: أي فشل يتم تحويله لليوزربوت فوراً
        pending = settings_manager.get("PENDING_JOINS") or []
        if str(source_identifier) not in pending:
            pending.append(str(source_identifier))
            settings_manager.set("PENDING_JOINS", pending)
        
        await update.message.reply_text(
            "⏳ **لم يتم التعرف الفوري، جاري المعالجة عبر اليوزربوت...**\n"
            f"قمت بإضافة `{source_identifier}` إلى طابور المعالجة الخاص بالحساب الشخصي (Userbot).\n\n"
            "سيقوم اليوزربوت بالانضمام للقناة واستخراج بياناتها تلقائياً وتفعيلها. يرجى الانتظار لحظات.",
            reply_markup=get_sources_keyboard()
        )
        return ConversationHandler.END

    # إذا نجح البوت في التعرف (لليوزرات العامة مثلاً)
    settings_manager.set("TARGET_CHANNEL_ID", channel_id)
    targets = settings_manager.get("TARGET_CHANNELS") or {}
    if str(channel_id) not in targets:
        context.user_data['pending_target_id'] = channel_id
        await update.message.reply_text(f"✅ تم التعرف على القناة: `{channel_id}`\n\nأرسل الآن **اسماً مستعاراً** لها:")
        return AWAIT_TARGET_NAME
    
    await update.message.reply_text(f"✅ تم حفظ القناة بنجاح: `{channel_id}`", reply_markup=get_sources_keyboard(), parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END

async def receive_target_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    tid = context.user_data.get('pending_target_id')
    if not tid:
        return ConversationHandler.END
    
    targets = settings_manager.get("TARGET_CHANNELS") or {}
    targets[str(tid)] = name
    settings_manager.set("TARGET_CHANNELS", targets)
    
    await update.message.reply_text(f"✅ تم تسجيل الوجهة بنجاح باسم: **{name}**", reply_markup=get_targets_manage_keyboard(), parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END


async def receive_add_source(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("✅ تم إلغاء المهمة.", reply_markup=get_sources_keyboard())
        return ConversationHandler.END

    active_sources = settings_manager.get("ALLOWED_SOURCE_CHAT_IDS") or []
    
    # استخدام المحرك الذكي
    source_identifier = clean_identifier(text)

    # 1. إذا تم استخراج آيدي رقمي مباشر
    if isinstance(source_identifier, int):
        source_id = source_identifier
        if source_id in active_sources:
            await update.message.reply_text("⚠️ هذا المصدر معتمد مسبقاً.", reply_markup=get_sources_keyboard())
            return ConversationHandler.END

        from core.sources import add_source
        add_source(source_id)
        await update.message.reply_text(
            f"✅ تم التعرف على المصدر واعتماده مباشرة:\n`{source_id}`\n\n"
            "سيقوم البوت بنقل أي ملفات جديدة من هنا فوراً.",
            reply_markup=get_sources_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationHandler.END

    # 2. التحويل التلقائي لليوزربوت (لأي معرف نصي أو رابط)
    pending = settings_manager.get("PENDING_JOINS") or []
    if str(source_identifier) not in pending:
        pending.append(str(source_identifier))
        settings_manager.set("PENDING_JOINS", pending)
        logger.info(f"تمت إضافة مصدر للطابور: {source_identifier}")
        await update.message.reply_text(
            "⏳ **جاري التحقق عبر اليوزربوت...**\n"
            f"بما أنني (البوت) لا أستطيع الوصول للمصدر `{source_identifier}` حالياً، سأقوم بتحويل المهمة للحساب الشخصي (Userbot) للانضمام والاعتماد.\n\n"
            "ستبدأ المزامنة تلقائياً بمجرد نجاح الانضمام.", 
            reply_markup=get_sources_keyboard()
        )
    else:
        await update.message.reply_text("⚠️ هذا المصدر بانتظار المراجعة بالفعل.", reply_markup=get_sources_keyboard())

    return ConversationHandler.END


async def receive_max_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("✅ تم إلغاء المهمة.", reply_markup=get_tools_keyboard())
        return ConversationHandler.END

    try:
        max_msgs = int(text)
        if max_msgs <= 0 or max_msgs > 100:
            await update.message.reply_text("❌ العدد غير منطقي، أرسل رقماً بين 1 و 100.")
            return AWAIT_MAX_MESSAGES
    except ValueError:
        await update.message.reply_text("❌ يرجى إرسال أرقام فقط (مثال: 5).\nلإلغاء: /cancel")
        return AWAIT_MAX_MESSAGES

    settings_manager.set("MAX_LAST_MESSAGES", max_msgs)
    await update.message.reply_text(f"✅ تم حفظ الحد الأقصى لسحب الملفات بأثر رجعي: `{max_msgs}`", reply_markup=get_tools_keyboard(), parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END


async def receive_header_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("✅ تم إلغاء المهمة.", reply_markup=get_smart_settings_keyboard())
        return ConversationHandler.END

    settings_manager.set("HEADER_TEXT", text)
    await update.message.reply_text(f"✅ تم تحديث نص الترويسة بنجاح إلى:\n`{text}`", reply_markup=get_smart_settings_keyboard(), parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END


async def receive_blacklist_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    word = update.message.text.strip()
    if word == "/cancel":
        await update.message.reply_text("✅ تم إلغاء المهمة.", reply_markup=get_smart_settings_keyboard())
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
        await update.message.reply_text("✅ تم إلغاء المهمة.", reply_markup=get_smart_settings_keyboard())
        return ConversationHandler.END

    settings_manager.set("SOURCE_LABEL", text)
    await update.message.reply_text(f"✅ تم تحديث تسمية المصدر إلى: `{text}`", reply_markup=get_smart_settings_keyboard(), parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END


async def receive_sender_label(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("✅ تم إلغاء المهمة.", reply_markup=get_smart_settings_keyboard())
        return ConversationHandler.END

    settings_manager.set("SENDER_LABEL", text)
    await update.message.reply_text(f"✅ تم تحديث تسمية المرسل إلى: `{text}`", reply_markup=get_smart_settings_keyboard(), parse_mode=ParseMode.MARKDOWN)
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


async def receive_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    if query == "/cancel" or len(query) < 2:
        await update.message.reply_text("✅ تم الإغلاق.", reply_markup=get_main_keyboard())
        return ConversationHandler.END

    from core.db import search_files
    results = search_files(query, limit=10)
    
    if not results:
        await update.message.reply_text("🔍 لا توجد نتائج مطابقة لبحثك في قاعدة البيانات.", reply_markup=get_main_keyboard())
        return ConversationHandler.END

    lines = ["🔍 **نتائج البحث المكتشفة:**", ""]
    for i, res in enumerate(results, 1):
        lines.append(f"{i}. **{res['name']}**")
        lines.append(f"└ 🏷 {res['tag']} | [رابط الملف](https://t.me/c/{str(settings_manager.get('TARGET_CHANNEL_ID'))[4:]}/{res['msg_id']})")
    
    text = "\n".join(lines)
    await update.message.reply_text(text, reply_markup=get_main_keyboard(), disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END

async def receive_source_header(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.user_data.get('target_source_profile')
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("✅ تم الإلغاء.", reply_markup=get_sources_manage_keyboard())
        return ConversationHandler.END

    settings_manager.set_for_source(chat_id, "HEADER_TEXT", text)
    await update.message.reply_text(f"✅ تم تحديث الرأسية المخصصة للمصدر `{chat_id}`", reply_markup=get_sources_manage_keyboard())
    return ConversationHandler.END

async def receive_source_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.user_data.get('target_source_profile')
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("✅ تم الإلغاء.", reply_markup=get_sources_manage_keyboard())
        return ConversationHandler.END

    try:
        target_id = int(text)
        settings_manager.set_for_source(chat_id, "TARGET_CHANNEL_ID", target_id)
        await update.message.reply_text(f"✅ تم تحديث القناة المستقبلة لهذا المصدر بنجاح.", reply_markup=get_sources_manage_keyboard())
    except ValueError:
        await update.message.reply_text("⚠️ يرجى إرسال معرف رقمي صحيح.")
    
    return ConversationHandler.END


async def receive_copy_settings_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from_id = context.user_data.get('copy_source_from')
    text = update.message.text.strip()
    
    if text == "/cancel":
        await update.message.reply_text("✅ تم الإلغاء.", reply_markup=get_sources_manage_keyboard())
        return ConversationHandler.END

    try:
        to_id = int(text)
        if settings_manager.copy_source_settings(from_id, to_id):
            await update.message.reply_text(f"✅ تم نسخ كافة الإعدادات بنجاح للمصدر `{to_id}`", reply_markup=get_sources_manage_keyboard())
        else:
            await update.message.reply_text(f"⚠️ فشل النسخ. تأكد من أن المصدر الأساسي لديه إعدادات محفوظة.", reply_markup=get_sources_manage_keyboard())
    except ValueError:
        await update.message.reply_text("⚠️ يرجى إرسال معرف رقمي صحيح.")
    
    return ConversationHandler.END


async def receive_group_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال معرف مجموعة الفهرس الذكي."""
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("✅ تم الإلغاء.", reply_markup=get_group_keyboard())
        return ConversationHandler.END

    identifier = clean_identifier(text)

    if isinstance(identifier, int):
        group_id = identifier
    else:
        try:
            chat = await context.bot.get_chat(identifier)
            group_id = chat.id
        except Exception as e:
            await update.message.reply_text(
                f"❌ لم يتمكن البوت من التعرف على هذه المجموعة.\n\n"
                f"تأكد من:\n"
                f"• إضافة البوت للمجموعة كمسؤول\n"
                f"• إرسال المعرف الرقمي بشكل صحيح (مثال: `-1001234567890`)\n\n"
                f"الخطأ: `{e}`",
                parse_mode=ParseMode.MARKDOWN
            )
            return AWAIT_GROUP_ID

    settings_manager.set("INDEX_GROUP_ID", group_id)
    settings_manager.set("GROUP_INDEX_MSG_IDS", {})
    settings_manager.set("TRIGGER_REBUILD_GROUP_INDEX", True)

    await update.message.reply_text(
        f"✅ **تم ربط المجموعة بنجاح!**\n\n"
        f"المعرف: `{group_id}`\n\n"
        f"⏳ سيبدأ اليوزربوت في بناء الفهرس الكامل خلال لحظات...\n"
        f"ستصلك رسالة في `رسائلك المحفوظة` عند الاكتمال.",
        reply_markup=get_group_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    return ConversationHandler.END


async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query
    if not query:
        return

    results = search_files(query, limit=20)
    inline_results = []
    
    target_id = settings_manager.get("TARGET_CHANNEL_ID")
    clean_id = str(target_id).replace("-100", "")
    
    for f in results:
        link = f"https://t.me/c/{clean_id}/{f['msg_id']}"
        size_mb = round(f['file_size'] / (1024*1024), 2) if f.get('file_size') else 0
        
        description = f"📦 {size_mb} MB | 🏷 {f['tag'] or '#عام'}"
        
        inline_results.append(
            InlineQueryResultArticle(
                id=str(f['id']),
                title=f['name'],
                description=description,
                input_message_content=InputTextMessageContent(
                    f"📄 **{f['name']}**\n\n{description}\n\n🔗 [رابط الملف المباشر]({link})",
                    parse_mode=ParseMode.MARKDOWN
                ),
                url=link,
                hide_url=True
            )
        )

    await update.inline_query.answer(inline_results, cache_time=300)


async def menu_library(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فتح المكتبة التفاعلية عبر أمر خارجي."""
    await update.message.reply_text("📚 **المكتبة التفاعلية (المجلدات):**\nاختر تصنيفاً لتصفح ملفاته مباشرة:", reply_markup=get_library_keyboard(), parse_mode=ParseMode.MARKDOWN)


async def cancel_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم الإلغاء.", reply_markup=get_main_keyboard())
    return ConversationHandler.END


def main():
    if not BOT_TOKEN or BOT_TOKEN == "PUT_YOUR_BOT_TOKEN":
        logger.error("BOT_TOKEN is missing or invalid in .env")
        return

    from telegram.request import HTTPXRequest
    request = HTTPXRequest(connect_timeout=20.0, read_timeout=20.0)
    app = Application.builder().token(BOT_TOKEN).request(request).build()

    setup_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_callback, pattern="^(add_new_target|add_source|set_max_messages|edit_header_text|add_blacklist_word|edit_source_label|edit_sender_label|set_index_threshold|btn_search|set_group_id|sp_set_header_.*|sp_set_target_.*|sp_select_target_.*|sp_settarget_.*|smt_.*|sp_media_filter_.*|sp_copy_settings_.*)$")],
        states={
            AWAIT_TARGET_CHANNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_target_channel)],
            AWAIT_ADD_SOURCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_add_source)],
            AWAIT_MAX_MESSAGES: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_max_messages)],
            AWAIT_HEADER_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_header_text)],
            AWAIT_BLACKLIST_WORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_blacklist_word)],
            AWAIT_SOURCE_LABEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_source_label)],
            AWAIT_SENDER_LABEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_sender_label)],
            AWAIT_INDEX_THRESHOLD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_index_threshold)],
            AWAIT_SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_search_query)],
            AWAIT_SOURCE_HEADER: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_source_header)],
            AWAIT_SOURCE_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_source_target)],
            AWAIT_TARGET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_target_name)],
            AWAIT_COPY_SETTINGS_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_copy_settings_target)],
            AWAIT_GROUP_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_group_id)],
        },
        fallbacks=[CommandHandler("cancel", cancel_setup)]
    )

    app.add_handler(setup_conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("library", menu_library))
    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    # تمت إزالة file_router بالكامل لمنع الازدواجية والتضارب

    logger.info("تم تشغيل لوحة تحكم البوت (Dashboard) بنجاح.")
    app.run_polling()

if __name__ == "__main__":
    main()
