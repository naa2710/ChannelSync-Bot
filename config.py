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
            "ALLOWED_SOURCE_CHAT_IDS": [
                int(x) for x in os.getenv("ALLOWED_SOURCE_CHAT_IDS", "").split(",") if x.strip()
            ],
            "REQUIRE_HASHTAG": os.getenv("REQUIRE_HASHTAG", "false").lower() == "true",
            "REQUIRED_HASHTAG": os.getenv("REQUIRED_HASHTAG", "#نشر"),
            "ADMINS_ONLY": os.getenv("ADMINS_ONLY", "false").lower() == "true",
            "USE_COPY_INSTEAD_OF_FORWARD": os.getenv("USE_COPY_INSTEAD_OF_FORWARD", "true").lower() == "true",
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
            "ENABLE_INDEXING": False,
            "INDEX_THRESHOLD": 50,
            "PENDING_INDEX_ITEMS": [],
            "PENDING_FETCH_REQUESTS": []
        }
        self.settings = self.load_settings()

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
                # التأكد من وجود المجلد إذا كان مساراً فرعياً
                os.makedirs(os.path.dirname(os.path.abspath(self.settings_file)), exist_ok=True)
                with open(self.settings_file, "w", encoding="utf-8") as f:
                    json.dump(self.settings, f, indent=4, ensure_ascii=False)
                
                # استدعاء دالة المزامنة إذا كانت موجودة
                if self.on_change_callback:
                    self.on_change_callback()
            except Exception as e:
                print(f"Error saving settings: {e}")

    def get(self, key):
        # لم نعد بحاجة لـ load_settings في كل مرة لتحسين الأداء
        # الاعتماد على النسخة في الذاكرة المزامنة
        return self.settings.get(key, self.defaults.get(key))

    def set(self, key, value):
        self.settings[key] = value
        self.save_settings()

    def get_all(self):
        return self.settings.copy()

settings_manager = SettingsManager()

API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")
PHONE = os.getenv("PHONE_NUMBER", "+967777231155")
BOT_TOKEN = os.getenv("BOT_TOKEN")
STRING_SESSION = os.getenv("STRING_SESSION")


