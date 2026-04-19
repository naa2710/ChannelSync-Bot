from config import settings_manager

def is_allowed_chat(chat_id: int) -> bool:
    """التحقق مما إذا كانت القناة/المجموعة معتمدة ضمن المصادر."""
    allowed = settings_manager.get("ALLOWED_SOURCE_CHAT_IDS")
    return chat_id in allowed

def add_source(chat_id: int, title: str = None) -> bool:
    """إضافة مصدر جديد للاعتماد المباشر وتخزين اسمه."""
    allowed = settings_manager.get("ALLOWED_SOURCE_CHAT_IDS")
    titles = settings_manager.get("SOURCE_TITLES") or {}
    
    chat_str_id = str(chat_id)
    added = False
    
    if chat_id not in allowed:
        allowed.append(chat_id)
        settings_manager.set("ALLOWED_SOURCE_CHAT_IDS", allowed)
        added = True
        
    if title:
        titles[chat_str_id] = title
        settings_manager.set("SOURCE_TITLES", titles)
        
    return added

def remove_source(chat_id: int) -> bool:
    """حذف مصدر موجود وتنظيف بياناته."""
    allowed = settings_manager.get("ALLOWED_SOURCE_CHAT_IDS")
    titles = settings_manager.get("SOURCE_TITLES") or {}
    
    chat_str_id = str(chat_id)
    removed = False
    
    if chat_id in allowed:
        allowed.remove(chat_id)
        settings_manager.set("ALLOWED_SOURCE_CHAT_IDS", allowed)
        removed = True
        
    if chat_str_id in titles:
        del titles[chat_str_id]
        settings_manager.set("SOURCE_TITLES", titles)
        
    return removed

def get_sources() -> list:
    """جلب جميع المصادر."""
    return settings_manager.get("ALLOWED_SOURCE_CHAT_IDS")

def clear_sources():
    """مسح جميع المصادر المعتمدة."""
    settings_manager.set("ALLOWED_SOURCE_CHAT_IDS", [])
