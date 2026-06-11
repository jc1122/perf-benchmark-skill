# hotspot-audit report

Suppressions: `suppressed_solo_author`=0
`suppressed_own_test_pairs`=0

## DECOMPOSE (2)
- `scripts/perf_benchmark/reporting.py:1` scripts/perf_benchmark/reporting.py -- churn_complexity_product=2316 [medium]
- `scripts/perf_benchmark_pipeline.py:1` scripts/perf_benchmark_pipeline.py -- churn_complexity_product=11328 [high]

## RESTRUCTURE (4)
- `README.md:1` README.md<->SKILL.md -- temporal_coupling_ratio=0.78 [medium]
- `README.md:1` README.md<->scripts/perf_benchmark_pipeline.py -- temporal_coupling_ratio=0.7 [medium]
- `SKILL.md:1` SKILL.md<->scripts/perf_benchmark_pipeline.py -- temporal_coupling_ratio=0.78 [medium]
- `scripts/perf_benchmark_pipeline.py:1` scripts/perf_benchmark_pipeline.py -- author_concentration=1 [low]

