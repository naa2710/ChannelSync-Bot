import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message

from config import API_ID, API_HASH, PHONE, STRING_SESSION, settings_manager
from core.sources import is_allowed_chat, add_source
from core.transfer import transfer_message, is_valid_message_type, message_has_required_hashtag, transfer_last_n_files
from core.resolver import clean_identifier
from core.index import generate_master_hub
from core.group_index import rebuild_full_group_index, update_stats_message
from core.dedup import dedup_manager
from core.logger import get_logger
from core.sync import restore_backups, safe_sync_backup, upload_backups

logger = get_logger("USERBOT")

# دالة وسيطة لربط النظام المتزامن (SettingsManager) مع النظام غير المتزامن (Async)
def sync_backup_wrapper():
    if app.is_connected:
        try:
            # استخدام loop الحالي لتشغيل عملية الرفع في الخلفية
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(safe_sync_backup(app))
        except Exception as e:
            logger.debug(f"فشل جدولة المزامنة: {e}")

# ربط الكولباك بمدير الإعدادات
settings_manager.on_change_callback = sync_backup_wrapper

app = Client(
    "channelsync_userbot",
    api_id=API_ID,
    api_hash=API_HASH,
    phone_number=PHONE,
    session_string=STRING_SESSION,
    workdir="."
)

# =========================
# معالجات الأوامر (الإدارة عبر الرسائل المحفوظة)
# =========================
@app.on_message(filters.command(["ping", "start"], prefixes=[".", "/"]) & filters.me)
async def ping_command(client: Client, message: Message):
    await message.edit_text("✅ بونج! البوت متصل والجهة الناقلة تعمل بكفاءة.")

@app.on_message(filters.command(["join", "انضم"], prefixes=[".", "/"]) & filters.me)
async def join_command(client: Client, message: Message):
    if len(message.command) < 2:
        await message.edit_text("❌ يرجى إرسال المعرف/الرابط. مثال: `/join @channel`")
        return
    
    chat_identifier = message.command[1]
    msg = await message.edit_text(f"⏳ جاري الانضمام إلى: `{chat_identifier}`...")
    
    try:
        chat = await client.join_chat(chat_identifier)
        if add_source(chat.id, chat.title):
            await msg.edit_text(f"✅ تم الانضمام والاعتماد المباشر للمصدر:\n{chat.title} (`{chat.id}`)")
        else:
            await msg.edit_text(f"✅ تم الانضمام (المصدر معتمد مسبقاً): {chat.title}")
    except Exception as e:
        await msg.edit_text(f"❌ فشل الانضمام: {str(e)}")

@app.on_message(filters.command(["last5", "اخر5"], prefixes=[".", "/"]) & filters.me)
async def last5_command(client: Client, message: Message):
    """جلب ونقل آخر 5 ملفات من المصدر المحدد."""
    if len(message.command) < 2:
        await message.edit_text("❌ يرجى تحديد المصدر. مثال: `/last5 @channel`")
        return
    
    source = message.command[1]
    msg = await message.edit_text(f"⏳ جاري البحث عن آخر 5 رسائل في `{source}` وتصديرها...")
    try:
        chat = await client.get_chat(source)
        await transfer_last_n_files(client, chat.id, limit=int(settings_manager.get("MAX_LAST_MESSAGES") or 5))
        await msg.edit_text(f"✅ اكتملت محاولة نقل آخر الرسائل من {chat.title}.")
    except Exception as e:
        await msg.edit_text(f"❌ حدث خطأ: {e}")

# =========================
# معالجات نقل الرسائل التلقائي (المحرك الرئيسي)
# =========================

@app.on_message(filters.all, group=-1)
async def debug_all_messages(client: Client, message: Message):
    if settings_manager.get("DEBUG_ALL_MESSAGES"):
        logger.info(f"DEBUG: رسالة واردة في المحادثة {message.chat.id} | نوعها: {message.chat.type}")

