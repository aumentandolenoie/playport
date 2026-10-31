# Keep Talking and Nobody Explodes (Steam 341800) — crash investigation

Scope: Playport 0.4.0, `ktane.exe`, Unity/Mono. This is a **diagnostic investigation**, not an established fix.

## Evidence

- Official report: https://github.com/playportdev/playport/issues/80
- Two user-supplied reports dated 2026-10-31 have repeated `[store-noalias]`, `c000001d`, and `0xc0000005` exits.
- A representative record: `[store-noalias] ... addr=0x54 ... NO pool/anon alias | region ... prot=5 max=5`.
- The second exported `playport.log` includes four `0xc0000005` exits after approximately four seconds. The `playport.previous.log` contents can overlap between ZIPs: do not mistake repeated history for independent attempts.
- DXMT, Vulkan/DXVK and a forced D3D9 path failed in testing. This weakens the hypothesis that changing only the graphics backend is sufficient.
- Repeated Mono fault offsets are useful for symbolisation but do **not** establish Mono as the primary cause: a prior JIT mapping failure may have corrupted execution state.

## Use the analyzer

```bash
python3 tools/ktane_triage.py /path/to/report.zip
python3 tools/ktane_triage.py --json /path/to/old.zip /path/to/new.zip > comparison.json
```

The tool reads only `playport.log` and `playport.previous.log` from archives, does not extract files, and counts *matching lines* rather than independent faults. Inspect private paths and account data before sharing a report.

## Investigation order before writing a runtime fix

1. Locate the actual `[store-noalias]` producer under `patches/fex-port/` and its upstream patched source. Find the mapping origin and ownership for `prot=5 max=5`; determine whether this was guest Mono JIT code, a PE image or another executable allocation.
2. Trace the allocator and any protection downgrade / dual-mapping registration. Verify whether an expected writable alias was never installed, or whether the attempted write should be reported as a guest fault.
3. Check Mono self-modifying code support and code invalidation in `patches/fex/`. Confirm the faulting guest instruction and the fault's guest/host program counters.
4. Review `patches/wine-port/` for conversion of the first exception to guest `c000001d` and later `c0000005`. Identify the *first causal error*, not just the last crash code.
5. Add bounded diagnostic logging at the correct source location; verify behavior with a known-working Unity/Mono game as a regression test.
6. Only then propose a narrow fix and build a development IPA. Compare fresh `playport.log` reports against the baseline.

**Do not** globally make RX pages writable, suppress exceptions, disable code invalidation, or change JIT protection for all games based solely on these logs. These changes may introduce correctness and security regressions.

Build notes: [docs/BUILDING.md](BUILDING.md). Keep the main branch unchanged until a fix is both compiled and verified on-device.

## Confirmed existing mechanisms (source inspection)

- `patches/fex-port/0048-FEX-wake-the-dormant-Mono-backpatcher-optimisation-o.patch` already installs a Mono bridge with an anonymous RX/RW alias table and `IosMonoResolveRW`.
- `patches/fex-port/0050-ARM64EC-anon-alias-atomic-coverage-and-SMC-retry.patch` already resolves anonymous aliases for atomic operations and handles a specific unaligned SMC retry, documented for Book of the Dead. This is **not** an established fix for KTANE.
- `patches/fex-port/0025-iOS-dual-map-fast-write-infra-trap-mode-default-iOS-.patch` handles the fixed JIT pool, which is distinct from Mono's anonymous aliases.
- Do not make the RX mapping globally writable or blindly redirect stores: first establish whether the failing address is registered to an eligible dual mapping.

## Analyzer regression tests

```bash
python3 -m unittest discover -s tools -p 'test_ktane_triage.py'
```

Tests cover ZIP report parsing only, **not** FEX behavior or actual gameplay. A host CI pass alone does not prove a playable IPA.

## Closer reading of the October 31 report

