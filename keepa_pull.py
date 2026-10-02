import os
import csv
import time
import math
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

# Keepa settings
BATCH_SIZE = 10
TOKEN_RESERVE = 5
TOKEN_CHECK_BUFFER_SECONDS = 5


# ============================================================
# BUMBLE AMAZON.COM ASINS
# 155 unique ASINs
# ============================================================

ASINS = """
B00TT4SWDA
B07B128C4S
B07BF6TJJ3
B07BF85XK6
B07BF925Q8
B07BFD4R6X
B07KYW9558
B07M5V332T
B07M9LFFS8
B07MNGP42J
B07P5TXVM2
B07QWMR736
B07QXLSQ33
B07QYP49RP
B07QZT3ST7
B07R1ZBWSB
B07R2Q6VTQ
B07YN8PL2N
B07YN8TWD2
B07YN8WYD6
B07YVHG44K
B07YVJ3SWJ
B081NWLZQW
B088335LSM
B08BWWG87L
B08CVC1447
B08DV991BD
B08DV9L919
B08DV9PRT2
B08DVBMXXW
B08G1CSJC2
B08G1DDD4X
B08G1DLKQB
B08G1DLM7N
B08G1DY5BV
B08G1F2PFG
B08G1F5JMQ
B08G1F7DZN
B08G1FFV96
B08G1FH467
B08G1FT42S
B08G1G3W5J
B08G1G8Y1Q
B08G1JM3NS
B08HLXPGZT
B08HM18F91
B08HS8GTDJ
B08HS8J2GZ
B08HS8WC6B
B08KG34TRV
B08KG5TRHS
B08KGDFY6Z
B08KH2M9PJ
B08KHRYFFK
B08KJ5CD3M
B08KJ66NS8
B08KJ8DG49
B08L9HW1Q3
B08TWXF3M9
B08WWP43BM
B08WWYFHN9
B0977KVM5D
B0977L4FTW
B0977LBCTH
B09QSTX47M
B09QSTZ55S
B09QSV3JNC
B09QSV4CTQ
B09QSVDDWH
B09QSVGB3V
B09QSVKD1W
B09QSVMQQP
B09QSVXK1R
B09QSWRRRK
B09QSWRT9J
B0D54JMSBY
B0D54KZ4FC
B0D54LD74B
B0D5CVXNMS
B0D5CX5DYJ
B0D5CY66L5
B0D5CYL4LH
B0D5CYM7SK
B0D5CZ2D35
B0D6GRWCC3
B0D6GTLNC6
B0D6GX6N13
B0D981GJRL
B0D98326NM
B0D983WMTN
B0D984NFWP
B0DBM24GL1
B0DBM35PCT
B0DBM4C49K
B0DBM52TL2
B0DHSLB3F9
B0DHSNNH2L
B0DHSP64SZ
B0DHSP7G9C
B0DHSP933F
B0DHSQZPNV
B0DJH6TLTZ
B0DJH848C1
B0DJH8J5BX
B0DJH93NDY
B0F3P8P3PM
B0F3P9DG4R
B0F3P9KM8J
B0F3P9R72F
B0F3PC6BCR
B0FHJ4HPB2
B0FHJ4JNVG
B0FHKR2RCK
B0FHKRQWHH
B0FHKSFW59
B0FHKSKRY3
B0FHKSQNTC
B0FHKSZ59V
B0FS7WH538
B0FS7X9D36
B0FS7XGM5H
B0FS81J6BL
B0FS81MKZF
B0FTSMYX9G
B0GR5SN87G
B0GR5WB3L4
B08HMSHZT6
B09QSSSWQ9
B09QSVGY1N
B09QSVXYPF
B09QSWCHZB
B07MD6B3LC
B07M5V3VLZ
B07MD6CBDV
B07XCXCF5V
B0DJH7R3HF
B09QST8HTT
B08WX8MWYY
B017BT28LG
B07QYP6NLZ
B07R1Z9H4M
B08835JSV5
B08TWHLP4C
B08TWKHVXN
B08XZFYBKQ
B09QSTKP64
B0DHSP48FK
B07XBT7L1G
B0FHKRQ81X
B0FGY5RL72
B0GR637NX1
B0GSVSR172
B0GXFQ89LC
B0GXFQVR8K
B0GXFPBNNC
""".strip().splitlines()

