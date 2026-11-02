import json, os, time, urllib.request, urllib.parse, datetime, sys

BASES = ["https://cdn.tsetmc.com", "https://cdn10.tsetmc.com"]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.tsetmc.com/",
}

def get_json(path):
    errors = []
    for base in BASES:
        try:
            req = urllib.request.Request(base + path, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as res:
                raw = res.read().decode("utf-8-sig")
            return json.loads(raw)
        except Exception as exc:
            errors.append(f"{base}: {exc}")
    raise RuntimeError("TSETMC API unavailable: " + " | ".join(errors))

def unwrap(obj, key):
    if isinstance(obj, dict):
        return obj.get(key, obj)
    return obj

def num(obj, *keys, default=0):
    for key in keys:
        val = obj.get(key) if isinstance(obj, dict) else None
        try:
            if val not in (None, ""):
                return float(val)
        except (TypeError, ValueError):
            pass
    return default

def main():
    search = unwrap(get_json("/api/Instrument/GetInstrumentSearch/" + urllib.parse.quote("عیار")), "instrumentSearch")
    if not isinstance(search, list):
        raise RuntimeError("Unexpected TSETMC instrument search response")
    exact = [x for x in search if str(x.get("lVal18AFC", "")).strip() == "عیار"]
    if not exact:
        exact = [x for x in search if "عیار" in str(x.get("lVal30", ""))]
    if not exact:
        raise RuntimeError("Fund symbol عیار not found in TSETMC search")
    inst = exact[0]
    inscode = str(inst["insCode"])
    history_raw = unwrap(get_json(f"/api/ClosingPrice/GetClosingPriceDailyList/{inscode}/0"), "closingPriceDaily")
    if not isinstance(history_raw, list) or len(history_raw) < 30:
        raise RuntimeError(f"Insufficient daily history for عیار: {len(history_raw) if isinstance(history_raw, list) else 'invalid'}")
    history = []
    for x in history_raw:
        try:
            date = int(x.get("dEven", 0))
            close = num(x, "pClosing", "pc")
            if date and close > 0:
                history.append({
                    "date": str(date),
                    "open": num(x, "priceFirst", "pf", default=close),
                    "high": num(x, "priceMax", "pmax", default=close),
                    "low": num(x, "priceMin", "pmin", default=close),
                    "close": close,
                    "last": num(x, "pDrCotVal", "pl", default=close),
                    "volume": num(x, "qTotTran5J", "qTotTran", default=0),
                    "value": num(x, "qTotCap", default=0),
                    "trades": num(x, "zTotTran", default=0),
                })
        except Exception:
            continue
    history.sort(key=lambda x: x["date"])
    quote = {}
    fund = {}
    try:
        quote = unwrap(get_json(f"/api/ClosingPrice/GetClosingPriceInfo/{inscode}"), "closingPriceInfo")
    except Exception as e:
        quote = {"error": str(e)}
    try:
        fund = unwrap(get_json(f"/api/Fund/GetETFByInsCode/{inscode}"), "eTFByInsCode")
    except Exception as e:
        fund = {"error": str(e)}
    payload = {
        "symbol": "عیار",
        "name": inst.get("lVal30", "صندوق طلای عیار"),
        "insCode": inscode,
        "isin": inst.get("cIsin"),
        "source": "TSETMC",
        "updatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "quote": quote,
        "fund": fund,
        "history": history,
    }
    os.makedirs("data", exist_ok=True)
    with open("ayar-data.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Saved {len(history)} rows for {payload['name']} ({inscode})")

if __name__ == "__main__":
    main()
