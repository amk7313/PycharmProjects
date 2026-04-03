import time
import random
import re
from datetime import datetime
from playwright.sync_api import sync_playwright
import AmazonScrapper as scraper
import extract_variants_with_dimensions as ext
from PythonProject.scraper_logger import safe_extract
from scraper_logger import log_block,scraper_logger
import extractChildAsins as eCA

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
    with (log_block("Product Parameters Extraction", asin, page=page)):
        url = f"https://www.amazon.in/dp/{asin}"
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("#productTitle", timeout=20000)
        # Optional soft wait (no crash)
        optional_signals_found = False
        wait_until = time.time() + 8
        while time.time() < wait_until:
            if (
                    page.locator("#twister").count() > 0
                    or page.get_by_text("Returnable", exact=False).count() > 0
                    or page.get_by_text("Top Brand", exact=False).count() > 0
                    or page.get_by_text("Warranty", exact=False).count() > 0):
                optional_signals_found = True
                break
            time.sleep(0.4)
        if not optional_signals_found:
            scraper_logger.info(f"⏳ No icons/variants row found after optional wait | ASIN: {asin}")
        time.sleep(random.uniform(3, 6))

        # ==================== CHILD ASINS + DIMENSIONS (size, color, pack, etc.) ====================
        #variants_info = safe_extract("variants_info",ext.extract_variants_with_dimensions(page, asin),
                  #                   asin)
        # ==================== BASIC FIELDS ====================
        #title = safe_extract("Title",lambda: page.locator("#productTitle").inner_text(timeout=5000).strip(),asin)
        title = safe_extract("Title",
                             lambda: page.locator("span#productTitle").inner_text(timeout=5000).strip(),
                             asin)
        title_length = len(title) if title else scraper_logger.warning(f"{title} "f"empty "f"| DataField: {asin}")
        brand = safe_extract("Brand",
                             lambda: page.query_selector("#bylineInfo").inner_text().strip()
                             if page.query_selector(
                                 "#bylineInfo") else None, asin)
        amazon_choice = safe_extract("Amazon Choice", lambda:
        page.locator('text="Amazon\'s Choice"').count() > 0, asin)
        top_brand = safe_extract("Top Brand", lambda: page.locator('text="Top Brand"').count() > 0, asin)
        features = safe_extract("Features", lambda: [b.inner_text().strip() for b in
                                                     page.query_selector_all
                                                     ("#feature-bullets li span.a-list-item") if
                                                     b.inner_text().strip()], asin)
        bullet_points_count = []
        if features:
            bullet_points_count = len(features)
        #warranty = safe_extract("Warranty", lambda: (
              # page.locator('text=/\\d+\\s*Year\\s*Warranty/i').first.inner_text().strip()
              # if page.locator(
               #    'text=/\\d+\\s*Year\\s*Warranty/i').count() > 0 else
              # page.locator('text=/Warranty/i').first.inner_text().strip()
             #                   ), asin)

        # ====================== RELIABLE WARRANTY EXTRACTION ======================
        warranty = safe_extract(
            "Warranty",
            lambda: (
                # Priority 1: Exact "X Year Warranty"
                page.locator('text=/\\d+\\s*Year\\s*Warranty/i').first.inner_text(timeout=4000).strip()
                if page.locator('text=/\\d+\\s*Year\\s*Warranty/i').count() > 0
                else
                # Priority 2: Any "Warranty" text
                page.locator('text=/Warranty/i').first.inner_text(timeout=4000).strip()
                if page.locator('text=/Warranty/i').count() > 0
                else None
            ),
            asin
        )

        # Optional: Clean up extra spaces
        if warranty:
            warranty = re.sub(r'\s+', ' ', warranty).strip()[:250]

        # BSR + Category (both main + sub-category if possible)
        bsr = None
        category = None
        sub_category = None
        full_text = safe_extract("full_text", lambda: page.inner_text("body"), asin)
        matches = re.findall(r'#([\d,]+)\s+in\s+([^\n(]+)', full_text, re.I)
        if matches:
            bsr = int(matches[0][0].replace(",", ""))
            category = matches[0][1].strip()
            if len(matches) > 1:
                sub_category = matches[1][1].strip()

        # Buybox seller
        buybox_seller = None
        seller_elem = safe_extract("buybox_seller", lambda: page.query_selector("#sellerProfileTriggerId"),
                                       asin)
        if seller_elem:
            buybox_seller = safe_extract("buybox_seller", lambda: seller_elem.inner_text().strip(),
                                             asin)
        if not buybox_seller:
                full_text = safe_extract("full_text", lambda: page.inner_text("body"), asin)

        m = re.search(r'Sold by\s+([^\n]+?)(?:\s+and|\s*\(|$)', full_text, re.I)
        if m:
            buybox_seller = m.group(1).strip()

        # ====================== FIXED PRICE + MRP + DISCOUNT ======================
        price = None
        mrp = None
        discount_percent = None
        # 1. Selling price (most reliable selector)
        price_el = safe_extract("Price",
                                lambda: page.query_selector(
                                    ".a-price .a-offscreen, .aok-inline-block .a-price .a-offscreen"),
                                asin)
        if price_el:
            price = safe_extract("Price Text", lambda: price_el.inner_text().strip(), asin)

        # 2. MRP - only pick basis/list price (avoid per-unit price such as "₹771.11 /100 ml")
        mrp_selectors = [
                "#corePriceDisplay_desktop_feature_div .basisPrice .a-price.a-text-price .a-offscreen",
                "#corePriceDisplay_desktop_feature_div .apex-basisprice-value .a-offscreen",
                "#corePriceDisplay_desktop_feature_div #listPrice .a-offscreen",
                "#corePriceDisplay_desktop_feature_div .basisPrice .a-offscreen",
        ]
        mrp_text = None
        for sel in mrp_selectors:
            mrp_el = safe_extract("MRP", lambda sel=sel: page.query_selector(sel), asin)
            if not mrp_el:
                continue
            candidate = safe_extract("MRP Text", lambda: mrp_el.inner_text().strip(), asin)
            if not candidate:
                continue
            # Strict currency-like extraction; rejects strings without a Rupee amount.
            amount_match = re.search(r'₹\s?[\d,]+(?:\.\d{1,2})?', candidate)
            if amount_match:
                mrp_text = amount_match.group(0).strip()
                break
        if mrp_text:
            mrp = mrp_text

        # 3. Calculate discount (safe)
        if price and mrp:
            try:
                p = float(re.sub(r'[^\d.]', '', price))
                m = float(re.sub(r'[^\d.]', '', mrp))
                if m > 0 and p < m:
                    discount_percent = round((m - p) / m * 100, 2)
                else:
                    discount_percent = 0
            except ValueError:
                pass  # malformed price string

        # Bought in last month
        bought_in_last_month = None
        bought_regex = re.compile(
            r'(?:\d[\d,]*\.?\d*\s*[KMB]?\+?)\s+'
            r'(?:bought|ordered|purchased)\s+in\s+past\s+month',
            re.I
        )
        bought_selectors = [
            "#social-proofing-faceout-title-tk_bought",
            "#socialProofingAsinFaceout_feature_div",
            "#socialProofingAsinFaceout_feature_div span",
            "span.a-size-base.a-color-secondary",
            "span.a-size-small",
        ]
        for selector in bought_selectors:
            candidate = safe_extract(
                "bought",
                lambda selector=selector: page.locator(selector).filter(has_text=bought_regex).
                first.inner_text().strip()
                if page.locator(selector).filter(has_text=bought_regex).count() > 0 else None,
                asin
            )
            if candidate:
                bought_in_last_month = re.sub(r"\s+", " ", candidate).strip()
                break

        # Child ASINs (variants) - must extract before closing page
        child_asins = safe_extract("Child ASINS",lambda: eCA.extract_child_asins(page, asin),asin)

        try:
            # ==================== FINAL RECORD ====================
            record = {
            "parent_asin": asin,
            "asin": asin,
            "title": title or "N/A",
            "title_length": title_length if title_length else 0,
            "brand": brand,
            "amazon_choice": amazon_choice,
            "top_brand": top_brand,
            "features": features,
            "bullet_points_count": bullet_points_count,
            "warranty": warranty,
            "bsr": bsr,
            "category":  category,
            "sub_category": sub_category,
            "buybox_seller": buybox_seller,
            "price": price,
            "mrp": mrp,
            "discount_percent": discount_percent,
            "bought_in_last_month": bought_in_last_month,
            #"manufacturer": manufacturer,
            # Child ASINs with full dimension mapping
            "child_asins": child_asins,
            #variants": variants_info["variants"] if variants_info else [],
            #"dimensions": variants_info["dimensions"] if variants_info else [],
            }
            """title_length": title_length,
            "top_brand": top_brand,
            "reviews_exact": reviews_exact,
            "bsr": bsr,
            "category": category,
            "sub_category": sub_category,
            
            "image_count": image_count,
            
            "size_weight": size_weight,
            "scrape_date": scrape_date,"""
            all_data.append(record)
        except Exception as e:
            scraper_logger.error(f"Failed to capture debug for {asin}: {e}")
    page.close()
    time.sleep(random.uniform(4, 8))
    return all_data