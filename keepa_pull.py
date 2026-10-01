import os
import csv
import requests
from datetime import datetime, timezone
from pathlib import Path

# ============================================================
# KEEPA SETTINGS
# ============================================================

API_KEY = os.getenv("KEEPA_API_KEY")

if not API_KEY:
    raise ValueError("KEEPA_API_KEY GitHub Secret is missing.")

DOMAIN = 1  # Amazon.com / US

# CONTROLLED TEST ONLY
# 1 Bumble ASIN + later replace second with an important competitor ASIN
ASINS = [
    "B08DV9Y1BD",
    "B08DV9Y1BD"
]

OUTPUT_DIR = Path("keepa_data")
OUTPUT_DIR.mkdir(exist_ok=True)

LATEST_FILE = OUTPUT_DIR / "keepa_latest.csv"
HISTORY_FILE = OUTPUT_DIR / "keepa_history.csv"


# ============================================================
# HELPERS
# ============================================================

def cents_to_price(value):
    """Convert Keepa integer price to dollars."""
    try:
        value = int(value)
        if value < 0:
            return None
        return round(value / 100, 2)
    except (TypeError, ValueError):
        return None


def safe_list_value(values, index):
    try:
        value = values[index]
        if value is None or value == -1:
            return None
        return value
    except (IndexError, TypeError):
        return None


# ============================================================
# KEEPA API
# ============================================================

def get_keepa_products(asins):

    url = "https://api.keepa.com/product"

    params = {
        "key": API_KEY,
        "domain": DOMAIN,
        "asin": ",".join(asins),
        "stats": 90,
        "history": 1
    }

    print(f"Requesting Keepa data for {len(asins)} ASIN(s)...")

    response = requests.get(
        url,
        params=params,
        timeout=60
    )

    response.raise_for_status()

    data = response.json()

    print("Keepa request successful.")
    print("Tokens consumed:", data.get("tokensConsumed"))
    print("Tokens left:", data.get("tokensLeft"))
    print("Refill rate:", data.get("refillRate"))

    return data


# ============================================================
# TRANSFORM
# ============================================================

def transform_product(product, pull_time):

    stats = product.get("stats") or {}
    current = stats.get("current") or []

    # Keepa current array indexes
    # 0 Amazon
    # 1 New
    # 3 Sales Rank
    # 10 Buy Box
    # 18 Reviews
    # 19 Rating

    amazon_price = cents_to_price(
        safe_list_value(current, 0)
    )

    new_price = cents_to_price(
        safe_list_value(current, 1)
    )

    sales_rank = safe_list_value(current, 3)

    buy_box_price = cents_to_price(
        safe_list_value(current, 10)
    )

    review_count = safe_list_value(current, 18)

    rating_raw = safe_list_value(current, 19)

    rating = None
    if rating_raw is not None:
        try:
            rating = round(float(rating_raw) / 10, 1)
        except (TypeError, ValueError):
            pass

    row = {
        "PullTimeUTC": pull_time,
        "ASIN": product.get("asin"),
        "Title": product.get("title"),
        "Brand": product.get("brand"),
        "Manufacturer": product.get("manufacturer"),
        "ProductGroup": product.get("productGroup"),
        "Model": product.get("model"),
        "AmazonPrice": amazon_price,
        "NewPrice": new_price,
        "BuyBoxPrice": buy_box_price,
        "SalesRank": sales_rank,
        "ReviewCount": review_count,
        "Rating": rating,
        "LastUpdate": product.get("lastUpdate"),
        "LastPriceChange": product.get("lastPriceChange"),
        "ListedSince": product.get("listedSince"),
        "RootCategory": product.get("rootCategory"),
        "PackageQuantity": product.get("packageQuantity")
    }

    return row


# ============================================================
# CSV SAVE
# ============================================================

def save_csv(rows):

    if not rows:
        print("No products returned. Nothing saved.")
        return

    fieldnames = list(rows[0].keys())

    # Latest snapshot - overwrite each run
    with open(
        LATEST_FILE,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )

        writer.writeheader()
        writer.writerows(rows)

    print(f"Latest snapshot saved: {LATEST_FILE}")

    # Historical archive - append
    history_exists = HISTORY_FILE.exists()

    with open(
        HISTORY_FILE,
        "a",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )

        if not history_exists:
            writer.writeheader()

        writer.writerows(rows)

    print(f"Historical data saved: {HISTORY_FILE}")


# ============================================================
# MAIN
# ============================================================

def main():

    pull_time = datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%d %H:%M:%S")

    # Remove duplicate ASINs
    unique_asins = list(dict.fromkeys(ASINS))

    data = get_keepa_products(unique_asins)

    products = data.get("products", [])

    print("Products returned:", len(products))

    rows = []

    for product in products:

        try:
            row = transform_product(
                product,
                pull_time
            )

            rows.append(row)

            print(
                "Processed:",
                row["ASIN"],
                "|",
                row["Brand"],
                "| BSR:",
                row["SalesRank"],
                "| Buy Box:",
                row["BuyBoxPrice"]
            )

        except Exception as error:

            print(
                "Error processing",
                product.get("asin"),
                ":",
                error
            )

    save_csv(rows)

    print("KEEPА PULL COMPLETE")


if __name__ == "__main__":
    main()
