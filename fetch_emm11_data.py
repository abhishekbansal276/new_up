import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL = "https://upmines.upsdc.gov.in//licensee/PrintLicenseeFormVehicleCheckValidOrNot.aspx?eId={}"
HEADLESS = True
CONCURRENCY_LIMIT = 10

async def fetch_single_emm11(playwright, emm11_num, district, log=print):
    url = BASE_URL.format(emm11_num)
    
    # Launch browser in headed mode to see it
    browser = await playwright.chromium.launch(headless=True, slow_mo=50)  # slow_mo=50ms per action
    page = await browser.new_page()

    try:
        log(f"🔍 Opening page for {emm11_num}")
        await page.goto(url, timeout=20000)  # increase timeout for slow pages

        # Optional: take screenshot for debugging
        await page.screenshot(path=f"screenshots/{emm11_num}.png")

        await page.wait_for_selector("#lbl_district", timeout=10000)
        district_text = await page.locator("#lbl_district").inner_text()
        quantity = await page.locator("#lbl_qty_to_Transport_Tonne").inner_text()
        address = await page.locator("#lbl_destination_address").inner_text()
        generated_on = await page.locator("#txt_eFormC_generated_on").inner_text()

        if district.upper() in district_text.strip().upper():
            return {
                "eMM11_num": emm11_num,
                "destination_district": district_text.strip(),
                "quantity_to_transport": quantity.strip(),
                "destination_address": address.strip(),
                "generated_on": generated_on.strip()
            }

    except Exception as e:
        log(f"[{emm11_num}] Error or Timeout: {e}")
    finally:
        # Keep browser open for debugging
        # await browser.close()
        pass

    return None

async def fetch_emm11_data(start_num, end_num, district, data_callback=None, log=print):
    results = []

    async with async_playwright() as playwright:
        semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

        async def limited_fetch(num):
            async with semaphore:
                result = await fetch_single_emm11(playwright, num, district, log=log)
                if result:
                    if data_callback:
                        await data_callback(result)
                    return result
                return None

        tasks = [limited_fetch(i) for i in range(start_num, end_num + 1)]
        all_results = await asyncio.gather(*tasks)

        if not data_callback:
            results = [r for r in all_results if r]
            return results

    return []
