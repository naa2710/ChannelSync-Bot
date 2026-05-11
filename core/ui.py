from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import settings_manager
import os

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

def get_smart_settings_keyboard():
    docs_only = "✅" if settings_manager.get("DOCUMENTS_ONLY") else "❌"
    hashtag = "✅" if settings_manager.get("REQUIRE_HASHTAG") else "❌"
    admins = "✅" if settings_manager.get("ADMINS_ONLY") else "❌"
    copy_mode = "✅" if settings_manager.get("USE_COPY_INSTEAD_OF_FORWARD") else "❌"
    header = "✅" if settings_manager.get("ADD_HEADER") else "❌"
    clean = "✅" if settings_manager.get("DEFAULT_CLEAN_CAPTION") else "❌"
    
    keyboard = [
        [InlineKeyboardButton(f"📄 مستندات فقط: {docs_only}", callback_data="toggle_docs_only")],
        [InlineKeyboardButton(f"🏷 اشتراط هاشتاق: {hashtag}", callback_data="toggle_hashtag")],
        [InlineKeyboardButton(f"👮‍♂️ للمشرفين فقط: {admins}", callback_data="toggle_admins")],
        [InlineKeyboardButton(f"🙈 إخفاء المصدر (Copy): {copy_mode}", callback_data="toggle_copy_mode")],
        [InlineKeyboardButton(f"📝 إضافة ترويسة: {header}", callback_data="toggle_add_header")],
        [InlineKeyboardButton(f"🧹 تنظيف الحقوق: {clean}", callback_data="toggle_clean_all")],
        [InlineKeyboardButton("✍️ تعديل نص الترويسة (Header)", callback_data="edit_header_text")],
        [InlineKeyboardButton("🚫 الكلمات المحظورة (Blacklist)", callback_data="menu_blacklist")],
        [InlineKeyboardButton("⬅️ عودة للرئيسية", callback_data="menu_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_stats_keyboard():
    keyboard = [[InlineKeyboardButton("🔄 تحديث", callback_data="menu_stats")], [InlineKeyboardButton("⬅️ عودة", callback_data="menu_main")]]
    return InlineKeyboardMarkup(keyboard)

def get_tools_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔄 سحب جماعي الآن", callback_data="trigger_fetch_all")],
        [InlineKeyboardButton("🔢 ضبط عدد رسائل السحب", callback_data="set_max_messages")],
        [InlineKeyboardButton("🗑 مسح كافة المصادر", callback_data="clear_sources_confirm")],
        [InlineKeyboardButton("⬅️ عودة للرئيسية", callback_data="menu_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_group_keyboard():
    group_id = settings_manager.get("INDEX_GROUP_ID")
    auto = "✅" if settings_manager.get("GROUP_AUTO_UPDATE") else "❌"
    status = f"🔗 `{group_id}`" if group_id else "❌ غير مرتبطة"
    
    keyboard = [
        [InlineKeyboardButton(f"🔗 المجموعة: {status}", callback_data="set_group_id")],
        [InlineKeyboardButton(f"⚡ التحديث التلقائي: {auto}", callback_data="grp_toggle_auto")],
        [
            InlineKeyboardButton("🔄 إعادة بناء الفهرس", callback_data="grp_rebuild"),
            InlineKeyboardButton("📊 تحديث الإحصائيات", callback_data="grp_update_stats"),
        ],
        [InlineKeyboardButton("⬅️ عودة للرئيسية", callback_data="menu_main")],
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

def get_blacklist_keyboard():
    words = settings_manager.get("BLACKLIST_WORDS") or []
    keyboard = []
    for word in words[:15]:
        keyboard.append([InlineKeyboardButton(f"❌ {word}", callback_data=f"del_word_{word}")])
    
    keyboard.append([InlineKeyboardButton("➕ إضافة كلمة", callback_data="add_blacklist_word")])
    keyboard.append([InlineKeyboardButton("⬅️ عودة", callback_data="menu_smart_settings")])
    return InlineKeyboardMarkup(keyboard)
