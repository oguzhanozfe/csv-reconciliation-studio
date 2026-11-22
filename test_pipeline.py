import csv
import io
import json
import unittest
from pathlib import Path
from pipeline import prepare, export


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(Path(__file__).with_name("example.json").read_text())
        self.e = prepare(self.data)

    def test_currency_block_and_ambiguity(self):
        self.assertEqual(len(self.e["candidates"]), 3)
        self.assertEqual(self.e["metrics"]["Ambiguous pairs"], 2)
        self.assertTrue(self.e["candidates"][0]["matching_reference"])

    def test_conflicting_approvals_rejected(self):
        with self.assertRaises(ValueError):
            export(self.data, self.e, self.e["candidates"])

    def test_one_to_one_conservation(self):
        out = export(self.data, self.e, self.e["candidates"][:2])
        count = lambda k: len(list(csv.DictReader(io.StringIO(out[k]))))
        self.assertEqual(2 * count("reconciled.csv") + count("unmatched.csv"), 7)

    def test_review_text_is_inert_and_signed_currency_remains_numeric(self):
        self.data["bank_csv"] = self.data["bank_csv"].replace("Return fee", "+priority")
        evidence = prepare(self.data)
        rows = csv.DictReader(
            io.StringIO(export(self.data, evidence, [])["unmatched.csv"])
        )
        fee = next(r for r in rows if r["id"] == "B20")
        self.assertEqual((fee["description"], fee["amount"]), ("'+priority", "-15.00"))
        self.assertEqual(
            next(r for r in evidence["records"] if r["source_id"] == "B20")[
                "description"
            ],
            "+priority",
        )

    def test_subcent_amount_rejected(self):
        with self.assertRaises(ValueError):
            prepare(
                dict(
                    self.data, bank_csv=self.data["bank_csv"].replace("89.95", "89.951")
                )
            )

    def test_malformed_header_and_out_of_range_amount_are_input_errors(self):
        samples = [
            '"unfinished header',
            self.data["bank_csv"].replace("89.95", "1e1000000"),
        ]
        for raw in samples:
            with self.subTest(raw=raw[:35]), self.assertRaises(ValueError):
                prepare(dict(self.data, bank_csv=raw))
