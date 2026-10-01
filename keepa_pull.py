import os
import csv
import time
import requests
from datetime import datetime, timezone
from pathlib import Path

# ============================================================
# SETTINGS
# ============================================================

API_KEY = os.getenv("KEEPA_API_KEY")

if not API_KEY:
    raise ValueError("KEEPA_API_KEY GitHub Secret is missing.")

DOMAIN = 1  # Amazon US

OUTPUT_DIR = Path("keepa_data")
OUTPUT_DIR.mkdir(exist_ok=True)

LATEST_FILE = OUTPUT_DIR / "keepa_latest.csv"
HISTORY_FILE = OUTPUT_DIR / "keepa_history.csv"

# ============================================================
# ACTUAL BUMBLE ASINS
# Add more ASINs here later if needed.
# Duplicate ASINs are automatically removed.
# ============================================================

ASINS = [
    "B0D5CY66L5",
    "B07QYP49RP",
    "B0D54JMSBY",
    "B0D6GRWCC3",
    "B08KHRYFFK",
    "B08DV9L919",
]

ASINS = list(dict.fromkeys([
    x.strip().upper()
    for x in ASINS
    if x.strip()
]))

# ============================================================
# HELPERS
# ============================================================

def safe_value(values, index):
    try:
        value = values[index]

        if value is None or value == -1:
            return None

        return value
    except (IndexError, TypeError):
        return None


def cents_to_dollars(value):
    if value is None:
        return None

    try:
        value = int(value)

        if value < 0:
            return None

        return round(value / 100, 2)

    except (TypeError, ValueError):
        return None


