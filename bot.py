import os
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

# ── Conversation states ───────────────────────────────────────────────────────
ASK_START, ASK_END, ASK_DISTRICT = range(3)

# Custom-fields conversation states — one state per field
(
    CF_DESTINATION,
    CF_DEST_DISTRICT,
    CF_GENERATED_ON,
    CF_DISTANCE,
    CF_SERIAL,
    CF_VALID_UPTO_DAYS,
) = range(3, 9)
# ─────────────────────────────────────────────────────────────────────────────

user_sessions = {}

SKIP_WORD = "skip"   # user types this to leave a field unchanged


# ── Helpers ───────────────────────────────────────────────────────────────────

def increment_serial(serial: str) -> str:
    """AAQGG704751 → AAQGG704752"""
    i = len(serial) - 1
    while i >= 0 and serial[i].isdigit():
        i -= 1
    prefix     = serial[:i + 1]
    number_str = serial[i + 1:]
    if not number_str:
        return serial
    incremented = str(int(number_str) + 1).zfill(len(number_str))
    return prefix + incremented


def random_date_between(start_str: str, end_str: str) -> str:
    """Return a random DD/MM/YYYY HH:MM between two dates."""
    fmt = "%d/%m/%Y"
    try:
        start_dt = datetime.strptime(start_str.strip(), fmt)
        end_dt   = datetime.strptime(end_str.strip(), fmt)
    except ValueError:
        raise ValueError("Date format must be DD/MM/YYYY")
    if end_dt < start_dt:
        start_dt, end_dt = end_dt, start_dt
    delta      = (end_dt - start_dt).days
    random_day = start_dt + timedelta(days=random.randint(0, delta))
    random_t   = timedelta(hours=random.randint(0, 23), minutes=random.randint(0, 59))
    return (random_day + random_t).strftime("%d/%m/%Y %H:%M")


def _skip_keyboard():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⏭ Skip (keep scraped value)", callback_data="cf_skip")]]
    )


# ── Main fetch conversation ───────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("👋 Welcome! Enter the *start number*:", parse_mode="Markdown")
    return ASK_START


async def ask_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['start'] = int(update.message.text.strip())
        await update.message.reply_text("Got it. Now enter the *end number*:", parse_mode="Markdown")
        return ASK_END
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number.")
        return ASK_START


async def ask_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['end'] = int(update.message.text.strip())
        await update.message.reply_text("Now enter the *district name*:", parse_mode="Markdown")
        return ASK_DISTRICT
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number.")
        return ASK_END


