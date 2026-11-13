import os
import json
import logging
import requests
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "123456789"))

CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

user_data_db = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔑 Set Gemini Key", callback_data="set_gemini_key")],
        [InlineKeyboardButton("⚡ Set Groq Key", callback_data="set_groq_key")],
        [InlineKeyboardButton("🌪 Set Mistral Key", callback_data="set_mistral_key")],
        [InlineKeyboardButton("🔗 Connect GitHub Repo", callback_data="set_github_token")],
        [InlineKeyboardButton("🎬 Create Clips", callback_data="create_clips")]
    ]
    await update.message.reply_text(
        "Welcome to the Multi-AI Viral Clip Bot!\n\n"
        "1. Choose your preferred AI Provider & save your API Key.\n"
        "2. Connect your GitHub repository.\n"
        "3. Send your video link to start generating clips!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "set_gemini_key":
        context.user_data["waiting_for"] = "gemini_key"
        await query.message.reply_text("Please reply with your Gemini API Key:")
    elif query.data == "set_groq_key":
        context.user_data["waiting_for"] = "groq_key"
        await query.message.reply_text("Please reply with your Groq API Key:")
    elif query.data == "set_mistral_key":
        context.user_data["waiting_for"] = "mistral_key"
        await query.message.reply_text("Please reply with your Mistral API Key:")
    elif query.data == "set_github_token":
        context.user_data["waiting_for"] = "github_token"
        await query.message.reply_text("Please reply with your GitHub Token in format: `username/repo:token`:")
    elif query.data == "create_clips":
        await query.message.reply_text("Please send your video link followed by ratio (e.g., `https://youtube.com/watch?v=... 9:16`).")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    waiting_for = context.user_data.get("waiting_for")

    if waiting_for == "gemini_key":
        user_data_db.setdefault(user_id, {})["ai_provider"] = "gemini"
        user_data_db[user_id]["ai_key"] = text
        context.user_data["waiting_for"] = None
        await update.message.reply_text("✅ Gemini API Key saved successfully!")
        return
    elif waiting_for == "groq_key":
        user_data_db.setdefault(user_id, {})["ai_provider"] = "groq"
        user_data_db[user_id]["ai_key"] = text
        context.user_data["waiting_for"] = None
        await update.message.reply_text("✅ Groq API Key saved successfully!")
        return
    elif waiting_for == "mistral_key":
        user_data_db.setdefault(user_id, {})["ai_provider"] = "mistral"
        user_data_db[user_id]["ai_key"] = text
        context.user_data["waiting_for"] = None
        await update.message.reply_text("✅ Mistral API Key saved successfully!")
        return

    if waiting_for == "github_token":
        try:
            repo_slug, token = text.split(":")
            user_data_db.setdefault(user_id, {})["github_repo"] = repo_slug.strip()
            user_data_db[user_id]["github_token"] = token.strip()
            context.user_data["waiting_for"] = None
            await update.message.reply_text("✅ GitHub Repository connected successfully!")
        except Exception:
            await update.message.reply_text("❌ Invalid format. Use `username/repo:ghp_xxx`")
        return

    parts = text.split()
    video_url = parts[0]
    aspect_ratio = parts[1] if len(parts) > 1 else "9:16"

    if not video_url.startswith("http"):
        await update.message.reply_text("Please send a valid video URL.")
        return

    if user_id not in user_data_db or "github_token" not in user_data_db[user_id]:
        await update.message.reply_text("⚠️ Please connect your GitHub repository first using /start.")
        return

    if user_id not in user_data_db or "ai_key" not in user_data_db[user_id]:
        await update.message.reply_text("⚠️ Please set your AI API key (Gemini, Groq, or Mistral) first using /start.")
        return

    repo = user_data_db[user_id]["github_repo"]
    cache_url = f"https://raw.githubusercontent.com/{repo}/main/cache.json"
    timestamps = None

    try:
        res = requests.get(cache_url)
        if res.status_code == 200:
            cache_data = res.json()
            if video_url in cache_data:
                timestamps = cache_data[video_url]
    except Exception:
        pass

    if timestamps:
        await update.message.reply_text("⚡ Cache hit! Using cached timestamps. Dispatching GitHub worker...")
    else:
        await update.message.reply_text("🔍 Analyzing video for high-viral moments using your AI key...")
        try:
            provider = user_data_db[user_id]["ai_provider"]
            ai_key = user_data_db[user_id]["ai_key"]
            config = load_config()
            prompt = config.get("ai_prompt", "Find viral timestamps in JSON format.")

            if provider == "gemini":
                genai.configure(api_key=ai_key)
                model = genai.GenerativeModel('gemini-1.5-pro')
                response = model.generate_content([video_url, prompt])
                raw_text = response.text.strip()
            elif provider in ["groq", "mistral"]:
                headers = {"Authorization": f"Bearer {ai_key}", "Content-Type": "application/json"}
                if provider == "groq":
                    data = {"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": f"{prompt}\nVideo URL: {video_url}"}]}
                    res_ai = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data)
                    raw_text = res_ai.json()["choices"][0]["message"]["content"].strip()
                else:
                    data = {"model": "mistral-large-latest", "messages": [{"role": "user", "content": f"{prompt}\nVideo URL: {video_url}"}]}
                    res_ai = requests.post("https://api.mistral.ai/v1/chat/completions", headers=headers, json=data)
                    raw_text = res_ai.json()["choices"][0]["message"]["content"].strip()

            if "```json" in raw_text:
                raw_text = raw_text.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_text:
                raw_text = raw_text.split("```")[1].split("```")[0].strip()

            timestamps = json.loads(raw_text)
        except Exception as e:
            await update.message.reply_text(f"❌ AI Analysis failed: {str(e)}")
            return

    await update.message.reply_text("🚀 Dispatching GitHub Actions runner...")

    gh_token = user_data_db[user_id]["github_token"]
    dispatch_url = f"https://api.github.com/repos/{repo}/actions/workflows/clip_process.yml/dispatches"
    headers = {
        "Authorization": f"Bearer {gh_token}",
        "Accept": "application/vnd.github+json"
    }
    payload = {
        "ref": "main",
        "inputs": {
            "video_url": video_url,
            "timestamps": json.dumps(timestamps),
            "aspect_ratio": aspect_ratio,
            "watermark_config": json.dumps(load_config()),
            "telegram_chat_id": str(update.effective_chat.id),
            "telegram_bot_token": BOT_TOKEN
        }
    }

    res = requests.post(dispatch_url, headers=headers, json=payload)
    if res.status_code == 204:
        await update.message.reply_text("✅ Workflow dispatched successfully! Clips will arrive shortly.")
    else:
        await update.message.reply_text(f"❌ Failed to dispatch workflow: {res.text}")

async def admin_set_watermark(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: `/setwatermark YourText`", parse_mode="Markdown")
        return

    new_wm = " ".join(args)
    config = load_config()
    config["watermark_content"] = new_wm
    save_config(config)
    await update.message.reply_text(f"✅ Watermark updated to: {new_wm}")

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setwatermark", admin_set_watermark))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()

if __name__ == "__main__":
    main()