@app.on_message(filters.all)
async def auto_transfer_router(client: Client, message: Message):
    if not settings_manager.get("IS_BOT_ACTIVE"):
        return

    chat_id = message.chat.id
    
    # 1. التحقق من أن المصدر معتمد
    if not is_allowed_chat(chat_id):
        # سنقوم بتسجيل هذا للمساعدة في تشخيص المصادر الناقصة
        logger.info(f"تلقيت رسالة من مصدر غير معتمد حالياً ({chat_id} - {message.chat.title}).")
        logger.info("إذا كنت تريد النقل من هذا المصدر، يرجى إضافته عبر لوحة تحكم البوت.")
        return

    logger.info(f"تم رصد رسالة جديدة ({message.id}) من مصدر معتمد ({chat_id})...")

    # 2. التحقق من التكرار
    if dedup_manager.is_duplicate(chat_id, message.id):
        logger.info(f"الرسالة ({message.id}) مكررة، سيتم تخطيها.")
        return

    # 3. التحقق من الهاشتاق
    if not message_has_required_hashtag(message.text, message.caption):
        logger.info(f"الرسالة ({message.id}) لا تحتوي على الهاشتاق المطلوب.")
        return

    # 4. التحقق من نوع الرسالة (صور، ملفات، نصوص طويلة الخ)
    if not is_valid_message_type(message, chat_id):
        logger.info(f"الرسالة ({message.id}) غير مطابقة لشروط النوع المسموح بالنقل.")
        return

    # 4.5 التحقق من القائمة السوداء
    from core.transfer import is_blacklisted
    if is_blacklisted(message):
        logger.info(f"الرسالة ({message.id}) محظورة لوجود كلمات في القائمة السوداء.")
        return

    # 5. محاولة النقل
    try:
        await transfer_message(client, message)
        # تسجيل المعالجة لمنع التكرار مستقبلاً
        dedup_manager.mark_processed(chat_id, message.id)
        logger.info(f"✅ نٌقلت بنجاح من {chat_id} (Message ID: {message.id})")
    except Exception as e:
        logger.error(f"❌ فشل النقل من {chat_id}: {e}")

