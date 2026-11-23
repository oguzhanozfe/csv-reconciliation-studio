import csv
import io
import json
import unittest
import zipfile
from pathlib import Path

import studio


class PaymentDecisionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent
        self.source = json.loads((self.root / "examples/settlement-signoff.json").read_text())
        self.report = studio.analyze(self.source)
        self.first, self.second = self.report["candidates"]

    def bundle(self, choices):
        with zipfile.ZipFile(io.BytesIO(studio.release(self.source, choices))) as z:
            return {name: z.read(name) for name in z.namelist()}

    def test_controller_authorizes_lower_ranked_pair_and_retry_preserves_release_contents(self):
        self.assertEqual(self.first["book_id"], "L41")
        self.assertEqual(self.second["book_id"], "L42")
        choices = {self.second["id"]: "Checked the settlement advice."}
        bundle = self.bundle(choices)
        self.assertEqual(bundle, self.bundle(choices))
        trace = json.loads(bundle["payment-decisions.json"])
        self.assertEqual([r["status"] for r in trace], ["excluded_by_approved_match", "approved"])
        self.assertEqual(trace[0]["approved_matches"], [self.second["id"]])
        self.assertEqual(trace[1]["signoff"]["advice_reference"], "ADVICE-742")
        self.assertEqual(trace[1]["signoff"]["role"], "settlement_controller")
        self.assertTrue(trace[1]["signoff"]["reason"])
        cleared = list(csv.DictReader(io.StringIO(bundle["reconciled.csv"].decode())))
        pending = list(csv.DictReader(io.StringIO(bundle["unmatched.csv"].decode())))
        self.assertEqual([(r["bank_id"], r["book_id"]) for r in cleared], [("B13", "L42")])
        self.assertEqual([(r["source"], r["id"]) for r in pending], [("book", "L41")])
        self.assertEqual(bundle["payment-decisions.json"],
                         (self.root / "docs/settlement-decisions.json").read_bytes())

    def test_signoff_alone_cannot_clear_money_and_wrong_pair_cannot_be_approved(self):
        before = self.bundle({})
        trace = json.loads(before["payment-decisions.json"])
        self.assertEqual([r["status"] for r in trace], ["awaiting_controller", "awaiting_reviewer"])
        self.assertEqual(len(list(csv.DictReader(io.StringIO(before["unmatched.csv"].decode())))), 3)
        with self.assertRaisesRegex(ValueError, "no controller sign-off"):
            self.bundle({self.first["id"]: "I prefer the closest date."})
        self.assertEqual(before, self.bundle({}))

    def test_invalid_or_conflicting_signoffs_fail_before_a_release(self):
        signoff = self.source["settlement_signoffs"][0]
        for change in ({"role": "preparer"}, {"reason": "   "}, {"book_id": "missing"},
                       {"advice_reference": ""}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                studio.analyze(dict(self.source, settlement_signoffs=[dict(signoff, **change)]))
        conflicting = dict(signoff, case_id="CASE-015", book_id="L41")
        with self.assertRaisesRegex(ValueError, "cannot allocate"):
            studio.analyze(dict(self.source, settlement_signoffs=[signoff, conflicting]))

    def test_empty_signoff_register_holds_ambiguous_matches_and_legacy_input_still_runs(self):
        self.source["settlement_signoffs"] = []
        with self.assertRaisesRegex(ValueError, "no controller sign-off"):
            self.bundle({self.second["id"]: ""})
        del self.source["settlement_signoffs"]
        self.assertNotIn("payment-decisions.json", self.bundle({self.second["id"]: ""}))