def convert_keepa_minutes(value):
    """
    Convert Keepa time to UTC timestamp.
    Keepa epoch starts 2011-01-01.
    """

    if value is None:
        return None

    try:
        keepa_epoch = 1293840000
        unix_time = keepa_epoch + (int(value) * 60)

        return datetime.fromtimestamp(
            unix_time,
            timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S")

    except Exception:
        return None


# ============================================================
# API
# ============================================================

def pull_keepa(asins):

    url = "https://api.keepa.com/product"

    params = {
        "key": API_KEY,
        "domain": DOMAIN,
        "asin": ",".join(asins),

        # Current stats + useful recent history
        "stats": 90,
        "history": 1
    }

    print("")
    print("=" * 60)
    print("Requesting:", ", ".join(asins))
    print("=" * 60)

    response = requests.get(
        url,
        params=params,
        timeout=120
    )

    response.raise_for_status()

    data = response.json()

    print("Tokens consumed:", data.get("tokensConsumed"))
    print("Tokens left:", data.get("tokensLeft"))
    print("Refill rate:", data.get("refillRate"))
    print("Products returned:", len(data.get("products", [])))

    return data


# ============================================================
# TRANSFORM
# ============================================================

def transform_product(product, pull_time):

    stats = product.get("stats") or {}
    current = stats.get("current") or []

    # Keepa current stats array
    amazon_price_raw = safe_value(current, 0)
    new_price_raw = safe_value(current, 1)
    sales_rank = safe_value(current, 3)
    buy_box_raw = safe_value(current, 10)

    review_count = safe_value(current, 17)
    rating_raw = safe_value(current, 16)

    rating = None

    if rating_raw is not None:
        try:
            rating = round(float(rating_raw) / 10, 1)
        except Exception:
            pass

    # Useful averages where available
    avg30 = stats.get("avg30") or []
    avg90 = stats.get("avg90") or []

    avg30_rank = safe_value(avg30, 3)
    avg90_rank = safe_value(avg90, 3)

    avg30_new = cents_to_dollars(
        safe_value(avg30, 1)
    )

    avg90_new = cents_to_dollars(
        safe_value(avg90, 1)
    )

    # Category ranks
    sales_ranks = product.get("salesRanks") or {}

    category_rank_count = len(sales_ranks)

    # Images
    images_csv = product.get("imagesCSV")

    first_image = None

    if images_csv:
        first_image_id = images_csv.split(",")[0]

        if first_image_id:
            first_image = (
                "https://images-na.ssl-images-amazon.com/"
                "images/I/" + first_image_id
            )

    row = {
        "PullTimeUTC": pull_time,

        "ASIN": product.get("asin"),
        "Title": product.get("title"),
        "Brand": product.get("brand"),
        "Manufacturer": product.get("manufacturer"),
        "Model": product.get("model"),
        "ProductGroup": product.get("productGroup"),

        "AmazonPrice": cents_to_dollars(
            amazon_price_raw
        ),

        "NewPrice": cents_to_dollars(
            new_price_raw
        ),

        "BuyBoxPrice": cents_to_dollars(
            buy_box_raw
        ),

        "CurrentBSR": sales_rank,

        "Avg30DayBSR": avg30_rank,
        "Avg90DayBSR": avg90_rank,

        "Avg30DayNewPrice": avg30_new,
        "Avg90DayNewPrice": avg90_new,

        "ReviewCount": review_count,
        "Rating": rating,

        "RootCategory": product.get("rootCategory"),
        "CategoryRankCount": category_rank_count,

        "PackageQuantity": product.get("packageQuantity"),

        "ListedSinceUTC": convert_keepa_minutes(
            product.get("listedSince")
        ),

        "LastUpdateUTC": convert_keepa_minutes(
            product.get("lastUpdate")
        ),

        "LastPriceChangeUTC": convert_keepa_minutes(
            product.get("lastPriceChange")
        ),

        "ImageURL": first_image
    }

    return row


# ============================================================
# SAVE CSV
# ============================================================

def save_latest(rows):

    if not rows:
        return

    fields = list(rows[0].keys())

    with open(
        LATEST_FILE,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fields
        )

        writer.writeheader()
        writer.writerows(rows)

    print("")
    print("Latest snapshot saved:", LATEST_FILE)


def append_history(rows):

    if not rows:
        return

    fields = list(rows[0].keys())

    file_exists = HISTORY_FILE.exists()
    file_has_data = (
        file_exists and
        HISTORY_FILE.stat().st_size > 0
    )

    # If old history has different columns,
    # preserve it as backup before starting new schema.
    if file_has_data:

        with open(
            HISTORY_FILE,
            "r",
            encoding="utf-8-sig"
        ) as existing:

            reader = csv.reader(existing)
            old_header = next(reader, [])

        if old_header != fields:

            backup_file = OUTPUT_DIR / (
                "keepa_history_old_schema.csv"
            )

            if not backup_file.exists():
                HISTORY_FILE.rename(backup_file)

                print(
                    "Old history preserved as:",
                    backup_file
                )

            file_has_data = False

    with open(
        HISTORY_FILE,
        "a",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fields
        )

        if not file_has_data:
            writer.writeheader()

        writer.writerows(rows)

    print(
        "History appended:",
        HISTORY_FILE
    )


# ============================================================
# MAIN
# ============================================================

def main():

    pull_time = datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%d %H:%M:%S")

    print("")
    print("BUMBLE KEEPA AUTOMATION")
    print("Pull time UTC:", pull_time)
    print("Unique ASIN count:", len(ASINS))

    all_rows = []

    # Keep batches small and safe.
    # Current list is tiny, so one batch is enough.
    BATCH_SIZE = 10

    for start in range(
        0,
        len(ASINS),
        BATCH_SIZE
    ):

        batch = ASINS[
            start:start + BATCH_SIZE
        ]

        data = pull_keepa(batch)

        products = data.get(
            "products",
            []
        )

        for product in products:

            try:

                row = transform_product(
                    product,
                    pull_time
                )

                all_rows.append(row)

                print(
                    "OK:",
                    row["ASIN"],
                    "|",
                    row["Brand"],
                    "| BSR:",
                    row["CurrentBSR"],
                    "| Buy Box:",
                    row["BuyBoxPrice"]
                )

            except Exception as error:

                print(
                    "ERROR:",
                    product.get("asin"),
                    error
                )

        # Only matters when we later have many batches
        if start + BATCH_SIZE < len(ASINS):
            time.sleep(2)

    print("")
    print(
        "Total products processed:",
        len(all_rows)
    )

    save_latest(all_rows)
    append_history(all_rows)

    print("")
    print("=" * 60)
    print("BUMBLE KEEPA PULL COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
