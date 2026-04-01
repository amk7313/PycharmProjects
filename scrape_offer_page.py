import time
import random
import re
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import  AmazonScrapper as scraper

if __name__ == "__main__":
    scraper = scraper.AmazonScraperMT(
        file_path="SCRAPPED_DATA/amazon_scrapamazonbyasin.csv",
        mode="scrapAmazonByChildASIN",      # ← this now works
        max_workers=3
    )
    scraper.run()

_PROMO_WORDS = ("bank offer", "cashback", "partner offer", "gst invoice")

def scrape_offer_page(page, asin: str, parent_ASIN: str):
    """Adapted version - takes page instead of context"""
    all_data = []
    url = f"https://www.amazon.in/dp/{asin}?aod=1"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("#productTitle", timeout=15000)
        try:
            page.wait_for_selector('text="Returnable" OR text="Top Brand" OR text="Warranty"', timeout=10000)
        except PlaywrightTimeout:
            pass
        time.sleep(random.uniform(3.5, 6))

        seller_count = get_seller_count(page)
        sellers = get_all_sellers_info(page)
        scrape_date = datetime.now().strftime("%Y-%m-%d %H:%M")

        all_data.append({
            "asin": asin,
            "parent_asin": parent_ASIN,
            "seller_count": seller_count,
            "sellers": sellers,
            "scrape_date": scrape_date
        })
    except Exception as e:
        print(f"   ⚠️ Offer page error for {asin}: {e}")
        return None

    time.sleep(random.uniform(4, 8))
    return all_data


def get_all_sellers_info(page):
    """
    Returns a list of dicts for third-party sellers on the All Offers (AOD) / OLP view.

    Keys:
        - seller_name (str)
        - price (str|None) e.g. '₹980.00'
        - rating (str, e.g. '4.5 stars') from visible star copy / sprite classes
        - rating_count (int|None)
        - positive_rating (str|None) e.g. '90% positive over last 12 months'
        - is_new_seller (bool)
        - fullfillment_type (str|None)
        - delivery_Fees (str|None)
    """
    sellers = []

    try:
        _wait_for_offer_rows(page)
        offers = _collect_offer_elements(page)

        for offer in offers:
            text = offer.inner_text()
            text_lower = text.lower()

            if not _offer_has_price(offer, text) or _is_promo_row(text_lower):
                continue

            seller_name = _extract_seller_name(offer, text)
            if _is_skip_amazon_seller(seller_name):
                continue

            stars_val = _star_rating_float_from_offer(offer, text)
            rating_label = _format_rating_stars_label(stars_val)

            price = _extract_offer_price(offer, text)

            rating_count = None
            count_elem = offer.query_selector(
                "span[aria-label*='rating'], a[aria-label*='rating']"
            )
            if count_elem:
                count_text = count_elem.inner_text()
                match = re.search(r"([\d,]+)\s*ratings?", count_text, re.I)
                if match:
                    rating_count = int(match.group(1).replace(",", ""))
            if rating_count is None:
                match = re.search(r"\(([\d,]+)\s*ratings?\)", text, re.I)
                if match:
                    rating_count = int(match.group(1).replace(",", ""))
            if rating_count is None:
                match = re.search(r"([\d,]+)\s+ratings?", text, re.I)
                if match:
                    rating_count = int(match.group(1).replace(",", ""))

            positive_rating = _positive_rating_phrase(text)

            # Fulfillment + delivery fee from AOD copy
            amazon_fullfilled = _extract_amazon_fullfilled_flag(offer)
            ships_from = _extract_ships_from(text)
            delivered_by = _extract_delivered_by(text)
            fullfillment_type = _calc_fullfillment_type(
                ships_from=ships_from,
                delivered_by=delivered_by,
                amazon_fullfilled=amazon_fullfilled,
            )
            delivery_fee = _extract_delivery_fee(text)

            is_new_seller = bool(
                "new seller" in text_lower or (rating_count is not None and rating_count < 5)
            )

            sellers.append({
                "seller_name": seller_name,
                "price": price,
                "rating": rating_label,
                "rating_count": rating_count,
                "positive_rating": positive_rating,
                "is_new_seller": is_new_seller,
                "fullfillment_type": fullfillment_type,
                "delivery_Fees": delivery_fee,
            })

        print(f"   ✅ Extracted {len(sellers)} real sellers")

    except Exception as e:
        print(f"   ⚠️ Get all sellers info error: {e}")

    return sellers


