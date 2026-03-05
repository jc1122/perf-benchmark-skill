# ASM Checklist

6-pattern reading guide for Tier 4 ASM audits. Use this after algorithmic, cache, and CPU issues have been resolved (Priorities 1-3). Micro-optimizations at the ASM level typically yield 1.1-2x improvements.

---

## Pattern Table

| # | Check | What to Look For | Good Sign | Bad Sign |
|---|-------|-------------------|-----------|----------|
| 1 | SIMD vectorization | xmm (128-bit), ymm (256-bit), zmm (512-bit) registers | Packed operations (`addpd`, `mulps`, `vfmadd213pd`) in hot loops | Scalar `movsd`/`movss` in tight loops where vectorization is expected |
| 2 | Branch-free arithmetic | `cmov`, `sbb`, `setcc`, bitwise ops (`and`, `or`, `xor`) | Conditional moves (`cmovl`, `cmovge`) in data-dependent hot paths | `jne`/`jle`/`jg` in inner loops processing every element |
| 3 | Function inlining | `call` instructions in hot paths; callgrind call depth | Hot functions inlined (loop body has no `call` instructions) | Repeated `call`/`ret` pairs in the hot path; deep call chains in callgrind |
| 4 | Memory access pattern | `mov` operands and addressing modes | Sequential access: `[rdi]`, `[rdi+8]`, `[rdi+16]` (stride-1) | Scattered access: `[rax+rbx*8]`, pointer chasing through linked structures |
| 5 | Loop overhead | Prologue/epilogue instructions, register spills | Tight loop body with minimal register pressure; loop in registers only | Many `push`/`pop` or stack spills (`mov [rsp+N], reg`) inside hot loop |
| 6 | Alignment | `.p2align` directives before loop headers | Loop entry point aligned to 16 or 32 bytes (`.p2align 4` or `.p2align 5`) | Unaligned loop entries; no alignment directives before hot loops |

---

## Reading objdump Output

### Setup

Compile with debug symbols (`-g`) and at least `-O2` to see optimized code with source annotations:

```bash
gcc -O2 -g -o program program.c
objdump -dS program | less
```

### Navigation

- **Find a function:** Search for `<function_name>:` in the output.
- **Source lines:** Interleaved C/C++ source appears as comment lines above the corresponding assembly.
- **Hot loops:** Look for backward jumps (`jmp`, `jne`, `jle` to a lower address). The target is the loop header.
- **Filter to one function:** Use `--start-address` and `--stop-address` or pipe through `sed`/`awk`.

### What to Check

1. **Locate the hot loop** (identified via callgrind or perf).
2. **Check pattern 1 (SIMD):** Are there `xmm`/`ymm`/`zmm` registers? Are the operations packed (`ps`, `pd` suffix) or scalar (`ss`, `sd` suffix)?
3. **Check pattern 2 (Branch-free):** Inside the loop body, are there conditional jumps (`jcc`) or conditional moves (`cmov`)?
4. **Check pattern 3 (Inlining):** Are there `call` instructions inside the loop?
5. **Check pattern 4 (Memory):** What addressing modes are used in `mov` instructions? Sequential offsets from a base register indicate good spatial locality.
6. **Check pattern 5 (Overhead):** Count instructions in the loop body. Are there register spills to the stack?
7. **Check pattern 6 (Alignment):** Is there a `.p2align` before the loop entry?

### Example: Recognizing a Vectorized Loop

```asm
.p2align 4
.L3:
    vmovupd  (%rdi,%rax), %ymm0       # load 4 doubles (packed)
    vfmadd213pd (%rsi,%rax), %ymm1, %ymm0  # fused multiply-add (packed)
    vmovupd  %ymm0, (%rdx,%rax)       # store 4 doubles (packed)
    addq     $32, %rax                 # advance by 32 bytes (4 * 8-byte doubles)
    cmpq     %rcx, %rax
    jne      .L3
```

Good signs: `ymm` registers, packed operations (`pd` suffix), stride-32 sequential access, aligned loop entry, minimal loop overhead.

### Example: Non-Vectorized Scalar Loop

```asm
.L5:
    movsd    (%rdi,%rax,8), %xmm0     # load 1 double (scalar)
    mulsd    %xmm1, %xmm0             # scalar multiply
    addsd    (%rsi,%rax,8), %xmm0     # scalar add
    movsd    %xmm0, (%rdx,%rax,8)     # store 1 double (scalar)
    incq     %rax
    cmpq     %rcx, %rax
    jne      .L5
```

Bad signs: `xmm` registers with scalar operations (`sd` suffix), stride-1 element at a time, no vectorization.

---

## Reading Numba inspect_asm() Output

### Setup

```python
import numba

@numba.njit
def hot_function(a, b, out):
    for i in range(len(a)):
        out[i] = a[i] * b[i] + a[i]

# Trigger compilation
import numpy as np
a = np.ones(1000)
b = np.ones(1000)
out = np.empty(1000)
hot_function(a, b, out)

# Inspect assembly for the compiled signature
sig = hot_function.signatures[0]
asm = hot_function.inspect_asm(sig)
print(asm)
```

### Navigation

- Numba ASM output is in AT&T syntax (same as objdump default).
- Search for the main loop by looking for backward jumps.
- Apply the same 6-pattern checks as with objdump output.

### Numba-Specific Notes

- Numba uses LLVM. Vectorization depends on loop structure and data types. Float64 arrays with simple element-wise operations usually vectorize.
- Look for `@llvm` prefixed internal calls which indicate LLVM intrinsics (generally fine).
- If vectorization is missing, check for unsupported operations in the loop body (e.g., Python object calls, exceptions, non-contiguous array access).
- Use `numba.config.DUMP_ASSEMBLY = True` as an alternative to `inspect_asm()` for automatic output during compilation.