ASINS = list(dict.fromkeys(a.strip() for a in ASINS if a.strip()))


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
# KEEPA TOKEN STATUS
# ============================================================

def get_token_status():

    url = "https://api.keepa.com/token"

    response = requests.get(
        url,
        params={"key": API_KEY},
        timeout=60
    )

    response.raise_for_status()

    data = response.json()

    tokens_left = int(data.get("tokensLeft") or 0)
    refill_rate = int(data.get("refillRate") or 0)

    print("")
    print(
        "Keepa tokens available:",
        tokens_left
    )

    print(
        "Keepa refill rate:",
        refill_rate,
        "token(s)/minute"
    )

    return tokens_left, refill_rate


# ============================================================
# WAIT FOR TOKENS
# ============================================================

def wait_for_tokens(required_tokens):

    while True:

        tokens_left, refill_rate = get_token_status()

        usable_tokens = max(
            tokens_left - TOKEN_RESERVE,
            0
        )

        if usable_tokens >= required_tokens:

            print(
                "Enough tokens available.",
                "Required:",
                required_tokens,
                "| Usable:",
                usable_tokens
            )

            return

        missing_tokens = required_tokens - usable_tokens

        if refill_rate <= 0:
            raise RuntimeError(
                "Keepa refill rate is 0. "
                "Cannot continue automatically."
            )

        wait_minutes = math.ceil(
            missing_tokens / refill_rate
        )

        wait_seconds = (
            wait_minutes * 60
            + TOKEN_CHECK_BUFFER_SECONDS
        )

        print("")
        print("=" * 60)
        print("WAITING FOR KEEPA TOKENS")
        print("=" * 60)

        print(
            "Required for next batch:",
            required_tokens
        )

        print(
            "Currently usable:",
            usable_tokens
        )

        print(
            "Missing:",
            missing_tokens
        )

        print(
            "Estimated wait:",
            wait_minutes,
            "minute(s)"
        )

        print(
            "Sleeping for:",
            wait_seconds,
            "seconds"
        )

        print("=" * 60)

        time.sleep(wait_seconds)


# ============================================================
# KEEPA API
# ============================================================

def pull_keepa(asins):

    url = "https://api.keepa.com/product"

    params = {
        "key": API_KEY,
        "domain": DOMAIN,
        "asin": ",".join(asins),
        "stats": 90,
        "history": 1
    }

    print("")
    print("=" * 60)
    print(
        "Requesting:",
        len(asins),
        "products"
    )
    print("=" * 60)

    response = requests.get(
        url,
        params=params,
        timeout=120
    )

    response.raise_for_status()

    data = response.json()

    print(
        "Tokens consumed:",
        data.get("tokensConsumed")
    )

    print(
        "Tokens left:",
        data.get("tokensLeft")
    )

    print(
        "Refill rate:",
        data.get("refillRate")
    )

    print(
        "Products returned:",
        len(data.get("products", []))
    )

    return data


# ============================================================
# TRANSFORM
# ============================================================

