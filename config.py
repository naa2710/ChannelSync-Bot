import json
import os
from threading import Lock
from dotenv import load_dotenv

load_dotenv()

def get_data_path(filename):
    """جلب مسار الملف مع دعم التخزين الدائم على المنصات السحابية."""
    # Hugging Face Spaces mount persistent storage at /data
    if os.path.exists("/data") and os.access("/data", os.W_OK):
        return os.path.join("/data", filename)
    
    # Fallback to current directory for local dev or Koyeb without PV
    return filename

class SettingsManager:
    def __init__(self, settings_file="settings.json"):
        self.settings_file = get_data_path(settings_file)
        self.lock = Lock()
        self.on_change_callback = None # سيتم ضبطه من قبل اليوزر بوت للمزامنة
        self.defaults = {
            "TARGET_CHANNEL_ID": int(os.getenv("TARGET_CHANNEL_ID", "-1001234567890")),
            "TARGET_CHANNELS": {}, # سجل الوجهات المتعددة { "chat_id": "اسم الوجهة" }
            "ALLOWED_SOURCE_CHAT_IDS": [
                int(x) for x in os.getenv("ALLOWED_SOURCE_CHAT_IDS", "").split(",") if x.strip()
            ],
            "REQUIRE_HASHTAG": os.getenv("REQUIRE_HASHTAG", "false").lower() == "true",
            "REQUIRED_HASHTAG": os.getenv("REQUIRED_HASHTAG", "#نشر"),
            "ADMINS_ONLY": os.getenv("ADMINS_ONLY", "false").lower() == "true",
            "USE_COPY_INSTEAD_OF_FORWARD": True,
            "ADD_HEADER": os.getenv("ADD_HEADER", "true").lower() == "true",
            "HEADER_TEXT": os.getenv("HEADER_TEXT", "ملف جديد وارد من إحدى المجموعات"),
            "SEND_HEADER_AS_SEPARATE_MESSAGE": os.getenv("SEND_HEADER_AS_SEPARATE_MESSAGE", "true").lower() == "true",
            "PENDING_JOINS": [],
            "IS_BOT_ACTIVE": True,
            "MAX_LAST_MESSAGES": 5,
            "TRIGGER_FETCH_ALL": False,
            "ALLOW_TEXT": True,
            "ALLOW_PHOTO": True,
            "ALLOW_DOCUMENT": True,
            "ALLOW_VIDEO": True,
            "ALLOW_VOICE": True,
            "ALLOW_AUDIO": True,
            "ALLOW_ANIMATION": True,
            "BLACKLIST_WORDS": [],
            "SOURCE_LABEL": "المصدر",
            "SENDER_LABEL": "المرسل",
            "SOURCE_TITLES": {},
            "SOURCE_CONFIGS": {}, # إعدادات مخصصة لكل مصدر { "chat_id": { "header": "...", "target": ID, "clean": True } }
            "ENABLE_INDEXING": False,
            "INDEX_THRESHOLD": 50,
            "PENDING_INDEX_ITEMS": [],
            "PENDING_FETCH_REQUESTS": [],
            "DEBUG_ALL_MESSAGES": False,
            "DEFAULT_CLEAN_CAPTION": True, # تنظيف الكابشن افتراضياً
            "FULL_NAME_HASHTAG": True, # تحويل اسم الملف بالكامل لهاشتاج
            "INDEX_HUB_MESSAGE_ID": None, # ID رسالة الفهرس المثبتة
            "INDEX_PER_CATEGORY": True, # تقسيم الفهرس لرسائل حسب القسم
            "APPEND_TAG_TO_CAPTION": True, # إلحاق الهاشتاج التلقائي بشرح الملف
            # ===== إعدادات المجموعة التفاعلية =====
            "INDEX_GROUP_ID": int(os.getenv("INDEX_GROUP_ID", "0")) or None,  # معرف مجموعة الفهرس
            "GROUP_INDEX_MSG_IDS": {},    # سجل معرفات الرسائل { "cat_📚 المكتبة": 123, "stats": 456 }
            "GROUP_AUTO_UPDATE": True,    # تحديث الفهرس تلقائياً بعد كل ملف
            "GROUP_INDEX_MODE": "category",  # نمط الفهرسة: category / source / both
            "TRIGGER_REBUILD_GROUP_INDEX": False,  # أمر إعادة البناء الكامل
        }
        self.settings = self.load_settings()
        try:
            self._last_mtime = os.path.getmtime(self.settings_file)
        except OSError:
            self._last_mtime = 0

    def load_settings(self):
        with self.lock:
            if os.path.exists(self.settings_file):
                try:
                    with open(self.settings_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        # دمج الإعدادات المحفوظة مع القيم الافتراضية لضمان وجود المفاتيح الجديدة
                        return {**self.defaults, **data}
                except Exception:
                    return self.defaults.copy()
            return self.defaults.copy()

    def save_settings(self):
        with self.lock:
            try:
                settings_dir = os.path.dirname(os.path.abspath(self.settings_file))
                os.makedirs(settings_dir, exist_ok=True)

                # حفظ ذري لتقليل احتمالية تلف ملف الإعدادات عند إعادة التشغيل المفاجئ
                temp_path = f"{self.settings_file}.tmp"
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(self.settings, f, indent=4, ensure_ascii=False)
                os.replace(temp_path, self.settings_file)
                
                # استدعاء دالة المزامنة إذا كانت موجودة
                if self.on_change_callback:
                    self.on_change_callback()
            except Exception as e:
                print(f"Error saving settings: {e}")

    def get(self, key, default=None):
        try:
            mtime = os.path.getmtime(self.settings_file)
            if getattr(self, '_last_mtime', 0) < mtime:
                self.settings = self.load_settings()
                self._last_mtime = mtime
        except OSError:
            pass
        return self.settings.get(key, default if default is not None else self.defaults.get(key))

    def get_for_source(self, chat_id, key):
        """جلب إعداد معين لمصدر محدد، وإذا لم يوجد نعود للإعداد العام."""
        configs = self.get("SOURCE_CONFIGS") or {}
        chat_str = str(chat_id)
        if chat_str in configs and key in configs[chat_str]:
            return configs[chat_str][key]
        return self.get(key)

    def set_for_source(self, chat_id, key, value):
        """ضبط إعداد معين لمصدر محدد."""
        configs = self.get("SOURCE_CONFIGS") or {}
        chat_str = str(chat_id)
        if chat_str not in configs:
            configs[chat_str] = {}
        configs[chat_str][key] = value
        self.set("SOURCE_CONFIGS", configs)

    def set(self, key, value):
        # Reload before setting to not overwrite other process changes
        try:
            mtime = os.path.getmtime(self.settings_file)
            if getattr(self, '_last_mtime', 0) < mtime:
                self.settings = self.load_settings()
        except OSError:
            pass
            
        self.settings[key] = value
        self.save_settings()
        try:
            self._last_mtime = os.path.getmtime(self.settings_file)
        except OSError:
            pass

    def get_all(self):
        return self.settings.copy()

    def copy_source_settings(self, from_id, to_id):
        """نسخ كافة الإعدادات المخصصة من مصدر إلى آخر."""
        configs = self.get("SOURCE_CONFIGS") or {}
        from_str = str(from_id)
        to_str = str(to_id)
        
        if from_str in configs:
            configs[to_str] = configs[from_str].copy()
            self.set("SOURCE_CONFIGS", configs)
            return True
        return False

settings_manager = SettingsManager()

API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")
PHONE = os.getenv("PHONE_NUMBER", "+967777231155")
BOT_TOKEN = os.getenv("BOT_TOKEN")
STRING_SESSION = os.getenv("STRING_SESSION")