async def ask_district(update: Update, context: ContextTypes.DEFAULT_TYPE):
    district = update.message.text.strip()
    start    = context.user_data['start']
    end      = context.user_data['end']
    user_id  = update.effective_user.id

    await update.message.reply_text(f"🔍 Fetching data for district: *{district}*...", parse_mode="Markdown")

    user_sessions[user_id] = {"data": []}

    async def send_entry(entry):
        msg = (
            f"`{entry['eMM11_num']}`\n"
            f"📍 {entry['destination_district']} — {entry['destination_address']}\n"
            f"⚖️ {entry['quantity_to_transport']}\n"
            f"🕐 {entry['generated_on']}"
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text=msg, parse_mode="Markdown"
        )
        user_sessions[user_id]["data"].append(entry)

    await fetch_emm11_data(start, end, district, data_callback=send_entry)

    entries = user_sessions[user_id]["data"]
    if entries:
        context.user_data["tp_num_list"] = [e['eMM11_num'] for e in entries]
        keyboard = [
            [InlineKeyboardButton("📄 Generate PDF (scraped values)", callback_data="generate_pdf")],
            [InlineKeyboardButton("✏️ Generate with Custom Fields",   callback_data="custom_generate")],
            [InlineKeyboardButton("🔁 Start Again",                   callback_data="start_again")],
            [InlineKeyboardButton("❌ Exit",                          callback_data="exit_process")],
        ]
        await update.message.reply_text(
            f"✅ Found *{len(entries)}* record(s). Choose an action:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("⚠️ No data found for that range/district.")

    return ConversationHandler.END


# ── Custom-fields sub-conversation ───────────────────────────────────────────

async def custom_gen_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry: tap '✏️ Generate with Custom Fields'."""
    query = update.callback_query
    await query.answer()
    context.user_data['cf'] = {}

    context.user_data['_cf_state'] = CF_DESTINATION
    await query.edit_message_text(
        "✏️ *Custom PDF Generation*\n\n"
        "*Step 1/6 — Destination*\n"
        "Enter the destination address, or tap Skip to keep the scraped value.",
        reply_markup=_skip_keyboard(),
        parse_mode="Markdown"
    )
    return CF_DESTINATION


# ── Core helper: send next prompt correctly whether from message or callback ──

async def _advance_cf(update, context, skipped: bool, current_state: int):
    """Move to next field in the custom-fields wizard."""
    NEXT = {
        CF_DESTINATION:     (CF_DEST_DISTRICT,   "*Step 2/6 — Destination District*\nEnter the destination district, or Skip."),
        CF_DEST_DISTRICT:   (CF_GENERATED_ON,    "*Step 3/6 — Generated On*\nEnter the date (DD/MM/YYYY), or Skip.\nTime will be auto-appended."),
        CF_GENERATED_ON:    (CF_DISTANCE,        "*Step 4/6 — Distance*\nEnter distance in km (e.g. `45`), or Skip."),
        CF_DISTANCE:        (CF_SERIAL,          "*Step 5/6 — Serial Number*\nEnter starting serial (e.g. `AAQGG704751`).\nEach PDF gets the next incremented number.\nOr Skip to keep scraped serials."),
        CF_SERIAL:          (CF_VALID_UPTO_DAYS, "*Step 6/6 — Valid Upto*\nEnter number of validity days from Generated On (e.g. `2`), or Skip."),
        CF_VALID_UPTO_DAYS: (None, None),
    }
    next_state, next_prompt = NEXT[current_state]

    is_callback = update.callback_query is not None

    async def send_next(text, reply_markup=None):
        if is_callback:
            await update.callback_query.edit_message_text(
                text, reply_markup=reply_markup, parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                text, reply_markup=reply_markup, parse_mode="Markdown"
            )

    if next_state is None:
        await send_next("✅ All fields collected! Starting generation...")
        await _run_custom_generation(update, context)
        return ConversationHandler.END

    context.user_data['_cf_state'] = next_state
    await send_next(next_prompt, reply_markup=_skip_keyboard())
    return next_state


# ── Individual field handlers ─────────────────────────────────────────────────

async def cf_destination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['_cf_state'] = CF_DESTINATION
    val = update.message.text.strip()
    if val.lower() != SKIP_WORD:
        context.user_data['cf']['destination'] = val
    return await _advance_cf(update, context, skipped=False, current_state=CF_DESTINATION)


async def cf_dest_district(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['_cf_state'] = CF_DEST_DISTRICT
    val = update.message.text.strip()
    if val.lower() != SKIP_WORD:
        context.user_data['cf']['destination_district'] = val
    return await _advance_cf(update, context, skipped=False, current_state=CF_DEST_DISTRICT)


async def cf_generated_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['_cf_state'] = CF_GENERATED_ON
    val = update.message.text.strip()
    if val.lower() != SKIP_WORD:
        try:
            datetime.strptime(val, "%d/%m/%Y")
            context.user_data['cf']['generated_on'] = val
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid format. Use DD/MM/YYYY or tap Skip:",
                reply_markup=_skip_keyboard()
            )
            return CF_GENERATED_ON
    return await _advance_cf(update, context, skipped=False, current_state=CF_GENERATED_ON)


async def cf_distance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['_cf_state'] = CF_DISTANCE
    val = update.message.text.strip()
    if val.lower() != SKIP_WORD:
        context.user_data['cf']['distance'] = val
    return await _advance_cf(update, context, skipped=False, current_state=CF_DISTANCE)


async def cf_serial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['_cf_state'] = CF_SERIAL
    val = update.message.text.strip()
    if val.lower() != SKIP_WORD:
        context.user_data['cf']['__serial_start__'] = val
    return await _advance_cf(update, context, skipped=False, current_state=CF_SERIAL)


async def cf_valid_upto_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['_cf_state'] = CF_VALID_UPTO_DAYS
    val = update.message.text.strip()
    if val.lower() != SKIP_WORD:
        if val.isdigit() and int(val) > 0:
            context.user_data['cf']['__valid_upto_days__'] = int(val)
        else:
            await update.message.reply_text(
                "❌ Please enter a positive whole number or tap Skip:",
                reply_markup=_skip_keyboard()
            )
            return CF_VALID_UPTO_DAYS
    return await _advance_cf(update, context, skipped=False, current_state=CF_VALID_UPTO_DAYS)


# ── Skip button handler (per-state) ──────────────────────────────────────────

async def _cf_skip_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, state: int):
    """Inline skip button handler bound to each state."""
    await update.callback_query.answer("Skipped ✓")
    context.user_data['_cf_state'] = state
    return await _advance_cf(update, context, skipped=True, current_state=state)


# ── Run generation after all fields collected ─────────────────────────────────

async def _run_custom_generation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cf      = context.user_data.get('cf', {})
    tp_list = context.user_data.get('tp_num_list', [])

    # Determine reply function — at this point update is always from a message
    # (last step was a text input), but guard for callback just in case
    if update.callback_query:
        msg_fn = update.callback_query.message.reply_text
    else:
        msg_fn = update.message.reply_text

    if not tp_list:
        await msg_fn("⚠️ No TP numbers in session. Please /start again.")
        return

    serial_start = cf.pop('__serial_start__', None)

    summary_lines = []
    if cf.get('destination'):           summary_lines.append(f"• Destination: {cf['destination']}")
    if cf.get('destination_district'):  summary_lines.append(f"• Dest District: {cf['destination_district']}")
    if cf.get('generated_on'):          summary_lines.append(f"• Generated On: {cf['generated_on']}")
    if cf.get('distance'):              summary_lines.append(f"• Distance: {cf['distance']}")
    if serial_start:                    summary_lines.append(f"• Starting Serial: {serial_start}")
    if cf.get('__valid_upto_days__'):   summary_lines.append(f"• Valid Upto: +{cf['__valid_upto_days__']} day(s)")
    if not summary_lines:               summary_lines.append("• All scraped values (no overrides)")

    await msg_fn(
        f"⚙️ Generating *{len(tp_list)}* PDF(s):\n" + "\n".join(summary_lines) + "\n\nPlease wait...",
        parse_mode="Markdown"
    )

    os.makedirs("pdf", exist_ok=True)
    generated      = []
    current_serial = serial_start

    for tp_num in tp_list:
        overrides = dict(cf)

        if current_serial:
            overrides['serial_number'] = current_serial

        try:
            await pdf_gen(
                [tp_num],
                log_callback=None,
                send_pdf_callback=None,
                field_overrides=overrides if overrides else None,
            )
            generated.append(tp_num)
            serial_info = f", serial `{current_serial}`" if current_serial else ""
            await msg_fn(f"✅ `{tp_num}`{serial_info}", parse_mode="Markdown")
        except Exception as e:
            await msg_fn(f"❌ Failed `{tp_num}`: {e}", parse_mode="Markdown")

        if current_serial:
            current_serial = increment_serial(current_serial)

    if generated:
        keyboard = (
            [[InlineKeyboardButton(f"📄 {tp}.pdf", callback_data=f"pdf_{tp}")] for tp in generated]
            + [[InlineKeyboardButton("❌ Exit", callback_data="exit_process")]]
        )
        await msg_fn(
            f"✅ Done! *{len(generated)}/{len(tp_list)}* PDF(s) generated. Tap to download:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        await msg_fn("❌ No PDFs were generated.")


async def cancel_custom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Custom generation cancelled.")
    return ConversationHandler.END


# ── Button handler (outside conversations) ────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "generate_pdf":
        tp_num_list = context.user_data.get("tp_num_list", [])
        if not tp_num_list:
            await query.edit_message_text("⚠️ No TP numbers found. Please /start again.")
            return

        await query.edit_message_text(
            f"⚙️ Generating *{len(tp_num_list)}* PDF(s) with scraped values...",
            parse_mode="Markdown"
        )
        await pdf_gen(tp_num_list, log_callback=None, send_pdf_callback=None)

        keyboard = (
            [[InlineKeyboardButton(f"📄 {tp}.pdf", callback_data=f"pdf_{tp}")] for tp in tp_num_list]
            + [[InlineKeyboardButton("❌ Exit", callback_data="exit_process")]]
        )
        await context.bot.send_message(
            chat_id=query.message.chat.id,
            text="✅ Done! Tap to download:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

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

    elif query.data == "start_again":
        await query.edit_message_text("🔁 Type /start to begin again.")
        user_sessions.pop(user_id, None)
        context.user_data.clear()

    elif query.data == "exit_process":
        await query.edit_message_text("❌ Session ended.")
        user_sessions.pop(user_id, None)
        context.user_data.clear()


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Cancelled.")
    return ConversationHandler.END


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    try:
        shutil.rmtree("pdf")
    except Exception:
        pass

    app = Application.builder().token(BOT_TOKEN).build()

    # Fetch conversation
    fetch_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_START:    [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_start)],
            ASK_END:      [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_end)],
            ASK_DISTRICT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_district)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Custom-fields conversation (entered via inline button)
    custom_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(custom_gen_start, pattern="^custom_generate$")],
        states={
            CF_DESTINATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cf_destination),
                CallbackQueryHandler(
                    lambda u, c: _cf_skip_handler(u, c, CF_DESTINATION),
                    pattern="^cf_skip$"
                ),
            ],
            CF_DEST_DISTRICT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cf_dest_district),
                CallbackQueryHandler(
                    lambda u, c: _cf_skip_handler(u, c, CF_DEST_DISTRICT),
                    pattern="^cf_skip$"
                ),
            ],
            CF_GENERATED_ON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cf_generated_on),
                CallbackQueryHandler(
                    lambda u, c: _cf_skip_handler(u, c, CF_GENERATED_ON),
                    pattern="^cf_skip$"
                ),
            ],
            CF_DISTANCE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cf_distance),
                CallbackQueryHandler(
                    lambda u, c: _cf_skip_handler(u, c, CF_DISTANCE),
                    pattern="^cf_skip$"
                ),
            ],
            CF_SERIAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cf_serial),
                CallbackQueryHandler(
                    lambda u, c: _cf_skip_handler(u, c, CF_SERIAL),
                    pattern="^cf_skip$"
                ),
            ],
            CF_VALID_UPTO_DAYS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cf_valid_upto_days),
                CallbackQueryHandler(
                    lambda u, c: _cf_skip_handler(u, c, CF_VALID_UPTO_DAYS),
                    pattern="^cf_skip$"
                ),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_custom)],
    )

    app.add_handler(fetch_conv)
    app.add_handler(custom_conv)
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot running...")
    app.run_polling()


if __name__ == '__main__':
    main()
