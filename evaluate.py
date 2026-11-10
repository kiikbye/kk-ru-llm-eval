import argparse
import csv
import hashlib
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
LABELS = ("bug", "docs", "feature")
LANGUAGES = ("kk", "ru")
STRATEGIES = ("zero-shot", "few-shot")
DEFAULT_MODEL = "Qwen2.5-0.5B-Instruct-Q4_K_M"
DEMO_IDS = ("kk-d02", "kk-d06", "kk-d13", "ru-d03", "ru-d08", "ru-d12")
GENERATION = {"temperature": 0, "seed": 42, "max_tokens": 48}
INSTRUCTION = (
    "Classify the software issue as bug, docs, or feature. "
    "Use bug for broken existing software behavior, docs for changes to documentation, "
    "and feature for new software behavior. Return only a JSON object with one key, label."
)


@dataclass(frozen=True)
class Issue:
    id: str
    split: str
    language: str
    label: str
    text: str


def read_issues(path):
    with path.open(encoding="utf-8", newline="") as source:
        rows = [Issue(**row) for row in csv.DictReader(source)]
    if not rows or len({row.id for row in rows}) != len(rows):
        raise ValueError("The dataset must have distinct issue IDs.")
    for issue in rows:
        if (issue.split not in ("dev", "test") or issue.language not in LANGUAGES
                or issue.label not in LABELS or not issue.text.strip()):
            raise ValueError(f"Invalid dataset entry: {issue.id}")
    for split in ("dev", "test"):
        cells = {(row.language, row.label) for row in rows if row.split == split}
        if cells != {(language, label) for language in LANGUAGES for label in LABELS}:
            raise ValueError(f"{split} must cover every language and label.")
    return rows


def digest(value):
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def dataset_digest(issues):
    return digest([asdict(issue) for issue in issues])


def prompt_messages(issue, strategy, examples):
    messages = [{"role": "system", "content": INSTRUCTION}]
    if strategy == "few-shot":
        for example in examples:
            messages.append({"role": "user", "content": example.text})
            messages.append({"role": "assistant", "content": json.dumps({"label": example.label})})
    return [*messages, {"role": "user", "content": issue.text}]


def examples_from(issues):
    development = {row.id: row for row in issues if row.split == "dev"}
    return [development[issue_id] for issue_id in DEMO_IDS]


def setup_digest(issues):
    examples = examples_from(issues)
    held_out = [issue for issue in issues if issue.split == "test"]
    return digest({
        "generation": GENERATION,
        "prompts": [prompt_messages(issue, strategy, examples)
                    for issue in held_out for strategy in STRATEGIES],
    })


def label_from(raw):
    try:
        fields = json.loads(raw, object_pairs_hook=tuple)
    except json.JSONDecodeError:
        return None
    if isinstance(fields, tuple) and len(fields) == 1:
        key, label = fields[0]
        if key == "label" and label in LABELS:
            return label
    return None


def classify(endpoint, model, messages):
    body = json.dumps({"model": model, "messages": messages, **GENERATION}).encode("utf-8")
    request = Request(endpoint, data=body, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=90) as response:
        value = json.load(response)["choices"][0]["message"]["content"]
    if not isinstance(value, str):
        raise ValueError("The model server returned a non-text response.")
    return value


def record(issues, endpoint, model, revision, engine):
    examples = examples_from(issues)
    held_out = [issue for issue in issues if issue.split == "test"]
    responses = []
    for number, issue in enumerate(held_out, start=1):
        for strategy in STRATEGIES:
            messages = prompt_messages(issue, strategy, examples)
            raw = classify(endpoint, model, messages)
            responses.append({"id": issue.id, "strategy": strategy, "raw": raw})
        print(f"{number}/{len(held_out)} issues evaluated", file=sys.stderr, flush=True)
    return {
        "model": model, "revision": revision, "engine": engine,
        "dataset_sha256": dataset_digest(issues), "setup_sha256": setup_digest(issues),
        "generation": GENERATION, "demo_ids": DEMO_IDS, "responses": responses,
    }


