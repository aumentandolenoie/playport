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
