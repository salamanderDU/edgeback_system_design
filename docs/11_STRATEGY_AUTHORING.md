# 11 — Strategy Authoring

หนึ่งกลยุทธ์ประกอบด้วย `strategy_specs/<id>.yaml`, `strategies/<id>.py` และ tests ของมันเอง

## Contract

- สืบทอด `Strategy[Params]`
- กำหนด `strategy_id`, `strategy_version`, `params_model`, `metadata()`
- พารามิเตอร์เป็น strict/frozen Pydantic model
- ใช้ `ctx.history()` ได้เฉพาะข้อมูลที่จบไม่เกิน engine time
- ส่งคืน `OrderIntent`; ห้ามแก้ portfolio, สั่ง broker, อ่านไฟล์/env, เรียก network หรือเขียน report
- ไม่มี ticker literal ใน logic
- state ต่อ session ต้อง reset ชัดเจนและ serialize ได้

ตัวอย่างโครง:

```python
from edgeback.strategy import Strategy, StrategyMetadata, StrategyParameters, register_strategy

class Params(StrategyParameters):
    lookback: int = 20

@register_strategy
class Example(Strategy[Params]):
    strategy_id = "example"
    strategy_version = "0.1.0"
    params_model = Params

    @classmethod
    def metadata(cls) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id=cls.strategy_id,
            version=cls.strategy_version,
            name="Example",
            description="Falsifiable hypothesis",
            supported_markets=("US_EQUITY",),
            supported_timeframes=("5m",),
            supported_directions=("long",),
            required_fields=("open", "high", "low", "close", "volume"),
            warmup_bars=20,
            research_status="hypothesis",
        )
```

เพิ่ม module name ใน trusted registry `src/edgeback/strategy/registry.py`; ระบบไม่โหลด path จาก YAML เพื่อหลีกเลี่ยง arbitrary code execution

## Required tests

parameter validation, warmup, entry/non-entry, exits, session reset, symbol portability, future-data mutation และ tiny golden backtest. เมื่อ logic เปลี่ยน signal ให้เพิ่ม semantic strategy version และใช้ unseen final test ใหม่
