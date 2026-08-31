# 12 — Provider Authoring

Provider adapter อยู่ใน `src/edgeback/data/providers/` และ implement `MarketDataProvider`:

- `describe_capabilities()` ระบุ feed, interval, limits และ warnings
- `resolve_symbol()` แยก canonical symbol จาก provider symbol
- `fetch_bars()` คืน raw frame + request metadata; ห้ามเขียน canonical storage เอง

Ingestion service เป็นผู้ normalize, กรอง session, validate และเขียน repository. Adapter ต้องระบุ adjustment, extended-hours, feed และ paging อย่างชัดเจน ห้าม fallback ไป provider อื่น

## Security

Credentials อ่านจาก environment ณ เวลาเรียก provider เท่านั้น ไม่อยู่ใน YAML, artifacts, logs หรือ tests. Network tests ต้อง mark `network` และ skip โดย default

## Contract checks

ทดสอบ mapping timestamp, pagination/retry bounds, empty/error responses, package/API metadata, canonical/provider symbols และไม่มี secret leakage โดย mock transport ไม่ต้องใช้ internet
