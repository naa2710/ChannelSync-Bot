"""
group_index.py — فهرس المجموعة الذكي والمنظّم

يبني فهرساً منظماً للملفات (documents فقط) في مجموعة تليجرام.
التنظيم: فئات ذكية بناءً على اسم الملف + فئات ديناميكية للكلمات المكررة 10+ مرات.
"""

import asyncio
import sqlite3
from datetime import datetime, timezone, timedelta

from pyrogram import Client

from config import settings_manager, get_data_path
from core.logger import get_logger
from core.categorizer import categorize_by_name, build_dynamic_categories

logger = get_logger("GROUP_INDEX")

_update_lock = asyncio.Lock()

DB_PATH = get_data_path("index.db")

# الفئة الاحتياطية
FALLBACK_CATEGORY = "📄 ملفات متنوعة"


def _now_str() -> str:
    now = datetime.now(timezone(timedelta(hours=3)))
    return now.strftime("%Y/%m/%d — %H:%M")


def _get_conn():
    import os
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def _channel_link(target_id, msg_id: int) -> str:
    clean_id = str(target_id).replace("-100", "")
    return f"https://t.me/c/{clean_id}/{msg_id}"


# ─── جلب البيانات ───────────────────────────────────────────────────────────

def get_all_documents() -> list:
    """جلب جميع الملفات من النوع document فقط."""
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, name, category, msg_id, file_size, tag
            FROM files
            WHERE file_type = 'document' OR (file_type IS NULL AND name != 'بدون اسم')
            ORDER BY id DESC
        """)
        return [dict(r) for r in cur.fetchall()]


def get_documents_count() -> int:
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM files WHERE file_type='document'")
        return cur.fetchone()[0]


# ─── تصنيف الملفات ────────────────────────────────────────────────────────

def _classify_documents(docs: list) -> dict:
    """
    توزيع الملفات على فئات ذكية:
    1. الكلمات المفتاحية المحددة مسبقاً (KEYWORD_MAP في categorizer.py)
    2. الكلمات المكررة 10+ مرات (فئات ديناميكية)
    3. ما تبقى → "📄 ملفات متنوعة"
    """
    categorized: dict[str, list] = {}
    uncategorized = []

    # المرحلة 1: التصنيف بالكلمات المفتاحية
    for doc in docs:
        name = doc.get("name") or ""
        # استخدام category المحفوظة أولاً
        saved_cat = doc.get("category")
        cat = saved_cat if saved_cat and saved_cat not in (None, "📄 أخرى", "None") else categorize_by_name(name)
        if cat:
            categorized.setdefault(cat, []).append(doc)
        else:
            uncategorized.append(doc)

    # المرحلة 2: الكلمات المكررة 10+ مرات كفئات ديناميكية
    dynamic_cats = build_dynamic_categories(
        [d.get("name", "") for d in uncategorized],
        threshold=10
    )

    remaining = []
    for doc in uncategorized:
        name = doc.get("name") or ""
        assigned = False
        for word, cat_label in sorted(dynamic_cats.items(), key=lambda x: -len(x[0])):
            if word.lower() in name.lower():
                categorized.setdefault(cat_label, []).append(doc)
                assigned = True
                break
        if not assigned:
            remaining.append(doc)

    # المرحلة 3: ما تبقى
    if remaining:
        categorized.setdefault(FALLBACK_CATEGORY, []).extend(remaining)

    return categorized


# ─── بناء نص الرسائل ─────────────────────────────────────────────────────

def _build_category_text(category: str, docs: list, target_id, limit: int = 50) -> str:
    """بناء نص فهرس فئة واحدة — مرتّب أبجدياً، بروابط مباشرة."""
    # أخذ آخر limit ملف (أحدث أولاً)
    shown = docs[:limit]

    # ترتيب أبجدي داخل كل صفحة (اسم تصاعدي)
    shown_sorted = sorted(shown, key=lambda d: (d.get("name") or "").strip().lower())

    lines = [
        f"**{category}**",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"📌 **{len(docs):,}** ملف — يعرض آخر {len(shown_sorted)}:",
        "",
    ]

    for i, doc in enumerate(shown_sorted, 1):
        name = doc.get("name") or "بدون اسم"
        # اختصار الاسم الطويل
        import re
        display = re.sub(r'\.[^.]+$', '', name)  # إزالة الامتداد
        if len(display) > 55:
            display = display[:52] + "…"

        link = _channel_link(target_id, doc["msg_id"])
        lines.append(f"{i}\\. [{display}]({link})")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🕐 آخر تحديث: `{_now_str()}`",
    ]
    return "\n".join(lines)


def _build_index_header(categorized: dict) -> str:
    """رسالة الفهرس الرئيسية — قائمة الفئات مع أعدادها."""
    total = sum(len(v) for v in categorized.values())

    # ترتيب الفئات: الأكثر ملفات أولاً
    sorted_cats = sorted(categorized.items(), key=lambda x: -len(x[1]))

    lines = [
        "📚 **فهرس مكتبة الملفات**",
        "━━━━━━━━━━━━━━━━━━━━",
        f"📁 إجمالي الملفات المفهرسة: **{total:,}**",
        "",
        "**📂 التصنيفات المتاحة:**",
    ]

    for cat, docs in sorted_cats:
        if len(docs) >= 1:
            lines.append(f"  {cat}: `{len(docs):,}` ملف")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🕐 آخر تحديث: `{_now_str()}`",
        "🔍 للبحث: اكتب اسم الملف هنا في المجموعة",
    ]
    return "\n".join(lines)


# ─── الإرسال والتعديل ────────────────────────────────────────────────────

async def _send_or_edit(client: Client, group_id: int, msg_id: int | None, text: str) -> int | None:
    """إرسال رسالة جديدة أو تعديل موجودة."""
    try:
        if msg_id:
            try:
                await client.edit_message_text(
                    chat_id=group_id,
                    message_id=msg_id,
                    text=text,
                    disable_web_page_preview=True,
                )
                return msg_id
            except Exception as e:
                if "MESSAGE_NOT_MODIFIED" in str(e):
                    return msg_id
                logger.warning(f"فشل تعديل رسالة {msg_id}: {e} — إنشاء جديدة")

        sent = await client.send_message(
            chat_id=group_id,
            text=text,
            disable_web_page_preview=True,
        )
        return sent.id

    except Exception as e:
        logger.error(f"فشل إرسال رسالة للمجموعة {group_id}: {e}")
        return msg_id


# ─── الدوال العامة ────────────────────────────────────────────────────────

async def update_single_category(client: Client, category: str):
    """
    تحديث رسالة فئة واحدة فقط بعد كل نقل.
    سريع ولا يُعيق البوت.
    """
    group_id = settings_manager.get("INDEX_GROUP_ID")
    if not group_id:
        return
    if not settings_manager.get("GROUP_AUTO_UPDATE"):
        return

    try:
        # فحص: لا تستخدم نفس القناة كمجموعة
        target = settings_manager.get("TARGET_CHANNEL_ID")
        if str(group_id) == str(target):
            return

        target_id = settings_manager.get("TARGET_CHANNEL_ID")
        msg_ids: dict = settings_manager.get("GROUP_INDEX_MSG_IDS") or {}
        group_id = int(group_id)

        # جلب ملفات هذه الفئة فقط
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, name, category, msg_id, file_size, tag
                FROM files WHERE category = ? AND file_type = 'document'
                ORDER BY id DESC LIMIT 50
            """, (category,))
            docs = [dict(r) for r in cur.fetchall()]

        if not docs:
            return

        text = _build_category_text(category, docs, target_id)
        key = f"cat_{category}"
        old_id = msg_ids.get(key)

        new_id = await _send_or_edit(client, group_id, old_id, text)
        if new_id and new_id != old_id:
            msg_ids[key] = new_id
            settings_manager.set("GROUP_INDEX_MSG_IDS", msg_ids)

    except Exception as e:
        logger.error(f"خطأ في تحديث فئة '{category}': {e}")


