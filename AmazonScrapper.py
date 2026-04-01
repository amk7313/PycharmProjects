import pandas as pd
import ast
import os
import time
import random
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import scrape_amazon   # your module with scrape_amazon
import  scrape_product_page
import  scrape_offer_page


class AmazonScraperMT:
    """
    Optimized multi-threaded Amazon scraper.
    Now supports keyword-based scrape_amazon (productPage mode).
    """

    def __init__(self, file_path: str, mode: str, max_workers: int = 5):
        self.file_path = file_path
        self.mode = mode.lower()          # always normalized
        self.max_workers = max_workers

        self.output_dir = "SCRAPPED_DATA"
        os.makedirs(self.output_dir, exist_ok=True)
        self.output_file = f"{self.output_dir}/amazon_{self.mode}.csv"

        self.df = pd.read_csv(file_path)
        self.asins = self.load_asins()

    def load_asins(self):
        if self.mode == "offer":
            data = self.df["child_asins"].dropna().astype(str).tolist()
            flat_asins = []
            for x in data:
                try:
                    parsed = ast.literal_eval(x)
                    if isinstance(parsed, list):
                        flat_asins.extend(parsed)
                    else:
                        flat_asins.append(str(parsed))
                except (ValueError, SyntaxError, TypeError):
                    continue
            return list(set(flat_asins))[:10],

        return list(set(self.df["asin"].dropna().astype(str).tolist()))[:10]
        # For testing purpose only:
        #return ["B06Y2CH63N","B0DZ2G11VV","B0CCBZMQFJ"]

    def save(self, all_results: list):
        """Write results with clear stats: total unique + new + updated."""
        if not all_results:
            print("⚠️ No results to save")
            return

        df_new = pd.DataFrame(all_results)

        # Count statistics before deduplication
        new_asins = set(df_new["asin"].astype(str))
        new_count = len(new_asins)
        updated_count = 0

        if os.path.exists(self.output_file):
            df_old = pd.read_csv(self.output_file)
            old_asins = set(df_old["asin"].astype(str))

            updated_count = len(new_asins & old_asins)  # overlapping ASINs = updated
            new_count = len(new_asins - old_asins)  # completely new ASINs

            df = pd.concat([df_old, df_new], ignore_index=True)
        else:
            df = df_new

        # Final deduplication (keep latest result for each ASIN)
        df = df.drop_duplicates(subset=["asin"], keep="last")

        df.to_csv(self.output_file, index=False)

        # Clear and informative output
        total_unique = len(df)
        print(f"💾 Saved {total_unique} unique records to {self.output_file}")
        print(f"   → {new_count} new records added")
        print(f"   → {updated_count} records updated (latest data kept)")

    def worker(self, asin: str = None):
        """Works for BOTH modes. asin is ignored in productPage mode."""
        result = None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                               "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
                )
                page = context.new_page()
                time.sleep(random.uniform(0.5, 1.5))
                #print(self.mode)
                if self.mode == "scrapAmazonByKeywords".lower():
                    # Keyword scraper - does NOT need asin
                    result = scrape_amazon.scrape_amazon(page)
                elif self.mode == "scrapamazonbyasin".lower(): # ← now correct call
                    #print("function called...hurray")
                    result = scrape_product_page.scrape_product_page(page,asin)
                elif self.mode == "scrapAmazonByChildASIN".lower():
                    result = scrape_offer_page.scrape_offer_page(page,asin)
                else:
                    # Normal ASIN-based scraper (you can add more later)
                    #print("No Function Called")
                    result = None  # placeholder

                page.close()
                context.close()
                browser.close()

        except Exception as e:
            #print(f"❌ Exception on {asin or 'productPage'}: {type(e).__name__} - {e}")
            result = None

        return asin or "productPage", result

    def run(self):
        #print(f"🚀 Starting scrape → Mode: {self.mode.upper()} | ASINs: {len(self.asins)} | Workers: {self.max_workers}")

        if not self.asins and self.mode.lower() != "scrapAmazonByKeywords".lower():
            #print("⚠️ No ASINs found!")
            return

        all_results = []
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            if self.mode.lower() == "scrapAmazonByKeywords".lower():
                # One worker only (keyword scraper)
                futures = [executor.submit(self.worker)]
            else:
                # Normal ASIN loop
                futures = [executor.submit(self.worker, asin) for asin in self.asins]

            for future in as_completed(futures):
                asin, result = future.result()

                if result is not None:
                    if isinstance(result, dict):
                        all_results.append(result)
                    elif isinstance(result, list):
                        all_results.extend(result)
                    else:
                        all_results.append({"asin": asin, "raw_result": str(result)})
                else:
                    all_results.append({"asin": asin, "error": "fail"})

                #print(f"✅ Done: {asin} ({len(all_results)} processed)")

        self.save(all_results)

        elapsed = time.time() - start_time
        #print(f"🎉 Finished in {elapsed:.1f} seconds!")


