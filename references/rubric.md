# Performance Rubric

7-dimension scoring rubric for Linux performance benchmarking.

**Scoring scale:** 0-4 per dimension (PASS=4, WARN=2, FAIL=0). Maximum score: 28.

N/A dimensions are excluded from the denominator.

## Priority Order

| Priority | Category | Typical Impact |
|----------|----------|----------------|
| PRIORITY 1 | ALGORITHMIC | 100-1000x |
| PRIORITY 2 | DATA LAYOUT | 5-20x |
| PRIORITY 3 | EXECUTION | 2-5x |
| PRIORITY 4 | MICRO | 1.1-2x (ASM audit, not scored) |

Always resolve higher-priority issues before pursuing lower-priority optimizations.

---

## Dimension 0: Algorithmic Scaling

Six sub-checks. All must pass for a PASS score.

### Sub-check 0a: Complexity Exponent (k)

Measure wall time at two or more input sizes. Fit `T(n) = c * n^k`.

| Tier | Condition |
|------|-----------|
| PASS | k <= 1.3 |
| WARN | 1.3 < k <= 1.8 |
| FAIL | k > 1.8 |

### Sub-check 0b: Call Amplification

Source: callgrind `call_count / input_size`.

| Tier | Condition |
|------|-----------|
| PASS | <= 10x |
| WARN | 10-100x |
| FAIL | > 100x |

### Sub-check 0c: Data Reuse Ratio

Source: cachegrind `Dr / input_size` per function.

| Tier | Condition |
|------|-----------|
| PASS | <= 10x |
| WARN | 10-100x |
| FAIL | > 100x |

### Sub-check 0d: Write Amplification

Source: cachegrind `Dw / Dr` per function.

| Tier | Condition |
|------|-----------|
| PASS | <= 0.2 |
| WARN | 0.2-0.5 |
| FAIL | > 0.5 |

### Sub-check 0e: Allocation Churn

Source: massif snapshots over time.

| Tier | Pattern |
|------|---------|
| PASS | Flat or monotonically increasing |
| WARN | Staircase pattern |
| FAIL | Sawtooth with > 5 peaks |

### Sub-check 0f: Multiplicative Call Paths

Source: callgrind call tree.

| Tier | Condition |
|------|-----------|
| PASS | No multiplicative paths |
| WARN | 1 path exceeding threshold N |
| FAIL | Multiple paths exceeding threshold N |

### Dimension 0 Composite Score

- **FAIL (0):** Any sub-check is FAIL.
- **WARN (2):** Two or more sub-checks are WARN (and none FAIL).
- **PASS (4):** Otherwise.

### --expected-complexity Override

The `--expected-complexity` flag adjusts the complexity exponent thresholds:

| Mode | WARN threshold | FAIL threshold |
|------|----------------|----------------|
| `linear` | k > 1.1 | k > 1.3 |
| `nlogn` (default) | k > 1.3 | k > 1.5 |
| `quadratic` | k > 2.0 | k > 2.2 |

---

## Dimensions 1-6

| # | Dimension | Tool Source | PASS (4) | WARN (2) | FAIL (0) |
|---|-----------|-------------|----------|----------|----------|
| 1 | Wall-time stability | pytest-benchmark / `time` x N | CV <= 3% | CV 3-8% | CV > 8% |
| 2 | CPU efficiency | callgrind + `perf stat` | top fn <= 20% of instructions, IPC >= 1.5 | top fn <= 35% or IPC 1.0-1.5 | top fn > 35% or IPC < 1.0 |
| 3 | L1 cache efficiency | cachegrind per-file | L1d miss <= 1% | L1d miss 1-5% | L1d miss > 5% |
| 4 | Last-level cache | cachegrind per-file | LL miss <= 0.5% | LL miss 0.5-2% | LL miss > 2% |
| 5 | Branch prediction | cachegrind / `perf` per-file | mispred <= 1% | mispred 1-3% | mispred > 3% |
| 6 | Memory profile | massif + tracemalloc | peak <= 1.1x baseline | peak 1.1-1.5x baseline | peak > 1.5x baseline |

---

## Interpretation

| Score Range | Assessment |
|-------------|------------|
| >= 22/28 | Strong performance profile |
| 15-21/28 | Workable baseline, targeted improvements recommended |
| < 15/28 | High risk, algorithmic or structural issues likely |
