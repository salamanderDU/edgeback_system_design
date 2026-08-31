from __future__ import annotations

from typing import Any

from edgeback.strategy.registry import get_strategy_class, strategy_classes


def list_strategies() -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "strategy_id": cls.strategy_id,
            "version": cls.strategy_version,
            "name": cls.metadata().name,
            "research_status": cls.metadata().research_status,
            "timeframes": cls.metadata().timeframes,
        }
        for cls in strategy_classes()
    )


def describe_strategy(strategy_id: str) -> dict[str, Any]:
    cls = get_strategy_class(strategy_id)
    metadata = cls.metadata().model_dump(mode="json")
    metadata["parameter_schema"] = cls.params_model.model_json_schema()
    return metadata
