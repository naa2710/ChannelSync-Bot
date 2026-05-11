import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import API_ID, API_HASH, PHONE, STRING_SESSION, ADMIN_IDS, settings_manager
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

from config import API_ID, API_HASH, PHONE, STRING_SESSION, BOT_TOKEN, settings_manager

app = Client(
    "channelsync_userbot",
    api_id=API_ID,
    api_hash=API_HASH,
    phone_number=PHONE,
    session_string=STRING_SESSION,
    workdir="."
)

# إضافة بوت التحكم بنفس المحرك لضمان تجاوز الحجب
bot = Client(
    "channelsync_bot_mtproto",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workdir="."
)

from core.ui import (
    get_main_keyboard, get_sources_keyboard, get_sources_manage_keyboard, 
    get_smart_settings_keyboard, get_stats_keyboard, get_tools_keyboard,
    get_group_keyboard, get_targets_manage_keyboard, get_blacklist_keyboard
)
import core.db as db

# قاموس لتخزين حالات المستخدمين (لعمليات الإدخال مثل إضافة قناة)
user_states = {}

@bot.on_message(filters.command("start") & filters.private)
async def bot_start(client, message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    version = "2.6 (Unified MTProto)"
    text = (
        f"🔘 **لوحة تحكم ChannelSync — {version}**\n\n"
        f"أهلاً بك يا {message.from_user.first_name}!\n"
        f"لقد تم تفعيل النظام الموحد لتجاوز كافة قيود الشبكة.\n\n"
        f"اختر القسم الذي تود إدارته من الأسفل:"
    )
    await message.reply_text(text, reply_markup=get_main_keyboard())

@bot.on_callback_query()
async def on_callback(client, query):
    data = query.data
    user_id = query.from_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ غير مسموح لك.", show_alert=True)
        return

    if data == "menu_main":
        await query.edit_message_text("🔘 **لوحة التحكم الرئيسية:**", reply_markup=get_main_keyboard())
    
    elif data == "menu_sources":
        await query.edit_message_text("📡 **إدارة المصادر والوجهات:**", reply_markup=get_sources_keyboard())
    
    elif data == "menu_stats":
        total = db.get_files_count()
        cat_stats = db.get_category_group_stats()
        stats_text = "\n".join([f"🔸 {cat}: {count} ملف" for cat, count in cat_stats])
        text = f"📊 **إحصائيات النظام:**\n\n🎯 إجمالي الملفات: {total}\n\n**التوزيع:**\n{stats_text}"
        await query.edit_message_text(text, reply_markup=get_stats_keyboard())

    elif data == "menu_smart_settings":
        await query.edit_message_text("⚙️ **الإعدادات الذكية:**", reply_markup=get_smart_settings_keyboard())

    elif data == "menu_library":
        await query.edit_message_text("📚 **المكتبة التفاعلية:**\nيرجى استخدام الأوامر اليدوية للتصفح حالياً أو بوابة الويب.", reply_markup=get_main_keyboard())

    elif data == "menu_tools":
        await query.edit_message_text("🛠 **الأدوات والمساعدة:**", reply_markup=get_tools_keyboard())

    elif data == "menu_group_index":
        await query.edit_message_text("📋 **المجموعة التفاعلية — الفهرس الذكي**", reply_markup=get_group_keyboard())

    elif data == "manage_targets":
        await query.edit_message_text("🎯 **إدارة قنوات الوجهة:**", reply_markup=get_targets_manage_keyboard())

    elif data == "menu_blacklist":
        await query.edit_message_text("🚫 **قائمة الكلمات المحظورة:**", reply_markup=get_blacklist_keyboard())

    elif data == "add_new_target":
        user_states[user_id] = "AWAIT_TARGET_CHANNEL"
        await query.edit_message_text("🎯 **إضافة قناة وجهة:**\nأرسل الآن رابط القناة أو الآيدي الخاص بها:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="manage_targets")]]))

    elif data == "add_source":
        user_states[user_id] = "AWAIT_ADD_SOURCE"
        await query.edit_message_text("➕ **إضافة قناة مصدر جديدة:**\n\nأرسل الآن **معرف القناة** أو **رابطها** أو **يوزرها**:\n(مثال: `@channel` أو `-100...`)", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="menu_sources")]]))

    elif data.startswith("manage_sources_"):
        page = int(data.split("_")[-1])
        await query.edit_message_text("📋 **قائمة المصادر:**", reply_markup=get_sources_manage_keyboard(page))

    elif data.startswith("del_source_"):
        parts = data.split("_")
        chat_id = int(parts[2])
        page = int(parts[3])
        from core.sources import remove_source
        remove_source(chat_id)
        await query.answer("✅ تم حذف المصدر")
        await query.edit_message_reply_markup(reply_markup=get_sources_manage_keyboard(page))

    elif data.startswith("del_target_"):
        tid = data.split("_")[-1]
        targets = settings_manager.get("TARGET_CHANNELS") or {}
        if tid in targets:
            targets.pop(tid)
            settings_manager.set("TARGET_CHANNELS", targets)
            await query.answer("✅ تم حذف الوجهة")
        await query.edit_message_reply_markup(reply_markup=get_targets_manage_keyboard())

    elif data == "trigger_fetch_all":
        settings_manager.set("TRIGGER_FETCH_ALL", True)
        await query.answer("⏳ تم جدولة سحب الملفات في الخلفية!", show_alert=True)

    elif data.startswith("fetch_100_"):
        chat_id = int(data.split("_")[2])
        requests = settings_manager.get("PENDING_FETCH_REQUESTS") or []
        if not any(r['chat_id'] == chat_id for r in requests):
            requests.append({"chat_id": chat_id, "limit": 100})
            settings_manager.set("PENDING_FETCH_REQUESTS", requests)
            await query.answer("⏳ تم جدولة سحب 100 ملف لهذا المصدر!", show_alert=True)
        else:
            await query.answer("⚠️ هناك طلب سحب جاري بالفعل لهذا المصدر.")

    elif data == "edit_header_text":
        user_states[user_id] = "AWAIT_HEADER_TEXT"
        await query.edit_message_text("📝 **تعديل نص الترويسة:**\nأرسل النص الجديد الذي تريده:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="menu_smart_settings")]]))

    elif data == "add_blacklist_word":
        user_states[user_id] = "AWAIT_BLACKLIST_WORD"
        await query.edit_message_text("🚫 **إضافة كلمة محظورة:**\nأرسل الكلمة التي تريد حظرها:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="menu_blacklist")]]))

    elif data.startswith("del_word_"):
        word = data.replace("del_word_", "")
        words = settings_manager.get("BLACKLIST_WORDS") or []
        if word in words:
            words.remove(word)
            settings_manager.set("BLACKLIST_WORDS", words)
            await query.answer(f"✅ تم حذف: {word}")
        await query.edit_message_reply_markup(reply_markup=get_blacklist_keyboard())

    elif data == "grp_rebuild":
        settings_manager.set("TRIGGER_REBUILD_GROUP_INDEX", True)
        await query.answer("⏳ جاري إعادة بناء الفهرس في الخلفية!", show_alert=True)

    elif data == "set_group_id":
        user_states[user_id] = "AWAIT_GROUP_ID"
        await query.edit_message_text("🔗 **ربط مجموعة الفهرس:**\nأرسل معرف المجموعة الجديد:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="menu_group_index")]]))

    elif data.startswith("toggle_"):
        key = data.replace("toggle_", "").upper()
        map_keys = {
            "DOCS_ONLY": "DOCUMENTS_ONLY", 
            "HASHTAG": "REQUIRE_HASHTAG", 
            "ADMINS": "ADMINS_ONLY", 
            "COPY_MODE": "USE_COPY_INSTEAD_OF_FORWARD",
            "ADD_HEADER": "ADD_HEADER",
            "CLEAN_ALL": "DEFAULT_CLEAN_CAPTION"
        }
        real_key = map_keys.get(key, key)
        settings_manager.set(real_key, not settings_manager.get(real_key))
        await query.answer("✅ تم التحديث")
        await query.edit_message_reply_markup(reply_markup=get_smart_settings_keyboard())

    await query.answer()

# معالج النصوص (لحالات الإدخال)
@bot.on_message(filters.private & filters.text)
async def on_text(client, message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS: return
    
    state = user_states.get(user_id)
    if not state: return
    
    text = message.text.strip()
    
    if state == "AWAIT_ADD_SOURCE":
        from core.sources import add_source
        from core.resolver import clean_identifier
        try:
            target = clean_identifier(text)
            chat = await app.get_chat(target)
            if add_source(chat.id, chat.title):
                await message.reply_text(f"✅ تم إضافة المصدر: **{chat.title}**", reply_markup=get_sources_keyboard())
                user_states.pop(user_id)
            else:
                await message.reply_text("⚠️ المصدر مضاف مسبقاً.")
        except Exception as e:
            await message.reply_text(f"❌ خطأ: {e}")

    elif state == "AWAIT_HEADER_TEXT":
        settings_manager.set("HEADER_TEXT", text)
        await message.reply_text("✅ تم تحديث الترويسة بنجاح.", reply_markup=get_smart_settings_keyboard())
        user_states.pop(user_id)

    elif state == "AWAIT_BLACKLIST_WORD":
        words = settings_manager.get("BLACKLIST_WORDS") or []
        if text not in words:
            words.append(text)
            settings_manager.set("BLACKLIST_WORDS", words)
            await message.reply_text(f"✅ تمت إضافة `{text}` للقائمة السوداء.", reply_markup=get_blacklist_keyboard())
        user_states.pop(user_id)

    elif state == "AWAIT_TARGET_CHANNEL":
        from core.resolver import clean_identifier
        target_id = clean_identifier(text)
        if isinstance(target_id, int):
            settings_manager.set("TARGET_CHANNEL_ID", target_id)
            user_states[user_id] = "AWAIT_TARGET_NAME"
            await message.reply_text(f"✅ تم التعرف على الوجهة: `{target_id}`\n\nأرسل الآن **اسماً مستعاراً** لهذه القناة:")
        else:
            await message.reply_text("❌ يرجى إرسال آيدي صحيح (مثال: -100...)")

    elif state == "AWAIT_TARGET_NAME":
        targets = settings_manager.get("TARGET_CHANNELS") or {}
        tid = settings_manager.get("TARGET_CHANNEL_ID")
        targets[str(tid)] = text
        settings_manager.set("TARGET_CHANNELS", targets)
        await message.reply_text(f"✅ تم حفظ الوجهة باسم: **{text}**", reply_markup=get_targets_manage_keyboard())
        user_states.pop(user_id)

    elif state == "AWAIT_GROUP_ID":
        from core.resolver import clean_identifier
        group_id = clean_identifier(text)
        if isinstance(group_id, int):
            settings_manager.set("INDEX_GROUP_ID", group_id)
            await message.reply_text(f"✅ تم ربط مجموعة الفهرس: `{group_id}`", reply_markup=get_group_keyboard())
            user_states.pop(user_id)
        else:
            await message.reply_text("❌ يرجى إرسال آيدي صحيح.")

# =========================
# المحرك الموحد
# =========================
async def start_all():
    await app.start()
    await bot.start()
    
    # 1. استعادة البيانات وتجهيز القنوات
    try:
        if await restore_backups(app):
            settings_manager.settings = settings_manager.load_settings()
    except: pass

    # محاولة "رؤية" قناة الوجهة لتجنب خطأ Peer id invalid
    target_id = settings_manager.get("TARGET_CHANNEL_ID")
    if target_id:
        try:
            await app.get_chat(target_id)
            logger.info(f"✅ تم التعرف على قناة الوجهة: {target_id}")
        except Exception as e:
            logger.warning(f"⚠️ تنبيه: اليوزربوت لا يرى قناة الوجهة ({target_id}). تأكد من أن الحساب عضو فيها. الخطأ: {e}")

    asyncio.create_task(monitor_pending_joins())
    
    logger.info("🚀 تم تشغيل المحرك الموحد (User + Bot) بنجاح!")
    await idle()
    await app.stop()
    await bot.stop()

# =========================
# معالجات الأوامر (الإدارة عبر الرسائل المحفوظة)
# =========================
@app.on_message(filters.command(["ping"], prefixes=[".", "/"]) & filters.me)
async def ping_command(client: Client, message: Message):
    await message.edit_text("✅ المحرك الموحد متصل والجهة الناقلة تعمل بكفاءة.")

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
# التشغيل الموحد (المحرك الجذري)
# =========================
async def run_unified_engine():
    if not API_ID or not API_HASH:
        logger.error("بيانات API_ID و API_HASH غير موجودة!")
        return
        
    logger.info("جاري تشغيل المحرك الموحد...")
    await app.start()
    await bot.start()
    
    # 1. استعادة البيانات من السحاب عند بدء التشغيل
    try:
        from core.sync import restore_backups
        if await restore_backups(app):
            logger.info("تم استعادة البيانات، جاري إعادة تحميل الإعدادات...")
            settings_manager.settings = settings_manager.load_settings()
    except Exception as e:
        logger.error(f"فشل أثناء عملية الاستعادة الأولية: {e}")

    # 2. تشغيل المهام الخلفية
    asyncio.create_task(monitor_pending_joins())
    
    # 3. مهمة النسخ الاحتياطي الدوري
    async def periodic_sync():
        while True:
            await asyncio.sleep(6 * 3600)
            if app.is_connected:
                from core.sync import upload_backups
                await upload_backups(app)
    
    asyncio.create_task(periodic_sync())
    
    from pyrogram import idle
    logger.info("✅ المحرك الموحد (UserBot + Dashboard) يعمل الآن وهو محصن ضد قيود الشبكة.")
    await idle()
    await app.stop()
    await bot.stop()

if __name__ == "__main__":
    from pyrogram import idle
    import asyncio
    import pyrogram.errors
    
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(run_unified_engine())
    except pyrogram.errors.AuthKeyDuplicated:
        print("\n" + "="*50)
        print("❌ CRITICAL ERROR: AUTH_KEY_DUPLICATED")
        print("The session string is already in use by another instance.")
        print("PLEASE STOP YOUR LOCAL BOT AND RESTART THE SPACE.")
        print("="*50 + "\n")
        # الانتظار لمنع تكرار المحاولات السريع جداً في Hugging Face
        import time
        time.sleep(30)
    except Exception as e:
        print(f"❌ FATAL ERROR: {e}")
        import time
        time.sleep(10)
