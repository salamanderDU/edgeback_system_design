# EdgeBack 0.1.0 — Deterministic Intraday Backtesting and Edge Research

EdgeBack เป็นระบบ backtest แบบ event-driven สำหรับหุ้นและ ETF สหรัฐ ออกแบบให้เปลี่ยนสัญลักษณ์ ช่วงเวลา timeframe ต้นทุน ความเสี่ยง และพารามิเตอร์กลยุทธ์ผ่าน YAML/CLI โดยไม่แก้ engine กลยุทธ์ทุกตัวแยกเป็นไฟล์ Python ภายใต้ `strategies/` และรับข้อมูลย้อนหลังผ่าน causal context เท่านั้น

> ซอฟต์แวร์นี้ใช้เพื่อการวิจัย ไม่ใช่คำแนะนำการลงทุน และผล backtest ไม่รับประกันผลลัพธ์ในอนาคต

## คุณสมบัติหลัก

- สัญญาณจากแท่งที่ปิดแล้วเข้าได้เร็วที่สุดที่ open ของแท่งถัดไป
- รองรับหลายสัญลักษณ์ เงินทุนร่วม และลำดับ allocation แบบ deterministic
- Market, limit, stop และ bracket order พร้อม stop/target ambiguity policy
- Spread, slippage, commission, volume participation, sizing และ daily lockout
- ปิดสถานะที่ session close รวมวัน early close จากปฏิทิน XNYS
- Data download/import แยกจาก backtest; backtest ไม่เรียก network โดยปริยาย
- Canonical Parquet, data manifest, validation report และ dataset checksum
- Run artifact แบบไม่เขียนทับ พร้อม config, orders, fills, trades, equity, metrics, warnings, checksums, SQLite registry และ HTML report
- Train/validation/final test, parameter sweep, walk-forward, cost/delay stress, concentration และ session bootstrap
- Built-in hypotheses: `opening_range_breakout`, `vwap_mean_reversion`, `gap_momentum`

## ติดตั้ง

ต้องใช้ Python 3.12 ขึ้นไป

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

ตรวจระบบ:

```bash
edgeback doctor -c configs/example_backtest.yaml
edgeback strategies list
edgeback strategies describe opening_range_breakout
```

## ทดสอบแบบออฟไลน์ทันที

Fixture เป็นข้อมูลสังเคราะห์สำหรับตรวจ mechanics ไม่ใช่หลักฐานของ edge:

```bash
edgeback data validate -c configs/example_backtest.yaml --fixture
edgeback backtest run -c configs/example_backtest.yaml --fixture
```

เปลี่ยนหุ้นโดยไม่แก้โค้ด:

```bash
edgeback backtest run -c configs/example_backtest.yaml --symbol AAPL --fixture
edgeback backtest run -c configs/example_backtest.yaml --symbol AAPL --symbol MSFT --fixture
```

Override พารามิเตอร์แบบ typed:

```bash
edgeback backtest run -c configs/example_backtest.yaml --fixture \
  --param opening_range_minutes=30 \
  --param reward_risk=2.0
```

## ดาวน์โหลดและใช้ข้อมูลจริง

การดาวน์โหลดเป็นคำสั่งแยกต่างหาก:

```bash
edgeback data download -c configs/example_backtest.yaml
edgeback data list --data-dir data
edgeback data validate -c configs/example_backtest.yaml
edgeback backtest run -c configs/example_backtest.yaml
```

Alpaca ใช้ตัวแปรสภาพแวดล้อมเท่านั้น:

```bash
export ALPACA_API_KEY='...'
export ALPACA_SECRET_KEY='...'
edgeback data download -c path/to/alpaca_config.yaml
```

Local CSV/Parquet:

```bash
edgeback data import -c configs/local_import.yaml --file bars.csv --symbol AAPL \
  --timestamp-column timestamp --timestamp-semantics bar_start --source-timezone America/New_York
```

## Research workflow

```bash
edgeback research sweep -c configs/example_sweep.yaml --fixture
edgeback research walk-forward -c configs/example_sweep.yaml --fixture
```

ผลสรุปใช้เฉพาะ label ที่กำหนด เช่น `INSUFFICIENT_EVIDENCE`, `OOS_FAILED`, `OOS_PROMISING_NOT_ROBUST` และ `ROBUST_ON_TESTED_DATA`; ระบบไม่ใช้คำว่า proven หรือ guaranteed

## Quality gates

```bash
pytest -m 'not network'
ruff check .
ruff format --check .
mypy src
```

อ่านต่อที่ `docs/10_USER_GUIDE.md`, `docs/11_STRATEGY_AUTHORING.md`, `docs/12_PROVIDER_AUTHORING.md`, `docs/13_ARTIFACTS_AND_RESEARCH.md` และ `docs/14_TROUBLESHOOTING.md`
