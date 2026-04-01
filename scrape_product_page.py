import time
import random
import re
from datetime import datetime
from playwright.sync_api import sync_playwright
import AmazonScrapper as scraper
import extract_variants_with_dimensions as ext
from scraper_logger import log_block,scraper_logger

if __name__ == "__main__":
    scraper = scraper.AmazonScraperMT(
        file_path="SCRAPPED_DATA/amazon_scrapamazonbykeywords.csv",
        mode="scrapAmazonByASIN",      # ← this now works
        max_workers=3
    )
    scraper.run()

# ====================== ENHANCED scrape_product_page (ALL REQUESTED PROPERTIES) ======================
def scrape_product_page(page, asin: str):
    """Full production scraper for ONE parent ASIN.
    Extracts EVERY property you asked for + rich child ASINs with size/color/pack/etc."""
    all_data = []
    with log_block("Product Parameters Extraction", asin, page=page):
        url = f"https://www.amazon.in/dp/{asin}"
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("#productTitle", timeout=20000)
    # === CRITICAL WAIT FOR ICONS / VARIANTS TO LOAD ===
    #with log_block("Optional Icons/Variants Wait", asin, page=page):
    optional_signals_found = False
    wait_until = time.time() + 8
    while time.time() < wait_until:
        if (
                page.locator("#twister").count() > 0
                or page.get_by_text("Returnable", exact=False).count() > 0
                or page.get_by_text("Top Brand", exact=False).count() > 0
                or page.get_by_text("Warranty", exact=False).count() > 0
        ):
            optional_signals_found = True
            break
        time.sleep(0.4)
    if not optional_signals_found:
        scraper_logger.info(f"⏳ No icons/variants row found after optional wait | ASIN: {asin}")
    time.sleep(random.uniform(3, 6))
    # ==================== BASIC FIELDS ====================
    title = page.locator("#productTitle").inner_text(timeout=5000).strip() if page.query_selector("#productTitle") else "N/A"
    brand = None
    with log_block("BRAND", asin, page=page):
        brand_el = page.query_selector("#bylineInfo")
        brand = brand_el.inner_text().strip() if brand_el else None

    with log_block("amazon_choice | top_brand", asin, page=page):
        amazon_choice = page.locator('text="Amazon\'s Choice"').count() > 0
        top_brand = page.locator('text="Top Brand"').count() > 0

    # Features / Bullet points
    features = []
    with log_block("bullets | features", asin, page=page):
        bullets = page.query_selector_all("#feature-bullets li span.a-list-item")
        features = [b.inner_text().strip() for b in bullets if b.inner_text().strip()]
    bullet_points_count = len(features)

    # Title length
    title_length = len(title)

    # Warranty
    warranty = None
    with log_block("Warranty", asin, page=page):
        loc = page.locator('text=/\\d+\\s*Year\\s*Warranty/i').first
        if loc.count() > 0:
            warranty = loc.inner_text().strip()
        else:
            warranty = page.locator('text=/Warranty/i').first.inner_text().strip()
    if not warranty:
        with log_block("Warranty", asin, page=page):
            full_text = page.inner_text("body")
            m = re.search(r'(?i)\b(?:\d+\s*(?:year|month|day)s?\s*)?warranty[^\.\n]{0,200}', full_text)
            if m:
                warranty = m.group(0).strip()[:250]


        # BSR + Category (both main + sub-category if possible)
    bsr = None
    category = None
    sub_category = None
    with log_block("bsr | category | sub_category", asin, page=page):
        full_text = page.inner_text("body")
        matches = re.findall(r'#([\d,]+)\s+in\s+([^\n(]+)', full_text, re.I)
        if matches:
            bsr = int(matches[0][0].replace(",", ""))
            category = matches[0][1].strip()
            if len(matches) > 1:
                sub_category = matches[1][1].strip()

    # Buybox seller
    buybox_seller = None
    with log_block("buybox_seller", asin, page=page):
        seller_elem = page.query_selector("#sellerProfileTriggerId")
        if seller_elem:
            buybox_seller = seller_elem.inner_text().strip()
    if not buybox_seller:
        with log_block("buybox_seller-full_text", asin, page=page):
            full_text = page.inner_text("body")
            m = re.search(r'Sold by\s+([^\n]+?)(?:\s+and|\s*\(|$)', full_text, re.I)
            if m:
                buybox_seller = m.group(1).strip()

    # Price, MRP, Discount Gap
    price = None
    mrp = None
    discount_percent = None
    with log_block("price | mrp | discount_percent", asin, page=page):
        price_el = page.query_selector(".a-price .a-offscreen")
        if price_el:
            price = price_el.inner_text().strip()

        mrp_el = page.query_selector("#listPrice, .a-text-price span.a-price.a-text-price, .a-price.a-text-price")
        if mrp_el:
            mrp = mrp_el.inner_text().strip()

        if price and mrp:
            p = float(re.sub(r'[^\d.]', '', price))
            m = float(re.sub(r'[^\d.]', '', mrp))
            if m > 0:
                discount_percent = round((m - p) / m * 100, 2)

    # Bought in last month
    bought_in_last_month = None
    with log_block("bought_in_last_month", asin, page=page):
        bought_el = page.locator('span.a-size-base').filter(
            has_text=re.compile(r'\d+\s+bought?\s+in?\s+past?\s+month', re.I)).first
        if bought_el.count() > 0:
            bought_in_last_month = bought_el.inner_text().strip()

    # Manufacturer
    manufacturer = None
    with log_block("manufacturer", asin, page=page):
        for row in page.query_selector_all("#productDetails_techSpec_section_1 tr, #detailBullets_feature_div ul li"):
            text = row.inner_text().strip()
            if any(k in text.lower() for k in ["manufacturer", "made by", "mfg"]):
                manufacturer = text.split(":", 1)[-1].strip() if ":" in text else text
                break

    # Size / Weight (from technical details)
    size_weight = None
    with log_block("manufacturer", asin, page=page):
        for row in page.query_selector_all("#productDetails_techSpec_section_1 tr, .a-keyvalue tr"):
            text = row.inner_text().strip().lower()
            if any(k in text for k in ["size", "weight", "dimensions", "package dimensions"]):
                size_weight = row.inner_text().strip()
                break

    # Image Count
    image_count = 0
    with log_block("image_count", asin, page=page):
        imgs = page.query_selector_all(
            "#altImages img, #main-image-container img, div.imgTagWrapper img, #landingImage")
        image_count = len([img for img in imgs if img.get_attribute("src")])

    # Reviews count
    reviews_exact = None
    with log_block("reviews_exact", asin, page=page):
        txt = page.query_selector("#acrCustomerReviewText")
        if txt:
            #reviews_exact = int(txt.inner_text().replace(",", "").split()[0])
            review_text = txt.inner_text().strip()
            match = re.search(r"\d[\d,]*", review_text)
            if match:
                reviews_exact = int(match.group(0).replace(",", ""))

        # Scrape date
        scrape_date = datetime.now().strftime("%Y-%m-%d %H:%M")

    with log_block("extract_variants_with_dimensions", asin, page=page):
        # ==================== CHILD ASINS + DIMENSIONS (size, color, pack, etc.) ====================
        variants_info = ext.extract_variants_with_dimensions(page, asin)

    with log_block("FINAL RECORD", asin, page=page):
        # ==================== FINAL RECORD ====================
        record = {
            "parent_asin": asin,
            "asin": asin,
            "title": title,
            "title_length": title_length,
            "brand": brand,
            "manufacturer": manufacturer,
            "price": price,
            "mrp": mrp,
            "discount_percent": discount_percent,
            "bought_in_last_month": bought_in_last_month,
            "warranty": warranty,
            "amazon_choice": amazon_choice,
            "top_brand": top_brand,
            "reviews_exact": reviews_exact,
            "bsr": bsr,
            "category": category,
            "sub_category": sub_category,
            "buybox_seller": buybox_seller,
            "image_count": image_count,
            "bullet_points_count": bullet_points_count,
            "size_weight": size_weight,
            "scrape_date": scrape_date,

            # Child ASINs with full dimension mapping
            "child_asins": variants_info["child_asins"],
            "variants": variants_info["variants"],          # each child with size/color/pack etc.
            "dimensions": variants_info["dimensions"],      # e.g. ["size_name", "color_name", "pack_size_name"]
        }

        all_data.append(record)

    page.close()
    time.sleep(random.uniform(4, 8))
    return all_data