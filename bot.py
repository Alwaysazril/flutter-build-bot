import os
import asyncio
import zipfile
import shutil
import requests
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ============ CONFIG ============
BOT_TOKEN = "8671540051:AAEaEoE_6oFAQ0EA1_j9cXqOWEZzM76J1cQ"
OWNER_ID = 5914076434
GITHUB_TOKEN = "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"
GITHUB_USER = "Alwaysazril"
GITHUB_REPO = "flutter-build-bot"
# ================================

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

def is_owner(user_id):
    return user_id == OWNER_ID

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Kamu tidak punya akses!")
        return
    
    text = (
        "🤖 *Flutter Build Bot*\n\n"
        "Kirim file `.zip` project Flutter kamu\n"
        "nanti saya auto build jadi APK!\n\n"
        "📋 *Cara pakai:*\n"
        "1. Zip folder project Flutter kamu\n"
        "2. Kirim file ZIP ke sini\n"
        "3. Tunggu APK dikirim balik\n\n"
        "⚡ Powered by GitHub Actions"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def handle_zip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Kamu tidak punya akses!")
        return

    doc = update.message.document
    if not doc or not doc.file_name.endswith(".zip"):
        await update.message.reply_text("❌ Kirim file .zip project Flutter kamu!")
        return

    # Progress bar awal
    msg = await update.message.reply_text(
        "📦 *Menerima file ZIP...*\n"
        "▓░░░░░░░░░ 10%",
        parse_mode="Markdown"
    )

    # Download ZIP
    file = await context.bot.get_file(doc.file_id)
    zip_path = f"/tmp/{doc.file_name}"
    await file.download_to_drive(zip_path)

    await msg.edit_text(
        "📂 *Membaca project Flutter...*\n"
        "▓▓▓░░░░░░░ 30%",
        parse_mode="Markdown"
    )

    # Upload ke GitHub dan trigger build
    success = await upload_and_trigger(zip_path, doc.file_name, msg)
    
    if not success:
        await msg.edit_text("❌ Gagal upload ke GitHub. Coba lagi!")
        return

    await msg.edit_text(
        "⚙️ *GitHub Actions sedang build APK...*\n"
        "▓▓▓▓▓░░░░░ 50%\n\n"
        "⏳ Estimasi: 5-10 menit",
        parse_mode="Markdown"
    )

    # Tunggu build selesai
    await wait_for_build(msg, update, context)

async def upload_and_trigger(zip_path, filename, msg):
    try:
        import base64
        
        with open(zip_path, "rb") as f:
            content = base64.b64encode(f.read()).decode()

        # Upload zip ke repo GitHub
        url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/upload/{filename}"
        
        # Cek apakah file sudah ada (untuk update)
        check = requests.get(url, headers=HEADERS)
        sha = None
        if check.status_code == 200:
            sha = check.json().get("sha")

        payload = {
            "message": f"Upload {filename} for build",
            "content": content,
        }
        if sha:
            payload["sha"] = sha

        res = requests.put(url, json=payload, headers=HEADERS)
        return res.status_code in [200, 201]
    except Exception as e:
        print(f"Upload error: {e}")
        return False

async def wait_for_build(msg, update, context):
    max_wait = 60  # max 60 x 15 detik = 15 menit
    check_count = 0
    
    progress_steps = [
        ("⚙️ *Menginstall Flutter SDK...*\n▓▓▓▓▓▓░░░░ 60%", 3),
        ("📦 *Menjalankan flutter pub get...*\n▓▓▓▓▓▓▓░░░ 70%", 4),
        ("🔨 *Building APK...*\n▓▓▓▓▓▓▓▓░░ 80%", 5),
        ("🔨 *Build APK hampir selesai...*\n▓▓▓▓▓▓▓▓▓░ 90%", 6),
    ]
    
    step_idx = 0
    step_timer = 0

    while check_count < max_wait:
        await asyncio.sleep(15)
        check_count += 1
        step_timer += 1

        # Update progress message
        if step_idx < len(progress_steps):
            text, threshold = progress_steps[step_idx]
            if step_timer >= threshold:
                try:
                    await msg.edit_text(text, parse_mode="Markdown")
                except:
                    pass
                step_idx += 1

        # Cek apakah APK sudah ada di GitHub releases atau artifacts
        apk_url = await check_apk_ready()
        
        if apk_url:
            await msg.edit_text(
                "✅ *APK Berhasil Dibuild!*\n"
                "▓▓▓▓▓▓▓▓▓▓ 100%\n\n"
                "📥 Sedang mengirim APK...",
                parse_mode="Markdown"
            )
            await send_apk(apk_url, update, context, msg)
            return

    await msg.edit_text(
        "⏰ *Timeout!*\n\n"
        "Build terlalu lama atau gagal.\n"
        "Cek di: github.com/Alwaysazril/flutter-build-bot/actions",
        parse_mode="Markdown"
    )

async def check_apk_ready():
    try:
        # Cek latest release
        url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"
        res = requests.get(url, headers=HEADERS)
        
        if res.status_code == 200:
            release = res.json()
            assets = release.get("assets", [])
            for asset in assets:
                if asset["name"].endswith(".apk"):
                    # Cek apakah release baru (dalam 20 menit terakhir)
                    created_at = asset.get("created_at", "")
                    return asset["browser_download_url"]
        return None
    except:
        return None

async def send_apk(apk_url, update, context, msg):
    try:
        # Download APK
        r = requests.get(apk_url, stream=True)
        apk_path = "/tmp/app-release.apk"
        
        with open(apk_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

        # Kirim APK ke Telegram
        with open(apk_path, "rb") as apk:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=apk,
                filename="app-release.apk",
                caption=(
                    "✅ *Build Sukses!*\n\n"
                    "📱 APK siap diinstall di HP kamu!\n"
                    "🔧 Aktifkan *Unknown Sources* dulu sebelum install."
                ),
                parse_mode="Markdown"
            )
        
        await msg.edit_text("✅ *APK sudah dikirim!*", parse_mode="Markdown")
        
    except Exception as e:
        await msg.edit_text(f"❌ Gagal kirim APK: {str(e)}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    
    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/actions/runs?per_page=1"
    res = requests.get(url, headers=HEADERS)
    
    if res.status_code == 200:
        runs = res.json().get("workflow_runs", [])
        if runs:
            run = runs[0]
            status_map = {
                "completed": "✅ Selesai",
                "in_progress": "⚙️ Sedang berjalan",
                "queued": "⏳ Antrian",
                "failure": "❌ Gagal",
            }
            conclusion_map = {
                "success": "✅ Sukses",
                "failure": "❌ Gagal",
                "cancelled": "🚫 Dibatalkan",
                None: ""
            }
            s = status_map.get(run["status"], run["status"])
            c = conclusion_map.get(run.get("conclusion"), "")
            
            text = (
                f"📊 *Status Build Terakhir*\n\n"
                f"Status: {s} {c}\n"
                f"Nama: `{run['name']}`\n"
                f"[Lihat di GitHub]({run['html_url']})"
            )
            await update.message.reply_text(text, parse_mode="Markdown")
        else:
            await update.message.reply_text("Belum ada build yang berjalan.")
    else:
        await update.message.reply_text("❌ Gagal cek status.")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_zip))
    
    print("🤖 Bot berjalan...")
    app.run_polling()

if __name__ == "__main__":
    main()
