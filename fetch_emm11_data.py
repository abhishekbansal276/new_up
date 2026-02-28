import asyncio
import os
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL = "https://upmines.upsdc.gov.in//licensee/PrintLicenseeFormVehicleCheckValidOrNot.aspx?eId={}"
HEADLESS = True
CONCURRENCY_LIMIT = 10

# Ensure screenshots directory exists
os.makedirs("screenshots", exist_ok=True)


async def fetch_single_emm11(browser, emm11_num, district, log=print):
    """Fetch data for a single eMM11 number using a shared browser instance."""
    url = BASE_URL.format(emm11_num)
    page = await browser.new_page()

    try:
        log(f"🔍 [{emm11_num}] Fetching page...")
        await page.goto(url, timeout=20000)

        # Wait for the key element to confirm page loaded
        await page.wait_for_selector("#lbl_destination_district", timeout=10000)

        # Take screenshot for debugging
        await page.screenshot(path=f"screenshots/{emm11_num}.png")

        # Read all required fields
        district_text = await page.locator("#lbl_destination_district").inner_text()
        quantity      = await page.locator("#lbl_qty_to_Transport_Tonne").inner_text()
        address       = await page.locator("#lbl_destination_address").inner_text()
        generated_on  = await page.locator("#txt_eFormC_generated_on").inner_text()

        # Check if the district matches
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
            log(f"⏭ [{emm11_num}] Skipped — District on page is '{district_text.strip()}', expected '{district.strip()}'")

    except PlaywrightTimeoutError:
        log(f"⏱ [{emm11_num}] Timeout — page took too long to load.")
    except Exception as e:
        log(f"❌ [{emm11_num}] Error: {e}")
    finally:
        await page.close()

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
    log(f"{'='*55}\n")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=HEADLESS, slow_mo=50)
        semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

        checked   = 0
        skipped   = 0
        errors    = 0
        lock      = asyncio.Lock()

        async def limited_fetch(num):
            nonlocal checked, skipped, errors
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

                    # Progress every 10 IDs
                    if checked % 10 == 0 or checked == total:
                        log(
                            f"📊 Progress: {checked}/{total} checked | "
                            f"✅ {len(results)} matched | "
                            f"⏭ {skipped} skipped"
                        )

                return result

        tasks = [limited_fetch(i) for i in range(start_num, end_num + 1)]
        await asyncio.gather(*tasks)
        await browser.close()

    # ── Final summary ──────────────────────────────────────────
    log(f"\n{'='*55}")
    log(f"📋 Scan Complete — Summary")
    log(f"   Range checked : {start_num} → {end_num}  ({total} IDs)")
    log(f"   District      : {district.strip().upper()}")
    log(f"   ✅ Matched     : {len(results)}")
    log(f"   ⏭ Skipped     : {skipped}  (different district / no data)")
    log(f"{'='*55}")

    if not results:
        log(f"\n⚠️  No records found for district '{district.strip().upper()}' in range {start_num}–{end_num}.")
    else:
        log(f"\n🎯 {len(results)} record(s) found for '{district.strip().upper()}':")
        for item in results:
            log(f"   • eMM11 #{item['eMM11_num']} | Qty: {item['quantity_to_transport']} | Generated: {item['generated_on']}")

    return results


# ── Example usage ────────────────────────────────────────────────────────────

# async def main():
#     matched = await fetch_emm11_data(
#         start_num=1000,
#         end_num=1050,
#         district="LUCKNOW",
#     )

# # if __name__ == "__main__":
# #     asyncio.run(main())
