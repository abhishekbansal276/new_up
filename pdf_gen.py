# import os
# import inspect
# import logging
# from io import BytesIO
# from datetime import datetime, timedelta
# import qrcode
# import paramiko
# from PIL import Image as PilImage

# from playwright.async_api import async_playwright
# from reportlab.pdfgen import canvas
# from reportlab.lib.pagesizes import A4
# from reportlab.lib.utils import ImageReader
# from PyPDF2 import PdfReader, PdfWriter
# import re

# # ---------- Logging Setup ----------
# logging.basicConfig(
#     format='[%(asctime)s] %(levelname)s: %(message)s',
#     level=logging.INFO
# )
# logger = logging.getLogger(__name__)
# # -----------------------------------

# # ── VPS / SFTP Configuration ────────────────────────────────────────────────
# VPS_CONFIG = {
#     "host":            "194.238.18.112",
#     "port":            22,
#     "username":        "root",
#     "password":        "29032001@Abhi",
#     "ssh_key_path":    None,
#     "remote_dir":      "/var/www/html/pdfs",
#     "public_base_url": "http://194.238.18.112/pdfs",
# }
# # ─────────────────────────────────────────────────────────────────────────────


# def screenshot_to_pdf(screenshot_path: str, output_pdf_path: str) -> str:
#     """
#     Convert a PNG screenshot to a PDF with a white background.
#     Scales to fit A4 width while preserving aspect ratio.
#     """
#     img      = PilImage.open(screenshot_path).convert("RGBA")
#     bg       = PilImage.new("RGBA", img.size, (255, 255, 255, 255))
#     bg.paste(img, mask=img.split()[3])
#     flat_img = bg.convert("RGB")

#     PAGE_W, PAGE_H = A4
#     img_w, img_h   = flat_img.size
#     scale          = PAGE_W / img_w
#     draw_w         = PAGE_W
#     draw_h         = img_h * scale

#     if draw_h > PAGE_H:
#         scale  = PAGE_H / img_h
#         draw_w = img_w * scale
#         draw_h = PAGE_H

#     x_offset   = (PAGE_W - draw_w) / 2
#     y_offset   = PAGE_H - draw_h

#     img_buffer = BytesIO()
#     flat_img.save(img_buffer, format="PNG")
#     img_buffer.seek(0)

#     c = canvas.Canvas(output_pdf_path, pagesize=A4)
#     c.setFillColorRGB(1, 1, 1)
#     c.rect(0, 0, PAGE_W, PAGE_H, fill=True, stroke=False)
#     c.drawImage(
#         ImageReader(img_buffer),
#         x_offset, y_offset,
#         width=draw_w, height=draw_h,
#         preserveAspectRatio=True,
#         mask='auto'
#     )
#     c.save()

#     size_kb = os.path.getsize(output_pdf_path) // 1024
#     logger.info(f"  🖼️  Screenshot → PDF: {output_pdf_path} ({size_kb} KB)")
#     return output_pdf_path


# def upload_file_to_vps(local_path: str, filename: str) -> str:
#     """Upload file to VPS via SFTP. Returns public URL."""
#     cfg       = VPS_CONFIG
#     transport = paramiko.Transport((cfg["host"], cfg["port"]))

#     try:
#         if cfg.get("ssh_key_path"):
#             key = paramiko.RSAKey.from_private_key_file(cfg["ssh_key_path"])
#             transport.connect(username=cfg["username"], pkey=key)
#             logger.info(f"🔐 SFTP connected via SSH key")
#         else:
#             transport.connect(username=cfg["username"], password=cfg["password"])
#             logger.info(f"🔐 SFTP connected via password")

#         sftp = paramiko.SFTPClient.from_transport(transport)

#         try:
#             sftp.stat(cfg["remote_dir"])
#         except FileNotFoundError:
#             sftp.mkdir(cfg["remote_dir"])
#             logger.info(f"  📁 Created remote dir: {cfg['remote_dir']}")

#         remote_path = f"{cfg['remote_dir']}/{filename}"
#         sftp.put(local_path, remote_path)
#         logger.info(f"  ☁️  Uploaded: {local_path} → {remote_path}")
#         sftp.close()
#     finally:
#         transport.close()

#     public_url = f"{cfg['public_base_url'].rstrip('/')}/{filename}"
#     logger.info(f"  🔗 Public URL: {public_url}")
#     return public_url


