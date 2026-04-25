import os
import asyncio
import requests
import base64
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ============ CONFIG ============
BOT_TOKEN = "8434117840:AAGyQrdg6U8_kVv8W5PIwfc6azxMJahDpfg"
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
        await update.message.reply_text("Kamu tidak punya akses!")
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
        await update.message.reply_text("Kamu tidak punya akses!")
        return

    doc = update.message.document
    if not doc or not doc.file_name.endswith(".zip"):
        await update.message.reply_text("Kirim file .zip project Flutter kamu!")
        return

    msg = await update.message.reply_text(
        "📦 *Menerima file ZIP...*\n"
        "▓░░░░░░░░░ 10%",
        parse_mode="Markdown"
    )

    try:
        # Download ZIP ke /tmp
        file = await context.bot.get_file(doc.file_id)
        zip_path = f"/tmp/flutter_build.zip"
        await file.download_to_drive(zip_path)

        await msg.edit_text(
            "📤 *Mengupload ke GitHub...*\n"
            "▓▓▓░░░░░░░ 30%",
            parse_mode="Markdown"
        )

        # Baca dan encode file
        with open(zip_path, "rb") as f:
            content = base64.b64encode(f.read()).decode()

        filename = doc.file_name
        url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/upload/{filename}"

        # Cek apakah file sudah ada
        check = requests.get(url, headers=HEADERS)
        sha = None
        if check.status_code == 200:
            sha = check.json().get("sha")

        payload = {
            "message": f"Build: {filename}",
            "content": content,
        }
        if sha:
            payload["sha"] = sha

        await msg.edit_text(
            "📤 *Upload ke GitHub...*\n"
            "▓▓▓▓▓░░░░░ 50%\n\n"
            "⏳ Sabar ya, file sedang diupload...",
            parse_mode="Markdown"
        )

        res = requests.put(url, json=payload, headers=HEADERS, timeout=120)

        if res.status_code not in [200, 201]:
            await msg.edit_text(
                f"❌ Gagal upload ke GitHub!\n"
                f"Error: {res.status_code}\n{res.text[:200]}"
            )
            return

        await msg.edit_text(
            "✅ *Upload berhasil!*\n"
            "▓▓▓▓▓▓░░░░ 60%\n\n"
            "⚙️ GitHub Actions sedang build APK...\n"
            "⏳ Estimasi: 5-10 menit",
            parse_mode="Markdown"
        )

        # Tunggu build selesai
        await tunggu_build(msg, update, context)

    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)[:300]}")

async def tunggu_build(msg, update, context):
    steps = [
        ("⚙️ *Install Flutter SDK...*\n▓▓▓▓▓▓▓░░░ 70%", 4),
        ("📦 *Flutter pub get...*\n▓▓▓▓▓▓▓▓░░ 80%", 4),
        ("🔨 *Building APK...*\n▓▓▓▓▓▓▓▓▓░ 90%", 5),
    ]
    step_idx = 0
    timer = 0
    max_cek = 50  # 50 x 15 detik = 12.5 menit

    for i in range(max_cek):
        await asyncio.sleep(15)
        timer += 1

        if step_idx < len(steps):
            text, threshold = steps[step_idx]
            if timer >= threshold:
                try:
                    await msg.edit_text(text, parse_mode="Markdown")
                except:
                    pass
                step_idx += 1
                timer = 0

        # Cek release terbaru
        apk_url = cek_apk()
        if apk_url:
            await msg.edit_text(
                "✅ *APK Selesai Dibuild!*\n"
                "▓▓▓▓▓▓▓▓▓▓ 100%\n\n"
                "📥 Mengirim APK ke kamu...",
                parse_mode="Markdown"
            )
            await kirim_apk(apk_url, update, context, msg)
            return

    await msg.edit_text(
        "⏰ *Timeout!*\n\n"
        "Build terlalu lama.\n"
        "Cek: github.com/Alwaysazril/flutter-build-bot/actions",
        parse_mode="Markdown"
    )

def cek_apk():
    try:
        url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            assets = res.json().get("assets", [])
            for asset in assets:
                if asset["name"].endswith(".apk"):
                    return asset["browser_download_url"]
        return None
    except:
        return None

async def kirim_apk(apk_url, update, context, msg):
    try:
        r = requests.get(apk_url, stream=True, timeout=120)
        apk_path = "/tmp/app-release.apk"
        with open(apk_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

        with open(apk_path, "rb") as apk:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=apk,
                filename="app-release.apk",
                caption=(
                    "✅ *Build Sukses!*\n\n"
                    "📱 APK siap diinstall!\n"
                    "Aktifkan *Unknown Sources* dulu."
                ),
                parse_mode="Markdown"
            )
        await msg.edit_text("✅ *APK sudah dikirim!*", parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Gagal kirim APK: {str(e)[:200]}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    try:
        url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/actions/runs?per_page=1"
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            runs = res.json().get("workflow_runs", [])
            if runs:
                run = runs[0]
                s = run["status"]
                c = run.get("conclusion", "-")
                await update.message.reply_text(
                    f"📊 *Status Build Terakhir*\n\n"
                    f"Status: `{s}`\n"
                    f"Hasil: `{c}`\n"
                    f"[Lihat di GitHub]({run['html_url']})",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("Belum ada build.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_zip))
    print("Bot berjalan...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
