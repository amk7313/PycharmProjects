import logging
import os
from datetime import datetime
import csv

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(f"{LOG_DIR}/debug", exist_ok=True)

log_file = os.path.join(LOG_DIR, f"scraper_{datetime.now().strftime('%Y-%m-%d')}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(threadName)s | %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# ← Use this name to avoid any conflict
scraper_logger = logging.getLogger(__name__)

from contextlib import contextmanager

@contextmanager
def log_block(label: str, identifier: str, page=None):
    """
    Clean way to wrap any block of code with automatic success/failure logging.
    """
    scraper_logger.info(f"Starting {label} | {identifier}")
    try:
        yield
        scraper_logger.info(f"✅ Completed {label} | {identifier}")
    except Exception as e:
        scraper_logger.exception(f"❌ Failed {label} | {identifier}")
        if page is not None:
            capture_debug(page, identifier, "critical")
        log_failure(identifier, str(e))
        raise   # re-raise so outer logic can continue if needed


def safe_query(label: str, selector: str, container, asin: str = "", many: bool = False):
    """
    One-liner for query_selector or query_selector_all with built-in logging.
    """
    def _extract():
        if many:
            return container.query_selector_all(selector)
        if selector == "[data-asin]":
            return container.get_attribute("data-asin")
        return container.query_selector(selector)

    return safe_extract(f"{label} selector", _extract, asin)

def safe_extract(label: str, func, asin: str):
    try:
        value = func()
        if value is None or (isinstance(value, (str, list, dict)) and not value):
            scraper_logger.warning(f"{label} empty | DataField: {asin}")
        return value
    except Exception:
        scraper_logger.exception(f"{label} extraction failed | DataField: {asin}")
        return None


def capture_debug(page, asin: str, error_type: str = "error"):
    try:
        timestamp = datetime.now().strftime("%H%M%S")
        file_base = f"{asin}_{error_type}_{timestamp}"
        page.screenshot(path=f"{LOG_DIR}/debug/{file_base}.png")
        with open(f"{LOG_DIR}/debug/{file_base}.html", "w", encoding="utf-8") as f:
            f.write(page.content())
        scraper_logger.info(f"Debug captured | Data_Field: {asin} | Type: {error_type}")
    except Exception as e:
        scraper_logger.error(f"Failed to capture debug for {asin}: {e}")


def log_failure(asin: str, reason: str):
    try:
        with open(f"{LOG_DIR}/failures.csv", "a", newline='', encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([asin, reason, datetime.now().isoformat()])
    except Exception:
        pass