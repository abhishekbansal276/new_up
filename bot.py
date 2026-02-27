import os
import asyncio
import shutil
import random
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
)
from fetch_emm11_data import fetch_emm11_data
from pdf_gen import pdf_gen

BOT_TOKEN = '8414234561:AAHkVLYrVcl1q_TBwrwwai4jD6JlQ6w-aDw'

ASK_START, ASK_END, ASK_DISTRICT = range(3)
CUSTOM_DESTINATION, CUSTOM_DATE_START, CUSTOM_DATE_END, CUSTOM_SERIAL = range(3, 7)

user_sessions = {}


# ───────────────── helpers ───────────────────────────────────────── #

def increment_serial(serial: str) -> str:
    """Increment the numeric suffix of a serial like AAQGG704751 → AAQGG704752"""
    i = len(serial) - 1
    while i >= 0 and serial[i].isdigit():
        i -= 1
    prefix = serial[:i + 1]
    number_str = serial[i + 1:]
    if not number_str:
        return serial  # nothing to increment
    incremented = str(int(number_str) + 1).zfill(len(number_str))
    return prefix + incremented


def random_date_between(start_str: str, end_str: str) -> str:
    """Return a random date string (DD/MM/YYYY HH:MM) between two dates."""
    fmt = "%d/%m/%Y"
    try:
        start_dt = datetime.strptime(start_str.strip(), fmt)
        end_dt   = datetime.strptime(end_str.strip(), fmt)
    except ValueError:
        raise ValueError("Date format must be DD/MM/YYYY")
    if end_dt < start_dt:
        start_dt, end_dt = end_dt, start_dt
    delta = (end_dt - start_dt).days
    random_day = start_dt + timedelta(days=random.randint(0, delta))
    # Add random hour:minute
    random_time = timedelta(hours=random.randint(0, 23), minutes=random.randint(0, 59))
    final_dt = random_day + random_time
    return final_dt.strftime("%d/%m/%Y %H:%M")


# ───────────────── main conversation ─────────────────────────────── #

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Please enter the start number:")
    return ASK_START

async def ask_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['start'] = int(update.message.text)
        await update.message.reply_text("Got it. Now enter the end number:")
        return ASK_END
    except ValueError:
        await update.message.reply_text("Please enter a valid number.")
        return ASK_START

async def ask_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['end'] = int(update.message.text)
        await update.message.reply_text("Now, please enter the district name:")
        return ASK_DISTRICT
    except ValueError:
        await update.message.reply_text("Please enter a valid number.")
        return ASK_END

async def ask_district(update: Update, context: ContextTypes.DEFAULT_TYPE):
    district = update.message.text
    start    = context.user_data['start']
    end      = context.user_data['end']
    user_id  = update.effective_user.id

    await update.message.reply_text(f"Fetching data for district: {district}...")

    user_sessions[user_id] = {"start": start, "end": end, "district": district, "data": []}

    async def send_entry(entry):
        msg = (
            f"{entry['eMM11_num']}\n"
            f"{entry['destination_district']}\n"
            f"{entry['destination_address']}\n"
            f"{entry['quantity_to_transport']}\n"
            f"{entry['generated_on']}"
        )
        await context.bot.send_message(chat_id=update.effective_chat.id, text=msg)
        user_sessions[user_id]["data"].append(entry)

    await fetch_emm11_data(start, end, district, data_callback=send_entry)

    if user_sessions[user_id]["data"]:
        context.user_data["tp_num_list"] = [
            entry['eMM11_num'] for entry in user_sessions[user_id]["data"]
        ]
        keyboard = [
            [InlineKeyboardButton("📄 Generate PDF",             callback_data="generate_pdf")],
            [InlineKeyboardButton("✏️ Generate with Custom Fields", callback_data="custom_generate")],
            [InlineKeyboardButton("🔁 Start Again",              callback_data="start_again")],
            [InlineKeyboardButton("❌ Exit",                     callback_data="exit_process")],
        ]
        await update.message.reply_text(
            "Data fetched. Choose an action:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text("No data found.")

    return ConversationHandler.END


# ───────────────── custom-generate sub-conversation ──────────────── #

async def custom_gen_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point when user taps '✏️ Generate with Custom Fields'."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "✏️ *Custom PDF Generation*\n\n"
        "Enter the *destination address* that will appear in all PDFs:",
        parse_mode="Markdown"
    )
    return CUSTOM_DESTINATION

async def custom_destination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['custom_destination'] = update.message.text.strip()
    await update.message.reply_text(
        "📅 Enter the *start date* for random date range (format: DD/MM/YYYY):",
        parse_mode="Markdown"
    )
    return CUSTOM_DATE_START

async def custom_date_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        datetime.strptime(update.message.text.strip(), "%d/%m/%Y")
        context.user_data['custom_date_start'] = update.message.text.strip()
        await update.message.reply_text(
            "📅 Enter the *end date* for random date range (format: DD/MM/YYYY):",
            parse_mode="Markdown"
        )
        return CUSTOM_DATE_END
    except ValueError:
        await update.message.reply_text("❌ Invalid format. Please use DD/MM/YYYY:")
        return CUSTOM_DATE_START

