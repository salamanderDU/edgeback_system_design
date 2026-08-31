# 10 — User Guide

## 1. Workflow

1. แก้ `data.symbols`, date range, interval, execution, risk และ strategy ใน YAML
2. รัน `edgeback data download` หรือ `edgeback data import` หนึ่งครั้ง
3. ตรวจ `edgeback data validate`
4. รัน `edgeback backtest run` แบบ offline หลายครั้งกับ dataset เดิม
5. ตรวจ `metrics.json`, `trades.parquet`, `warnings.json`, `gate_results.json` และ `report.html`
6. ใช้ sweep/walk-forward ก่อนสรุปว่าผลมีความน่าเชื่อถือ

## 2. Configuration precedence

ค่ามีลำดับจาก application defaults → base YAML → selected YAML → environment เฉพาะ secrets → CLI overrides. Unknown keys ถูกปฏิเสธ และ resolved config ถูกบันทึกในทุก run

`--symbol` แทนที่ `data.symbols`; `--param name=value` แก้เฉพาะ strategy params; `--set path=value` ใช้ safe typed parsing ไม่มี `eval`

## 3. Data rules

Canonical timestamps เก็บ UTC ส่วน session logic ใช้ `America/New_York` ผ่าน XNYS calendar. ระบบไม่ forward-fill, ไม่สลับ provider/feed อัตโนมัติ และไม่ใช้ incomplete bar. CSV import ต้องระบุ timestamp semantics และ source timezone ชัดเจน

## 4. CLI reference

```text
edgeback doctor
edgeback strategies list|describe
edgeback data providers|download|import|validate|list
edgeback backtest run|batch
edgeback runs list|show
edgeback report build
edgeback research sweep|walk-forward
```

ใช้ `edgeback --help` และ `edgeback <group> --help` เป็น command reference จากตัวโปรแกรม

## 5. Exit codes

- 0 success
- 2 configuration error
- 3 data unavailable
- 4 data validation failure
- 5 strategy error
- 6 simulation failure
- 7 artifact/report failure
- 8 research gate failure เมื่อ command รองรับ fail-on-gate

## 6. Reproducibility

การรันที่เทียบเท่ากันกำหนดโดย resolved config hash, data manifest hash, strategy/version/params, engine version, dependency snapshot, seed และ execution model. Run ID/timestamp ต่างกันได้ แต่ canonical results ต้องเหมือนกัน