def transform_product(product, pull_time):

    stats = product.get("stats") or {}
    current = stats.get("current") or []

    amazon_price_raw = safe_value(
        current,
        0
    )

    new_price_raw = safe_value(
        current,
        1
    )

    sales_rank = safe_value(
        current,
        3
    )

    buy_box_raw = safe_value(
        current,
        10
    )

    rating_raw = safe_value(
        current,
        16
    )

    review_count = safe_value(
        current,
        17
    )

    rating = None

    if rating_raw is not None:

        try:
            rating = round(
                float(rating_raw) / 10,
                1
            )

        except Exception:
            pass

    avg30 = stats.get("avg30") or []
    avg90 = stats.get("avg90") or []

    avg30_rank = safe_value(
        avg30,
        3
    )

    avg90_rank = safe_value(
        avg90,
        3
    )

    avg30_new = cents_to_dollars(
        safe_value(
            avg30,
            1
        )
    )

    avg90_new = cents_to_dollars(
        safe_value(
            avg90,
            1
        )
    )

    sales_ranks = (
        product.get("salesRanks")
        or {}
    )

    category_rank_count = len(
        sales_ranks
    )

    images_csv = product.get(
        "imagesCSV"
    )

    first_image = None

    if images_csv:

        first_image_id = (
            images_csv
            .split(",")[0]
            .strip()
        )

        if first_image_id:

            first_image = (
                "https://images-na.ssl-images-amazon.com/"
                "images/I/"
                + first_image_id
            )

    return {

        "PullTimeUTC": pull_time,

        "ASIN": product.get(
            "asin"
        ),

        "Title": product.get(
            "title"
        ),

        "Brand": product.get(
            "brand"
        ),

        "Manufacturer": product.get(
            "manufacturer"
        ),

        "Model": product.get(
            "model"
        ),

        "ProductGroup": product.get(
            "productGroup"
        ),

        "AmazonPrice":
            cents_to_dollars(
                amazon_price_raw
            ),

        "NewPrice":
            cents_to_dollars(
                new_price_raw
            ),

        "BuyBoxPrice":
            cents_to_dollars(
                buy_box_raw
            ),

        "CurrentBSR":
            sales_rank,

        "Avg30DayBSR":
            avg30_rank,

        "Avg90DayBSR":
            avg90_rank,

        "Avg30DayNewPrice":
            avg30_new,

        "Avg90DayNewPrice":
            avg90_new,

        "ReviewCount":
            review_count,

        "Rating":
            rating,

        "RootCategory":
            product.get(
                "rootCategory"
            ),

        "CategoryRankCount":
            category_rank_count,

        "PackageQuantity":
            product.get(
                "packageQuantity"
            ),

        "ListedSinceUTC":
            convert_keepa_minutes(
                product.get(
                    "listedSince"
                )
            ),

        "LastUpdateUTC":
            convert_keepa_minutes(
                product.get(
                    "lastUpdate"
                )
            ),

        "LastPriceChangeUTC":
            convert_keepa_minutes(
                product.get(
                    "lastPriceChange"
                )
            ),

        "ImageURL":
            first_image
    }


# ============================================================
# SAVE LATEST
# ============================================================

def save_latest(rows):

    if not rows:
        return

    fields = list(
        rows[0].keys()
    )

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
    print(
        "Latest snapshot saved:",
        LATEST_FILE
    )


# ============================================================
# APPEND HISTORY
# ============================================================

