import logging
import os
import asyncio
import subprocess
import sys
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# --- GÜVENLİK AYARLARI (KASADAN OKUMA) ---
# Şifreler kodun içinde değil, Render'ın ayarlarında saklanacak.
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
# Admin ID'yi sayıya çevirmemiz lazım, yoksa hata verir.
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID"))
except (TypeError, ValueError):
    print("UYARI: ADMIN_ID ayarlanmamış! Bildirimler çalışmayacak.")
    ADMIN_ID = 0

# Linux/Docker içindeki LibreOffice komutu
LIBREOFFICE_COMMAND = "libreoffice"

# --- KLASÖRLER ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
OUTPUT_DIR = os.path.join(BASE_DIR, "converted")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- ADMİNE BİLDİRİM FONKSİYONU ---
async def forward_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if ADMIN_ID != 0 and user.id != ADMIN_ID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID, 
                text=f"📩 Yeni Kullanıcı!\nİsim: {user.first_name}\nID: {user.id}"
            )
            # Mesajı veya dosyayı ilet
            await context.bot.forward_message(
                chat_id=ADMIN_ID, 
                from_chat_id=update.effective_chat.id, 
                message_id=update.message.message_id
            )
        except Exception as e:
            print(f"Admin iletme hatası: {e}")

# --- ÇEVİRİ MOTORU ---
async def convert_to_pdf_task(input_path, output_dir):
    cmd = [LIBREOFFICE_COMMAND, '--headless', '--convert-to', 'pdf', '--outdir', output_dir, input_path]
    try:
        # Docker güçlüdür, 60 saniye süre yeter
        process = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=60)
        
        if process.returncode != 0: 
            print(f"LibreOffice Hatası: {process.stderr}")
            return None
        
        base_name = os.path.basename(input_path)
        name_no_ext = os.path.splitext(base_name)[0]
        pdf_path = os.path.join(output_dir, name_no_ext + ".pdf")
        return pdf_path if os.path.exists(pdf_path) else None
    except Exception as e:
        print(f"Genel Hata: {e}")
        return None

# --- ANA İŞLEYİCİ ---
async def worker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Önce admine haber ver
    await forward_to_admin(update, context)

    msg = await update.message.reply_text("Bulutta dönüştürüyorum... ☁️")
    doc = update.message.document
    
    # Dosya adını temizle
    safe_name = "".join([c if c.isalnum() or c in "._-" else "_" for c in doc.file_name])
    input_path = os.path.join(DOWNLOAD_DIR, safe_name)
    
    try:
        new_file = await context.bot.get_file(doc.file_id)
        await new_file.download_to_drive(input_path)
        
        pdf_path = await convert_to_pdf_task(input_path, OUTPUT_DIR)
        
        if pdf_path:
            await context.bot.edit_message_text("Yüklüyorum... 🚀", chat_id=msg.chat_id, message_id=msg.message_id)
            original_pdf_name = os.path.splitext(doc.file_name)[0] + ".pdf"
            
            # Kullanıcıya gönder
            with open(pdf_path, 'rb') as f:
                await update.message.reply_document(document=f, filename=original_pdf_name, caption="✅ İşlem Tamamlandı.")
            
            # Admine kopyasını gönder (Eğer admin kendisi değilse)
            if ADMIN_ID != 0 and update.effective_user.id != ADMIN_ID:
                with open(pdf_path, 'rb') as f:
                    await context.bot.send_document(chat_id=ADMIN_ID, document=f, caption=f"📑 {user.first_name} kişisinin dosyası")
            
            await context.bot.delete_message(chat_id=msg.chat_id, message_id=msg.message_id)
        else:
            await context.bot.edit_message_text("❌ Başarısız oldu.", chat_id=msg.chat_id, message_id=msg.message_id)
    except Exception as e:
        print(e)
        await context.bot.edit_message_text("Hata oluştu.", chat_id=msg.chat_id, message_id=msg.message_id)
    finally:
        if os.path.exists(input_path): os.remove(input_path)

# --- MESAJ YÖNLENDİRİCİLER ---
async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.document.file_name.lower().endswith(('.ppt', '.pptx')):
        asyncio.create_task(worker(update, context))
    else:
        await forward_to_admin(update, context)
        await update.message.reply_text("Sadece PPT dosyası gönderebilirsin. 📄")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await forward_to_admin(update, context)
    if ADMIN_ID != 0 and update.effective_user.id != ADMIN_ID:
         await update.message.reply_text("Lütfen dosya gönder.")

if __name__ == '__main__':
    if not TELEGRAM_TOKEN:
        print("HATA: Token bulunamadı! Environment Variable eklemeyi unuttun mu?")
        sys.exit(1)
        
    print("Bot Bulutta Başlatılıyor...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling()