# # Maps field_overrides keys → CSS selectors on the web page
# FIELD_SELECTOR_MAP = {
#     "distance":             "#lbl_distrance",
#     "lessee_name":          "#lbl_name_of_license",
#     "lessee_mobile":        "#lbl_mobile_no",
#     "serial_number":        "#lbl_SerialNumber",
#     "lessee_id":            "#lbl_LicenseId",
#     "lease_details":        "#lbl_licenseDetails",
#     "tehsil":               "#lbl_tehsil",
#     "district":             "#lbl_district",
#     "qty":                  "#lbl_qty_to_Transport_Tonne",
#     "mineral":              "#lbl_type_of_mining_mineral",
#     "loading_from":         "#lbl_loadingfrom",
#     "destination":          "#lbl_destination_address",
#     "destination_district": "#lbl_destination_district",
#     "generated_on":         "#txt_eFormC_generated_on",
#     "valid_upto":           "#txt_eFormC_valid_upto",
#     "valid_upto_label":     "#lbl_formValidUpTo",
#     "travel_duration":      "#lbl_travel_duration",
#     "pit_value":            "#lblSellingPrice",
#     "registration_number":  "#lbl_registraton_number_of_vehicle",
#     "driver_name":          "#lbl_name_of_driver",
#     "driver_mobile":        "#lbl_mobile_number_of_driver",
# }


# def append_time(date_str: str, time_str: str | None = None) -> str:
#     """Append HH:MM:SS AM/PM to a date string. Skips if already present."""
#     if "AM" in date_str.upper() or "PM" in date_str.upper():
#         return date_str
#     if time_str is None:
#         time_str = datetime.now().strftime("%I:%M:%S %p")
#     return f"{date_str} {time_str}"


# def compute_valid_upto(generated_on_str: str, days: int) -> str:
#     """Add `days` to the date in generated_on_str, preserving time component."""
#     date_part = generated_on_str.strip().split(" ")[0]
#     time_part = " ".join(generated_on_str.strip().split(" ")[1:]) or None

#     DATE_FORMATS = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"]
#     base_date = None
#     for fmt in DATE_FORMATS:
#         try:
#             base_date = datetime.strptime(date_part, fmt)
#             break
#         except ValueError:
#             continue
#     if base_date is None:
#         logger.warning(f"  ⚠ Could not parse {generated_on_str!r}, using today.")
#         base_date = datetime.today()

#     result_date = (base_date + timedelta(days=days)).strftime("%d/%m/%Y")
#     return append_time(result_date, time_part if time_part else None)


# def draw_data(c, data):
#     c.setFont("Helvetica-Bold", 6)

#     def draw_wrapped_text(x, y, text, max_words=4, line_spacing=6):
#         words = text.split()
#         lines = []
#         for i in range(0, len(words), max_words):
#             lines.append(" ".join(words[i:i + max_words]))
#         for i, line in enumerate(lines[:3]):
#             c.drawString(x, y - i * line_spacing, line)

#     raw_emM11   = data.get("emM11", "")
#     clean_emM11 = re.sub(r"[^\d]", "", raw_emM11)
#     c.drawString(273, 764.7, clean_emM11)
#     c.drawString(381, 764.7, data.get("lessee_id", ""))

#     draw_wrapped_text(102, 755, data.get("lessee_name", ""))
#     c.drawString(260, 753, data.get("lessee_mobile", ""))
#     draw_wrapped_text(430, 755, data.get("lease_details", ""))

#     c.drawString(100, 724, data.get("tehsil", ""))
#     c.drawString(260, 719, data.get("district", ""))
#     c.drawString(405, 718, data.get("qty", ""))

#     draw_wrapped_text(103, 706, data.get("mineral", ""))
#     c.drawString(265, 706, data.get("loading_from", ""))
#     draw_wrapped_text(435, 707, data.get("destination", ""))

#     c.drawString(135,  688, data.get("distance", ""))
#     c.drawString(259, 687.5, data.get("generated_on", ""))
#     c.drawString(435, 687.5, data.get("valid_upto", ""))

#     c.drawString(265, 670, data.get("travel_duration", ""))
#     c.drawString(90,  670, data.get("destination_district", ""))

#     c.drawString(120, 645, data.get("pit_value", ""))

#     c.drawString(160, 628, data.get("registration_number", ""))
#     c.drawString(170, 618, data.get("driver_mobile", ""))
#     c.drawString(320, 628, data.get("vehicle_type", ""))
#     c.drawString(350, 618, data.get("driver_dl", ""))
#     c.drawString(520, 628, data.get("driver_name", ""))

#     c.drawString(340, 655, data.get("serial_number", ""))

#     # ── QR code ───────────────────────────────────────────────────────────────
#     qr_url = data.get("qr_url")
#     if qr_url:
#         try:
#             qr_img    = qrcode.make(qr_url)
#             qr_buffer = BytesIO()
#             qr_img.save(qr_buffer, format="PNG")
#             qr_buffer.seek(0)
#             qr_image  = ImageReader(qr_buffer)

#             qr_size        = 40
#             PAGE_WIDTH, PAGE_HEIGHT = A4
#             margin_right   = 70
#             margin_top     = 30
#             padding        = 5

#             x_qr = PAGE_WIDTH  - qr_size - margin_right
#             y_qr = PAGE_HEIGHT - qr_size - margin_top

#             c.setFillColorRGB(1, 1, 1)
#             c.rect(x_qr - padding, y_qr - padding,
#                    qr_size + padding * 2, qr_size + padding * 2,
#                    fill=True, stroke=False)
#             c.drawImage(qr_image, x_qr, y_qr,
#                         width=qr_size, height=qr_size,
#                         preserveAspectRatio=True, mask='auto')
#             logger.info(f"  ✅ QR drawn → {qr_url}")
#         except Exception as e:
#             logger.warning(f"⚠️ QR drawing failed: {e}")


