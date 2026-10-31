#!/usr/bin/env python3
"""Compare Playport KTANE crash report ZIPs. Standard-library only, read-only."""
import argparse
import collections
import json
import re
import zipfile
from pathlib import Path

PATTERNS = {
    "store_noalias": re.compile(r"\[store-noalias\]"),
    "illegal_instruction": re.compile(r"\bcode[=:]c000001d\b", re.I),
    "access_violation": re.compile(r"(?:\bc0000005\b|AV READ)", re.I),
    "jit_host_pc": re.compile(r"HOST PC LEAKED INTO STATE\.RIP"),
    "code_buffer_protection": re.compile(r"Failed to mprotect last page of code buffer", re.I),
    "mono": re.compile(r"\bmono(?:-2\.0-bdwgc)?\.dll\b", re.I),
    "title_start": re.compile(r"ktane\.exe", re.I),
    "av_detail": re.compile(r"\[av-detail\]"),
    "alias_owned": re.compile(r"\[alias-own\].*OWNED by live anon JIT alias"),
    "unowned_guest_stack": re.compile(r"\[mach-deliver\].*no TEB owns sp="),
    "near_null_load": re.compile(r"\[store-noalias\].*addr=0x54\b.*insn=0xb84000c8", re.I),
    "near_null_fault": re.compile(r"(?:\[fault_rip\]|\[av-detail\]).*(?:addr=0x54\b|p1=0x54\b)"),
}
EXIT = re.compile(r"\btitle: done\s+exit=(0x[0-9a-f]+)\s+after_s=(\d+)", re.I)

def analyze(path):
    output = {"file": str(path), "logs": []}
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if not re.search(r"playport(?:\.previous)?\.log$", name, re.I):
                continue
            if archive.getinfo(name).file_size > 100_000_000:
                raise ValueError("Log exceeds 100 MB: " + name)
            counts = collections.Counter()
            examples = {}
            exits = []
            for number, line in enumerate(archive.read(name).decode("utf-8", "replace").splitlines(), 1):
                for key, pattern in PATTERNS.items():
                    if pattern.search(line):
                        counts[key] += 1
                        if key not in examples:
                            examples[key] = {"line": number, "text": line[:500]}
                match = EXIT.search(line)
                if match:
                    exits.append({"exit": match.group(1).lower(), "seconds": int(match.group(2)), "line": number})
            output["logs"].append({"name": name, "counts": dict(counts), "examples": examples, "exits": exits})
    return output

def main():
    parser = argparse.ArgumentParser(description="Compare Playport KTANE logs without extracting ZIPs")
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    reports = [analyze(path) for path in args.reports]
    if args.json:
        print(json.dumps(reports, indent=2))
    else:
        print("Previous logs may overlap across exported reports; do not count them as independent runs.")
        for report in reports:
            print("\n" + report["file"])
            for log in report["logs"]:
                print(" ", log["name"])
                print("  ", log["counts"])
                print("  exits:", log["exits"])
                for key in ("store_noalias", "illegal_instruction", "jit_host_pc"):
                    if key in log["examples"]:
                        print("  ", key, log["examples"][key])

if __name__ == "__main__":
    main()