async def custom_date_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        datetime.strptime(update.message.text.strip(), "%d/%m/%Y")
        context.user_data['custom_date_end'] = update.message.text.strip()
        await update.message.reply_text(
            "🔢 Enter the *starting serial number* (e.g. AAQGG704751):\n"
            "Each PDF will get the next incremented serial.",
            parse_mode="Markdown"
        )
        return CUSTOM_SERIAL
    except ValueError:
        await update.message.reply_text("❌ Invalid format. Please use DD/MM/YYYY:")
        return CUSTOM_DATE_END

async def custom_serial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    serial   = update.message.text.strip()
    dest     = context.user_data.get('custom_destination', '')
    d_start  = context.user_data.get('custom_date_start', '')
    d_end    = context.user_data.get('custom_date_end', '')
    tp_list  = context.user_data.get('tp_num_list', [])
    user_id  = update.effective_user.id

    if not tp_list:
        await update.message.reply_text("⚠️ No TP numbers in session. Please /start again.")
        return ConversationHandler.END

    await update.message.reply_text(
        f"⚙️ Generating {len(tp_list)} PDFs with:\n"
        f"• Destination: {dest}\n"
        f"• Date range: {d_start} → {d_end}\n"
        f"• Starting serial: {serial}\n\n"
        f"Please wait..."
    )

    os.makedirs("pdf", exist_ok=True)

    current_serial = serial
    generated = []

    for tp_num in tp_list:
        random_date = random_date_between(d_start, d_end)
        overrides = {
            "destination":          dest,
            "destination_district": dest,
            "generated_on":         random_date,
            "serial_number":        current_serial,
        }
        try:
            await pdf_gen(
                [tp_num],
                log_callback=None,
                send_pdf_callback=None,
                field_overrides=overrides,
            )
            generated.append(tp_num)
            await update.message.reply_text(
                f"✅ {tp_num} → serial {current_serial}, date {random_date}"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Failed {tp_num}: {e}")

        current_serial = increment_serial(current_serial)

    if generated:
        keyboard = (
            [[InlineKeyboardButton(f"📄 {tp}.pdf", callback_data=f"pdf_{tp}")] for tp in generated]
            + [[InlineKeyboardButton("❌ Exit", callback_data="exit_process")]]
        )
        await update.message.reply_text(
            "✅ All done! Tap to download:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text("❌ No PDFs were generated.")

    return ConversationHandler.END

async def cancel_custom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Custom generation cancelled.")
    return ConversationHandler.END


# ───────────────── button handler ────────────────────────────────── #

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # "✏️ Generate with Custom Fields" — hand off to sub-conversation
    if query.data == "custom_generate":
        await custom_gen_start(update, context)
        return

    if query.data == "generate_pdf":
        tp_num_list = context.user_data.get("tp_num_list", [])
        if not tp_num_list:
            await query.edit_message_text("⚠️ No TP numbers found. Please fetch data first.")
            return

        await pdf_gen(
            tp_num_list,
            log_callback=None,
            send_pdf_callback=None,
        )

        keyboard = (
            [[InlineKeyboardButton(f"📄 {tp}.pdf", callback_data=f"pdf_{tp}")] for tp in tp_num_list]
            + [[InlineKeyboardButton("❌ Exit", callback_data="exit_process")]]
        )
        await context.bot.send_message(
            chat_id=query.message.chat.id,
            text="✅ Click below to download PDFs:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    elif query.data.startswith("pdf_"):
        tp_num   = query.data.replace("pdf_", "")
        pdf_path = os.path.join("pdf", f"{tp_num}.pdf")
        if os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                await context.bot.send_document(
                    chat_id=query.message.chat.id,
                    document=f,
                    filename=f"{tp_num}.pdf",
                    caption=f"📎 {tp_num}.pdf"
                )
        else:
            await context.bot.send_message(
                chat_id=query.message.chat.id,
                text=f"❌ PDF for {tp_num} not found. Please regenerate."
            )
        return

    elif query.data == "start_again":
        await query.edit_message_text("🔁 Restarting... Type /start to begin.")
        user_sessions.pop(user_id, None)

    elif query.data == "exit_process":
        await query.edit_message_text("❌ Session ended.")
        user_sessions.pop(user_id, None)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Operation cancelled.")
    return ConversationHandler.END


# ───────────────── main ──────────────────────────────────────────── #

def main():
    try:
        shutil.rmtree("pdf")
    except Exception:
        pass

    app = Application.builder().token(BOT_TOKEN).build()

    # Main fetch conversation
    fetch_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_START:    [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_start)],
            ASK_END:      [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_end)],
            ASK_DISTRICT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_district)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Custom-generate sub-conversation (entered via inline button)
    custom_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(custom_gen_start, pattern="^custom_generate$")],
        states={
            CUSTOM_DESTINATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, custom_destination)],
            CUSTOM_DATE_START:  [MessageHandler(filters.TEXT & ~filters.COMMAND, custom_date_start)],
            CUSTOM_DATE_END:    [MessageHandler(filters.TEXT & ~filters.COMMAND, custom_date_end)],
            CUSTOM_SERIAL:      [MessageHandler(filters.TEXT & ~filters.COMMAND, custom_serial)],
        },
        fallbacks=[CommandHandler("cancel", cancel_custom)],
    )

    app.add_handler(fetch_conv)
    app.add_handler(custom_conv)
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot is running...")
    app.run_polling()


if __name__ == '__main__':
    main()