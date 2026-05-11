from collections import OrderedDict
from threading import Lock
from core.db import mark_message_processed, was_message_processed

class DedupManager:
    """إدارة منع التكرار باستخدام ذاكرة مؤقتة مع تخزين دائم في القاعدة."""
    def __init__(self, max_size=5000):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.lock = Lock()

    def is_duplicate(self, chat_id: int, message_id: int) -> bool:
        """يتحقق مما إذا كانت الرسالة مكررة أو تمت معالجتها سابقاً."""
        key = f"{chat_id}_{message_id}"
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return True

        if was_message_processed(chat_id, message_id):
            with self.lock:
                self.cache[key] = True
                if len(self.cache) > self.max_size:
                    self.cache.popitem(last=False)
            return True

        return False

    def mark_processed(self, chat_id: int, message_id: int):
        """يسجل الرسالة كـ معالجة لمنع تكرارها لاحقاً."""
        key = f"{chat_id}_{message_id}"
        mark_message_processed(chat_id, message_id)
        with self.lock:
            self.cache[key] = True
            if len(self.cache) > self.max_size:
                self.cache.popitem(last=False)

# جلب نسخة عالمية يتم استخدامها من قبل جميع الملفات
dedup_manager = DedupManager()
