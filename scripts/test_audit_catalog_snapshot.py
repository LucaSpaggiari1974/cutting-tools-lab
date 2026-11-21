#!/usr/bin/env python3
"""Test di regressione per l'audit read-only dello snapshot gzip."""
import gzip
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("audit_catalog_snapshot.py")

class CatalogAuditTests(unittest.TestCase):
    def run_audit(self, payload):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "catalog.json.gz"
            with gzip.open(path, "wt", encoding="utf-8") as stream:
                json.dump(payload, stream)
            return subprocess.run(
                [sys.executable, str(SCRIPT), str(path)],
                text=True, capture_output=True, check=False,
            )

    def test_spgx_and_duplicate_candidates_are_reported_without_changes(self):
        items = [
            {"code": "SPGX110708WG", "grade": "IN2505", "vc": None},
            {"code": "SPGX140512WG", "grade": "IN2505"},
            {"code": "SPGX110708WG", "grade": "IN2505"},
            {"code": "SPGX110708WG", "grade": "OTHER"},
        ]
        result = self.run_audit({"items": items})
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["items"], 4)
        self.assertEqual(len(report["spgxCandidates"]["SPGX110708WG"]), 3)
        self.assertEqual(len(report["spgxCandidates"]["SPGX140512WG"]), 1)
        self.assertIn(
            {"code": "SPGX110708WG", "grade": "IN2505", "count": 2},
            report["duplicateIdentityCandidates"],
        )
        self.assertEqual(report["spgxCandidates"]["SPGX110708WG"][0]["record"]["vc"], None)

    def test_similar_but_different_code_is_not_a_match(self):
        result = self.run_audit({"items": [{"code": "XSPGX110708WG", "grade": "IN2505"}, {"code": "SPGX110708WG", "grade": "IN2505"}]})
        self.assertEqual(result.returncode, 0, result.stderr)
        hits = json.loads(result.stdout)["spgxCandidates"]["SPGX110708WG"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["record"]["code"], "SPGX110708WG")

    def test_exact_grade_is_not_inferred_from_code_only(self):
        items = [
            {"code": "SPGX110708WG", "grade": "OTHER"},
            {"code": "SPGX110708WG"},
            {"code": "SPGX110708WG", "grade": "IN2505"},
            {"code": "SPGX110708WG IN2505"},
        ]
        result = self.run_audit({"items": items})
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(len(report["spgxCandidates"]["SPGX110708WG"]), 4)
        self.assertEqual(len(report["spgxExactIN2505Candidates"]["SPGX110708WG"]), 2)

    def test_unexpected_schema_fails_closed(self):
        result = self.run_audit({"products": [{"code": "SPGX110708WG"}]})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Struttura inattesa", result.stderr)

    def test_list_root_is_supported(self):
        result = self.run_audit([{"codice": "SPGX140512WG", "grado": "IN2505"}])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["items"], 1)

if __name__ == "__main__":
    unittest.main()
