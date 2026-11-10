import unittest
from collections import Counter
from copy import deepcopy

from evaluate import (
    ROOT, STRATEGIES, dataset_digest, examples_from, label_from, prompt_messages,
    read_issues, read_predictions, render_report, score, setup_digest,
)


class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.issues = read_issues(ROOT / "data" / "issues.csv")

    def capture(self):
        return {
            "model": "test-double",
            "revision": "fixture",
            "engine": "unit test",
            "dataset_sha256": dataset_digest(self.issues),
            "setup_sha256": setup_digest(self.issues),
            "responses": [
                {"id": row.id, "strategy": mode, "raw": '{"label":"bug"}'}
                for row in self.issues if row.split == "test" for mode in STRATEGIES
            ],
        }

    def test_balanced_split(self):
        counts = Counter((row.split, row.language, row.label) for row in self.issues)
        self.assertEqual(len(counts), 12)
        self.assertEqual(set(counts.values()), {5})
        self.assertEqual(len({row.text for row in self.issues}), 60)

    def test_few_shot_examples_are_only_from_dev(self):
        examples = examples_from(self.issues)
        self.assertTrue(all(example.split == "dev" for example in examples))
        self.assertEqual(len({(row.language, row.label) for row in examples}), 6)
        target = next(row for row in self.issues if row.split == "test")
        for mode, length in (("zero-shot", 2), ("few-shot", 14)):
            messages = prompt_messages(target, mode, examples)
            self.assertEqual(len(messages), length)
            self.assertEqual(messages[-1], {"role": "user", "content": target.text})

    def test_strict_output_contract(self):
        self.assertEqual(label_from(' {"label": "docs"}\n'), "docs")
        for value in (
            'docs', '{"label":"other"}', '{"label":"docs","extra":1}', '["docs"]',
            '{"label":"bug","label":"docs"}', 'null', '~~~json\n{"label":"docs"}\n~~~',
            '{"label":{"label":"docs"}}',
        ):
            with self.subTest(value=value):
                self.assertIsNone(label_from(value))

    def test_invalid_answer_counts_as_false_negative(self):
        count, correct, valid, f1 = score(["bug", "docs", "feature"], ["bug", None, "feature"])
        self.assertEqual((count, correct, valid), (3, 2, 2))
        self.assertAlmostEqual(f1, 2 / 3)

    def test_replay_requires_complete_capture_and_same_setup(self):
        valid = self.capture()
        for change in ("missing", "duplicate", "dataset", "setup"):
            capture = deepcopy(valid)
            if change == "missing":
                capture["responses"].pop()
            elif change == "duplicate":
                capture["responses"].append(capture["responses"][0])
            else:
                capture[f"{change}_sha256"] = "bad-digest"
            with self.subTest(change=change), self.assertRaises(ValueError):
                read_predictions(self.issues, capture)

    def test_report_keeps_language_breakdown(self):
        report = render_report(self.issues, self.capture())
        for mode in STRATEGIES:
            for language in ("kk", "ru"):
                self.assertIn(f"| {mode} | {language} | 5/15 | 15/15 | 0.167 |", report)


if __name__ == "__main__":
    unittest.main()