# def generate_pdf(data, template_path, output_path):
#     """Generate merged PDF (template + overlay data + QR)."""
#     overlay_stream = BytesIO()
#     c = canvas.Canvas(overlay_stream, pagesize=A4)
#     draw_data(c, data)
#     c.save()
#     overlay_stream.seek(0)

#     bg_reader = PdfReader(template_path)
#     ov_reader = PdfReader(overlay_stream)
#     writer    = PdfWriter()

#     page = bg_reader.pages[0]
#     page.merge_page(ov_reader.pages[0])
#     writer.add_page(page)

#     with open(output_path, "wb") as f:
#         writer.write(f)


# async def apply_overrides_to_page(page, field_overrides: dict):
#     """Push overridden values into DOM so screenshot reflects them."""
#     for key, value in field_overrides.items():
#         selector = FIELD_SELECTOR_MAP.get(key)
#         if not selector:
#             continue
#         try:
#             element = page.locator(selector)
#             tag     = await element.evaluate("el => el.tagName.toLowerCase()")
#             if tag in ("input", "textarea"):
#                 await element.evaluate(f"el => el.value = {repr(value)}")
#             else:
#                 await element.evaluate(f"el => el.innerText = {repr(value)}")
#             logger.info(f"  ↳ DOM: {key} = {value!r}")
#         except Exception as e:
#             logger.warning(f"  ⚠️ DOM update failed {key}: {e}")


# async def pdf_gen(
#     tp_num_list,
#     template_path="form_template.pdf",
#     log_callback=None,
#     send_pdf_callback=None,
#     field_overrides: dict | None = None,
# ):
#     """
#     Generate PDFs for each TP number.

#     field_overrides keys (all optional — pass only what you want to override):
#         destination          str   e.g. "Lucknow"
#         destination_district str   e.g. "Lucknow"
#         generated_on         str   e.g. "27/02/2026"  (time auto-appended)
#         distance             str   e.g. "45"
#         serial_number        str   e.g. "AAQGG704751"
#         __valid_upto_days__  int   e.g. 2  (computed as generated_on + N days)
#     """
#     if not tp_num_list:
#         logger.info("ℹ️ No TP numbers provided.")
#         return []

#     os.makedirs("pdf",        exist_ok=True)
#     os.makedirs("screenshot", exist_ok=True)
#     os.makedirs("ss_pdf",     exist_ok=True)
#     all_pdfs = []

#     async with async_playwright() as p:
#         browser = await p.chromium.launch(headless=True)
#         ctx     = await browser.new_context()

#         for tp_num in tp_num_list:
#             tp_num = str(tp_num)
#             logger.info(f"📦 Processing TP: {tp_num}")
#             try:
#                 page = await ctx.new_page()
#                 url  = (
#                     f"https://upmines.upsdc.gov.in//licensee/"
#                     f"PrintLicenseeFormVehicleCheckValidOrNot.aspx?eId={tp_num}"
#                 )
#                 await page.goto(url, timeout=20000)

#                 lbl_etpNo = await page.locator("#lbl_eForm_cNo").inner_text()
#                 if tp_num not in lbl_etpNo:
#                     raise ValueError(f"Mismatch: expected {tp_num}, got {lbl_etpNo}")

#                 # ── Scrape all fields ────────────────────────────────────────
#                 data = {
#                     "distance":             await page.locator('#lbl_distrance').inner_text(),
#                     "destination_state":    "Uttar Pradesh",
#                     "emM11":                tp_num,
#                     "lessee_name":          await page.locator('#lbl_name_of_license').inner_text(),
#                     "lessee_mobile":        await page.locator("#lbl_mobile_no").inner_text(),
#                     "serial_number":        await page.locator("#lbl_SerialNumber").inner_text(),
#                     "lessee_id":            await page.locator("#lbl_LicenseId").inner_text(),
#                     "lease_details":        await page.locator('#lbl_licenseDetails').inner_text(),
#                     "tehsil":               await page.locator("#lbl_tehsil").inner_text(),
#                     "district":             await page.locator("#lbl_district").inner_text(),
#                     "qty":                  await page.locator("#lbl_qty_to_Transport_Tonne").inner_text(),
#                     "mineral":              await page.locator("#lbl_type_of_mining_mineral").inner_text(),
#                     "loading_from":         await page.locator("#lbl_loadingfrom").inner_text(),
#                     "destination":          await page.locator("#lbl_destination_address").inner_text(),
#                     "destination_district": await page.locator("#lbl_destination_district").inner_text(),
#                     "generated_on":         await page.locator("#txt_eFormC_generated_on").inner_text(),
#                     "valid_upto":           await page.locator("#txt_eFormC_valid_upto").inner_text(),
#                     "travel_duration":      await page.locator("#lbl_travel_duration").inner_text(),
#                     "pit_value":            await page.locator("#lblSellingPrice").inner_text(),
#                     "registration_number":  await page.locator("#lbl_registraton_number_of_vehicle").inner_text(),
#                     "driver_name":          await page.locator("#lbl_name_of_driver").inner_text(),
#                     "driver_mobile":        await page.locator("#lbl_mobile_number_of_driver").inner_text(),
#                     "vehicle_type":         "14 TYRE TRUCK",
#                 }
#                 # ─────────────────────────────────────────────────────────────

