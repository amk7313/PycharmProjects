import re
import json

def extract_child_asins(page, parent_asin: str):
    """
    Extracts ONLY true child ASINs (variants) of the current product.
    Ignores all unrelated products on the page.
    Works for products with AND without variants.
    """
    parent_asin = (parent_asin or "").strip().upper()
    found = set()

    try:
        # 1. Target ONLY the #twister section (where real variants live)
        twister = page.locator("#twister")
        if twister.count() > 0:
            twister_html = twister.inner_html()

            # a) Variation links inside twister
            for m in re.finditer(r'href=[\'"](/dp/([A-Z0-9]{10}))', twister_html, re.I):
                found.add(m.group(2).upper())

            # b) Data attributes on variation buttons
            for m in re.finditer(r'data-(?:default)?asin=[\'"]([A-Z0-9]{10})', twister_html, re.I):
                found.add(m.group(1).upper())

        # 2. Hidden variation JSON (most reliable method for complex variants)
        html = page.content()

        json_patterns = [
            r'asinVariationValues["\s:]*(\{[^}]+\})',
            r'dimensionToAsinMap["\s:]*(\{[^}]+\})',
            r'variationValues["\s:]*(\{[^}]+\})',
            r'"dimensionToAsinMap"\s*:\s*(\{[^}]+\})',
        ]

        for pattern in json_patterns:
            for match in re.finditer(pattern, html, re.I | re.DOTALL):
                json_str = match.group(1)
                try:
                    # Some JSON is truncated; fix it
                    if not json_str.endswith('}'):
                        json_str += '}'
                    data = json.loads(json_str)

                    def extract_asins(obj):
                        if isinstance(obj, dict):
                            for k, v in obj.items():
                                if isinstance(v, str) and re.fullmatch(r'[A-Z0-9]{10}', v, re.I):
                                    found.add(v.upper())
                                else:
                                    extract_asins(v)
                        elif isinstance(obj, list):
                            for item in obj:
                                extract_asins(item)

                    extract_asins(data)
                except:
                    continue

    except Exception:
        pass  # Never crash the scraper

    found.discard(parent_asin)
    return sorted(found)