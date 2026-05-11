"""ترحيل البيانات: تصنيف السجلات الموجودة في قاعدة البيانات."""
import sqlite3, sys, os
sys.path.insert(0, os.path.dirname(__file__))

from core.categorizer import categorize_by_name

DB_PATH = "index.db"
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("SELECT id, name, file_type, category FROM files WHERE category IS NULL OR category IN ('None', '', 'other')")
rows = cur.fetchall()
print(f"سجلات تحتاج تصنيف: {len(rows)}")

updated = 0
for row_id, name, file_type, old_cat in rows:
    cat = None
    if file_type == "document" or file_type is None:
        cat = categorize_by_name(name or "")
    if not cat:
        type_map = {"video": "مقاطع فيديو", "audio": "صوتيات", "photo": "صور", "text": "نصوص"}
        cat = type_map.get(file_type, "ملفات متنوعة")
    cur.execute("UPDATE files SET category = ? WHERE id = ?", (cat, row_id))
    updated += 1

conn.commit()
print(f"✅ تم تحديث {updated} سجل")

cur.execute("SELECT category, COUNT(*) c FROM files GROUP BY category ORDER BY c DESC")
print("\n=== التوزيع الجديد ===")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")

conn.close()