#                 # ── Append time to date fields ───────────────────────────────
#                 _now_time            = datetime.now().strftime("%I:%M:%S %p")
#                 data["generated_on"] = append_time(data["generated_on"], _now_time)
#                 data["valid_upto"]   = append_time(data["valid_upto"],   _now_time)
#                 # ─────────────────────────────────────────────────────────────

#                 # ── Apply field overrides ────────────────────────────────────
#                 dom_updates = {}   # collects what needs to go back to DOM

#                 if field_overrides:
#                     resolved = dict(field_overrides)

#                     # Resolve days-based valid_upto
#                     if "__valid_upto_days__" in resolved:
#                         days          = resolved.pop("__valid_upto_days__")
#                         base_date_str = resolved.get("generated_on", data["generated_on"])
#                         computed      = compute_valid_upto(base_date_str, days)
#                         resolved["valid_upto"]       = computed
#                         resolved["valid_upto_label"] = computed
#                         logger.info(f"  ↳ valid_upto: {base_date_str} + {days}d = {computed}")

#                     # Append time to user-supplied generated_on if plain date
#                     if "generated_on" in resolved:
#                         resolved["generated_on"] = append_time(
#                             resolved["generated_on"], _now_time
#                         )

#                     # Apply to data dict
#                     for k, v in resolved.items():
#                         if k in data:
#                             data[k] = v
#                             logger.info(f"  ↳ Override: {k} = {v!r}")

#                     # Mirror valid_upto → label if not explicitly set
#                     if "valid_upto" in resolved and "valid_upto_label" not in resolved:
#                         resolved["valid_upto_label"] = resolved["valid_upto"]

#                     dom_updates = resolved

#                 # Always push these to DOM (time-appended dates + serial)
#                 dom_updates.setdefault("generated_on",     data["generated_on"])
#                 dom_updates.setdefault("valid_upto",       data["valid_upto"])
#                 dom_updates.setdefault("valid_upto_label", data["valid_upto"])
#                 dom_updates.setdefault("serial_number",    data["serial_number"])

#                 await apply_overrides_to_page(page, dom_updates)
#                 # ─────────────────────────────────────────────────────────────

#                 # ── Screenshot ───────────────────────────────────────────────
#                 timestamp           = datetime.now().strftime("%Y%m%d_%H%M%S")
#                 screenshot_filename = f"{tp_num}_{timestamp}.png"
#                 screenshot_path     = f"screenshot/{screenshot_filename}"
#                 await page.screenshot(path=screenshot_path, full_page=True)
#                 logger.info(f"📸 Screenshot: {screenshot_path}")
#                 # ─────────────────────────────────────────────────────────────

#                 # ── Convert screenshot → white-background PDF ─────────────────
#                 ss_pdf_filename = f"{tp_num}_{timestamp}_ss.pdf"
#                 ss_pdf_path     = f"ss_pdf/{ss_pdf_filename}"
#                 screenshot_to_pdf(screenshot_path, ss_pdf_path)
#                 # ─────────────────────────────────────────────────────────────

#                 # ── Upload to VPS ─────────────────────────────────────────────
#                 try:
#                     qr_url = upload_file_to_vps(ss_pdf_path, ss_pdf_filename)
#                     logger.info(f"  ✅ Hosted: {qr_url}")
#                 except Exception as upload_err:
#                     logger.warning(f"  ⚠️ Upload failed: {upload_err} — fallback to TP URL")
#                     qr_url = url
#                 # ─────────────────────────────────────────────────────────────

#                 # ── Generate final PDF with QR ────────────────────────────────
#                 data["qr_url"] = qr_url
#                 final_pdf_path = f"pdf/{tp_num}.pdf"
#                 generate_pdf(data, template_path, final_pdf_path)
#                 all_pdfs.append((tp_num, final_pdf_path))
#                 logger.info(f"✅ PDF: {final_pdf_path}  |  QR → {qr_url}")
#                 # ─────────────────────────────────────────────────────────────

#                 if log_callback:
#                     msg = f"✅ {tp_num} generated"
#                     if inspect.iscoroutinefunction(log_callback):
#                         await log_callback(msg)
#                     else:
#                         log_callback(msg)

#                 if send_pdf_callback:
#                     if inspect.iscoroutinefunction(send_pdf_callback):
#                         await send_pdf_callback(final_pdf_path, tp_num)
#                     else:
#                         send_pdf_callback(final_pdf_path, tp_num)

#                 await page.close()

#             except Exception as e:
#                 logger.error(f"❌ Failed TP {tp_num}: {e}")

#         await browser.close()

