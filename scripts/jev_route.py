"""Evaluate project task routing with TypeSafe Jev, without invoking agents.

Usage (from repository root):
  Set TYPESAFE_API_KEY in scripts/.env (or the shell environment).
  cd backend && uv run python ../scripts/jev_route.py --cases ../scripts/jev_route_cases.json
  cd backend && uv run python ../scripts/jev_route.py --task "Find references to a config key"

Task text is sent to the external TypeSafe API. Do not include secrets or private source.
"""

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path
from urllib import error, request

API_URL = "https://api.typesafe.ai/v1/systemone"
ENV_FILE = Path(__file__).with_name(".env")
LABELS = ("luna_low", "sol_low", "sol_medium", "main_astra")
CRITERIA = {
    "luna_low": (
        "Only bounded search, file discovery, or repetition of a fully decided "
        "mechanical edit rule; no implementation design or independent judgment."
    ),
    "sol_low": (
        "Ordinary application or tool implementation with established requirements, "
        "tests, and limited design decisions; not merely mechanical work."
    ),
    "sol_medium": (
        "Stuck debugging where evidence is conflicting or the root cause is not yet "
        "clear; investigate and test hypotheses before fixing."
    ),
    "main_astra": (
        "Planning, orchestration, final independent review, or a difficult new "
        "database, concurrency, security, payment, or architecture decision. Do not "
        "choose merely because the task mentions these domains if its rule is already decided."
    ),
}
QUESTION = (
    "Under this project's AGENTS.md and model delegation guide, who should own "
    "the task at `tasks[{index}].text`? Select the least costly sufficient tier. "
    "Classify the work actually requested, not just domain words. "
    "This is advisory only; do not execute or delegate the task."
)


class RouteError(Exception):
    """Safe-to-display input, service, or response error."""


def validate_cases(data):
    if not isinstance(data, list) or not data:
        raise RouteError("Cases must be a non-empty JSON array.")
    if len(data) > 50:
        raise RouteError("At most 50 cases are allowed per request.")
    seen = set()
    for index, case in enumerate(data):
        if not isinstance(case, dict):
            raise RouteError(f"Case {index + 1} must be an object.")
        case_id, task = case.get("id"), case.get("task")
        if not isinstance(case_id, str) or not case_id.strip() or len(case_id) > 80:
            raise RouteError(f"Case {index + 1} has an invalid id.")
        if case_id in seen:
            raise RouteError(f"Duplicate case id: {case_id}")
        seen.add(case_id)
        if not isinstance(task, str) or not task.strip() or len(task) > 4000:
            raise RouteError(f"Case {case_id} has invalid task text.")
        if case.get("expected") not in LABELS:
            raise RouteError(f"Case {case_id} has invalid expected label.")
    return data


def build_payload(cases):
    return {
        "state": {"tasks": [{"id": case["id"], "text": case["task"]} for case in cases]},
        "model": "jev-latest",
        "questions": {
            f"route_{index}": {
                "type": "choice",
                "instructions": QUESTION.format(index=index),
                "criteria": CRITERIA,
            }
            for index in range(len(cases))
        },
    }


def fetch(payload, api_key, *, timeout=25, retries=2, sleep=time.sleep):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    for attempt in range(retries + 1):
        req = request.Request(
            API_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=timeout) as response:
                return json.load(response)
        except error.HTTPError as exc:
            if exc.code in (429, 529) and attempt < retries:
                sleep(2**attempt)
                continue
            raise RouteError(f"Jev API returned HTTP {exc.code}.") from None
        except (error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            if attempt < retries:
                sleep(2**attempt)
                continue
            raise RouteError(f"Jev API network failure ({type(exc).__name__}).") from None
        except (ValueError, UnicodeError):
            raise RouteError("Jev API returned invalid JSON.") from None
    raise RouteError("Jev API request failed.")


def validate_answers(response, count):
    if not isinstance(response, dict) or not isinstance(response.get("answers"), dict):
        raise RouteError("Jev API response has no answers object.")
    answers = response["answers"]
    expected_ids = {f"route_{index}" for index in range(count)}
    if set(answers) != expected_ids:
        raise RouteError("Jev API response question IDs do not match the request.")
    result = []
    for index in range(count):
        answer = answers[f"route_{index}"]
        if not isinstance(answer, dict) or answer.get("type") != "choice":
            raise RouteError(f"Jev API response route_{index} is not a Choice.")
        choice, confidence, probabilities = (
            answer.get("choice"),
            answer.get("confidence"),
            answer.get("probabilities"),
        )
        if (
            choice not in LABELS
            or not isinstance(probabilities, dict)
            or set(probabilities) != set(LABELS)
        ):
            raise RouteError(f"Jev API response route_{index} has invalid options.")
        values = (confidence, *probabilities.values())
        if any(
            type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1
            for value in values
        ):
            raise RouteError(f"Jev API response route_{index} has invalid probabilities.")
        if abs(sum(probabilities.values()) - 1) > 0.02:
            raise RouteError(f"Jev API response route_{index} probabilities do not sum to one.")
        result.append(answer)
    return result


def load_api_key(env_file=None):
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if key:
        return key
    if env_file is None:
        env_file = ENV_FILE
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError):
        raise RouteError("Cannot read the Jev env file.") from None
    for line in lines:
        name, separator, value = line.partition("=")
        if separator and name.strip() == "TYPESAFE_API_KEY":
            key = value.strip()
            if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
                key = key[1:-1]
            return key or None
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--task", help="One task to route")
    source.add_argument("--cases", type=Path, help="JSON array of {id, task, expected} cases")
    parser.add_argument("--probabilities", action="store_true", help="Show the Choice distribution")
    args = parser.parse_args(argv)
    try:
        if args.cases:
            try:
                cases = validate_cases(json.loads(args.cases.read_text(encoding="utf-8")))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise RouteError(f"Cannot read cases file ({type(exc).__name__}).") from None
        else:
            if not args.task or not args.task.strip():
                raise RouteError("Task text must not be empty.")
            cases = [{"id": "task", "task": args.task, "expected": "sol_low"}]
        api_key = load_api_key()
        if not api_key:
            raise RouteError("TYPESAFE_API_KEY is not set in the shell or scripts/.env.")
        answers = validate_answers(fetch(build_payload(cases), api_key), len(cases))
        print(f"{'ID':<18} {'PREDICTED':<14} {'EXPECTED':<14} {'MATCH':<5} CONF")
        correct = 0
        for case, answer in zip(cases, answers, strict=True):
            matched = answer["choice"] == case["expected"]
            correct += matched
            expected = case["expected"] if args.cases else "-"
            match = "yes" if matched else "no" if args.cases else "-"
            print(
                f"{case['id']:<18} {answer['choice']:<14} {expected:<14} "
                f"{match:<5} {answer['confidence']:.2f}"
            )
            if args.probabilities:
                print(
                    "  " + " ".join(f"{key}={answer['probabilities'][key]:.2f}" for key in LABELS)
                )
        if args.cases:
            print(f"Accuracy: {correct}/{len(cases)} ({correct / len(cases):.0%})")
        return 0
    except RouteError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
