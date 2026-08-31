# 14 — Troubleshooting

## `DataUnavailableError`

Backtest ไม่ดาวน์โหลดข้อมูลอัตโนมัติ ให้รัน `edgeback data download`/`import`, ตรวจ `data list`, provider/feed, symbols, interval และ date coverage

## Validation fails

ตรวจ timezone semantics, duplicates, OHLC invariants, incomplete latest bar, adjustment mode, session membership และ completeness. ระบบไม่ซ่อมหรือ forward-fill โดยเงียบ

## No trades

ดู `intents.parquet`, `decisions.parquet`, `warnings.json`, time cutoffs, warmup, volume ratio, opening-range bounds และ risk rejection reason. Zero trades เป็นผลสำเร็จของ computation ไม่ใช่ crash

## Alpaca authentication

ตั้ง `ALPACA_API_KEY` และ `ALPACA_SECRET_KEY`; `doctor` แสดงเฉพาะ present/absent. Feed ฟรีต้องตั้ง `iex` และควรตีความ volume-sensitive strategy อย่างระมัดระวัง

## yfinance range

Intraday request ต้องอยู่ในช่วงที่ provider รองรับ; adapter ปฏิเสธ request เกิน policy ก่อนเรียก network. Re-verify current provider limits before production research

## Rebuild report

`edgeback report build <run_id> --output-dir runs` เขียน derived report ใต้ `runs/derived_reports/` และไม่แก้ completed run folder

## Quality tooling absent

ติดตั้ง `python -m pip install -e '.[dev]'` แล้วรัน pytest/Ruff/mypy ตาม README. Core tests ไม่ต้องใช้ API keys
