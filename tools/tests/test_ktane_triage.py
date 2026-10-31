#!/usr/bin/env python3
"""Run with: python3 -m unittest discover -s tools -p 'test_ktane_triage.py'."""
import tempfile
import unittest
import zipfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ktane_triage import analyze


class ReportTriageTests(unittest.TestCase):
    def test_two_logs_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "report.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("reports/playport.log", "\n".join([
                    "title: running ktane.exe",
                    "[store-noalias] NO pool/anon alias",
                    "[exc-disp] raise tid=00d0 code=c000001d",
                    "Exception: Code: C0000005",
                    "title: done exit=0xc0000005 after_s=4",
                ]))
                z.writestr("reports/playport.previous.log", "title: done exit=0xc0000005 after_s=6")
                z.writestr("report.json", "{}")
            report = analyze(archive)
            self.assertEqual(len(report["logs"]), 2)
            current = next(x for x in report["logs"] if x["name"].endswith("/playport.log"))
            self.assertEqual(current["counts"]["store_noalias"], 1)
            self.assertEqual(current["counts"]["illegal_instruction"], 1)
            self.assertEqual(current["counts"]["access_violation"], 2)
            self.assertEqual(current["exits"][0]["seconds"], 4)

    def test_distinguishes_near_null_and_mapped_alias(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "fault.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("playport.log", "\n".join([
                    "[store-noalias] addr=0x54 insn=0xb84000c8 NO pool/anon alias",
                    "[fault_rip] addr=0x54 kr=1(INVALID_ADDRESS)",
                    "[alias-own] OWNED by live anon JIT alias",
                    "[mach-deliver] no TEB owns sp=0x73fd2d0000",
                    "[av-detail] p0=READ p1=0x54",
                ]))
            counts = analyze(archive)["logs"][0]["counts"]
            self.assertEqual(counts["near_null_fault"], 2)
            self.assertEqual(counts["near_null_load"], 1)
            self.assertEqual(counts["alias_owned"], 1)
            self.assertEqual(counts["unowned_guest_stack"], 1)
            self.assertEqual(counts["store_noalias"], 1)

    def test_near_null_instruction_repeats_across_sessions(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "repeat.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("playport.log", "\n".join([
                    "[store-noalias] addr=0x54 insn=0xb84000c8",
                    "[fault_rip] addr=0x54 kr=1(INVALID_ADDRESS)",
                    "title: done exit=0xc0000005 after_s=4",
                    "[store-noalias] addr=0x54 insn=0xb84000c8",
                    "[fault_rip] addr=0x54 kr=1(INVALID_ADDRESS)",
                    "title: done exit=0xc0000005 after_s=4",
                ]))
            result = analyze(archive)["logs"][0]
            self.assertEqual(result["counts"]["near_null_load"], 2)
            self.assertEqual(len(result["exits"]), 2)

    def test_no_matching_logs(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "empty.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("report.json", "{}")
            self.assertEqual(analyze(archive)["logs"], [])


if __name__ == "__main__":
    unittest.main()
