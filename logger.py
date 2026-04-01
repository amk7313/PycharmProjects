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