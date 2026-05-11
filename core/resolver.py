import re

def clean_identifier(text: str) -> str | int:
    """
    تحويل أي مدخل (رابط، يوزر، آيدي) إلى صيغة معيارية يفهمها تليجرام.
    """
    if not text:
        return text
    
    text = text.strip()
    
    # 1. إذا كان آيدي رقمي صريح (مثلاً -100123456)
    if re.match(r'^-?\d+$', text):
        return int(text)
    
    # 2. روابط القنوات الخاصة (https://t.me/c/123456789/10)
    private_match = re.search(r'(?:t\.me|telegram\.me|telegram\.dog)/c/(\d+)', text)
    if private_match:
        return int(f"-100{private_match.group(1)}")
    
    # 3. روابط الانضمام (joinchat أو +الخ)
    if "joinchat" in text or "+" in text:
        # استخراج الرابط بالكامل حتى لو بدون https://
        join_match = re.search(r'((?:https?://)?(?:t\.me|telegram\.me|telegram\.dog)/(?:\+|joinchat/)\S+)', text)
        if join_match:
            return join_match.group(1)
        return text 
    
    # 4. الروابط العامة (https://t.me/username أو https://t.me/username/123)
    public_match = re.search(r'(?:https?://)?(?:t\.me|telegram\.me|telegram\.dog)/([a-zA-Z0-9_]+)', text)
    if public_match:
        username = public_match.group(1)
        # استبعاد الكلمات المحجوزة
        if username.lower() not in ['share', 'contact', 'addstickers', 'setlanguage', 'c', 'joinchat']:
            return f"@{username}"
        return text # إذا كانت كلمة محجوزة نترك النص كما هو
    
    # 5. يوزرات @username
    if text.startswith('@'):
        return text
    
    return text

def is_numeric_id(identifier) -> bool:
    if isinstance(identifier, int):
        return True
    if isinstance(identifier, str):
        return bool(re.match(r'^-?\d+$', identifier))
    return False