The runtime emits multiple distinct event classes. In `playport.log`, a fault at `0x702b823e8c` is marked `p0=WRITE` with protection failure, followed by `[alias-own] ... OWNED by live anon JIT alias`. That is **not** evidence of a missing alias for this address: the runtime knows its backing RX/RW alias. Separately, the eventual read at `0x54` is a near-null guest fault; a generic `[store-noalias]` record at such an address must not be treated as proof of a missing anonymous JIT mapping. Correlate each candidate with its own `p0`, `p1`, program counter, and region/alias lines.

The report also shows `[mach-deliver] no TEB owns sp=0x73fd2d0000 -> BEST-EFFORT delivery on guest stack` on repeated Mono-related exceptions. This is worth investigating in Wine/FEX exception delivery: confirm whether TEB/stack ownership and ARM64EC context restoration are correct when a native Mono thread faults. **Neither a bad stack owner nor a missing JIT alias is established as the root cause yet.**

A future runtime instrumentation patch should record *one complete exception chain* (thread ID, event order, original fault PC, guest RIP, protection result, alias lookup, exception dispatch result) with bounded log volume; otherwise repeated normal handled JIT faults may obscure the first unhandled exception. The primary fix must follow that chain, not the last `0xC0000005` alone.

## Oct 31 crash: decoded fault and next debugging target

Direct inspection of the second ZIP's `playport.log` at lines 18827–18849 establishes:

1. A Mono-related code allocation is registered with `[jit-pool] anon RWX`; an earlier protected-page store on thread `002c` triggers Wine exception dispatch and a context restore.
2. `[store-noalias] addr=0x54 insn=0xb84000c8 pc=0x11b829208` follows. **Despite this diagnostic tag's name, instruction 0xb84000c8 is an ARM64 `LDR W8, [X6]`-family load, not a store.**
3. `[fault_rip] ... kr=1(INVALID_ADDRESS)`, `[fault-rgn] ... region=unknown/foreign`, and `[exc-disp] ... p0=0 p1=54` independently establish a **read at 0x54**, not a missing writable alias.
4. FEX reconstructs guest RIP `0x73f9724175`, in the loaded Mono image, and forwards `C0000005 AV READ of 54`. An ensuing `C000001D` appears on an exception/crash path. The near-null read is a better primary target than the misleading `store-noalias` label.

**Important:** these observations do not yet prove whether the null register was caused by Mono logic, a preceding exception-context restore, or FEX's translated register state. Do not patch allocation protections on the basis of the misleading log tag.

### Concrete next runtime probe

At the **first** `0x54` access, capture guest GPRs and guest RIP *before* Wine exception dispatch and *after* context reconstruction (the `[set-ctx]` transition), plus the exception flags and owner thread. Compare the register that supplies the base of `LDR W8, [X6]` and the relevant guest x86 registers against a Windows baseline, if available. Keep instrumentation behind an opt-in environment variable and a small log cap. Then examine the preceding `[set-ctx] ... sp=0x73fd2d0000` on thread `002c` to determine whether an exception-handling path has altered state.

### Readiness gate

No new iPhone IPA should be labeled *fixed* until the first-fault state is resolved in source and the same game passes a fresh on-device launch. Buildability, passing Python report tests and absence of the final code in a later log are insufficient independently.

## Real-report validation (two exports, October 31)

The original ZIPs were checked directly, not inferred from the synthetic fixtures. In `playport.log`:

| Export | `[store-noalias] addr=0x54 insn=0xb84000c8` | `[fault_rip] ... addr=0x54` | `title: done exit=0xc0000005` |
| --- | ---: | ---: | ---: |
| 16:55:25 | 2 | 1 | 1 |
| 17:05:57 | 8 | 4 | 4 |

Two `store-noalias` records may occur per fatal read, so **do not equate diagnostic line counts to independent crashes**. The second archive also includes prior logs; avoid double-counting them.

### Delivery/build limitation

The checked-in `.github/workflows/checks.yml` is source-only by design. It deliberately does not build or upload an IPA, and `tools/tests/test_release_ci.py` enforces the approved workflow. Don't bypass that policy or commit a public IPA deployment workflow merely to test KTANE. A real app build still requires the toolchains detailed in `docs/BUILDING.md`, an authorized signing and distribution route, and on-device runtime test. No source-only test establishes that the crash is fixed.
