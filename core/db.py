import sqlite3
import os
from config import get_data_path

DB_PATH = get_data_path("index.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

def init_db():
    """تهيئة قاعدة البيانات وإنشاء الجداول إذا لم تكن موجودة."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                tag TEXT,
                source TEXT,
                msg_id INTEGER NOT NULL,
                indexed BOOLEAN DEFAULT 0,
                file_size INTEGER,
                file_type TEXT,
                caption TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # التحديث للقواعد القديمة (Migrations)
        cursor.execute("PRAGMA table_info(files)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'file_size' not in columns:
            cursor.execute('ALTER TABLE files ADD COLUMN file_size INTEGER')
        if 'file_type' not in columns:
            cursor.execute('ALTER TABLE files ADD COLUMN file_type TEXT')
        if 'caption' not in columns:
            cursor.execute('ALTER TABLE files ADD COLUMN caption TEXT')
        if 'category' not in columns:
            cursor.execute('ALTER TABLE files ADD COLUMN category TEXT')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_messages (
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                processed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, message_id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_indexed_timestamp ON files(indexed, timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_msg_id ON files(msg_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_tag ON files(tag)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_name ON files(name)')
        conn.commit()

def add_file_to_db(name: str, tag: str, source: str, msg_id: int, file_size: int = None, file_type: str = None, caption: str = None, category: str = "other"):
    """إضافة سجل ملف جديد لقاعدة البيانات."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO files (name, tag, source, msg_id, file_size, file_type, caption, category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name, tag, source, msg_id, file_size, file_type, caption, category))
        conn.commit()

def search_files(query: str, limit: int = 10):
    """البحث عن الملفات بواسطة الاسم أو الوصف."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        search_query = f"%{query}%"
        cursor.execute('''
            SELECT * FROM files 
            WHERE name LIKE ? OR caption LIKE ? OR tag LIKE ?
            ORDER BY timestamp DESC LIMIT ?
        ''', (search_query, search_query, search_query, limit))
        rows = cursor.fetchall()
    return [dict(row) for row in rows]

def get_unindexed_files():
    """جلب كافة الملفات التي لم يتم إدراجها في فهرس بعد."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM files WHERE indexed = 0 ORDER BY timestamp ASC')
        rows = cursor.fetchall()
    return [dict(row) for row in rows]

def mark_as_indexed(ids: list):
    """تحديث الملفات لتحديدها كمؤرشة بمجرد نشر الفهرس."""
    if not ids:
        return
    with get_connection() as conn:
        cursor = conn.cursor()
        placeholders = ','.join(['?'] * len(ids))
        cursor.execute(f'UPDATE files SET indexed = 1 WHERE id IN ({placeholders})', ids)
        conn.commit()

def get_files_count():
    """جلب إجمالي عدد الملفات."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM files')
        count = cursor.fetchone()[0]
    return count


def get_category_group_stats():
    """جلب إحصائيات لكل فئة (نوع)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT category, COUNT(*) as count 
            FROM files 
            WHERE category IS NOT NULL
            GROUP BY category 
            ORDER BY count DESC
        ''')
        return cursor.fetchall()

def get_source_group_stats():
    """جلب إحصائيات لكل مصدر."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT source, COUNT(*) as count 
            FROM files 
            GROUP BY source 
            ORDER BY count DESC
        ''')
        return cursor.fetchall()

def get_tag_group_stats():
    """جلب إحصائيات لكل هاشتاج (تصنيف)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT tag, COUNT(*) as count 
            FROM files 
            GROUP BY tag 
            ORDER BY count DESC
        ''')
        return cursor.fetchall()

def get_tags_list():
    """جلب قائمة بكافة الهاشتاقات (التصنيفات) الفريدة."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT tag FROM files WHERE tag IS NOT NULL ORDER BY tag ASC')
        return [row[0] for row in cursor.fetchall()]

def get_categories_list():
    """جلب قائمة بكافة الفئات (النوع) المتوفرة."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT category FROM files WHERE category IS NOT NULL ORDER BY category ASC')
        return [row[0] for row in cursor.fetchall()]

def get_sources_list():
    """جلب قائمة بكافة المصادر الفريدة."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT source FROM files WHERE source IS NOT NULL ORDER BY source ASC')
        return [row[0] for row in cursor.fetchall()]

def get_files_by_tag(tag: str, limit: int = 50, offset: int = 0):
    """جلب الملفات التابعة لتصنيف معين."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM files 
            WHERE tag = ? 
            ORDER BY timestamp DESC 
            LIMIT ? OFFSET ?
        ''', (tag, limit, offset))
        return [dict(row) for row in rows] if (rows := cursor.fetchall()) else []

def get_files_by_category(category: str, limit: int = 50, offset: int = 0):
    """جلب الملفات التابعة لفئة معينة (كتب، فيديو، الخ)."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM files 
            WHERE category = ? 
            ORDER BY timestamp DESC 
            LIMIT ? OFFSET ?
        ''', (category, limit, offset))
        return [dict(row) for row in rows] if (rows := cursor.fetchall()) else []

def get_files_by_source(source: str, limit: int = 50, offset: int = 0):
    """جلب الملفات القادمة من مصدر معين."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM files 
            WHERE source = ? 
            ORDER BY timestamp DESC 
            LIMIT ? OFFSET ?
        ''', (source, limit, offset))
        return [dict(row) for row in rows] if (rows := cursor.fetchall()) else []

def get_all_files_paginated(limit: int = 20, offset: int = 0, sort_by: str = "timestamp"):
    """جلب كافة الملفات مع دعم التقسيم والفرز لواجهة الويب."""
    valid_sorts = ["timestamp", "name", "file_size"]
    if sort_by not in valid_sorts: sort_by = "timestamp"
    
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(f'''
            SELECT * FROM files 
            ORDER BY {sort_by} DESC 
            LIMIT ? OFFSET ?
        ''', (limit, offset))
        return [dict(row) for row in rows] if (rows := cursor.fetchall()) else []

def was_message_processed(chat_id: int, message_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT 1 FROM processed_messages WHERE chat_id = ? AND message_id = ? LIMIT 1',
            (chat_id, message_id)
        )
        return cursor.fetchone() is not None

def mark_message_processed(chat_id: int, message_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT OR IGNORE INTO processed_messages (chat_id, message_id) VALUES (?, ?)',
            (chat_id, message_id)
        )
        conn.commit()

# تهيئة القاعدة عند الاستيراد
init_db()
