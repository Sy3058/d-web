"""Offline contract tests for the Jev routing CLI."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import jev_route

CASES = [
    {
        "id": "search",
        "task": "Find references to a config key.",
        "expected": "luna_low",
    },
    {"id": "feature", "task": "Implement an approved endpoint.", "expected": "sol_low"},
]


def response(*choices):
    return {
        "answers": {
            f"route_{index}": {
                "type": "choice",
                "choice": choice,
                "confidence": 0.8,
                "probabilities": {label: int(label == choice) for label in jev_route.LABELS},
            }
            for index, choice in enumerate(choices)
        }
    }


class FakeResponse:
    def __init__(self, data):
        self.data = json.dumps(data).encode()

    def __enter__(self):
        return io.BytesIO(self.data)

    def __exit__(self, *_):
        return False


class JevRouteTests(unittest.TestCase):
    def test_payload_has_one_choice_per_case(self):
        payload = jev_route.build_payload(CASES)
        self.assertEqual(payload["model"], "jev-latest")
        self.assertEqual(len(payload["questions"]), 2)
        self.assertEqual(payload["state"]["tasks"][1]["text"], CASES[1]["task"])
        self.assertEqual(payload["questions"]["route_0"]["type"], "choice")
        self.assertEqual(set(payload["questions"]["route_1"]["criteria"]), set(jev_route.LABELS))

    def test_http_request_and_batch_report(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "cases.json"
            path.write_text(json.dumps(CASES), encoding="utf-8")
            output = io.StringIO()

            def urlopen(req, timeout):
                self.assertEqual(req.full_url, jev_route.API_URL)
                self.assertEqual(req.get_method(), "POST")
                self.assertEqual(req.get_header("Authorization"), "Bearer secret")
                self.assertEqual(timeout, 25)
                self.assertEqual(len(json.loads(req.data)["questions"]), 2)
                return FakeResponse(response("luna_low", "sol_medium"))

            with (
                patch.dict(os.environ, {"TYPESAFE_API_KEY": "secret"}),
                patch.object(jev_route.request, "urlopen", side_effect=urlopen),
                redirect_stdout(output),
            ):
                code = jev_route.main(["--cases", str(path), "--probabilities"])
            self.assertEqual(code, 0)
            self.assertIn("Accuracy: 1/2", output.getvalue())
            self.assertIn("luna_low=1.00", output.getvalue())
            self.assertNotIn("secret", output.getvalue())

    def test_case_validation(self):
        for cases in (
            [],
            [{"id": "x", "task": "", "expected": "sol_low"}],
            [CASES[0], CASES[0]],
            [{"id": "x", "task": "Do it", "expected": "bad"}],
        ):
            with self.subTest(cases=cases), self.assertRaises(jev_route.RouteError):
                jev_route.validate_cases(cases)

    def test_response_validation(self):
        invalid = [
            {},
            {"answers": {}},
            response("unknown"),
            {"answers": {"route_0": {"type": "noul"}}},
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(jev_route.RouteError):
                jev_route.validate_answers(value, 1)
        value = response("sol_low")
        value["answers"]["route_0"]["probabilities"]["sol_low"] = 0.2
        with self.assertRaises(jev_route.RouteError):
            jev_route.validate_answers(value, 1)

    def test_missing_key_does_not_call_api(self):
        stderr = io.StringIO()
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.dict(os.environ, {}, clear=True),
            patch.object(jev_route, "ENV_FILE", Path(temp) / "missing.env"),
            patch.object(jev_route, "fetch") as fetch,
            redirect_stderr(stderr),
        ):
            code = jev_route.main(["--task", "Find files"])
        self.assertEqual(code, 1)
        self.assertIn("TYPESAFE_API_KEY is not set", stderr.getvalue())
        fetch.assert_not_called()

    def test_api_key_loads_from_local_env_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / ".env"
            path.write_text('TYPESAFE_API_KEY="file-secret"\n', encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(jev_route.load_api_key(path), "file-secret")
            with patch.dict(os.environ, {"TYPESAFE_API_KEY": "shell-secret"}):
                self.assertEqual(jev_route.load_api_key(path), "shell-secret")

    def test_auth_error_does_not_leak_key_or_response(self):
        secret = "test-secret-never-print"
        http_error = HTTPError(jev_route.API_URL, 401, secret, {}, io.BytesIO(secret.encode()))
        with patch.object(jev_route.request, "urlopen", side_effect=http_error):
            with self.assertRaisesRegex(jev_route.RouteError, "HTTP 401") as caught:
                jev_route.fetch(jev_route.build_payload(CASES), secret, sleep=lambda _: None)
        self.assertNotIn(secret, str(caught.exception))

    def test_retries_only_transient_failures(self):
        with patch.object(
            jev_route.request,
            "urlopen",
            side_effect=[
                HTTPError(jev_route.API_URL, 429, "rate limited", {}, None),
                URLError("offline"),
                FakeResponse(response("luna_low")),
            ],
        ) as urlopen:
            value = jev_route.fetch(
                jev_route.build_payload(CASES[:1]), "secret", sleep=lambda _: None
            )
        self.assertEqual(value["answers"]["route_0"]["choice"], "luna_low")
        self.assertEqual(urlopen.call_count, 3)


if __name__ == "__main__":
    unittest.main()
