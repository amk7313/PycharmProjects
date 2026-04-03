import time
import random
import re
from datetime import datetime
import  AmazonScrapper as scraper
from scraper_logger import scraper_logger, safe_extract, capture_debug, log_failure, log_block, safe_query

if __name__ == "__main__":
    scraper = scraper.AmazonScraperMT(
        file_path="SCRAPPED_DATA/amazon_products.csv",
        mode="scrapAmazonByKeywords",      # ← this now works
        max_workers=3
    )
    scraper.run()

def scrape_amazon(page) -> list:
    #print("scraping Amazon...huuuh")
    all_data = []
    seen_asins = set()

    keywords = [
        "best seller"
    ]
    sort_options = [""]

    for keyword in keywords:
        for sort in sort_options:
            for page_num in range(1, 2):
                url = (f"https://www.amazon.in/s?k={keyword.replace(' ', '+')}"
                       f"{sort}&page={page_num}")

                with log_block("Search Page Load", url, page=page):
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(random.uniform(2.5, 5.5))

                    # scrolling...
                    for _ in range(random.randint(3, 5)):
                        page.mouse.wheel(0, random.randint(700, 1400))
                        time.sleep(random.uniform(0.7, 1.6))

                    page.wait_for_selector("div.s-main-slot div[data-component-type='s-search-result']",
                                           timeout=15000)

                products = safe_query("Search Results",
                                      "div.s-main-slot div[data-component-type='s-search-result']",
                                      page,
                                      many=True)

                for product in products[:45]:
                    asin = safe_query("ASIN Attribute", "[data-asin]", container=product)
                    if not asin or asin in seen_asins or len(asin) < 8:
                        continue
                    seen_asins.add(asin)

                    with log_block("Product Extraction", asin, page=page):
                        title_elem = safe_query("Title", "h2 span.a-size-medium", product) or safe_query("Title Fallback", "h2 span", product)
                        title = title_elem.inner_text().strip() if title_elem else "N/A"

                    # ==================== PRICE (FIXED) ====================
                    price = None
                    with log_block("Price Extraction",asin,page=page):
                        # Best & most reliable selector
                        price_block = safe_query("Price Block",".a-price .a-offscreen",
                                                   product)
                        if price_block:
                            price_text = price_block.inner_text().replace(",", "").strip()
                            match = re.search(r'\d+', price_text)
                            if match:
                                price = int(match.group(0))
                            # Fallback
                        if not price:
                            whole = safe_query("whole", ".a-price-whole",
                                                 "")
                            if whole:
                                price = int(whole.inner_text().replace(",", "").strip())

                    # Rating
                    rating = None
                    with log_block("Ratings Extraction", asin, page=page):
                        rating_text = safe_query("Ratings", ".a-icon-alt",
                                                   product)
                        if rating_text:
                            rating = float(rating_text.inner_text().split()[0])

                    # Review reliable
                    reviews = None
                    with log_block("Reviews Extraction", asin, page=page):
                        anchor = safe_query(

                            "anchor", "a[href*='customerReviews']",
                                    product)
                        if anchor:
                            txt = anchor.inner_text().replace(",", "")
                            # match = re.search(r'(\d{2,})', txt)
                            # if match:
                            reviews = txt

                        # 2. Fallback: underline text (any size)
                        if not reviews:
                            elem = safe_query("elem", ".s-underline-text",
                                                    product,asin)
                            if elem:
                                txt = elem.inner_text().replace(",", "")
                                if txt.isdigit():
                                    reviews = int(txt)

                        # 3. Fallback: scan spans intelligently
                        if not reviews:
                            spans = safe_query("spans", "span",
                                               product, asin, True)
                            for s in spans:
                                txt = s.inner_text().replace(",", "").strip()

                                # Skip ratings like 4.3
                                if "." in txt:
                                    continue

                                # Reviews are usually > 10
                                # if re.fullmatch(r'\d{2,}', txt):
                                #  reviews = int(txt)
                                # break

                    if price == reviews:
                        # ==================== REVIEWS (FIXED) ====================
                        reviews = None
                        with log_block("REVIEWS (FIXED)", asin, page=page):
                            # 1. Primary: Reviews link
                            anchor = safe_query("anchor", "a[href*='customerReviews']",
                                                product, asin)
                            if anchor:
                                txt = anchor.inner_text().replace(",", "")
                                # match = re.search(r'(\d{2,})', txt)
                                # if match:
                                reviews = txt

                            # 2. Underline text (very common)
                            if not reviews:
                                underline = safe_query("underline", ".s-underline-text",
                                                       product)
                                if underline:
                                    txt = underline.inner_text().replace(",", "").strip()
                                    # if txt.isdigit() and int(txt) > 5:  # avoid tiny numbers
                                    reviews = int(txt)

                            # 3. Strict span fallback - skip anything near price
                            if not reviews:
                                spans = safe_query("spans", "span.a-size-base",
                                                     product,asin,True)
                                for span in spans:
                                    txt = span.inner_text().replace(",", "").strip()
                                    # if "." in txt:  # skip ratings like 4.1
                                    #   continue
                                    # if re.fullmatch(r'\d{3,}', txt):  # only large numbers (>=100)
                                    # Extra safety: skip if parent or nearby has price class
                                    if "a-price" not in str(span.get_attribute("class") or ""):
                                        reviews = int(txt)
                                        break
                    # "X bought in past month" etc.
                    bought = None
                    with log_block("last bought field", asin, page=page):
                        spans = safe_query("spans-bought","span.a-size-base", page,
                                           asin,True)
                        for span in spans:
                            txt = span.inner_text().lower()
                            if any(kw in txt for kw in ["bought", "ordered", "purchased", "past month"]):
                                bought = span.inner_text().strip()
                                break
                    with log_block("Rows", asin, page=page):
                        rows = safe_query("rows", "#productDetails_detailBullets_sections1 tr",
                                            page, asin, True)
                        bsr = None
                        category = None
                        for row in rows:
                            header = safe_query("header","th",row,asin)
                            value = safe_query("value","td",row,asin)
                            if header and "Best Sellers Rank" in header.inner_text():
                                match = re.search(r"#([\d,]+)", value.inner_text())
                                if match:
                                    bsr = int(match.group(1).replace(",", ""))
                                    category = match.group(2).strip()


                    all_data.append({
                        "asin": asin,
                        "title": title,
                        "price": price,
                        "rating": rating,
                        "reviews": reviews,
                        "bought": bought,
                        "keyword": keyword,
                        "sort": "relevance" if not sort else sort,
                        "page": page_num,
                        "scrape_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "bsr": bsr,
                        "category": category
                    })
                scraper_logger.info(f"{all_data} extracted on {datetime.now()}")
                # Polite delay between pages
                time.sleep(random.uniform(4, 8))
    return all_data
