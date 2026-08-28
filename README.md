# EdgeBack — ชุดเอกสารออกแบบระบบ Backtest สำหรับหา Intraday Edge

> สถานะปัจจุบัน: **ออกแบบระบบเสร็จแล้ว แต่ยังไม่ได้เขียนตัวโปรแกรมจริง**

EdgeBack ถูกออกแบบให้เป็นระบบ backtest แบบ event-driven ด้วย Python สำหรับหุ้นและ ETF โดยเปลี่ยนหุ้นได้จากไฟล์ config และแยกกลยุทธ์ออกเป็นคนละไฟล์อย่างชัดเจน เหมาะสำหรับให้ AI CLI เช่น Codex CLI, Claude Code, Gemini CLI หรือ agent ใน IDE อ่านเอกสารทั้งชุดแล้วค่อยสร้างระบบตามลำดับงาน

## สิ่งสำคัญที่ชุดนี้กำหนดไว้แล้ว

- เปลี่ยนหุ้นจาก `symbols:` ใน YAML หรือใช้ `--symbol` โดยไม่แก้โค้ด engine
- กลยุทธ์ทุกตัวอยู่คนละไฟล์ เช่น `strategies/opening_range_breakout.py`
- ใช้ backtest แบบเดินทีละแท่ง เพื่อควบคุม look-ahead bias และลำดับการ fill
- สัญญาณที่สร้างจากราคาปิดของแท่งหนึ่ง จะเข้าซื้อ/ขายได้เร็วที่สุดที่แท่งถัดไป
- จำลอง spread, slippage, commission, stop loss, take profit และกรณี stop/target ถูกแตะในแท่งเดียวกัน
- ปิดสถานะก่อนหรือเมื่อจบ session โดยค่าเริ่มต้น เพื่อให้เป็น day trade
- แยกขั้นตอน download data ออกจากการ backtest ทำให้รันซ้ำแบบ offline ได้
- เก็บข้อมูลเป็น Parquet และเก็บผลแต่ละรันแบบ immutable พร้อม config, checksum, trade log และ report
- มีขั้นตอน walk-forward, out-of-sample และ stress test ก่อนเรียกผลว่าเป็น edge
- มี `TASK.md` และ `STATUS.md` เพื่อให้ AI ตัวใหม่ resume งานต่อได้เมื่อ session เดิมติดลิมิต

## วิธีส่งให้ AI CLI

1. แตกไฟล์ ZIP แล้วเปิดโฟลเดอร์นี้เป็น project root
2. ส่งข้อความจาก `AI_CLI_PROMPT.txt` ให้ AI CLI
3. ให้ AI อ่าน `PROJECT_MANIFEST.yaml` และ `AGENTS.md` ก่อน
4. AI จะเริ่มจาก task แรกใน `TASK.md` และต้องอัปเดต `TASK.md`/`STATUS.md` ระหว่างทำงาน

ไฟล์หลักที่มนุษย์ควรรู้จัก:

- `PROJECT_MANIFEST.yaml` — ลำดับอ่านและข้อกำหนดระดับโครงการ
- `AGENTS.md` — กติกาบังคับสำหรับ AI ที่เขียนโค้ด
- `docs/` — requirements, architecture, data, engine, strategy, research และ testing
- `strategy_specs/` — นิยามกลยุทธ์ตั้งต้น แยกคนละไฟล์
- `configs/` — ตัวอย่าง config สำหรับ backtest และ parameter sweep
- `TASK.md` — backlog และหลักฐานว่า task ไหนเสร็จแล้ว
- `STATUS.md` — checkpoint ล่าสุดและคำสั่ง/งานถัดไปที่ต้องทำ
- `DECISIONS.md` — บันทึกการตัดสินใจทางสถาปัตยกรรม

## ตัวอย่างแนวคิดการเปลี่ยนหุ้นหลังระบบถูกสร้าง

```yaml
data:
  symbols: [NVDA]
  interval: 5m

strategy:
  name: opening_range_breakout
```

เปลี่ยนเป็น:

```yaml
data:
  symbols: [AAPL, MSFT, AMZN]
```

หรือใช้ CLI override โดยไม่แตะไฟล์กลยุทธ์:

```bash
edgeback backtest run -c configs/example_backtest.yaml --symbol AAPL
```

## ขอบเขต MVP

- ตลาดเริ่มต้น: หุ้นและ ETF สหรัฐ
- Session เริ่มต้น: Regular Trading Hours
- Timeframe: 1m, 5m และ 15m โดย 5m เป็นค่าเริ่มต้น
- รองรับ long/short ในโมเดล แต่ข้อมูลฟรีไม่สามารถรับรอง borrow availability ของการ short
- ข้อมูลเริ่มต้น: `yfinance` สำหรับทดลองช่วงล่าสุด และ Alpaca Basic/IEX สำหรับประวัติที่ยาวกว่า
- รองรับ CSV/Parquet ที่ผู้ใช้นำมาเองตั้งแต่ต้น เพื่ออัปเกรดไปสู่ข้อมูลเสียเงินภายหลังโดยไม่เปลี่ยน engine
- ยังไม่รวม live trading, options, tick data, Level 2, broker routing หรือการเลือก universe ย้อนหลังแบบไร้ survivorship bias

## ข้อจำกัดของข้อมูลฟรี

ข้อมูล intraday ฟรีมีข้อจำกัดด้านช่วงเวลา ความครบถ้วนของตลาด rate limit และสิทธิ์การใช้งาน จึงต้องบันทึก provider/feed ในทุก experiment และห้ามเอาผลจากคนละ feed มาเทียบกันโดยไม่ระบุ ระบบนี้สร้างเพื่อการวิจัย ไม่ใช่หลักฐานว่ากลยุทธ์จะทำกำไรจริง