def read_predictions(issues, capture):
    if capture["dataset_sha256"] != dataset_digest(issues):
        raise ValueError("The recorded dataset differs from the current dataset.")
    if capture["setup_sha256"] != setup_digest(issues):
        raise ValueError("The recorded prompts or generation settings differ from this version.")
    expected = {(row.id, mode) for row in issues if row.split == "test" for mode in STRATEGIES}
    predictions = {}
    for row in capture["responses"]:
        key = row["id"], row["strategy"]
        if key not in expected or key in predictions or not isinstance(row["raw"], str):
            raise ValueError(f"Unexpected, duplicate, or non-text response: {key}")
        predictions[key] = label_from(row["raw"])
    if set(predictions) != expected:
        raise ValueError("The capture is incomplete.")
    return predictions


def score(expected, predicted):
    scores = []
    for label in LABELS:
        tp = sum(gold == actual == label for gold, actual in zip(expected, predicted))
        total = expected.count(label) + predicted.count(label)
        scores.append(2 * tp / total if total else 0)
    count = len(expected)
    correct = sum(gold == actual for gold, actual in zip(expected, predicted))
    valid = sum(label is not None for label in predicted)
    return count, correct, valid, sum(scores) / len(scores)


def render_report(issues, capture):
    predictions = read_predictions(issues, capture)
    held_out = [issue for issue in issues if issue.split == "test"]
    lines = [
        "# Recorded evaluation", "",
        f"**Model** · {capture['model']}", "",
        f"**Model revision** · {capture['revision']}", "",
        f"**Runtime** · {capture['engine']}", "",
        "| Strategy | Language | Correct | Schema-valid JSON | Macro-F1 |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for strategy in STRATEGIES:
        for language in (*LANGUAGES, "all"):
            group = [issue for issue in held_out if language in (issue.language, "all")]
            expected = [issue.label for issue in group]
            predicted = [predictions[issue.id, strategy] for issue in group]
            count, correct, valid, f1 = score(expected, predicted)
            lines.append(f"| {strategy} | {language} | {correct}/{count} | {valid}/{count} | {f1:.3f} |")
    lines += [
        "", "Macro-F1 averages the F1 scores for bug, docs, and feature. "
        "Malformed JSON, extra fields, and unknown labels count as incorrect.",
        "", "## Example disagreements and errors", "",
        "| ID | Issue | Expected | Zero-shot | Few-shot |",
        "| --- | --- | --- | --- | --- |",
    ]
    errors = []
    for issue in held_out:
        first, second = (predictions[issue.id, strategy] for strategy in STRATEGIES)
        if first != issue.label or second != issue.label:
            errors.append((issue, first, second))
    # Show changing predictions before persistent errors.
    errors.sort(key=lambda item: item[1] == item[2])
    for issue, first, second in errors[:6]:
        text = issue.text.replace("|", "&#124;")
        lines.append(f"| {issue.id} | {text} | {issue.label} | {first or 'invalid'} | {second or 'invalid'} |")
    if not errors:
        lines += ["", "Both strategies matched all labels in this run."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Evaluate bilingual software issue routing.")
    commands = parser.add_subparsers(dest="command", required=True)
    for mode in ("run", "replay"):
        command = commands.add_parser(mode)
        command.add_argument("--capture", type=Path, default=ROOT / "results" / "capture.json")
        command.add_argument("--report", type=Path)
        if mode == "run":
            command.add_argument("--endpoint", default="http://127.0.0.1:8080/v1/chat/completions")
            command.add_argument("--model", default=DEFAULT_MODEL)
            command.add_argument("--revision", required=True)
            command.add_argument("--engine", required=True)
    args = parser.parse_args()
    try:
        issues = read_issues(ROOT / "data" / "issues.csv")
        if args.command == "run":
            url = urlsplit(args.endpoint)
            if url.scheme != "http" or url.hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError("Use an HTTP endpoint on localhost for live inference.")
            capture = record(issues, args.endpoint, args.model, args.revision, args.engine)
            report = render_report(issues, capture)
            args.capture.parent.mkdir(parents=True, exist_ok=True)
            args.capture.write_text(json.dumps(capture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        else:
            capture = json.loads(args.capture.read_text(encoding="utf-8"))
            report = render_report(issues, capture)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(report, encoding="utf-8")
        else:
            print(report, end="")
    except (OSError, URLError, ValueError, KeyError, TypeError, IndexError) as error:
        parser.exit(1, f"Evaluation failed: {error}\n")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