# =========================
# معالج الذكاء والخلفية (Auto-Resolve & Join & Transfer)
# =========================
async def monitor_pending_joins():
    while True:
        try:
            # === معالجة أمر السحب اليدوي الجماعي ===
            if settings_manager.get("TRIGGER_FETCH_ALL"):
                settings_manager.set("TRIGGER_FETCH_ALL", False)
                sources = settings_manager.get("ALLOWED_SOURCE_CHAT_IDS") or []
                limit = int(settings_manager.get("MAX_LAST_MESSAGES") or 5)
                logger.info(f"بدء عملية السحب الجماعي التلقائي لآخر {limit} ملفات من {len(sources)} مصدر...")
                
                success_count = 0
                for src in sources:
                    try:
                        await transfer_last_n_files(app, src, limit=limit)
                        success_count += 1
                        # إضافة تأخير بسيط بين كل مصدر وآخر لتجنب الضغط
                        await asyncio.sleep(3) 
                    except Exception as e:
                        logger.error(f"خطأ أثناء سحب ملفات من مصدر {src}: {e}")
                try:
                    await app.send_message("me", f"✅ اكتملت عملية السحب الجماعي السريع لآخر {limit} ملفات من {success_count} مصدر معتمد.")
                except Exception:
                    pass

            # === معالجة تحديث بوابة الملاحة المركزية (Hub) ===
            if settings_manager.get("TRIGGER_HUB_UPDATE"):
                settings_manager.set("TRIGGER_HUB_UPDATE", False)
                target_chat_id = settings_manager.get("TARGET_CHANNEL_ID")
                logger.info("جاري تحديث بوابة الملاحة المركزية...")
                await generate_master_hub(app, target_chat_id)
                try:
                    await app.send_message("me", "✅ تم تحديث بوابة الملاحة المركزية (Hub) في القناة بنجاح.")
                except Exception:
                    pass

            # === معالجة إعادة بناء فهرس المجموعة التفاعلية ===
            if settings_manager.get("TRIGGER_REBUILD_GROUP_INDEX"):
                settings_manager.set("TRIGGER_REBUILD_GROUP_INDEX", False)
                logger.info("جاري إعادة بناء فهرس المجموعة التفاعلية...")
                await rebuild_full_group_index(app)
                try:
                    await app.send_message("me", "✅ تمت إعادة بناء فهرس المجموعة التفاعلية بنجاح ✅")
                except Exception:
                    pass

            # === معالجة طابور الانضمام والمصادر الجديدة ===
            pending = settings_manager.get("PENDING_JOINS")
            if pending and len(pending) > 0:
                target_raw = pending[0]
                logger.info(f"عثرت على مصدر جديد للمعالجة: {target_raw}")
                
                # تطهير المعرف باستخدام المحرك الذكي
                target_identifier = clean_identifier(target_raw)
                chat = None

                # 1. Try to get chat (if it's public or we're already a member)
                try:
                    logger.info("Attempting get_chat...")
                    chat = await app.get_chat(target_identifier)
                    logger.info("get_chat successful.")
                except Exception as e:
                    logger.info(f"get_chat failed: {e}. Attempting join_chat...")
                    # 2. Try to join chat (if it's a join link or we are not a member)
                    try:
                        chat = await app.join_chat(target_identifier)
                        logger.info("join_chat successful.")
                    except Exception as e2:
                        logger.error(f"فشل الانضمام لـ {target_raw}: {e2}")
                        try:
                            await app.send_message("me", f"❌ فشل الدخول للمصدر `{target_raw}`:\n{e2}")
                        except Exception:
                            pass
                
                # 3. If successfully resolved/joined
                if chat:
                    logger.info(f"Chat resolved. Adding to sources: {chat.id}")
                    if add_source(chat.id, chat.title):
                        logger.info(f"تم الاعتماد المباشر للمصدر: {chat.title}")
                        try:
                            await app.send_message("me", f"✅ تم الاعتماد المباشر للمصدر: **{chat.title}**\nسيتم سحب آخر الملفات منه الآن...")
                        except Exception:
                            pass
                        
                        # 4. نقل آخر 5 ملفات تلقائياً
                        try:
                            logger.info(f"Starting transfer sequence for last files...")
                            limit = int(settings_manager.get("MAX_LAST_MESSAGES") or 5)
                            await transfer_last_n_files(app, chat.id, limit=limit)
                            logger.info(f"Transfer sequence finished.")
                            await asyncio.sleep(2) # تأخير بسيط بعد الانضمام والنقل
                            try:
                                await app.send_message("me", f"✅ تم سحب آخر {limit} ملفات متأخرة بنجاح من: **{chat.title}**")
                            except Exception:
                                pass
                        except Exception as e:
                            logger.error(f"فشل أثناء سحب الملفات المتأخرة من {chat.title}: {e}")
                    else:
                        logger.info("Chat already in sources.")
                        try:
                            await app.send_message("me", f"⚠️ المصدر معتمد مسبقاً: **{chat.title}**")
                        except Exception:
                            pass
                
                # إزالة الرابط من الطابور
                logger.info("Removing from pending queue...")
                pending.pop(0)
                settings_manager.set("PENDING_JOINS", pending)
                logger.info("Done processing this target.")

            # === معالجة طلبات السحب المخصصة (Specific Fetch Requests) ===
            fetch_reqs = settings_manager.get("PENDING_FETCH_REQUESTS") or []
            if fetch_reqs:
                current_req = fetch_reqs[0]
                chat_id = current_req['chat_id']
                limit = current_req['limit']
                
                logger.info(f"بدء تنفيذ طلب سحب مخصص للمصدر {chat_id} بحد {limit} ملفات...")
                try:
                    await transfer_last_n_files(app, chat_id, limit=limit)
                    await app.send_message("me", f"✅ اكتملت عملية السحب المخصصة ({limit} ملف) للمصدر: `{chat_id}`")
                except Exception as e:
                    logger.error(f"فشل السحب المخصص للمصدر {chat_id}: {e}")
                
                # إزالة الطلب المكتمل
                fetch_reqs.pop(0)
                settings_manager.set("PENDING_FETCH_REQUESTS", fetch_reqs)

        except Exception as e:
            logger.exception("خطأ في نظام المعالجة الخلفي")
        
        await asyncio.sleep(5)

# =========================
# التشغيل
# =========================
async def run_userbot():
    if not API_ID or not API_HASH:
        logger.error("بيانات API_ID و API_HASH غير موجودة!")
        return
        
    await app.start()
    
    # 1. استعادة البيانات من السحاب عند بدء التشغيل
    try:
        if await restore_backups(app):
            logger.info("تم استعادة البيانات، جاري إعادة تحميل الإعدادات...")
            settings_manager.settings = settings_manager.load_settings()
    except Exception as e:
        logger.error(f"فشل أثناء عملية الاستعادة الأولية: {e}")

    # 2. تشغيل المهام الخلفية
    asyncio.create_task(monitor_pending_joins())
    
    # 3. مهمة النسخ الاحتياطي الدوري (كل 6 ساعات مثلاً للضمان)
    async def periodic_sync():
        while True:
            await asyncio.sleep(6 * 3600)
            if app.is_connected:
                await upload_backups(app)
    
    asyncio.create_task(periodic_sync())
    
    from pyrogram import idle
    logger.info("تم تشغيل محرك النقل التلقائي (UserBot) وهو الآن يراقب المصادر...")
    await idle()
    await app.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run_userbot())
