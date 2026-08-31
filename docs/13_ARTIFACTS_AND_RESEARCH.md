# 13 — Artifacts and Research

## Run directory

ทุก run เขียนใน temp directory ก่อน rename เป็น final และไม่เขียนทับ run เดิม ไฟล์หลัก:

```text
RUN_STATE.json
config.input.yaml
config.resolved.yaml
run_metadata.json
data_manifest.json
intents.parquet orders.parquet fills.parquet trades.parquet equity.parquet
metrics.json gate_results.json warnings.json logs.jsonl report.html
```

`run_metadata.json` เก็บ checksum ของ artifacts; ใช้ `edgeback.artifacts.verify_run_directory(path)` เพื่อตรวจ tampering. SQLite เป็นเพียง index; run folder อ่านได้แม้ registry สูญหาย

## Research discipline

- split ตาม complete sessions และรักษาลำดับเวลา
- warmup ก่อน evaluation ได้ แต่ห้าม trade/fit ใน warmup
- parameter selection ใช้ train/validation เท่านั้น
- final test ถูกเรียกหนึ่งครั้งต่อ hypothesis/version
- walk-forward ต่อเฉพาะ OOS trades
- stress 2x/3x costs, delayed entry, parameter neighborhood, concentration และ session bootstrap

Label `ROBUST_ON_TESTED_DATA` หมายถึงผ่าน gates บนข้อมูลที่ทดสอบเท่านั้น ไม่ใช่การรับรองผลกำไรในอนาคต

## PyArrow

Production install ต้องมี PyArrow และเขียน Parquet จริง ใน environment ทดสอบที่ไม่มี binary wheel ระบบใช้ไฟล์ fallback ซึ่งมี magic header เฉพาะและ manifest เปิดเผย format ชัดเจน จึงไม่ปลอมตัวเป็น Parquet
