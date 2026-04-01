from playwright.sync_api import sync_playwright
import random
import time

def get_random_user_agent():
    return random.choice([
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/134.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/134.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0"
    ])

def scrape_asin_html(asin):
    url = f"https://www.amazon.in/dp/{asin}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent=get_random_user_agent(),
            viewport={"width": 1366, "height": 768}
        )

        page = context.new_page()

        page.goto(url, timeout=60000)

        # optional delay to let JS fully render
        time.sleep(3)

        html = page.content()   # 🔥 THIS is what you want

        browser.close()
        return html


html = scrape_asin_html("B0DRCT1MTK")

print(html)   # preview first 2000 chars