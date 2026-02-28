import asyncio
import os
import random
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL   = "https://upmines.upsdc.gov.in//licensee/PrintLicenseeFormVehicleCheckValidOrNot.aspx?eId={}"
HEADLESS   = True
CONCURRENCY_LIMIT = 10
RETRIES    = 3          # Number of retries per ID on timeout
GOTO_TIMEOUT   = 60000  # ms
SELECT_TIMEOUT = 30000  # ms
RETRY_DELAY    = 2      # seconds between retries

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

os.makedirs("screenshots", exist_ok=True)


async def fetch_single_emm11(browser, emm11_num, district, log=print):
    """
    Fetch data for a single eMM11 number.
    Retries up to RETRIES times on timeout before giving up.
    """
    url = BASE_URL.format(emm11_num)

    for attempt in range(1, RETRIES + 1):
        page = await browser.new_page()
        await page.set_extra_http_headers({
            "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
            "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

        try:
            log(f"🔍 [{emm11_num}] Attempt {attempt}/{RETRIES} — fetching page...")
            await page.goto(url, timeout=GOTO_TIMEOUT, wait_until="domcontentloaded")
            await page.wait_for_selector("#lbl_destination_district", timeout=SELECT_TIMEOUT)
            await page.screenshot(path=f"screenshots/{emm11_num}.png")

            district_text = await page.locator("#lbl_destination_district").inner_text()
            quantity      = await page.locator("#lbl_qty_to_Transport_Tonne").inner_text()
            address       = await page.locator("#lbl_destination_address").inner_text()
            generated_on  = await page.locator("#txt_eFormC_generated_on").inner_text()

            if (
                district.strip().upper() == district_text.strip().upper()
                or district.strip().upper() in district_text.strip().upper()
            ):
                log(f"✅ [{emm11_num}] Match found — District: {district_text.strip()}")
                return {
                    "eMM11_num":             emm11_num,
                    "destination_district":  district_text.strip(),
                    "quantity_to_transport": quantity.strip(),
                    "destination_address":   address.strip(),
                    "generated_on":          generated_on.strip(),
                }
            else:
                log(
                    f"⏭ [{emm11_num}] Skipped — District on page is "
                    f"'{district_text.strip()}', expected '{district.strip()}'"
                )
                return None  # Wrong district — no retry needed

        except PlaywrightTimeoutError:
            log(f"⏱ [{emm11_num}] Timeout on attempt {attempt}/{RETRIES}.")
            try:
                await page.close()
            except Exception:
                pass
            if attempt < RETRIES:
                wait = RETRY_DELAY * attempt + random.uniform(0, 1)
                log(f"   ↻ Retrying in {wait:.1f}s...")
                await asyncio.sleep(wait)
            else:
                log(f"❌ [{emm11_num}] All {RETRIES} attempts timed out. Giving up.")
            continue

        except Exception as e:
            log(f"❌ [{emm11_num}] Unexpected error: {e}")
            try:
                await page.close()
            except Exception:
                pass
            return None

        finally:
            try:
                if not page.is_closed():
                    await page.close()
            except Exception:
                pass

    return None


async def fetch_emm11_data(start_num, end_num, district, data_callback=None, log=print):
    """
    Scrape eMM11 data for a range of IDs.

    Args:
        start_num     : First eMM11 ID to check (inclusive).
        end_num       : Last eMM11 ID to check (inclusive).
        district      : District name to filter results by.
        data_callback : Optional async callable(result_dict) called for each match found.
                        If provided, results are streamed via callback and [] is returned.
                        If None, all results are collected and returned as a list.
        log           : Logging function (default: print).

    Returns:
        List of matched result dicts (only when data_callback is None).
    """
    results = []
    total   = end_num - start_num + 1

    log(f"\n{'='*55}")
    log(f"🚀 Starting eMM11 scan")
    log(f"   Range    : {start_num} → {end_num}  ({total} IDs)")
    log(f"   District : {district.strip().upper()}")
    log(f"   Retries  : {RETRIES} per ID")
    log(f"   Timeout  : {GOTO_TIMEOUT // 1000}s (goto) / {SELECT_TIMEOUT // 1000}s (selector)")
    log(f"{'='*55}\n")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=HEADLESS,
            slow_mo=50,
            args=[
                f"--user-agent={USER_AGENT}",
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
        )

        semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
        checked   = 0
        skipped   = 0
        lock      = asyncio.Lock()

        async def limited_fetch(num):
            nonlocal checked, skipped
            async with semaphore:
                result = await fetch_single_emm11(browser, num, district, log=log)

                async with lock:
                    checked += 1
                    if result:
                        results.append(result)
                        if data_callback:
                            await data_callback(result)
                    else:
                        skipped += 1

                    if checked % 10 == 0 or checked == total:
                        log(
                            f"📊 Progress: {checked}/{total} checked | "
                            f"✅ {len(results)} matched | "
                            f"⏭ {skipped} skipped/timed-out"
                        )

                return result

        tasks = [limited_fetch(i) for i in range(start_num, end_num + 1)]
        await asyncio.gather(*tasks)
        await browser.close()

    log(f"\n{'='*55}")
    log(f"📋 Scan Complete — Summary")
    log(f"   Range checked : {start_num} → {end_num}  ({total} IDs)")
    log(f"   District      : {district.strip().upper()}")
    log(f"   ✅ Matched     : {len(results)}")
    log(f"   ⏭ Skipped     : {skipped}  (different district / no data / timeout)")
    log(f"{'='*55}")

    if not results:
        log(f"\n⚠️  No records found for district '{district.strip().upper()}' in range {start_num}–{end_num}.")
    else:
        log(f"\n🎯 {len(results)} record(s) found for '{district.strip().upper()}':")
        for item in results:
            log(
                f"   • eMM11 #{item['eMM11_num']} | "
                f"Qty: {item['quantity_to_transport']} | "
                f"Generated: {item['generated_on']}"
            )

    return results


# ── Quick debug helper ────────────────────────────────────────────────────────

async def debug_single(emm11_num: int, headless: bool = False):
    """
    Open a single eMM11 page in a visible browser window so you can
    inspect what actually renders. Run this first when the scraper times out
    to confirm the URL and ID are valid.

    Usage:
        asyncio.run(debug_single(3111230699026810767, headless=False))
    """
    print(f"🔎 Opening {BASE_URL.format(emm11_num)}")
    print("   Waiting up to 60s for page to load...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, slow_mo=100)
        page    = await browser.new_page()
        await page.set_extra_http_headers({"Accept-Language": "en-IN,en;q=0.9"})

        try:
            await page.goto(BASE_URL.format(emm11_num), timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_selector("#lbl_destination_district", timeout=30000)

            district = await page.locator("#lbl_destination_district").inner_text()
            qty      = await page.locator("#lbl_qty_to_Transport_Tonne").inner_text()
            addr     = await page.locator("#lbl_destination_address").inner_text()
            gen_on   = await page.locator("#txt_eFormC_generated_on").inner_text()

            print(f"\n✅ Page loaded successfully!")
            print(f"   District  : {district}")
            print(f"   Quantity  : {qty}")
            print(f"   Address   : {addr}")
            print(f"   Generated : {gen_on}")

        except PlaywrightTimeoutError:
            print("❌ Timed out — the page did not load in 60s.")
            print("   Try opening the URL manually in your browser to confirm the ID is valid.")
            await page.screenshot(path=f"screenshots/debug_{emm11_num}.png")
            print(f"   Screenshot saved to screenshots/debug_{emm11_num}.png")
        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            await browser.close()


# ── Example usage ────────────────────────────────────────────────────────────

# Normal range scan:
# async def main():
#     matched = await fetch_emm11_data(
#         start_num = 1000,
#         end_num   = 1050,
#         district  = "RAMPUR",
#     )
#
# if __name__ == "__main__":
#     asyncio.run(main())


# Debug a single ID in a visible browser window:
# if __name__ == "__main__":
#     asyncio.run(debug_single(3111230699026810767, headless=False))