async def update_stats_message(client: Client):
    """تحديث رسالة الفهرس الرئيسية (قائمة الفئات)."""
    group_id = settings_manager.get("INDEX_GROUP_ID")
    if not group_id:
        return

    target = settings_manager.get("TARGET_CHANNEL_ID")
    if str(group_id) == str(target):
        return

    try:
        docs = get_all_documents()
        if not docs:
            return

        categorized = _classify_documents(docs)
        text = _build_index_header(categorized)
        msg_ids: dict = settings_manager.get("GROUP_INDEX_MSG_IDS") or {}
        old_id = msg_ids.get("header")

        new_id = await _send_or_edit(client, int(group_id), old_id, text)
        if new_id and new_id != old_id:
            msg_ids["header"] = new_id
            settings_manager.set("GROUP_INDEX_MSG_IDS", msg_ids)
            # تثبيت رسالة الفهرس الرئيسية
            try:
                await client.pin_chat_message(int(group_id), new_id, disable_notification=True)
            except Exception:
                pass

    except Exception as e:
        logger.error(f"خطأ في تحديث رأس الفهرس: {e}")


async def rebuild_full_group_index(client: Client):
    """
    إعادة بناء الفهرس الكامل في المجموعة.
    ينشئ رسالة لكل فئة + رسالة رئيسية مثبتة.
    """
    group_id = settings_manager.get("INDEX_GROUP_ID")
    if not group_id:
        logger.warning("لم يتم تعيين معرف المجموعة (INDEX_GROUP_ID).")
        return

    # فحص: لا تستخدم القناة كمجموعة
    target = settings_manager.get("TARGET_CHANNEL_ID")
    if str(group_id) == str(target):
        logger.error("❌ INDEX_GROUP_ID = TARGET_CHANNEL_ID — يجب أن تكون المجموعة مختلفة عن القناة!")
        return

    async with _update_lock:
        logger.info(f"⏳ بدء إعادة بناء فهرس المجموعة {group_id}...")
        group_id = int(group_id)
        target_id = settings_manager.get("TARGET_CHANNEL_ID")
        msg_ids: dict = settings_manager.get("GROUP_INDEX_MSG_IDS") or {}

        # 1. جلب وتصنيف جميع الملفات
        docs = get_all_documents()
        if not docs:
            logger.info("لا توجد ملفات مفهرسة بعد.")
            return

        categorized = _classify_documents(docs)

        # 2. رسالة رأس الفهرس (مثبتة)
        header_text = _build_index_header(categorized)
        old_header_id = msg_ids.get("header")
        new_header_id = await _send_or_edit(client, group_id, old_header_id, header_text)
        if new_header_id:
            msg_ids["header"] = new_header_id
            if new_header_id != old_header_id:
                try:
                    await client.pin_chat_message(group_id, new_header_id, disable_notification=True)
                except Exception:
                    pass
        settings_manager.set("GROUP_INDEX_MSG_IDS", msg_ids)
        await asyncio.sleep(2)

        # 3. رسالة لكل فئة (الأكثر ملفات أولاً، الفئات الصغيرة تُدمج)
        sorted_cats = sorted(categorized.items(), key=lambda x: -len(x[1]))

        for cat, cat_docs in sorted_cats:
            if len(cat_docs) < 1:
                continue  # تخطي الفئات الفارغة

            text = _build_category_text(cat, cat_docs, target_id)
            key = f"cat_{cat}"
            old_id = msg_ids.get(key)
            new_id = await _send_or_edit(client, group_id, old_id, text)

            if new_id:
                msg_ids[key] = new_id

            settings_manager.set("GROUP_INDEX_MSG_IDS", msg_ids)
            await asyncio.sleep(2.5)  # تأخير لتفادي الحظر

        logger.info(f"✅ اكتمل بناء الفهرس: {len(categorized)} فئة — {len(docs)} ملف")