#     return all_pdfs


# # ── main() kept for local testing only — NOT called in production ─────────────
# # async def main():
# #     TEST_TP_NUMBERS = ["3111230699026810767"]
# #     TEMPLATE_PATH   = "form_template.pdf"
# #     results = await pdf_gen(
# #         tp_num_list=TEST_TP_NUMBERS,
# #         template_path=TEMPLATE_PATH,
# #     )
# #     for tp_num, path in results:
# #         print(f"✅ {tp_num} → {path}")
# #
# # if __name__ == "__main__":
# #     import asyncio
# #     asyncio.run(main())

import os
import inspect
import logging
from io import BytesIO
from datetime import datetime, timedelta
import qrcode
import paramiko
from PIL import Image as PilImage, ImageDraw, ImageFont

from playwright.async_api import async_playwright
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from PyPDF2 import PdfReader, PdfWriter
import re

# ---------- Logging Setup ----------
logging.basicConfig(
    format='[%(asctime)s] %(levelname)s: %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
# -----------------------------------

# ── VPS / SFTP Configuration ────────────────────────────────────────────────
VPS_CONFIG = {
    "host":            "194.238.18.112",
    "port":            22,
    "username":        "root",
    "password":        "29032001@Abhi",
    "ssh_key_path":    None,
    "remote_dir":      "/var/www/html/screenshots",
    "public_base_url": "http://194.238.18.112/screenshots",
}

# ── Netlify Viewer Base URL ──────────────────────────────────────────────────
NETLIFY_VIEWER_BASE_URL = "https://qme-qr.netlify.app/"
# ─────────────────────────────────────────────────────────────────────────────

# ── Watermark / header text to draw on screenshot ───────────────────────────
SCREENSHOT_HEADER_TEXT = "Back"
# ─────────────────────────────────────────────────────────────────────────────


def add_header_text(image_path: str, text: str) -> None:
    """
    Draw `text` at the top of the image in blue with an underline.
    Overwrites the file in-place.
    """
    img  = PilImage.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    img_w = img.size[0]

    # ── Font: try to load a bold TTF, fall back to PIL default ──
    font_size = 28
    font = None
    for font_path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]:
        if os.path.exists(font_path):
            try:
                font = ImageFont.truetype(font_path, font_size)
                break
            except Exception:
                pass
    if font is None:
        font = ImageFont.load_default()

    # ── Measure text ──
    bbox   = draw.textbbox((0, 0), text, font=font)
    t_w    = bbox[2] - bbox[0]
    t_h    = bbox[3] - bbox[1]

    x = 16   # left-aligned with padding
    y = 10                    # 10px from top

    # ── Blue link colour + underline ──
    blue = (0, 0, 200)
    draw.text((x, y), text, font=font, fill=blue)
    underline_y = y + t_h + 4
    draw.line([(x, underline_y), (x + t_w, underline_y)], fill=blue, width=2)

    img.save(image_path)
    logger.info(f"  🖊️  Header text drawn: '{text}'")


def upload_file_to_vps(local_path: str, filename: str) -> str:
    """Upload file to VPS via SFTP. Returns public URL."""
    cfg       = VPS_CONFIG
    transport = paramiko.Transport((cfg["host"], cfg["port"]))

    try:
        if cfg.get("ssh_key_path"):
            key = paramiko.RSAKey.from_private_key_file(cfg["ssh_key_path"])
            transport.connect(username=cfg["username"], pkey=key)
            logger.info(f"🔐 SFTP connected via SSH key")
        else:
            transport.connect(username=cfg["username"], password=cfg["password"])
            logger.info(f"🔐 SFTP connected via password")

        sftp = paramiko.SFTPClient.from_transport(transport)

        try:
            sftp.stat(cfg["remote_dir"])
        except FileNotFoundError:
            sftp.mkdir(cfg["remote_dir"])
            logger.info(f"  📁 Created remote dir: {cfg['remote_dir']}")

        remote_path = f"{cfg['remote_dir']}/{filename}"
        sftp.put(local_path, remote_path)
        logger.info(f"  ☁️  Uploaded: {local_path} → {remote_path}")
        sftp.close()
    finally:
        transport.close()

    public_url = f"{cfg['public_base_url'].rstrip('/')}/{filename}"
    logger.info(f"  🔗 Public URL: {public_url}")
    return public_url


# Maps field_overrides keys → CSS selectors on the web page
FIELD_SELECTOR_MAP = {
    "distance":             "#lbl_distrance",
    "lessee_name":          "#lbl_name_of_license",
    "lessee_mobile":        "#lbl_mobile_no",
    "serial_number":        "#lbl_SerialNumber",
    "lessee_id":            "#lbl_LicenseId",
    "lease_details":        "#lbl_licenseDetails",
    "tehsil":               "#lbl_tehsil",
    "district":             "#lbl_district",
    "qty":                  "#lbl_qty_to_Transport_Tonne",
    "mineral":              "#lbl_type_of_mining_mineral",
    "loading_from":         "#lbl_loadingfrom",
    "destination":          "#lbl_destination_address",
    "destination_district": "#lbl_destination_district",
    "generated_on":         "#txt_eFormC_generated_on",
    "valid_upto":           "#txt_eFormC_valid_upto",
    "valid_upto_label":     "#lbl_formValidUpTo",
    "travel_duration":      "#lbl_travel_duration",
    "pit_value":            "#lblSellingPrice",
    "registration_number":  "#lbl_registraton_number_of_vehicle",
    "driver_name":          "#lbl_name_of_driver",
    "driver_mobile":        "#lbl_mobile_number_of_driver",
}


