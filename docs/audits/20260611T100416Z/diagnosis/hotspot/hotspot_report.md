# hotspot-audit report

## DECOMPOSE (2)
- `SKILL.md:1` SKILL.md -- churn_complexity_product=1488 [low]
- `scripts/perf_benchmark_pipeline.py:1` scripts/perf_benchmark_pipeline.py -- churn_complexity_product=10455 [high]

## RESTRUCTURE (4)
- `README.md:1` README.md<->SKILL.md -- temporal_coupling_ratio=0.88 [medium]
- `README.md:1` README.md<->scripts/perf_benchmark_pipeline.py -- temporal_coupling_ratio=0.7 [medium]
- `SKILL.md:1` SKILL.md<->scripts/perf_benchmark_pipeline.py -- temporal_coupling_ratio=0.88 [medium]
- `scripts/perf_benchmark_pipeline.py:1` scripts/perf_benchmark_pipeline.py -- author_concentration=1 [low]

