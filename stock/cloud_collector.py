#!/usr/bin/env python3
"""
MinuteLedger cloud archive collector.

Shared data layer for:
1) stock/index.html (browser client)
2) ChatGPT via the linked GitHub repository

No Massive dependency. Yahoo is the default public source. Alpaca is optional
when ALPACA_KEY / ALPACA_SECRET are configured as GitHub Actions secrets.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "cloud_data"
MINUTES = DATA / "minutes"
DAILY = DATA / "daily"
SUMMARIES = DATA / "summaries"
ANALYSIS = DATA / "analysis"
CONFIG = ROOT / "cloud_config.json"
MANIFEST = DATA / "manifest.json"
ET = ZoneInfo("America/New_York")

DEFAULT_SYMBOLS = ["QQQ","SOXX","SNDK","MU","TSM","NVDA","AMD","AVGO","INTC","MRVL","DELL","TSLA"]
DEFAULT_LONG_HISTORY_SYMBOLS = ["QQQ","SOXX","SNDK","MU","TSM","NVDA"]
DEFAULT_LONG_HISTORY_TRADING_DAYS = 400
DEFAULT_LONG_HISTORY_CALENDAR_DAYS = 700
UA = "Mozilla/5.0 MinuteLedgerCloud/3.2"


def load_config():
    if CONFIG.exists():
        try:
            return json.loads(CONFIG.read_text("utf-8"))
        except Exception as exc:
            print(f"config warning: {exc}", file=sys.stderr)
    return {
        "symbols": DEFAULT_SYMBOLS,
        "longHistorySymbols": DEFAULT_LONG_HISTORY_SYMBOLS,
        "longHistoryTradingDays": DEFAULT_LONG_HISTORY_TRADING_DAYS,
        "longHistoryCalendarDays": DEFAULT_LONG_HISTORY_CALENDAR_DAYS,
    }


def http_json(url: str, headers: dict | None = None, timeout: int = 25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def et_parts(ts_ms: int):
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).astimezone(ET)


def session_for(ts_ms: int):
    d = et_parts(ts_ms)
    m = d.hour * 60 + d.minute
    if m >= 20 * 60 or m < 4 * 60:
        return "overnight"
    if m < 9 * 60 + 30:
        return "premarket"
    if m < 16 * 60:
        return "regular"
    return "afterhours"


def trading_date(ts_ms: int):
    d = et_parts(ts_ms)
    day = d.date() + (timedelta(days=1) if d.hour >= 20 else timedelta())
    return day.isoformat()


def norm_bar(symbol: str, ts_ms: int, o, h, l, c, v, source: str):
    try:
        c = float(c)
        if not c > 0:
            return None
        o = float(o) if o is not None else c
        h = float(h) if h is not None else c
        l = float(l) if l is not None else c
        v = float(v or 0)
    except Exception:
        return None
    return {
        "symbol": symbol,
        "t": int(ts_ms),
        "o": o,
        "h": h,
        "l": l,
        "c": c,
        "v": v,
        "session": session_for(ts_ms),
        "source": source,
        "tradingDate": trading_date(ts_ms),
    }


def yahoo_chunk(symbol: str, start: datetime, end: datetime):
    params = {
        "period1": int(start.timestamp()),
        "period2": int(end.timestamp()),
        "interval": "1m",
        "includePrePost": "true",
        "events": "div,splits",
    }
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(symbol) + "?" + urllib.parse.urlencode(params)
    j = http_json(url)
    z = ((j.get("chart") or {}).get("result") or [None])[0]
    if not z:
        err = (j.get("chart") or {}).get("error")
        raise RuntimeError(f"Yahoo {symbol}: {err}")
    q = (((z.get("indicators") or {}).get("quote") or [{}])[0])
    out = []
    for i, ts in enumerate(z.get("timestamp") or []):
        close = (q.get("close") or [None] * (i + 1))[i]
        if close is None:
            continue
        def at(name):
            a = q.get(name) or []
            return a[i] if i < len(a) else None
        b = norm_bar(symbol, int(ts) * 1000, at("open"), at("high"), at("low"), close, at("volume"), "Yahoo")
        if b:
            out.append(b)
    return out


def yahoo_minutes(symbol: str, days: int):
    now = datetime.now(timezone.utc) + timedelta(minutes=2)
    start_all = now - timedelta(days=days)
    out = {}
    cur = start_all
    while cur < now:
        nxt = min(cur + timedelta(days=7), now)
        try:
            rows = yahoo_chunk(symbol, cur, nxt)
            for b in rows:
                out[b["t"]] = b
            print(f"{symbol} Yahoo {cur.date()}..{nxt.date()}: {len(rows)} bars")
        except Exception as exc:
            print(f"{symbol} Yahoo chunk failed {cur.date()}..{nxt.date()}: {exc}", file=sys.stderr)
        cur = nxt + timedelta(seconds=1)
        time.sleep(0.25)
    return list(out.values())


def alpaca_minutes(symbol: str, days: int):
    key = os.getenv("ALPACA_KEY", "").strip()
    secret = os.getenv("ALPACA_SECRET", "").strip()
    if not key or not secret:
        return []
    feed = os.getenv("ALPACA_FEED", "iex").strip() or "iex"
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    token = None
    out = {}
    pages = 0
    while pages < 5000:
        params = {
            "timeframe": "1Min",
            "start": start.isoformat().replace("+00:00", "Z"),
            "end": end.isoformat().replace("+00:00", "Z"),
            "limit": "10000",
            "sort": "asc",
            "adjustment": "raw",
            "feed": feed,
        }
        if token:
            params["page_token"] = token
        url = "https://data.alpaca.markets/v2/stocks/" + urllib.parse.quote(symbol) + "/bars?" + urllib.parse.urlencode(params)
        j = http_json(url, {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret})
        for x in j.get("bars") or []:
            ts_ms = int(datetime.fromisoformat(x["t"].replace("Z", "+00:00")).timestamp() * 1000)
            b = norm_bar(symbol, ts_ms, x.get("o"), x.get("h"), x.get("l"), x.get("c"), x.get("v"), "Alpaca/" + feed)
            if b:
                out[b["t"]] = b
        token = j.get("next_page_token")
        pages += 1
        if not token:
            break
    print(f"{symbol} Alpaca: {len(out)} bars / {pages} pages")
    return list(out.values())


def yahoo_daily(symbol: str):
    params = {
        "range": "max",
        "interval": "1d",
        "includePrePost": "false",
        "events": "div,splits",
    }
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(symbol) + "?" + urllib.parse.urlencode(params)
    j = http_json(url)
    z = ((j.get("chart") or {}).get("result") or [None])[0]
    if not z:
        raise RuntimeError(f"Yahoo daily {symbol}: no result")
    q = (((z.get("indicators") or {}).get("quote") or [{}])[0])
    rows = []
    for i, ts in enumerate(z.get("timestamp") or []):
        closes = q.get("close") or []
        c = closes[i] if i < len(closes) else None
        if c is None:
            continue
        d = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(ET).date().isoformat()
        rows.append({"tradingDate": d, "regularClose": float(c)})
    rows.sort(key=lambda x: x["tradingDate"])
    for i, row in enumerate(rows):
        row["previousClose"] = rows[i-1]["regularClose"] if i else None
    return rows


def read_jsonl(path: Path):
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    tmp.replace(path)


def merge_minutes(symbol: str, bars):
    grouped = defaultdict(list)
    for b in bars:
        month = b["tradingDate"][:7]
        grouped[month].append(b)
    touched = []
    for month, newrows in grouped.items():
        path = MINUTES / symbol / f"{month}.jsonl"
        merged = {int(x["t"]): x for x in read_jsonl(path) if "t" in x}
        for b in newrows:
            merged[int(b["t"])] = b
        rows = sorted(merged.values(), key=lambda x: x["t"])
        write_jsonl(path, rows)
        touched.append(path)
    return touched


def minute_of_et(ts_ms: int):
    d = et_parts(ts_ms)
    return d.hour * 60 + d.minute


def load_symbol_minutes(symbol: str):
    folder = MINUTES / symbol
    if not folder.exists():
        return []
    rows = []
    for path in sorted(folder.glob("*.jsonl")):
        rows.extend(read_jsonl(path))
    rows.sort(key=lambda x: x["t"])
    return rows


def write_daily(symbol: str, rows):
    DAILY.mkdir(parents=True, exist_ok=True)
    path = DAILY / f"{symbol}.json"
    path.write_text(json.dumps({"symbol": symbol, "source": "Yahoo daily", "rows": rows}, ensure_ascii=False, separators=(",", ":")), "utf-8")


def build_summary(symbol: str, daily_rows):
    daily_map = {x["tradingDate"]: x for x in daily_rows}
    groups = defaultdict(list)
    for b in load_symbol_minutes(symbol):
        if b.get("session") == "premarket":
            m = minute_of_et(int(b["t"]))
            if 240 <= m < 570:
                groups[b["tradingDate"]].append(b)
    samples = []
    for d in sorted(groups):
        a = sorted(groups[d], key=lambda x: x["t"])
        meta = daily_map.get(d) or {}
        base = meta.get("previousClose")
        if not a or base is None or not float(base) > 0:
            continue
        base = float(base)
        slots = {minute_of_et(int(x["t"])) for x in a}
        samples.append({
            "tradingDate": d,
            "previousClose": base,
            "premarketMinutes": len(slots),
            "premarketComplete": len(slots) == 330,
            "openPct": (float(a[0]["o"]) / base - 1) * 100,
            "highPct": (max(float(x["h"]) for x in a) / base - 1) * 100,
            "lowPct": (min(float(x["l"]) for x in a) / base - 1) * 100,
            "lastPct": (float(a[-1]["c"]) / base - 1) * 100,
            "firstTs": int(a[0]["t"]),
            "lastTs": int(a[-1]["t"]),
        })
    # Preserve/import longer validated historical premarket datasets already stored
    # under cloud_data/analysis. The newer minute archive must not hide older SIP history.
    legacy = ANALYSIS / f"{symbol}_premarket_400d_sip.json"
    if legacy.exists():
        try:
            payload0 = json.loads(legacy.read_text("utf-8"))
            merged_samples = {}
            for x in payload0.get("samples") or []:
                d = x.get("date") or x.get("tradingDate")
                if not d:
                    continue
                merged_samples[d] = {
                    "tradingDate": d,
                    "previousClose": x.get("previousClose"),
                    "premarketMinutes": x.get("bars"),
                    "premarketComplete": x.get("bars") == 330,
                    "openPct": x.get("openPct"),
                    "highPct": x.get("highPct"),
                    "lowPct": x.get("lowPct"),
                    "lastPct": x.get("lastPct"),
                    "firstTs": x.get("firstTs"),
                    "lastTs": x.get("lastTs"),
                    "historicalSource": payload0.get("source", "stored analysis"),
                }
            for x in samples:
                merged_samples[x["tradingDate"]] = x
            samples = [merged_samples[d] for d in sorted(merged_samples)]
        except Exception as exc:
            print(f"{symbol} historical analysis import failed: {exc}", file=sys.stderr)

    SUMMARIES.mkdir(parents=True, exist_ok=True)
    path = SUMMARIES / f"{symbol}_premarket.json"
    payload = {
        "version": 2,
        "symbol": symbol,
        "timezone": "America/New_York",
        "definition": "premarket 04:00-09:29 ET; all percentages vs previous regular-session close",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "samples": samples,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), "utf-8")
    return samples


def build_manifest(symbols, long_history_symbols, long_history_target):
    old = {}
    if MANIFEST.exists():
        try:
            old = json.loads(MANIFEST.read_text("utf-8"))
        except Exception:
            old = {}
    result = {
        "version": 1,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "sharedArchive": True,
        "chatgptReadable": True,
        "minuteSource": "Yahoo recent archive; Alpaca when repository credentials are configured; stored validated SIP analysis is merged into statistics summaries",
        "alpacaCredentialsConfigured": bool(os.getenv("ALPACA_KEY", "").strip() and os.getenv("ALPACA_SECRET", "").strip()),
        "yahooLimitation": "Yahoo 1-minute history is limited to recent weeks. Alpaca historical equities data is used for older minute bars when credentials permit; provider coverage is recorded rather than silently treated as complete.",
        "longHistoryTargetTradingDays": long_history_target,
        "longHistorySymbols": sorted(long_history_symbols),
        "symbols": {},
    }
    for symbol in symbols:
        months = []
        folder = MINUTES / symbol
        all_days = set()
        first_ts = None
        last_ts = None
        total = 0
        if folder.exists():
            for path in sorted(folder.glob("*.jsonl")):
                rows = read_jsonl(path)
                if not rows:
                    continue
                days = sorted({x.get("tradingDate") for x in rows if x.get("tradingDate")})
                total += len(rows)
                all_days.update(days)
                fts = min(int(x["t"]) for x in rows)
                lts = max(int(x["t"]) for x in rows)
                first_ts = fts if first_ts is None else min(first_ts, fts)
                last_ts = lts if last_ts is None else max(last_ts, lts)
                months.append({
                    "month": path.stem,
                    "path": f"cloud_data/minutes/{symbol}/{path.name}",
                    "bars": len(rows),
                    "tradingDays": len(days),
                    "firstTs": fts,
                    "lastTs": lts,
                })
        summary_path = SUMMARIES / f"{symbol}_premarket.json"
        summary = {}
        if summary_path.exists():
            try:
                summary = json.loads(summary_path.read_text("utf-8"))
            except Exception:
                summary = {}
        samples = summary.get("samples") or []
        long_required = symbol in long_history_symbols
        long_ready = (len(samples) >= long_history_target) if long_required else None
        hist_sources = sorted({str(x.get("historicalSource")) for x in samples if x.get("historicalSource")})
        result["symbols"][symbol] = {
            "bars": total,
            "tradingDays": len(all_days),
            "earliestTradingDate": min(all_days) if all_days else None,
            "latestTradingDate": max(all_days) if all_days else None,
            "firstTs": first_ts,
            "lastTs": last_ts,
            "premarketDays": len(samples),
            "completePremarketDays": sum(1 for x in samples if x.get("premarketComplete")),
            "longHistoryRequired": long_required,
            "longHistoryTargetTradingDays": long_history_target if long_required else None,
            "longHistoryReady": long_ready,
            "longHistoryMissingDays": max(0, long_history_target - len(samples)) if long_required else 0,
            "historicalSources": hist_sources,
            "dailyPath": f"cloud_data/daily/{symbol}.json",
            "premarketSummaryPath": f"cloud_data/summaries/{symbol}_premarket.json",
            "months": months,
        }
    DATA.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
    return result


def main():
    cfg = load_config()
    symbols = [str(x).strip().upper() for x in cfg.get("symbols", DEFAULT_SYMBOLS) if str(x).strip()]
    long_history_symbols = {
        str(x).strip().upper()
        for x in cfg.get("longHistorySymbols", DEFAULT_LONG_HISTORY_SYMBOLS)
        if str(x).strip()
    }
    # A symbol added to longHistorySymbols is automatically collected even if
    # it was accidentally omitted from the ordinary symbols list.
    symbols = list(dict.fromkeys(symbols + sorted(long_history_symbols)))
    long_history_target = max(1, int(cfg.get("longHistoryTradingDays", DEFAULT_LONG_HISTORY_TRADING_DAYS)))
    long_history_calendar_days = max(
        long_history_target,
        int(cfg.get("longHistoryCalendarDays", DEFAULT_LONG_HISTORY_CALENDAR_DAYS)),
    )

    explicit = os.getenv("CLOUD_BACKFILL_DAYS", "").strip()
    alpaca_configured = bool(os.getenv("ALPACA_KEY", "").strip() and os.getenv("ALPACA_SECRET", "").strip())

    old_manifest = {}
    if MANIFEST.exists():
        try:
            old_manifest = json.loads(MANIFEST.read_text("utf-8") or "{}")
        except Exception:
            old_manifest = {}
    old_symbols = old_manifest.get("symbols") or {}

    print(
        f"MinuteLedger cloud collector: {len(symbols)} symbols; "
        f"long-history target={long_history_target} trading days for {sorted(long_history_symbols)}; "
        f"alpaca={'yes' if alpaca_configured else 'no'}"
    )

    for symbol in symbols:
        old_meta = old_symbols.get(symbol) or {}
        existing_pm_days = int(old_meta.get("premarketDays") or 0)
        is_new_symbol = symbol not in old_symbols

        if explicit.isdigit():
            days = int(explicit)
        elif symbol in long_history_symbols and existing_pm_days < long_history_target and alpaca_configured:
            # Retry the long backfill on every run until this symbol reaches the target.
            days = long_history_calendar_days
        elif is_new_symbol:
            # Newly added symbols bootstrap a wider recent window automatically.
            days = 28
        else:
            days = 8
        days = max(1, min(days, 36500))

        bars = []
        try:
            bars = alpaca_minutes(symbol, days)
        except Exception as exc:
            print(f"{symbol} Alpaca failed: {exc}", file=sys.stderr)
        if not bars:
            try:
                bars = yahoo_minutes(symbol, min(days, 28))
            except Exception as exc:
                print(f"{symbol} Yahoo minutes failed: {exc}", file=sys.stderr)
        if bars:
            merge_minutes(symbol, bars)
        try:
            daily_rows = yahoo_daily(symbol)
            write_daily(symbol, daily_rows)
            samples = build_summary(symbol, daily_rows)
            if symbol in long_history_symbols and len(samples) < long_history_target:
                reason = (
                    "Alpaca credentials are not configured in GitHub Actions"
                    if not alpaca_configured
                    else "provider/backfill coverage is still incomplete"
                )
                print(
                    f"{symbol}: LONG_HISTORY_NOT_READY "
                    f"{len(samples)}/{long_history_target}; {reason}",
                    file=sys.stderr,
                )
            else:
                print(f"{symbol}: cloud premarket samples={len(samples)}")
        except Exception as exc:
            print(f"{symbol} daily/summary failed: {exc}", file=sys.stderr)
        time.sleep(0.4)

    manifest = build_manifest(symbols, long_history_symbols, long_history_target)
    print(json.dumps({
        s: {
            "bars": manifest["symbols"][s]["bars"],
            "days": manifest["symbols"][s]["tradingDays"],
            "premarketDays": manifest["symbols"][s]["premarketDays"],
            "longHistoryReady": manifest["symbols"][s]["longHistoryReady"],
            "longHistoryMissingDays": manifest["symbols"][s]["longHistoryMissingDays"],
        }
        for s in symbols
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
