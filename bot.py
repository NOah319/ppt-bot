import logging
import os
import asyncio
import subprocess
import sys
import threading
import gc
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# --- FLASK (UYANIK KALMA) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot Kuyruk Sistemiyle Calisiyor! 🤖"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- AYARLAR ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID"))
except:
    ADMIN_ID = 0

LIBREOFFICE_COMMAND = "libreoffice"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
OUTPUT_DIR = os.path.join(BASE_DIR, "converted")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- KUYRUK SİSTEMİ (EN ÖNEMLİ KISIM) ---
# Aynı anda sadece 1 dosya işlensin (Semaphore(1))
conversion_lock = asyncio.Semaphore(1)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

async def forward_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if ADMIN_ID != 0 and user.id != ADMIN_ID:
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"📩 İşlem: {user.first_name}")
        except: pass

async def convert_to_pdf_task(input_path, output_dir):
    cmd = [LIBREOFFICE_COMMAND, '--headless', '--convert-to', 'pdf', '--outdir', output_dir, input_path]
    try:
        process = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=90)
        
        # RAM Temizliği yapalım (Render Free için önemli)
        gc.collect()
        
        if process.returncode != 0: return None
        base_name = os.path.basename(input_path)
        name_no_ext = os.path.splitext(base_name)[0]
        pdf_path = os.path.join(output_dir, name_no_ext + ".pdf")
        return pdf_path if os.path.exists(pdf_path) else None
    except: return None

async def worker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await forward_to_admin(update, context)
    
    doc = update.message.document
    msg = await update.message.reply_text("📥 Dosya alındı. Kuyruk durumu kontrol ediliyor...")
    
    # --- KUYRUK BAŞLANGICI ---
    # Eğer başkası işlem yapıyorsa burada bekler
    async with conversion_lock:
        try:
            await context.bot.edit_message_text("⚙️ İşlem sırası sizde! Dönüştürülüyor...", chat_id=msg.chat_id, message_id=msg.message_id)
            
            safe_name = "".join([c if c.isalnum() or c in "._-" else "_" for c in doc.file_name])
            input_path = os.path.join(DOWNLOAD_DIR, safe_name)
            
            # Dosyayı indir
            new_file = await context.bot.get_file(doc.file_id)
            await new_file.download_to_drive(input_path)
            
            # Çevir
            pdf_path = await convert_to_pdf_task(input_path, OUTPUT_DIR)
            
            if pdf_path:
                await context.bot.edit_message_text("🚀 Yükleniyor...", chat_id=msg.chat_id, message_id=msg.message_id)
                original_pdf_name = os.path.splitext(doc.file_name)[0] + ".pdf"
                
                with open(pdf_path, 'rb') as f:
                    await update.message.reply_document(document=f, filename=original_pdf_name, caption="✅ İşlem Tamamlandı.")
                
                if ADMIN_ID != 0 and update.effective_user.id != ADMIN_ID:
                    with open(pdf_path, 'rb') as f:
                        await context.bot.send_document(chat_id=ADMIN_ID, document=f, caption="📑 Kopya")
                
                await context.bot.delete_message(chat_id=msg.chat_id, message_id=msg.message_id)
            else:
                await context.bot.edit_message_text("❌ Dönüştürme başarısız (Dosya bozuk olabilir).", chat_id=msg.chat_id, message_id=msg.message_id)

        except Exception as e:
            print(e)
            await context.bot.edit_message_text("⚠️ Bir hata oluştu.", chat_id=msg.chat_id, message_id=msg.message_id)
        finally:
            if os.path.exists(input_path): os.remove(input_path)
    # --- KUYRUK SONU (Sıradaki kişiye geçer) ---

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.document.file_name.lower().endswith(('.ppt', '.pptx')):
        # task olarak başlatıyoruz ki bot donmasın, diğer mesajları alabilsin
        asyncio.create_task(worker(update, context))
    else:
        await update.message.reply_text("Sadece PPT atabilirsin.")

if __name__ == '__main__':
    if not TELEGRAM_TOKEN: sys.exit(1)

    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    print("Kuyruk Sistemli Bot Başlatılıyor...")
    app_bot = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app_bot.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    app_bot.run_polling()