def append_history(rows):

    if not rows:
        return

    fields = list(
        rows[0].keys()
    )

    file_exists = (
        HISTORY_FILE.exists()
    )

    file_has_data = (
        file_exists
        and HISTORY_FILE.stat().st_size > 0
    )

    if file_has_data:

        with open(
            HISTORY_FILE,
            "r",
            encoding="utf-8-sig"
        ) as existing:

            reader = csv.reader(
                existing
            )

            old_header = next(
                reader,
                []
            )

        if old_header != fields:

            timestamp = datetime.now(
                timezone.utc
            ).strftime(
                "%Y%m%d_%H%M%S"
            )

            backup_file = (
                OUTPUT_DIR
                / (
                    "keepa_history_old_schema_"
                    + timestamp
                    + ".csv"
                )
            )

            HISTORY_FILE.rename(
                backup_file
            )

            print(
                "Old history preserved:",
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
    ).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    print("")
    print("=" * 60)
    print("BUMBLE KEEPA AUTOMATION")
    print("=" * 60)

    print(
        "Pull time UTC:",
        pull_time
    )

    print(
        "Total Bumble US ASINs:",
        len(ASINS)
    )

    print(
        "Batch size:",
        BATCH_SIZE
    )

    print(
        "Token reserve:",
        TOKEN_RESERVE
    )

    print("")
    print(
        "All ASINs will be processed in this run."
    )

    print(
        "If tokens run low, script will wait "
        "for Keepa refill automatically."
    )

    all_rows = []

    total_asins = len(ASINS)

    total_batches = math.ceil(
        total_asins / BATCH_SIZE
    )

    for batch_number, start in enumerate(
        range(
            0,
            total_asins,
            BATCH_SIZE
        ),
        start=1
    ):

        batch = ASINS[
            start:start + BATCH_SIZE
        ]

        required_tokens = len(
            batch
        )

        print("")
        print("#" * 60)

        print(
            "BATCH",
            batch_number,
            "OF",
            total_batches
        )

        print(
            "ASIN",
            start + 1,
            "to",
            min(
                start + len(batch),
                total_asins
            )
        )

        print(
            "Products in batch:",
            len(batch)
        )

        print(
            "Products remaining after batch:",
            total_asins
            - min(
                start + len(batch),
                total_asins
            )
        )

        print("#" * 60)

        # ----------------------------------------------------
        # WAIT UNTIL ENOUGH TOKENS EXIST
        # ----------------------------------------------------

        wait_for_tokens(
            required_tokens
        )

        # ----------------------------------------------------
        # PULL BATCH
        # ----------------------------------------------------

        try:

            data = pull_keepa(
                batch
            )

        except Exception as error:

            print("")
            print(
                "KEEPA API ERROR:",
                error
            )

            raise

        products = data.get(
            "products",
            []
        )

        returned_asins = set()

        for product in products:

            try:

                row = transform_product(
                    product,
                    pull_time
                )

                asin = row.get(
                    "ASIN"
                )

                if asin:
                    returned_asins.add(
                        asin
                    )

                all_rows.append(
                    row
                )

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
                    "PRODUCT ERROR:",
                    product.get(
                        "asin"
                    ),
                    error
                )

        # ----------------------------------------------------
        # REPORT ANY ASIN NOT RETURNED
        # ----------------------------------------------------

        missing_from_batch = [
            asin
            for asin in batch
            if asin not in returned_asins
        ]

        if missing_from_batch:

            print("")
            print(
                "WARNING:",
                len(missing_from_batch),
                "ASIN(s) not returned by Keepa:"
            )

            for asin in missing_from_batch:
                print(
                    "MISSING:",
                    asin
                )

        print("")
        print(
            "Progress:",
            len(all_rows),
            "/",
            total_asins,
            "products returned"
        )

        # Small pause between API calls
        time.sleep(2)

    # ========================================================
    # FINAL VALIDATION
    # ========================================================

    print("")
    print("=" * 60)
    print("FINAL VALIDATION")
    print("=" * 60)

    # Remove accidental duplicate ASIN rows
    unique_rows = {}

    for row in all_rows:

        asin = row.get(
            "ASIN"
        )

        if asin:
            unique_rows[asin] = row

    final_rows = list(
        unique_rows.values()
    )

    expected_asins = set(
        ASINS
    )

    returned_asins = set(
        unique_rows.keys()
    )

    missing_asins = sorted(
        expected_asins
        - returned_asins
    )

    print(
        "Expected ASINs:",
        len(expected_asins)
    )

    print(
        "Unique ASINs returned:",
        len(returned_asins)
    )

    print(
        "Missing ASINs:",
        len(missing_asins)
    )

    if missing_asins:

        print("")
        print(
            "These ASINs were not returned:"
        )

        for asin in missing_asins:
            print(
                "MISSING:",
                asin
            )

        print("")
        print(
            "IMPORTANT: Existing keepa_latest.csv "
            "will NOT be overwritten with an "
            "incomplete snapshot."
        )

        raise RuntimeError(
            "Keepa pull incomplete: "
            + str(len(missing_asins))
            + " ASIN(s) missing."
        )

    # ========================================================
    # SAVE ONLY AFTER ALL 155 COMPLETE
    # ========================================================

    save_latest(
        final_rows
    )

    append_history(
        final_rows
    )

    print("")
    print("=" * 60)
    print("BUMBLE KEEPA PULL COMPLETE")
    print("=" * 60)

    print(
        "FINAL RESULT:",
        len(final_rows),
        "/",
        len(ASINS),
        "ASINs completed successfully."
    )

    print(
        "Latest snapshot:",
        LATEST_FILE
    )

    print(
        "History file:",
        HISTORY_FILE
    )

    print("=" * 60)


# ============================================================
# EXECUTE
# ============================================================

if __name__ == "__main__":
    main()