def get_seller_count(page):
    """Third-party seller rows with price (AOD list), excluding promos and Amazon retail."""
    try:
        _wait_for_offer_rows(page)
        offers = _collect_offer_elements(page)

        real_sellers = 0
        for offer in offers:
            text = offer.inner_text()
            text_lower = text.lower()
            if not _offer_has_price(offer, text) or _is_promo_row(text_lower):
                continue
            if _is_skip_amazon_seller(_extract_seller_name(offer, text)):
                continue
            real_sellers += 1

        if real_sellers > 0:
            print(f"   ✅ Real seller count: {real_sellers}")
            return real_sellers

        full_text = page.inner_text("body")
        match = re.search(r"New\s*\((\d+)\)", full_text, re.I)
        if match:
            count = int(match.group(1))
            print(f"   ✅ Found via 'New (X)' text: {count}")
            return count

        match = re.search(r"(\d+)\s*new\s*offers", full_text, re.I)
        if match:
            count = int(match.group(1))
            print(f"   ⚠️ Fallback 'new offers' count: {count}")
            return count

    except Exception as e:
        print(f"   ⚠️ Seller count error: {e}")

    print("   ⚠️ No real seller count found")
    return 0


def _wait_for_offer_rows(page):
    """Amazon redirects /gp/offer-listing/ to PDP ?aod=1 (All Offers). Wait for either DOM."""
    try:
        page.wait_for_selector(
            "#aod-offer-list [role='listitem'], div.olpOffer",
            timeout=15000,
        )
    except Exception:
        pass
    time.sleep(1.5)


def _offer_has_price(offer, text: str) -> bool:
    if offer.query_selector(".a-price, .a-price-whole, .a-price .a-offscreen"):
        return True
    # Rupee in text; Amazon uses U+20B9
    if re.search(r"(\u20b9|₹)\s*[\d,]+", text):
        return True
    if re.search(r"rs\.?\s*[\d,]+", text, re.I):
        return True
    return False


def _is_promo_row(text_lower: str) -> bool:
    return any(w in text_lower for w in _PROMO_WORDS)


def _collect_offer_elements(page):
    aod = page.query_selector_all("#aod-offer-list [role='listitem']")
    if aod:
        return aod
    return page.query_selector_all("div.olpOffer")


# Link text / labels that are not merchant names (first `a[href*=seller]` can be "Details" → aag/details)
_BAD_SELLER_LINK_TEXT = frozenset(
    {
        "details",
        "terms",
        "more",
        "see more",
        "add to cart",
        "learn more",
    }
)


def _name_from_seller_link(el):
    if not el:
        return None
    aria = (el.get_attribute("aria-label") or "").strip()
    if aria:
        if ". Opens a new page" in aria:
            cand = aria.split(". Opens a new page")[0].strip()
        else:
            cand = aria
        if cand and cand.lower() not in _BAD_SELLER_LINK_TEXT:
            return cand
    t = (el.inner_text() or "").strip()
    if t and t.lower() not in _BAD_SELLER_LINK_TEXT:
        return t
    return None