def append_time(date_str: str, time_str: str | None = None) -> str:
    """Append HH:MM:SS AM/PM to a date string. Skips if already present."""
    if "AM" in date_str.upper() or "PM" in date_str.upper():
        return date_str
    if time_str is None:
        time_str = datetime.now().strftime("%I:%M:%S %p")
    return f"{date_str} {time_str}"


def compute_valid_upto(generated_on_str: str, days: int) -> str:
    """Add `days` to the date in generated_on_str, preserving time component."""
    date_part = generated_on_str.strip().split(" ")[0]
    time_part = " ".join(generated_on_str.strip().split(" ")[1:]) or None

    DATE_FORMATS = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"]
    base_date = None
    for fmt in DATE_FORMATS:
        try:
            base_date = datetime.strptime(date_part, fmt)
            break
        except ValueError:
            continue
    if base_date is None:
        logger.warning(f"  ⚠ Could not parse {generated_on_str!r}, using today.")
        base_date = datetime.today()

    result_date = (base_date + timedelta(days=days)).strftime("%d/%m/%Y")
    return append_time(result_date, time_part if time_part else None)


def draw_data(c, data):
    c.setFont("Helvetica-Bold", 6)

    def draw_wrapped_text(x, y, text, max_words=4, line_spacing=6):
        words = text.split()
        lines = []
        for i in range(0, len(words), max_words):
            lines.append(" ".join(words[i:i + max_words]))
        for i, line in enumerate(lines[:3]):
            c.drawString(x, y - i * line_spacing, line)

    raw_emM11   = data.get("emM11", "")
    clean_emM11 = re.sub(r"[^\d]", "", raw_emM11)
    c.drawString(273, 764.4, clean_emM11)
    c.drawString(430, 763, data.get("lessee_id", ""))

    draw_wrapped_text(102, 752, data.get("lessee_name", ""))
    c.drawString(270, 751, data.get("lessee_mobile", ""))
    draw_wrapped_text(430, 752, data.get("lease_details", ""))

    c.drawString(100, 724, data.get("tehsil", ""))
    c.drawString(270, 724, data.get("district", ""))
    c.drawString(405, 717, data.get("qty", ""))

    draw_wrapped_text(103, 706, data.get("mineral", ""))
    c.drawString(270, 706, data.get("loading_from", ""))
    draw_wrapped_text(435, 707, data.get("destination", ""))

    c.drawString(135, 688, data.get("distance", "") + " K.M.")
    _gen = data.get("generated_on", "")
    _gen_parts = _gen.rsplit(" ", 2)  # split off AM/PM token
    _gen_date  = " ".join(_gen_parts[:-1]) if len(_gen_parts) > 1 else _gen
    _gen_ampm  = _gen_parts[-1] if len(_gen_parts) > 1 else ""
    c.drawString(270, 687.5, _gen_date)
    c.drawString(270, 679.5, _gen_ampm)
    c.drawString(435, 687.5, data.get("valid_upto", ""))

    c.drawString(265, 669, data.get("travel_duration", ""))
    c.drawString(90,  669, data.get("destination_district", ""))

    c.drawString(110, 645, data.get("pit_value", ""))

    c.drawString(160, 628, data.get("registration_number", ""))
    c.drawString(170, 618, data.get("driver_mobile", ""))
    c.drawString(320, 628, data.get("vehicle_type", ""))
    c.drawString(350, 618, data.get("driver_dl", ""))
    c.drawString(520, 628, data.get("driver_name", ""))

    c.drawString(320, 655, data.get("serial_number", ""))

    # ── QR code ───────────────────────────────────────────────────────────────
    qr_url = data.get("qr_url")
    if qr_url:
        try:
            qr_img    = qrcode.make(qr_url)
            qr_buffer = BytesIO()
            qr_img.save(qr_buffer, format="PNG")
            qr_buffer.seek(0)
            qr_image  = ImageReader(qr_buffer)

            qr_size        = 40
            PAGE_WIDTH, PAGE_HEIGHT = A4
            margin_right   = 70
            margin_top     = 30
            padding        = 5

            x_qr = PAGE_WIDTH  - qr_size - margin_right
            y_qr = PAGE_HEIGHT - qr_size - margin_top

            c.setFillColorRGB(1, 1, 1)
            c.rect(x_qr - padding, y_qr - padding,
                   qr_size + padding * 2, qr_size + padding * 2,
                   fill=True, stroke=False)
            c.drawImage(qr_image, x_qr, y_qr,
                        width=qr_size, height=qr_size,
                        preserveAspectRatio=True, mask='auto')
            logger.info(f"  ✅ QR drawn → {qr_url}")
        except Exception as e:
            logger.warning(f"⚠️ QR drawing failed: {e}")


