# On-demand: extra daily Keepa history from 2025-01-01 -> keepa_data/keepa_extra_daily.csv
# Our ASINs (from keepa_pull.py) + 3 competitors. Per day: rating, review count, Buy Box price,
# Buy Box share of the listing owner, list (strike-through) price, lightning deal price, coupon,
# new offer count, Amazon price, BSR and new price (BSR/new price mainly for the competitors).
import os, re, csv, time, math, requests
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

KEY = os.getenv("KEEPA_API_KEY")
if not KEY:
    raise ValueError("KEEPA_API_KEY GitHub Secret is missing.")
START = datetime(2025, 1, 1, tzinfo=timezone.utc).date()
OUT = Path("keepa_data") / "keepa_extra_daily.csv"
COMPETITORS = {"B07WMQP4SF": "Homaxy", "B009N83O1C": "Utopia", "B0982ZVLJF": "Infinitee"}
src = Path("keepa_pull.py").read_text(encoding="utf-8")
# Keepa tokens refill slowly (about 1 a minute), so only the ASINs needed for the 4002 family study are pulled.
FAMILY = ["B07QZT3ST7", "B07QXLSQ33", "B07R2Q6VTQ", "B0DBM52TL2", "B0DBM4C49K",                     # 4002
          "B07M5V332T", "B07MNGP42J", "B07M9LFFS8", "B08KJ8DG49", "B0DBM24GL1", "B0DBM35PCT",       # 4008
          "B0DHSLB3F9", "B0DHSP48FK", "B0DHSP7G9C",                                                 # 3068
          "B0DHSP64SZ", "B0DHSNNH2L", "B0DHSP933F", "B0DHSQZPNV"]                                   # 3069
OURS = FAMILY
ASINS = OURS + [a for a in COMPETITORS if a not in OURS]
print("ASINs:", len(OURS), "ours +", len(ASINS) - len(OURS), "competitors")


def tokens():
    d = requests.get("https://api.keepa.com/token", params={"key": KEY}, timeout=60).json()
    return int(d.get("tokensLeft") or 0), int(d.get("refillRate") or 1)


def wait(n):
    while True:
        left, rate = tokens()
        if left - 5 >= n:
            return
        m = math.ceil((n - (left - 5)) / max(rate, 1))
        print("waiting", m, "min for tokens (left", left, ")")
        time.sleep(m * 60 + 5)


def ts(km):
    return datetime.fromtimestamp(1293840000 + int(km) * 60, timezone.utc)


def daily(arr, scale=None, step=2):
    # Keepa [time, value, ...] (or [time, price, shipping] when step=3) -> {date: last value of that day}
    out = {}
    if not arr:
        return out
    for i in range(0, len(arr) - (step - 1), step):
        v = arr[i + 1]
        if v is None or v < 0:
            v = None
        elif scale:
            v = round(v / scale, 2)
        out[ts(arr[i]).date()] = v
    return out


def ffill(d, dates):
    res, last, keys, k = {}, None, sorted(d), 0
    for dt in dates:
        while k < len(keys) and keys[k] <= dt:
            last = d[keys[k]]
            k += 1
        res[dt] = last
    return res


def bb_share(hist, dates):
    # buyBoxSellerIdHistory ["time", "sellerId", ...] -> per day: {seller: minutes held}
    per = defaultdict(Counter)
    if not hist or len(hist) < 2:
        return {}, None
    ev = [(ts(int(hist[i])), str(hist[i + 1])) for i in range(0, len(hist) - 1, 2)]
    ev.sort()
    end = datetime.now(timezone.utc)
    for j, (t0, s) in enumerate(ev):
        t1 = ev[j + 1][0] if j + 1 < len(ev) else end
        t = t0
        while t < t1:
            nxt = min(t1, datetime.combine(t.date() + timedelta(days=1), datetime.min.time(), timezone.utc))
            per[t.date()][s] += (nxt - t).total_seconds() / 60
            t = nxt
    total = Counter()
    for c in per.values():
        total.update(c)
    owner = next((s for s, _ in total.most_common() if s not in ("-1", "-2")), None)
    return per, owner


today = datetime.now(timezone.utc).date()
dates = [START + timedelta(days=i) for i in range((today - START).days + 1)]
rows = []
for b in range(0, len(ASINS), 10):
    batch = ASINS[b:b + 10]
    wait(len(batch) * 4)
    r = requests.get("https://api.keepa.com/product", params={"key": KEY, "domain": 1, "asin": ",".join(batch),
                     "history": 1, "rating": 1, "buybox": 1}, timeout=240)
    r.raise_for_status()
    data = r.json()
    print(b + len(batch), "/", len(ASINS), "tokens left", data.get("tokensLeft"))
    for p in data.get("products") or []:
        a = p.get("asin")
        cs = p.get("csv") or []
        g = lambda i: cs[i] if len(cs) > i else None
        rating = ffill(daily(g(16), 10), dates)
        reviews = ffill(daily(g(17)), dates)
        bbp = ffill(daily(g(18), 100, 3), dates)
        listp = ffill(daily(g(4), 100), dates)
        ld = daily(g(8), 100)
        offers = ffill(daily(g(11)), dates)
        amz = ffill(daily(g(0), 100), dates)
        bsr = ffill(daily(g(3)), dates)
        newp = ffill(daily(g(1), 100), dates)
        coupon = {}
        ch = p.get("couponHistory") or []
        for i in range(0, len(ch) - 2, 3):
            v = ch[i + 1]
            coupon[ts(ch[i]).date()] = (str(v) + "%" if v and v > 0 else ("$" + str(round(-v / 100, 2)) if v and v < 0 else None))
        coupon = ffill(coupon, dates)
        per, owner = bb_share(p.get("buyBoxSellerIdHistory"), dates)
        for dt in dates:
            if bsr[dt] is None and newp[dt] is None and reviews[dt] is None:
                continue
            c = per.get(dt) if per else None
            tot = sum(c.values()) if c else 0
            share = round(100 * c.get(owner, 0) / tot, 1) if c and owner and tot else None
            rows.append([dt.isoformat(), a, COMPETITORS.get(a, "Bumble"), rating[dt], reviews[dt], bbp[dt], share,
                         len([s for s in (c or {}) if s not in ("-1", "-2")]) if c else None, listp[dt], ld.get(dt),
                         coupon[dt], offers[dt], amz[dt], bsr[dt], newp[dt]])

OUT.parent.mkdir(exist_ok=True)
with OUT.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Date", "ASIN", "Brand", "Rating", "ReviewCount", "BuyBoxPrice", "BuyBoxOwnerPct", "BuyBoxSellers",
                "ListPrice", "LightningDealPrice", "Coupon", "NewOfferCount", "AmazonPrice", "BSR", "NewPrice"])
    w.writerows(rows)
print("rows", len(rows), "->", OUT)
