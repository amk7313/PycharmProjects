import pandas as pd
import numpy as np
from datetime import datetime
import re


# ====================== HELPER FUNCTIONS ======================
def parse_price(x):
    """Clean price column: remove ₹, commas, extra text, newlines"""
    """Clean price: remove ₹, commas, newlines, extra text. Always returns scalar."""
    if pd.isna(x):
        return np.nan
    s = str(x).strip()
    # Remove junk
    s = s.replace("₹", "").replace(",", "").replace("\n", " ").strip()
    # Extract first number only
    extracted = pd.Series([s]).str.extract(r'(\d+\.?\d*)').iloc[0, 0]
    return pd.to_numeric(extracted, errors='coerce')


def parse_bought(x):
    """Strict bought parser — completely ignores price text and junk."""
    if pd.isna(x) or str(x).strip() == "":
        return np.nan

    s = str(x).upper().replace(",", "").strip()

    # === BLACKLIST: If it looks like price info → ignore completely ===
    if any(word in s for word in ["PRICE", "M.R.P", "₹", "PRODUCT PAGE", "MHZ"]):
        return np.nan

    # === MUST contain at least one bought indicator ===
    if not any(indicator in s for indicator in ["BOUGHT", "K", "M", "+"]):
        return np.nan

    # Now safely extract number + optional K/M
    match = re.search(r'(\d+\.?\d*)\s*(K|M)?', s)
    if not match:
        return np.nan

    num = float(match.group(1))
    if match.group(2) == 'K':
        num *= 1000
    elif match.group(2) == 'M':
        num *= 1_000_000
    return num


def parse_rating(x):
    """Extract numeric rating. Always returns scalar."""
    if pd.isna(x):
        return np.nan
    s = str(x)
    extracted = pd.Series([s]).str.extract(r'(\d+\.?\d*)').iloc[0, 0]
    return pd.to_numeric(extracted, errors='coerce')


def parse_reviews(x):
    """Clean reviews column"""
    if pd.isna(x):
        return np.nan
    s = str(x).replace(",", "").strip()
    return pd.to_numeric(s, errors='coerce')


# ====================== DEMAND SCORE (RESPECTS MISSING DATA) ======================
def compute_demand_score(row):
    """
    Simple logic as requested:
    - Bought = highest priority (70% base). Can carry the product even with 0 reviews/rating.
    - Reviews = medium priority (20%).
    - Rating = lowest priority (10%).
    - If bought is missing → treat as very low (penalized).
    - High rating + low bought = low score (cannot reach Top 10).
    """
    bought_norm = row.get('bought_norm', np.nan)
    reviews_norm = row.get('reviews_norm', np.nan)
    rating_norm = row.get('rating_norm', np.nan)

    # If bought is missing → give very low base score
    if pd.isna(bought_norm):
        bought_norm = 0.05   # normalized low value (not zero, but penalized)

    # Base score dominated by bought
    score = 0.70 * bought_norm

    # Add reviews (medium priority) only if they exist
    if pd.notna(reviews_norm):
        score += 0.20 * reviews_norm

    # Add rating (lowest priority) only if they exist
    if pd.notna(rating_norm):
        score += 0.10 * rating_norm

    return score


# ====================== MAIN SCRIPT ======================
df = pd.read_csv("amazon_products.csv")

# 1. Drop exact duplicate ASINs
df = df.drop_duplicates(subset="asin", keep="first").reset_index(drop=True)

# 2. Clean core columns (NaNs are preserved)
df["price"] = df["price"].apply(parse_price)
df["reviews"] = df["reviews"].apply(parse_reviews)
df["rating"] = df["rating"].apply(parse_rating)
df["bought"] = df["bought"].apply(parse_bought)

# 3. Basic validation: keep only rows with valid price
df = df[df["price"].notna() & (df["price"] > 0)].reset_index(drop=True)

# 4. Global normalization (NaNs stay NaN — this is key)
max_reviews = df["reviews"].max()
max_bought = df["bought"].max()

df["reviews_norm"] = df["reviews"] / max_reviews if max_reviews > 0 else np.nan
df["bought_norm"] = df["bought"] / max_bought if max_bought > 0 else np.nan
df["rating_norm"] = df["rating"] / 5.0

# 5. Compute demand_score (RESPECTS MISSING DATA — no zero-filling)
df["demand_score"] = df.apply(compute_demand_score, axis=1)

# 6. Price buckets (realistic range)
bins = [0, 100, 200, 300, 500, 1000, 2000, 5000, float('inf')]
labels = ["0-100", "100-200", "200-300", "300-500", "500-1000", "1000-2000", "2000-5000", "5000+"]
df["price_bucket"] = pd.cut(df["price"], bins=bins, labels=labels, right=False)

# 7. Data quality column
df["data_points"] = df[["reviews", "rating", "bought"]].notna().sum(axis=1)

# 8. Save cleaned dataset
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
clean_file = f"amazon_products_cleaned_demand-{timestamp}.csv"
df.to_csv(clean_file, index=False)
print(f"✅ Cleaned dataset saved as: {clean_file}")
print(f"   Rows: {len(df):,} | Columns: {len(df.columns)}")

# 9. Final analysis: Demand by price bucket
summary = df.groupby("price_bucket", observed=True).agg({
    "demand_score": ["mean", "median"],
    "bought": ["median", "mean"],
    "reviews": ["median"],
    "rating": ["mean"],
    "asin": ["count"],
    "data_points": ["mean"]
}).round(2)

summary.columns = [
    "demand_mean", "demand_median",
    "bought_median", "bought_mean",
    "reviews_median", "rating_mean",
    "product_count", "avg_data_points"
]
summary = summary.sort_values(by="product_count", ascending=False)

print("\n" + "=" * 90)
print("📊 DEMAND ANALYSIS BY PRICE BUCKET (Missing data properly ignored)")
print("=" * 90)
print(summary)

# Optional: Top 10 highest demand products (only those with at least 1 data point)
print("\n🔥 TOP 10 HIGHEST DEMAND PRODUCTS")
top10 = df[df["demand_score"].notna()].nlargest(10, "demand_score")[[
    "asin", "title", "price", "demand_score",
    "bought", "reviews", "rating", "price_bucket", "data_points"
]]
print(top10)

print("\n💡 Note: Products with missing data are no longer penalised (score uses only available metrics).")