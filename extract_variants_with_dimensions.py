import re
import json


def _extract_balanced_json(text: str, key: str):
    """Helper: Find key and extract the FULL balanced {} JSON (handles nested objects)."""
    pos = text.find(key)
    if pos == -1:
        return None
    # Find the opening { after the key
    start = text.find('{', pos)
    if start == -1:
        return None

    count = 0
    end = start
    for i in range(start, len(text)):
        if text[i] == '{':
            count += 1
        elif text[i] == '}':
            count -= 1
            if count == 0:
                end = i + 1
                break
    return text[start:end]


def extract_variants_with_dimensions(page, parent_asin: str):
    """
    Production-grade variant extractor.
    Returns ONLY true child variants + their dynamic dimensions (size, color, pack, etc.).
    """
    parent_asin = (parent_asin or "").strip().upper()
    found_asins = set()
    variant_map = {}  # asin → {dimension_name: value}
    dimension_names = set()

    try:
        # 1. Scan ALL <script> tags for variation data (the real source)
        scripts = page.query_selector_all("script")
        for script in scripts:
            content = (script.inner_html() or "").strip()
            if not any(
                    k in content for k in ["asinVariationValues", "dimensionToAsinMap", "variationValues", "twister"]):
                continue

            # 2. Try multiple possible JSON keys with balanced extraction
            keys = ["asinVariationValues", "dimensionToAsinMap", "variationValues", "twister-js-init-dpx-data"]
            for key in keys:
                json_str = _extract_balanced_json(content, key)
                if not json_str:
                    continue

                try:
                    data = json.loads(json_str)

                    # Extract ASINs + dimensions
                    asin_map = (data.get("asinVariationValues") or
                                data.get("dimensionToAsinMap") or
                                data.get("variationValues") or {})

                    if isinstance(asin_map, dict):
                        for child_key, dims in asin_map.items():
                            child_asin = str(child_key).upper()
                            if len(child_asin) == 10 and child_asin != parent_asin:
                                found_asins.add(child_asin)
                                if isinstance(dims, dict):
                                    variant_map[child_asin] = dims
                                    dimension_names.update(dims.keys())

                    # Dimension names (if separate)
                    if isinstance(data.get("variationValues"), dict):
                        for dim_name in data["variationValues"].keys():
                            dimension_names.add(str(dim_name))

                except json.JSONDecodeError:
                    continue

        # 3. DOM fallback inside #twister (for pages that don't expose full JSON)
        twister = page.locator("#twister")
        if twister.count() > 0:
            twister_html = twister.inner_html()
            for m in re.finditer(r'/dp/([A-Z0-9]{10})', twister_html, re.I):
                found_asins.add(m.group(1).upper())
            for m in re.finditer(r'data-(?:default)?asin=[\'"]([A-Z0-9]{10})', twister_html, re.I):
                found_asins.add(m.group(1).upper())

    except Exception:
        pass  # Never crash the scraper

    found_asins.discard(parent_asin)

    # Build clean variants list with dimensions
    variants = []
    for child in sorted(found_asins):
        dims = variant_map.get(child, {})
        row = {"asin": child}
        for k, v in dims.items():
            clean_key = str(k).lower().replace(" ", "_").replace("-", "_")
            if isinstance(v, (str, int, float)):
                row[clean_key] = str(v)
        variants.append(row)

    result = {
        "child_asins": sorted(found_asins),
        "variants": variants,
        "dimensions": sorted(dimension_names)
    }

    return result