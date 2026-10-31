# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-only security regression tests for the optional private log archive.

This is not a Swift/iOS compile and cannot replace device tests.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UPLOAD = ROOT / "app/Sources/S1Probe/UI/PrivateReportUpload.swift"
DETAIL = ROOT / "app/Sources/S1Probe/UI/GameDetailView.swift"


class PrivateReportUploadSourceTests(unittest.TestCase):
    def test_private_destination_gate_is_present(self):
        text = UPLOAD.read_text()
        self.assertIn('json["private"] as? Bool == true', text)
        self.assertIn("try await validatePrivateRepository(repository: repository, token: credential)", text)
        self.assertIn("try await validatePrivateRepository(repository: repository, token: credential)", text)

    def test_token_not_embedded_or_in_defaults(self):
        text = UPLOAD.read_text()
        self.assertIn("SecItemAdd(values as CFDictionary", text)
        self.assertIn("kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly", text)
        self.assertNotIn("UserDefaults.standard.set(credential", text)
        self.assertNotIn("UserDefaults.standard.set(token", text)

    def test_share_sheet_still_works_and_unique_folder(self):
        text = DETAIL.read_text()
        self.assertIn("present(zip.map { [$0] } ?? urls)", text)
        self.assertIn("PrivateReportUpload.uploadIfEnabled(zip, gameID: t.id)", text)
        self.assertIn('UUID().uuidString', text)


if __name__ == "__main__":
    unittest.main()
