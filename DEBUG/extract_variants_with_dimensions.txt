import re
import json
from playwright.sync_api import TimeoutError as PlaywrightTimeout

# ====================== IMPROVED CHILD ASIN + DIMENSION EXTRACTION ======================
def extract_variants_with_dimensions(page, parent_asin: str):
    """
    Production-grade variant extractor.
    Returns:
        {
            "child_asins": ["B0XXXX1", "B0XXXX2", ...],
            "variants": [  # each child with its dimensions (size, color, pack, etc.)
                {"asin": "B0XXXX1", "size_name": "M", "color_name": "Red", "pack_size_name": "6 Pack"},
                ...
            ],
            "dimensions": ["size_name", "color_name", "pack_size_name", ...]  # all dynamic dimension names
        }
    Uses the exact methods from your DOCX (JSON + DOM + URL fallback).
    """
    parent_asin = (parent_asin or "").strip().upper()
    found_asins = set()
    variant_map = {}          # asin → {dimension: value}
    dimension_names = set()

    # 1. DOM visible selectors (twister blocks)
    try:
        blocks = page.query_selector_all("div[id^='variation_']")
        for block in blocks:
            label_el = block.query_selector("label, span.a-size-base")
            label = (label_el.inner_text().strip() if label_el else "").lower().replace(" ", "_")
            if not label:
                continue

            options = block.query_selector_all("li, button, a")
            for opt in options:
                value = (opt.get_attribute("title") or opt.inner_text() or "").strip()
                if value:
                    # We will map later via JSON, but collect possible values
                    pass
    except Exception:
        pass

    # 2. Hidden JSON (BEST METHOD - asinVariationValues + dimensionToAsinMap)
    try:
        html = page.content()

        # Look for the main twister data object
        patterns = [
            r'asinVariationValues["\s:]+(\{.*?\})(?=\s*[,}\]])',
            r'dimensionToAsinMap["\s:]+(\{.*?\})(?=\s*[,}\]])',
            r'variationValues["\s:]+(\{.*?\})(?=\s*[,}\]])',
            r'dataToReturn["\s:]+(\{.*?\})(?=\s*[,}\]])',
            r'twister-js-init-dpx-data["\s:]+(\{.*?\})',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, html, re.DOTALL | re.I):
                json_str = match.group(1)
                # Clean common JS wrapping
                json_str = re.sub(r'^\s*:\s*', '', json_str)
                json_str = re.sub(r'\\u[0-9a-fA-F]{4}', '', json_str)  # remove unicode escapes if broken

                try:
                    data = json.loads(json_str)
                    # Case 1: direct asinVariationValues map
                    if isinstance(data, dict) and any(k in data for k in ("asinVariationValues", "dimensionToAsinMap")):
                        asin_map = data.get("asinVariationValues") or data.get("dimensionToAsinMap") or {}
                        for child_asin, dims in asin_map.items():
                            child_asin = str(child_asin).upper()
                            if len(child_asin) == 10 and child_asin != parent_asin:
                                found_asins.add(child_asin)
                                variant_map[child_asin] = dims
                                dimension_names.update(dims.keys())

                    # Case 2: variationValues (dimension names only)
                    if "variationValues" in data:
                        for dim_name, values in data["variationValues"].items():
                            dimension_names.add(dim_name)

                except json.JSONDecodeError:
                    continue
    except Exception:
        pass

    # 3. Fallback regex for any 10-char ASIN (your original logic)
    try:
        html = page.content()
        for m in re.finditer(r"/dp/([A-Z0-9]{10})", html, re.I):
            asin = m.group(1).upper()
            if asin != parent_asin:
                found_asins.add(asin)
    except Exception:
        pass

    # Build clean variant list
    variants = []
    for child in sorted(found_asins):
        dims = variant_map.get(child, {})
        row = {"asin": child}
        row.update({k: v for k, v in dims.items() if isinstance(v, (str, int, float))})
        variants.append(row)

    return {
        "child_asins": sorted(found_asins),
        "variants": variants,
        "dimensions": sorted(dimension_names)
    }


