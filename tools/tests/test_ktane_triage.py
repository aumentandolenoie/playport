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

    def test_no_matching_logs(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "empty.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("report.json", "{}")
            self.assertEqual(analyze(archive)["logs"], [])


if __name__ == "__main__":
    unittest.main()