def generate_pdf(data, template_path, output_path):
    """Generate merged PDF (template + overlay data + QR)."""
    overlay_stream = BytesIO()
    c = canvas.Canvas(overlay_stream, pagesize=A4)
    draw_data(c, data)
    c.save()
    overlay_stream.seek(0)

    bg_reader = PdfReader(template_path)
    ov_reader = PdfReader(overlay_stream)
    writer    = PdfWriter()

    page = bg_reader.pages[0]
    page.merge_page(ov_reader.pages[0])
    writer.add_page(page)

    with open(output_path, "wb") as f:
        writer.write(f)


async def apply_overrides_to_page(page, field_overrides: dict):
    """Push overridden values into DOM so screenshot reflects them."""
    for key, value in field_overrides.items():
        selector = FIELD_SELECTOR_MAP.get(key)
        if not selector:
            continue
        try:
            element = page.locator(selector)
            tag     = await element.evaluate("el => el.tagName.toLowerCase()")
            if tag in ("input", "textarea"):
                await element.evaluate(f"el => el.value = {repr(value)}")
            else:
                await element.evaluate(f"el => el.innerText = {repr(value)}")
            logger.info(f"  ↳ DOM: {key} = {value!r}")
        except Exception as e:
            logger.warning(f"  ⚠️ DOM update failed {key}: {e}")


