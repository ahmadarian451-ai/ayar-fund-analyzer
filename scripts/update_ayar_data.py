import datetime
import html
import json
import re
import urllib.request
from html.parser import HTMLParser

URLS = [
    "https://www.tgju.org/profile/ime_fund_ayar/history",
    "https://www.tgju.org/profile/ime_fund_ayar",
]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
    "Referer": "https://www.tgju.org/",
}

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self.rows = [], []
        self.row, self.cell = None, None
    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)
    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join(self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None

def normalize_digits(value):
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    return value.translate(trans).replace("\u066c", ",").replace("\u066b", ".")

def number(value):
    s = normalize_digits(value).replace(",", "").replace("٬", "").strip()
    s = re.sub(r"[^0-9.\\-]", "", s)
    try:
        return float(s) if s and s not in ("-", ".") else None
    except ValueError:
        return None

def jalali_to_gregorian(jy, jm, jd):
    jy -= 979
    days = 365 * jy + (jy // 33) * 8 + ((jy % 33 + 3) // 4) + 78 + jd
    days += (jm - 1) * 31 if jm <= 7 else 186 + (jm - 7) * 30
    gy = 1600 + 400 * (days // 146097)
    days %= 146097
    leap = True
    if days > 36524:
        gy += 100 * ((days - 1) // 36524)
        days = (days - 1) % 36524
        if days >= 365:
            days += 1
        else:
            leap = False
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
        leap = False
    else:
        leap = True
    gd = days + 1
    month_days = [31, 29 if ((gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 1
    while gm <= 12 and gd > month_days[gm - 1]:
        gd -= month_days[gm - 1]
        gm += 1
    return gy, gm, gd

def parse_date(value):
    s = normalize_digits(value).strip().replace("-", "/")
    m = re.search(r"(13|14|20)\\d{2}/\\d{1,2}/\\d{1,2}", s)
    if not m:
        return None
    y, mo, d = map(int, m.group(0).split("/"))
    if y < 1700:
        y, mo, d = jalali_to_gregorian(y, mo, d)
    try:
        return datetime.date(y, mo, d).strftime("%Y%m%d")
    except ValueError:
        return None

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=35) as response:
        return response.read().decode("utf-8", "replace")

def parse_rows(source):
    parser = TableParser()
    parser.feed(source)
    found = {}
    for row in parser.rows:
        date_idx = next((i for i, cell in enumerate(row) if parse_date(cell)), None)
        if date_idx is None:
            continue
        date = parse_date(row[date_idx])
        cells = row[:date_idx] if date_idx >= 4 else row[date_idx + 1:]
        vals = [number(x) for x in cells]
        vals = [x for x in vals if x is not None]
        if len(vals) < 4:
            continue
        # TGJU archive columns: open, low, high, close, then change/percent.
        op, low, high, close = vals[:4]
        if min(op, low, high, close) <= 0:
            continue
        found[date] = {
            "date": date, "open": op, "low": min(low, op, close),
            "high": max(high, op, close), "close": close,
            "last": close, "volume": 0, "value": 0, "trades": 0,
        }
    return found

def main():
    merged = {}
    page_used = None
    errors = []
    # Try the archive endpoint and a few common pagination forms; stop on repeats.
    for base in URLS:
        for page in range(1, 9):
            url = base if page == 1 else base + ("&" if "?" in base else "?") + f"page={page}"
            try:
                rows = parse_rows(fetch(url))
                if not rows:
                    if page == 1:
                        errors.append(f"{url}: no archive rows parsed")
                    break
                before = len(merged)
                merged.update(rows)
                page_used = base
                if page > 1 and len(merged) == before:
                    break
            except Exception as exc:
                errors.append(f"{url}: {exc}")
                break
        if len(merged) >= 30:
            break
    history = [merged[k] for k in sorted(merged)]
    if len(history) < 30:
        raise RuntimeError("TGJU archive unavailable or too short. " + " | ".join(errors))
    latest = history[-1]
    payload = {
        "symbol": "عیار",
        "name": "صندوق طلای عیار",
        "source": "TGJU",
        "sourceUrl": page_used,
        "updatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "quote": {
            "pDrCotVal": latest["close"],
            "pClosing": latest["close"],
            "priceYesterday": history[-2]["close"] if len(history) > 1 else None,
            "priceMin": latest["low"],
            "priceMax": latest["high"],
            "note": "TGJU archive daily close; not a live tick feed",
        },
        "fund": {},
        "history": history,
    }
    with open("ayar-data.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Saved {len(history)} daily candles from TGJU. Latest: {latest['date']} close={latest['close']}")

if __name__ == "__main__":
    main()
