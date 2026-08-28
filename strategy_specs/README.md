# Strategy Specification Files

Each YAML file is a falsifiable hypothesis and implementation contract. It is not executable code and does not claim an edge.

One strategy should map to:

```text
strategy_specs/<id>.yaml
strategies/<id>.py
tests/strategies/test_<id>.py
```

Required fields:

- `id`, `version`, `research_status`
- target market/timeframes/directions
- hypothesis and falsification criteria
- required causal data
- session state and warmup
- strict parameters with units/ranges
- entry and exit rules
- risk intent fields
- invariants and acceptance tests
- known biases/limitations

When rules change in a way that can alter signals, increment the strategy version. Preserve old experiment identity. A post-hoc filter discovered from final-test results requires a new version and new unseen data.
