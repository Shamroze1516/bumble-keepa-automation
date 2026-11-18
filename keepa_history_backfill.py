# One-time / on-demand: daily Keepa history (BSR, sub-category ranks, new price, monthly sold)
# for every ASIN in keepa_pull.py, from 2025-01-01 -> keepa_data/keepa_bsr_daily.csv
import os, re, csv, time, math, requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

KEY = os.getenv("KEEPA_API_KEY")
if not KEY:
    raise ValueError("KEEPA_API_KEY GitHub Secret is missing.")
START = datetime(2025, 1, 1, tzinfo=timezone.utc).date()
OUT = Path("keepa_data") / "keepa_bsr_daily.csv"
src = Path("keepa_pull.py").read_text(encoding="utf-8")
ASINS = list(dict.fromkeys(a.strip() for a in re.search(r'ASINS = """(.*?)"""', src, re.S).group(1).split() if a.strip()))
print("ASINs:", len(ASINS))

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

def day(km):
    return datetime.fromtimestamp(1293840000 + int(km) * 60, timezone.utc).date()

def daily(arr, cents=False):
    # Keepa [time, value, time, value...] -> {date: last value of that day}, forward-filled later
    out = {}
    if not arr:
        return out
    for i in range(0, len(arr) - 1, 2):
        v = arr[i + 1]
        v = None if v is None or v < 0 else (round(v / 100, 2) if cents else v)
        out[day(arr[i])] = v
    return out

def ffill(d, dates):
    res, last, keys, k = {}, None, sorted(d), 0
    for dt in dates:
        while k < len(keys) and keys[k] <= dt:
            last = d[keys[k]]
            k += 1
        res[dt] = last
    return res

today = datetime.now(timezone.utc).date()
dates = [START + timedelta(days=i) for i in range((today - START).days + 1)]
rows = []
for b in range(0, len(ASINS), 10):
    batch = ASINS[b:b + 10]
    wait(len(batch))
    r = requests.get("https://api.keepa.com/product", params={"key": KEY, "domain": 1, "asin": ",".join(batch), "history": 1}, timeout=180)
    r.raise_for_status()
    data = r.json()
    print(b + len(batch), "/", len(ASINS), "tokens left", data.get("tokensLeft"))
    for p in data.get("products") or []:
        cs = p.get("csv") or []
        names = {str(c.get("catId")): c.get("name") for c in (p.get("categoryTree") or [])}
        main = str(p.get("salesRankReference") or "")
        sr = p.get("salesRanks") or {}
        subs = [k for k in sr if str(k) != main][:2]
        bsr = ffill(daily(cs[3] if len(cs) > 3 else None), dates)
        newp = ffill(daily(cs[1] if len(cs) > 1 else None, True), dates)
        sold = ffill(daily(p.get("monthlySoldHistory")), dates)
        s1 = ffill(daily(sr.get(subs[0])), dates) if len(subs) > 0 else {}
        s2 = ffill(daily(sr.get(subs[1])), dates) if len(subs) > 1 else {}
        n1 = names.get(str(subs[0]), str(subs[0])) if len(subs) > 0 else ""
        n2 = names.get(str(subs[1]), str(subs[1])) if len(subs) > 1 else ""
        mname = names.get(main, main)
        for dt in dates:
            if bsr[dt] is None and newp[dt] is None and s1.get(dt) is None:
                continue
            rows.append([dt.isoformat(), p.get("asin"), bsr[dt], mname, n1, s1.get(dt), n2, s2.get(dt), newp[dt], sold[dt]])

with OUT.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Date", "ASIN", "BSR", "BSRCategory", "SubCat1", "SubCat1Rank", "SubCat2", "SubCat2Rank", "NewPrice", "MonthlySold"])
    w.writerows(rows)
print("rows", len(rows), "->", OUT)
