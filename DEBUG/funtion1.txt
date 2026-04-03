import re

def extract_child_asins(page, parent_asin: str):
    """
    Collect variant (child) ASINs available on the PDP.
    Strategy:
      - Twister links/buttons that contain /dp/{ASIN} or data-defaultasin
      - Embedded JSON blobs in page HTML (asinVariationValues / dimensionToAsinMap)
    Returns: sorted unique list excluding parent_asin.
    """
    parent_asin = (parent_asin or "").strip()
    found = set()

    # 1) Twister swatches often have direct dp links
    try:
        for a in page.query_selector_all("#twister a[href*='/dp/'], #twister a[href*='dp/']"):
            href = (a.get_attribute("href") or "")
            m = re.search(r"/dp/([A-Z0-9]{10})", href, re.I)
            if m:
                found.add(m.group(1).upper())
    except Exception:
        pass

    # 2) Some nodes store ASIN in attributes
    try:
        for el in page.query_selector_all("#twister [data-defaultasin], #twister [data-asin]"):
            for attr in ("data-defaultasin", "data-asin"):
                v = (el.get_attribute(attr) or "").strip()
                if re.fullmatch(r"[A-Z0-9]{10}", v, re.I):
                    found.add(v.upper())
    except Exception:
        pass

    # 3) Embedded JSON fallback (covers cases where twister isn't link-based)
    try:
        html = page.content()
        # common keys that hold ASINs in variation maps
        for key in ("asinVariationValues", "dimensionToAsinMap", "dimensionToAsinMapString"):
            if key in html:
                # Extract any 10-char ASIN tokens near these keys
                for m in re.finditer(rf"{re.escape(key)}[\s\S]{{0,40000}}?([A-Z0-9]{{10}})", html, re.I):
                    found.add(m.group(1).upper())
        # broad but safe: any /dp/ASIN in HTML
        for m in re.finditer(r"/dp/([A-Z0-9]{10})", html, re.I):
            found.add(m.group(1).upper())
    except Exception:
        pass

    found.discard(parent_asin.upper())
    return sorted(found)