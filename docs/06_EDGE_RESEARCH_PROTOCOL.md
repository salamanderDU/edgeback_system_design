# 06 — Edge Research Protocol

## 1. Definition of an edge in this project

A candidate edge is a clearly stated, causal market hypothesis that remains economically positive after realistic costs across unseen sessions and reasonable perturbations. A profitable backtest alone is not an edge.

EdgeBack reports evidence and uncertainty. It does not certify profitability.

## 2. Hypothesis card

Every strategy begins with a file under `strategy_specs/` containing:

- economic/behavioral hypothesis;
- target instruments and market regime;
- exact observable inputs available at decision time;
- entry and exit logic;
- risk logic;
- expected holding period and trade frequency;
- falsification criteria;
- major biases/limitations;
- parameter ranges chosen before viewing final test results.

A strategy without a hypothesis card may be used for engine testing but not promoted through the research workflow.

## 3. Research stages

### Stage A — Mechanical validation

- Confirm signals and fills on tiny hand-built bars.
- Prove no future access and next-bar timing.
- Confirm costs, stops, targets, and forced close.
- Visually inspect a small sample of trades.

### Stage B — Baseline

Run a simple predeclared parameter set. Record gross and net results. Do not optimize before the baseline is stored.

### Stage C — Train/validation exploration

Explore a bounded parameter grid or deterministic random sample using training sessions. Use validation sessions for model/parameter selection. Track every trial, including failures.

### Stage D — Final holdout

Run the selected rule once on untouched test sessions. Do not return to tuning based on this result. If the hypothesis changes, create a new strategy version and a new holdout.

### Stage E — Walk-forward

Use rolling or anchored session windows. Fit/select only inside each training window, apply to the next out-of-sample window, and concatenate only OOS trades.

### Stage F — Stress and robustness

- 2x and 3x cost stress;
- entry delayed by one additional bar;
- nearby parameter values;
- symbol subsets;
- year/month/regime slices;
- removal of best day and best trade;
- missing-session sensitivity;
- alternative same-bar ambiguity policy;
- bootstrap confidence intervals.

### Stage G — Paper observation

Outside the MVP engine, monitor prospective signals without capital before considering live use. This stage must not be backfilled into historical validation.

## 4. Data splitting rules

- Split by complete exchange sessions, never random rows.
- Default illustrative split: 60% train, 20% validation, 20% final test.
- For short free-data windows, report that statistical power is limited; do not relax the meaning of holdout.
- Provide warmup data before each evaluation window, but prevent trades and parameter fitting in warmup.
- Use at least a one-session embargo when labels/trades can overlap boundaries.
- Preserve chronological order.

## 5. Selection criteria

Do not optimize a single metric. A candidate should be evaluated on:

- net P&L and return after costs;
- maximum drawdown;
- profit factor;
- expectancy per trade;
- win rate and payoff ratio;
- daily Sharpe/Sortino with sample size shown;
- exposure and turnover;
- trade count and active sessions;
- concentration by day, trade, symbol, and time bucket;
- cost share of gross profit;
- out-of-sample consistency.

The report may provide a ranking score for workflow convenience, but must show its formula and all component metrics.

## 6. Default promotion gates

These defaults are research warnings rather than universal truths. Config may override them, and the report must show overrides.

A strategy version is not promoted beyond `hypothesis` unless:

- no mechanical/look-ahead test fails;
- final test and aggregate walk-forward net expectancy are positive;
- at least 100 OOS trades exist, or the report explicitly states insufficient evidence;
- no single trade contributes more than 20% of OOS net profit;
- no single session contributes more than 30% of OOS net profit;
- results remain nonnegative under 2x baseline transaction costs;
- nearby parameters form a plateau rather than one isolated optimum;
- at least two symbols or two non-overlapping market periods support the effect, when the hypothesis claims generality;
- drawdown and capital requirements fit the declared risk budget.

Failing a gate does not delete the experiment. It changes the conclusion.

## 7. Overfitting controls

- Record the number of tested parameter combinations and strategy versions.
- Never overwrite failed trials.
- Keep the final test immutable.
- Use constrained parameter ranges derived from the hypothesis.
- Prefer simple rules with fewer degrees of freedom.
- Report both best and median validation performance across nearby parameters.
- Add Deflated Sharpe Ratio or Probability of Backtest Overfitting in a later milestone if experiment volume becomes large.

## 8. Bootstrap and uncertainty

Bootstrap at the session level by default to preserve within-day trade dependence. Produce confidence intervals for net expectancy, daily return, profit factor where numerically stable, and max drawdown distributions. Set and record the seed.

A confidence interval crossing zero must be displayed prominently rather than hidden by a point estimate.

## 9. Regime and slice analysis

Without fitting on final test outcomes, report results by:

- symbol;
- long/short;
- weekday;
- entry hour;
- volatility bucket derived causally;
- gap direction/size where relevant;
- trend/range proxy defined before analysis;
- calendar year/month when history permits.

Slice analysis is diagnostic. Post-hoc profitable slices are not a new edge until turned into a versioned hypothesis and retested on new data.

## 10. Experiment record

Each trial stores:

- parent research ID and trial ID;
- hypothesis/strategy version;
- resolved parameters;
- split/fold identity;
- dataset and provider/feed hashes;
- cost and fill policies;
- code/dependency metadata;
- seed;
- metrics and gate outcomes;
- warnings and failure reason;
- artifact paths.

## 11. Required report conclusion labels

Use one of:

- `ENGINE_VALIDATION_ONLY`
- `INSUFFICIENT_EVIDENCE`
- `IN_SAMPLE_ONLY`
- `OOS_FAILED`
- `OOS_PROMISING_NOT_ROBUST`
- `ROBUST_ON_TESTED_DATA`

Never use `PROVEN`, `GUARANTEED`, or equivalent language.

## 12. Seed hypothesis usage

The included ORB, VWAP mean-reversion, and gap-momentum specifications are deliberately ordinary. Their purpose is to exercise the research pipeline and provide falsifiable starting hypotheses. They must not be presented as recommendations to trade.