def _extract_seller_name(offer, text: str):
    """
    Prefer the storefront link inside #aod-offer-soldBy (/gp/aag/main?...seller=...).
    Do not use the first a[href*=seller] — it is often "Details" (/gp/aag/details?...).
    """
    sold = offer.query_selector("#aod-offer-soldBy")
    if sold:
        link = sold.query_selector('a[href*="/gp/aag/main"]')
        name = _name_from_seller_link(link)
        if name:
            return name
        for el in sold.query_selector_all('a[href*="seller="]'):
            href = (el.get_attribute("href") or "").lower()
            if "/gp/aag/details" in href:
                continue
            if "customer/display" in href or "/gp/help/" in href:
                continue
            name = _name_from_seller_link(el)
            if name:
                return name

    for sel in (
        "a[href*='/gp/aag/main']",
        "a[href*='seller=']",
        "a[href*='/sp?']",
        "span.olpSellerName",
        ".seller-name",
        "#sellerProfileTriggerId",
    ):
        for el in offer.query_selector_all(sel):
            href = (el.get_attribute("href") or "").lower()
            if href and "/gp/aag/details" in href:
                continue
            name = _name_from_seller_link(el)
            if name:
                return name

    for pattern in (
        r"Sold by\s*\n+\s*([^\n(]+)",
        r"Sold by\s*[:\s]+([^\n(]+)",
        r"Ships from and sold by\s+([^\n(]+)",
        r"Fulfills from Amazon and sold by\s+([^\n(]+)",
    ):
        m = re.search(pattern, text, re.I | re.MULTILINE)
        if m:
            raw = m.group(1).strip()
            if raw.lower() not in _BAD_SELLER_LINK_TEXT:
                return raw
    return None


def _is_skip_amazon_seller(name: str) -> bool:
    if not name:
        return True
    n = name.strip().lower()
    if n in ("amazon", "amazon.in", "amazon.com"):
        return True
    if n.startswith("amazon ") and "seller" not in n:
        return True
    return False


def _star_rating_float_from_offer(offer, text: str):
    """
    Parse seller star value (1–5, halves) from AOD copy, .a-icon-alt text,
    aria-labels, or Amazon sprite classes like a-star-mini-4-5.
    """
    m = re.search(
        r"Seller rating is\s+(\d+\.?\d*)\s*out of 5 stars",
        text,
        re.I,
    )
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+\.?\d*)\s*out of 5 stars", text, re.I)
    if m:
        return float(m.group(1))
    for el in offer.query_selector_all(".a-icon-alt"):
        alt = (el.inner_text() or "").strip()
        m = re.search(r"(\d+\.?\d*)\s*out of 5 stars", alt, re.I)
        if m:
            return float(m.group(1))
    for el in offer.query_selector_all("[aria-label*='out of 5'], [aria-label*='star']"):
        lab = el.get_attribute("aria-label") or ""
        m = re.search(r"(\d+\.?\d*)\s*out of 5", lab, re.I)
        if m:
            return float(m.group(1))
    try:
        html = offer.evaluate("e => e.innerHTML")
    except Exception:
        html = ""
    m = re.search(r"a-star-(?:mini|small|medium)-(\d)-(\d)", html)
    if m:
        return int(m.group(1)) + int(m.group(2)) / 10.0
    m = re.search(r"\ba-star-medium-(\d{2})\b", html)
    if m:
        v = int(m.group(1))
        if 10 <= v <= 50:
            return v / 10.0
    return None


def _format_rating_stars_label(stars: float) -> str:
    """Human label e.g. '1 star', '4 stars', '4.5 stars'."""
    if stars is None:
        return None
    r = round(stars, 2)
    if abs(r - int(round(r))) < 0.001:
        n = int(round(r))
        return f"{n} star" if n == 1 else f"{n} stars"
    s = f"{stars:.2f}".rstrip("0").rstrip(".")
    return f"{s} stars"


def _positive_rating_phrase(text: str):
    """e.g. '90% positive over last 12 months'."""
    m = re.search(
        r"(\d{1,3})\s*%\s*positive\s+over\s+(?:the\s+)?(?:last|past)\s+12\s*months",
        text,
        re.I,
    )
    if m:
        return f"{m.group(1)}% positive over last 12 months"
    m = re.search(
        r"(\d{1,3}\s*%\s*positive[^\n]*)",
        text,
        re.I,
    )
    if m:
        frag = " ".join(m.group(1).split())
        if re.search(r"12|month", frag, re.I):
            return frag
    return None


