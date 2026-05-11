import subprocess
import sys
import time

from core.logger import get_logger
from core.db import get_all_files_paginated, get_files_count, get_category_group_stats, get_files_by_category
import urllib.parse

import psutil
import os

logger = get_logger("RUN")

def cleanup_zombies():
    """البحث عن عمليات البوت العالقة وقتلها لضمان عدم قفل قاعدة البيانات."""
    current_pid = os.getpid()
    logger.info("جاري فحص وتنظيف العمليات العالقة...")
    
    deleted_count = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # نحن نبحث عن عمليات python التي ليست العملية الحالية
            if proc.info['pid'] == current_pid:
                continue
                
            if 'python' in proc.info['name'].lower():
                cmdline = proc.info.get('cmdline') or []
                # إذا كانت العملية تشغل bot.py أو user_bot.py في هذا المجلد
                if any(script in ' '.join(cmdline) for script in ["bot.py", "user_bot.py", "run.py"]):
                    logger.info(f"إغلاق عملية عالقة: {proc.info['pid']}")
                    proc.kill()
                    deleted_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    if deleted_count > 0:
        logger.info(f"تم تنظيف {deleted_count} عمليات عالقة بنجاح.")
        time.sleep(1)
    else:
        logger.info("لم يتم العثور على عمليات عالقة.")

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

class GalleryHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_path.query)
        cat_filter = query_params.get('cat', [None])[0]
        
        # جلب البيانات
        if cat_filter:
            files = get_files_by_category(cat_filter, limit=50)
        else:
            files = get_all_files_paginated(limit=50)
            
        count = get_files_count()
        cat_stats = get_category_group_stats()

        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()

        html = self.generate_html(files, count, cat_stats, cat_filter)
        self.wfile.write(html.encode('utf-8'))

    def generate_html(self, files, total_count, cat_stats, active_cat):
        # توليد شريط التصنيفات
        cat_buttons = f'<a href="/" class="cat-btn {"active" if not active_cat else ""}">جميع الملفات</a>'
        for cat, c_count in cat_stats:
            active_class = "active" if active_cat == cat else ""
            cat_buttons += f'<a href="/?cat={urllib.parse.quote(cat)}" class="cat-btn {active_class}">{cat} ({c_count})</a>'

        cards = ""
        for f in files:
            size_mb = round(f['file_size'] / (1024*1024), 2) if f.get('file_size') else 0
            target_id = os.getenv("TARGET_CHANNEL_ID", "-1001234567890")
            clean_id = str(target_id).replace("-100", "")
            link = f"https://t.me/c/{clean_id}/{f['msg_id']}"
            
            cards += f"""
            <div class="card">
                <div class="icon">{"🎬" if f['file_type'] == "video" else "📚" if f['category'] == "📚 المكتبة" else "📄"}</div>
                <div class="name">{f['name']}</div>
                <div class="meta">
                    <span>📦 {size_mb} MB</span>
                    <span>📂 {f['category'] or 'أخرى'}</span>
                </div>
                <div class="tag">🏷 {f['tag'] or '#عام'}</div>
                <a href="{link}" target="_blank" class="btn">فتح في تليجرام</a>
            </div>
            """

        return f"""
        <!DOCTYPE html>
        <html lang="ar" dir="rtl">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>مكتبة القناة الذكية</title>
            <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;700&display=swap" rel="stylesheet">
            <style>
                body {{ font-family: 'Tajawal', sans-serif; background: #0f172a; color: white; margin: 0; padding: 20px; }}
                .container {{ max-width: 1200px; margin: 0 auto; }}
                header {{ text-align: center; margin-bottom: 30px; padding: 40px; background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border-radius: 20px; border: 1px solid #334155; }}
                h1 {{ margin: 0; color: #38bdf8; font-size: 2.5em; }}
                .stats {{ color: #94a3b8; margin-top: 10px; }}
                .filter-bar {{ display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 30px; justify-content: center; }}
                .cat-btn {{ background: #1e293b; color: #94a3b8; text-decoration: none; padding: 10px 20px; border-radius: 30px; border: 1px solid #334155; transition: 0.3s; }}
                .cat-btn:hover, .cat-btn.active {{ background: #38bdf8; color: #0f172a; border-color: #38bdf8; }}
                .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; }}
                .card {{ background: #1e293b; border-radius: 15px; padding: 20px; border: 1px solid #334155; transition: transform 0.2s; position: relative; }}
                .card:hover {{ transform: translateY(-5px); border-color: #38bdf8; }}
                .icon {{ font-size: 40px; margin-bottom: 15px; }}
                .name {{ font-weight: bold; margin-bottom: 10px; color: #f1f5f9; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; height: 3em; }}
                .meta {{ font-size: 0.85em; color: #94a3b8; display: flex; justify-content: space-between; margin-bottom: 10px; padding-bottom: 10px; border-bottom: 1px solid #334155; }}
                .tag {{ font-size: 0.8em; color: #38bdf8; margin-bottom: 15px; }}
                .btn {{ display: block; text-align: center; background: #0284c7; color: white; text-decoration: none; padding: 10px; border-radius: 8px; font-weight: bold; transition: background 0.3s; }}
                .btn:hover {{ background: #0369a1; }}
                @media (max-width: 600px) {{ .grid {{ grid-template-columns: 1fr; }} .filter-bar {{ flex-direction: column; }} }}
            </style>
        </head>
        <body>
            <div class="container">
                <header>
                    <h1>📚 مكتبة القناة الذكية</h1>
                    <div class="stats">إجمالي الملفات المؤرشفة: {total_count} ملف</div>
                </header>
                <div class="filter-bar">
                    {cat_buttons}
                </div>
                <div class="grid">
                    {cards}
                </div>
            </div>
        </body>
        </html>
        """

    def log_message(self, format, *args):
        return # Disable logging

def start_gallery_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), GalleryHandler)
    logger.info(f"Gallery Web Server started on port {port}")
    server.serve_forever()

def run_bots():
    cleanup_zombies()
    
    # تشغيل خادم المعرض في خيط منفصل
    threading.Thread(target=start_gallery_server, daemon=True).start()
    
    logger.info("جاري بدء تشغيل النظام الكامل الشامل (Launcher)...")
    
    scripts = {
        "user_bot.py": None
    }
    
    try:
        while True:
            for script, proc in scripts.items():
                if proc is None or proc.poll() is not None:
                    if proc is not None:
                        logger.error(f"⚠️ العملية {script} (PID: {proc.pid}) توقفت! جاري إعادة التشغيل...")
                        time.sleep(2)
                    
                    logger.info(f"🚀 بدء تشغيل {script}...")
                    scripts[script] = subprocess.Popen([sys.executable, script])
            
            time.sleep(5)
            
    except KeyboardInterrupt:
        logger.info("\nجاري إغلاق جميع العمليات بأمان...")
        for proc in scripts.values():
            if proc:
                proc.terminate()
                proc.wait()
        logger.info("تم تفريغ النظام وإغلاقه.")

if __name__ == "__main__":
    run_bots()
