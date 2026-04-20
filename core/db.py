import sqlite3
import os
from config import get_data_path
from datetime import datetime

DB_PATH = get_data_path("index.db")

def init_db():
    """تهيئة قاعدة البيانات وإنشاء الجداول إذا لم تكن موجودة."""
    conn = sqlite3.connect(DB_PATH, timeout=15)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            tag TEXT,
            source TEXT,
            msg_id INTEGER NOT NULL,
            indexed BOOLEAN DEFAULT 0,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def add_file_to_db(name: str, tag: str, source: str, msg_id: int):
    """إضافة سجل ملف جديد لقاعدة البيانات."""
    conn = sqlite3.connect(DB_PATH, timeout=15)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO files (name, tag, source, msg_id)
        VALUES (?, ?, ?, ?)
    ''', (name, tag, source, msg_id))
    conn.commit()
    conn.close()

def get_unindexed_files():
    """جلب كافة الملفات التي لم يتم إدراجها في فهرس بعد."""
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM files WHERE indexed = 0 ORDER BY timestamp ASC')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def mark_as_indexed(ids: list):
    """تحديث الملفات لتحديدها كمؤرشة بمجرد نشر الفهرس."""
    if not ids: return
    conn = sqlite3.connect(DB_PATH, timeout=15)
    cursor = conn.cursor()
    placeholders = ','.join(['?'] * len(ids))
    cursor.execute(f'UPDATE files SET indexed = 1 WHERE id IN ({placeholders})', ids)
    conn.commit()
    conn.close()

def get_files_count():
    """جلب إجمالي عدد الملفات."""
    conn = sqlite3.connect(DB_PATH, timeout=15)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM files')
    count = cursor.fetchone()[0]
    conn.close()
    return count

# تهيئة القاعدة عند الاستيراد
if not os.path.exists(DB_PATH):
    init_db()