def _extract_amazon_fullfilled_flag(offer) -> bool:
    """
    Best-effort boolean for the offer row.
    On AOD, seller links usually include `isAmazonFulfilled=1/0`.
    """
    # Primary: seller link query param
    try:
        for a in offer.query_selector_all("a[href*='isAmazonFulfilled=']"):
            href = (a.get_attribute("href") or "").strip()
            if re.search(r"isAmazonFulfilled=(1|true)", href, re.I):
                return True
            if re.search(r"isAmazonFulfilled=(0|false)", href, re.I):
                return False
    except Exception:
        pass

    # Fallback: hidden text tokens in HTML
    try:
        html = offer.evaluate("e => e.innerHTML")
    except Exception:
        html = ""
    if re.search(r"amazon_fullfilled-batch.*(1|true)", html, re.I):
        return True
    if re.search(r"amazon_fullfilled-batch.*(0|false)", html, re.I):
        return False
    return False


def _extract_ships_from(text: str):
    m = re.search(r"Ships\s*from\s+([^\n]+)", text, re.I)
    return m.group(1).strip() if m else None


def _extract_delivered_by(text: str):
    m = re.search(r"Delivered\s*by\s+([^\n]+)", text, re.I)
    return m.group(1).strip() if m else None


def _extract_delivery_fee(text: str):
    # Amazon sometimes prints: "FREE delivery Thursday, 2 April."
    if re.search(r"\bFREE\s+delivery\b", text, re.I):
        return "Free"

    # Normalize Rs./RS to the rupee symbol
    t = re.sub(r"Rs\.?\s*", "₹", text, flags=re.I)
    m = re.search(r"(₹\s*[\d,]+(?:\.\d+)?)\s*delivery\b", t, re.I)
    if m:
        return m.group(1).replace(" ", "")
    return None


def _extract_offer_price(offer, text: str):
    """
    Offer price for this row.
    Prefer the rendered price node; fallback to first rupee amount in text.
    """
    # Most reliable: a-offscreen contains full formatted price like "₹980.00"
    el = offer.query_selector(".a-price .a-offscreen")
    if el:
        v = (el.inner_text() or "").strip()
        if v:
            return v

    # Fallback: combine whole + fraction when present
    whole = offer.query_selector(".a-price-whole")
    if whole:
        w = (whole.inner_text() or "").strip().replace(",", "")
        frac_el = offer.query_selector(".a-price-fraction")
        f = (frac_el.inner_text() or "").strip() if frac_el else ""
        if w.isdigit():
            return f"₹{w}.{f}" if f.isdigit() else f"₹{w}"

    # Last resort: first rupee amount (avoid M.R.P.)
    cleaned = re.sub(r"M\\.R\\.P\\.:.*?(\\n|$)", "", text, flags=re.I)
    m = re.search(r"(₹\s*[\d,]+(?:\.\d{1,2})?)", cleaned)
    if m:
        return m.group(1).replace(" ", "")
    return None


def _calc_fullfillment_type(ships_from, delivered_by, amazon_fullfilled: bool):
    ships_from_norm = (ships_from or "").strip().lower()
    delivered_by_norm = (delivered_by or "").strip().lower()

    ships_from_amazon = ships_from_norm.startswith("amazon")
    delivered_by_amazon = delivered_by_norm.startswith("amazon")
    delivered_by_seller = bool(delivered_by_norm) and not delivered_by_amazon

    if ships_from_amazon and amazon_fullfilled:
        return "FBA"
    if delivered_by_amazon and not amazon_fullfilled:
        return "FBA / Hybrid"
    # Some AOD rows omit the "Delivered by ..." line. If it's not Amazon-fulfilled
    # and it's not shipping from Amazon, treat as seller fulfilled (FBM).
    ships_from_seller = bool(ships_from_norm) and not ships_from_amazon
    if (delivered_by_seller and not amazon_fullfilled) or (
        ships_from_seller and not amazon_fullfilled
    ):
        return "FBM"
    return None