async def pdf_gen(
    tp_num_list,
    template_path="form_template.pdf",
    log_callback=None,
    send_pdf_callback=None,
    field_overrides: dict | None = None,
):
    """
    Generate PDFs for each TP number.

    field_overrides keys (all optional — pass only what you want to override):
        destination          str   e.g. "Lucknow"
        destination_district str   e.g. "Lucknow"
        generated_on         str   e.g. "27/02/2026"  (time auto-appended)
        distance             str   e.g. "45"
        serial_number        str   e.g. "AAQGG704751"
        __valid_upto_days__  int   e.g. 2  (computed as generated_on + N days)
    """
    if not tp_num_list:
        logger.info("ℹ️ No TP numbers provided.")
        return []

    os.makedirs("pdf",        exist_ok=True)
    os.makedirs("screenshot", exist_ok=True)
    all_pdfs = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx     = await browser.new_context()

        for tp_num in tp_num_list:
            tp_num = str(tp_num)
            logger.info(f"📦 Processing TP: {tp_num}")
            try:
                page = await ctx.new_page()
                url  = (
                    f"https://upmines.upsdc.gov.in//licensee/"
                    f"PrintLicenseeFormVehicleCheckValidOrNot.aspx?eId={tp_num}"
                )
                await page.goto(url, timeout=20000)

                lbl_etpNo = await page.locator("#lbl_eForm_cNo").inner_text()
                if tp_num not in lbl_etpNo:
                    raise ValueError(f"Mismatch: expected {tp_num}, got {lbl_etpNo}")

                # ── Scrape all fields ────────────────────────────────────────
                data = {
                    "distance":             await page.locator('#lbl_distrance').inner_text(),
                    "destination_state":    "Uttar Pradesh",
                    "emM11":                tp_num,
                    "lessee_name":          await page.locator('#lbl_name_of_license').inner_text(),
                    "lessee_mobile":        await page.locator("#lbl_mobile_no").inner_text(),
                    "serial_number":        await page.locator("#lbl_SerialNumber").inner_text(),
                    "lessee_id":            await page.locator("#lbl_LicenseId").inner_text(),
                    "lease_details":        await page.locator('#lbl_licenseDetails').inner_text(),
                    "tehsil":               await page.locator("#lbl_tehsil").inner_text(),
                    "district":             await page.locator("#lbl_district").inner_text(),
                    "qty":                  await page.locator("#lbl_qty_to_Transport_Tonne").inner_text(),
                    "mineral":              await page.locator("#lbl_type_of_mining_mineral").inner_text(),
                    "loading_from":         await page.locator("#lbl_loadingfrom").inner_text(),
                    "destination":          await page.locator("#lbl_destination_address").inner_text(),
                    "destination_district": await page.locator("#lbl_destination_district").inner_text(),
                    "generated_on":         await page.locator("#txt_eFormC_generated_on").inner_text(),
                    "valid_upto":           await page.locator("#txt_eFormC_valid_upto").inner_text(),
                    "travel_duration":      await page.locator("#lbl_travel_duration").inner_text(),
                    "pit_value":            await page.locator("#lblSellingPrice").inner_text(),
                    "registration_number":  await page.locator("#lbl_registraton_number_of_vehicle").inner_text(),
                    "driver_name":          await page.locator("#lbl_name_of_driver").inner_text(),
                    "driver_mobile":        await page.locator("#lbl_mobile_number_of_driver").inner_text(),
                    "vehicle_type":         "14 TYRE TRUCK",
                }
                # ─────────────────────────────────────────────────────────────

                # ── Append time to date fields ───────────────────────────────
                _now_time            = datetime.now().strftime("%I:%M:%S %p")
                data["generated_on"] = append_time(data["generated_on"], _now_time)
                data["valid_upto"]   = append_time(data["valid_upto"],   _now_time)
                # ─────────────────────────────────────────────────────────────

                # ── Apply field overrides ────────────────────────────────────
                dom_updates = {}

                if field_overrides:
                    resolved = dict(field_overrides)

                    if "__valid_upto_days__" in resolved:
                        days          = resolved.pop("__valid_upto_days__")
                        base_date_str = resolved.get("generated_on", data["generated_on"])
                        computed      = compute_valid_upto(base_date_str, days)
                        resolved["valid_upto"]       = computed
                        resolved["valid_upto_label"] = computed
                        logger.info(f"  ↳ valid_upto: {base_date_str} + {days}d = {computed}")

                    if "generated_on" in resolved:
                        resolved["generated_on"] = append_time(
                            resolved["generated_on"], _now_time
                        )

                    for k, v in resolved.items():
                        if k in data:
                            data[k] = v
                            logger.info(f"  ↳ Override: {k} = {v!r}")

                    if "valid_upto" in resolved and "valid_upto_label" not in resolved:
                        resolved["valid_upto_label"] = resolved["valid_upto"]

                    dom_updates = resolved

                dom_updates.setdefault("generated_on",     data["generated_on"])
                dom_updates.setdefault("valid_upto",       data["valid_upto"])
                dom_updates.setdefault("valid_upto_label", data["valid_upto"])
                dom_updates.setdefault("serial_number",    data["serial_number"])

                await apply_overrides_to_page(page, dom_updates)
                # ─────────────────────────────────────────────────────────────

                # ── Screenshot ───────────────────────────────────────────────
                timestamp           = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_filename = f"{tp_num}_{timestamp}.png"
                screenshot_path     = f"screenshot/{screenshot_filename}"
                await page.screenshot(path=screenshot_path, full_page=True)
                logger.info(f"📸 Screenshot: {screenshot_path}")

                # ── Crop left/right margins ───────────────────────────────────
                _crop_px = 170
                _img     = PilImage.open(screenshot_path)
                _w, _h   = _img.size
                _img     = _img.crop((_crop_px, 0, _w - _crop_px, _h))
                _img.save(screenshot_path)
                logger.info(f"  ✂️  Cropped {_crop_px}px each side → {_w - _crop_px * 2}px wide")

                # ── Draw blue underlined header text on top ───────────────────
                add_header_text(screenshot_path, SCREENSHOT_HEADER_TEXT)
                # ─────────────────────────────────────────────────────────────

                # ── Upload screenshot PNG to VPS ──────────────────────────────
                try:
                    raw_img_url = upload_file_to_vps(screenshot_path, screenshot_filename)
                    logger.info(f"  ✅ Screenshot hosted: {raw_img_url}")
                except Exception as upload_err:
                    logger.warning(f"  ⚠️ Upload failed: {upload_err} — fallback to TP URL")
                    raw_img_url = url

                # ── Build Netlify viewer URL ──────────────────────────────────
                import urllib.parse
                encoded_img_url = urllib.parse.quote(raw_img_url, safe="")
                qr_url = f"{NETLIFY_VIEWER_BASE_URL.rstrip('/')}/?img={encoded_img_url}"
                logger.info(f"  🔗 Netlify viewer URL: {qr_url}")
                # ─────────────────────────────────────────────────────────────

                # ── Generate final PDF with QR ────────────────────────────────
                data["qr_url"] = qr_url
                final_pdf_path = f"pdf/{tp_num}.pdf"
                generate_pdf(data, template_path, final_pdf_path)
                all_pdfs.append((tp_num, final_pdf_path))
                logger.info(f"✅ PDF: {final_pdf_path}  |  QR → {qr_url}")
                # ─────────────────────────────────────────────────────────────

                if log_callback:
                    msg = f"✅ {tp_num} generated"
                    if inspect.iscoroutinefunction(log_callback):
                        await log_callback(msg)
                    else:
                        log_callback(msg)

                if send_pdf_callback:
                    if inspect.iscoroutinefunction(send_pdf_callback):
                        await send_pdf_callback(final_pdf_path, tp_num)
                    else:
                        send_pdf_callback(final_pdf_path, tp_num)

                await page.close()

            except Exception as e:
                logger.error(f"❌ Failed TP {tp_num}: {e}")

        await browser.close()

    return all_pdfs


# ── main() kept for local testing only — NOT called in production ─────────────
async def main():
    TEST_TP_NUMBERS = ["3111230699026810767"]
    TEMPLATE_PATH   = "form_template.pdf"
    results = await pdf_gen(
        tp_num_list=TEST_TP_NUMBERS,
        template_path=TEMPLATE_PATH,
    )
    for tp_num, path in results:
        print(f"✅ {tp_num} → {path}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
