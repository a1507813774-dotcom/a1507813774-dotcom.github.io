# MinuteLedger shared cloud archive

This folder is the shared data layer between `stock/index.html` and ChatGPT.

- `manifest.json`: coverage/index.
- `minutes/<SYMBOL>/<YYYY-MM>.jsonl`: raw 1-minute OHLCV, one JSON object per line.
- `daily/<SYMBOL>.json`: regular-session daily closes and previous closes.
- `summaries/<SYMBOL>_premarket.json`: per-day premarket open/high/low/last percentages vs previous regular close.

The archive is updated by `.github/workflows/minute-ledger-cloud.yml`.
Yahoo is the default source and does not provide 400 trading days of 1-minute history. The collector therefore records only data actually obtained and accumulates it prospectively. Optional Alpaca repository secrets can extend the available minute-history range without any Massive dependency.
