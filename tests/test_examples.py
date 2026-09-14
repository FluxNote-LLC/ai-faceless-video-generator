"""Offline contract tests: only a local mock server, never production APIs."""
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("example", ROOT / "python/generate.py")
example = importlib.util.module_from_spec(spec)
spec.loader.exec_module(example)
INPUT = ROOT / "examples/ocean-facts.json"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.reply()

    def do_POST(self):
        self.reply()

    def reply(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.server.calls.append((self.command, self.path, dict(self.headers), json.loads(body) if body else None))
        mode = self.server.mode
        status = int(mode) if mode.isdigit() else 200
        data = {"status": "failed", "id": "test-video"}
        if self.path.endswith("/estimate"):
            data = {"estimated_credits": 100}
        elif self.command == "POST":
            status = 202
            data = {"id": "test-video"}
            if mode == "create-error":
                status = 503
        elif self.path.endswith(("/voices", "/options")):
            data = {"data": []}
        if mode == "redirect":
            status = 302
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        if status == 429:
            self.send_header("Retry-After", "10")
        if status == 302:
            self.send_header("Location", "/never-follow-this")
        self.end_headers()
        if mode == "broken":
            self.wfile.write(b"not-json")
        else:
            # Deliberately hostile error text must never reach command output.
            if status >= 400:
                data = {"error": {"message": "private mock-secret"}}
            self.wfile.write(json.dumps(data).encode())


class ExamplesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.server.calls = []
        self.server.mode = "normal"
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def run_cli(self, language, *args):
        entry = (["node", str(ROOT / "javascript/generate.mjs")] if language == "js" else
                 [os.sys.executable, str(ROOT / "python/generate.py")])
        return subprocess.run(entry + list(args), cwd=self.temp.name, text=True, capture_output=True, timeout=15,
                              env={**os.environ, "FLUXNOTE_API_KEY": "mock-secret", "FLUXNOTE_API_URL": self.origin})

    def test_catalog_both_languages(self):
        for language in ("js", "py"):
            self.server.calls.clear()
            result = self.run_cli(language, "catalog")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([c[1] for c in self.server.calls], ["/v1/options", "/v1/voices"])

    def test_default_create_is_estimate_only(self):
        for language in ("js", "py"):
            self.server.calls.clear()
            result = self.run_cli(language, "create", str(INPUT))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([c[1] for c in self.server.calls], ["/v1/videos/estimate"])
            self.assertFalse(list(Path(self.temp.name).glob("*.receipt.json")))

    def test_confirmed_create_receipt_and_failed_job(self):
        for language in ("js", "py"):
            self.server.calls.clear()
            result = self.run_cli(language, "create", str(INPUT), "--confirm")
            self.assertEqual(result.returncode, 1)
            self.assertIn("failed or stopped", result.stderr)
            self.assertEqual([c[1] for c in self.server.calls], ["/v1/videos/estimate", "/v1/videos", "/v1/videos/test-video"])
            create = self.server.calls[1]
            headers = {k.lower(): v for k, v in create[2].items()}
            key = headers["idempotency-key"]
            receipt = json.loads((Path(self.temp.name) / (key + ".receipt.json")).read_text())
            self.assertEqual(receipt["idempotency_key"], key)
            self.assertEqual(receipt["input"], create[3])
            self.assertEqual(receipt["id"], "test-video")
            self.assertNotIn("mock-secret", json.dumps(receipt) + result.stdout + result.stderr)
            if os.name != "nt":
                self.assertEqual((Path(self.temp.name) / (key + ".receipt.json")).stat().st_mode & 0o777, 0o600)

    def test_errors_are_actionable_and_do_not_leak_key(self):
        for language in ("js", "py"):
            for status, message in (("401", "API key"), ("403", "scopes"), ("402", "credits"), ("429", "10 seconds")):
                with self.subTest(language=language, status=status):
                    self.server.mode = status
                    self.server.calls.clear()
                    result = self.run_cli(language, "estimate", str(INPUT))
                    self.assertEqual(result.returncode, 1)
                    self.assertIn(message, result.stderr)
                    self.assertNotIn("mock-secret", result.stderr)
                    self.assertEqual(len(self.server.calls), 1)

    def test_api_redirects_and_invalid_json(self):
        for language in ("js", "py"):
            for mode in ("redirect", "broken"):
                self.server.mode = mode
                self.server.calls.clear()
                result = self.run_cli(language, "estimate", str(INPUT))
                self.assertEqual(result.returncode, 1)
                self.assertEqual(len(self.server.calls), 1)

    def test_invalid_input_never_sends_request(self):
        path = Path(self.temp.name) / "invalid.json"
        path.write_text('{"prompt":"hello","script":"hello"}')
        for language in ("js", "py"):
            result = self.run_cli(language, "create", str(path), "--confirm")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(self.server.calls, [])

    def test_resume_never_creates_another_video(self):
        path = Path(self.temp.name) / "job.receipt.json"
        path.write_text(json.dumps({"origin": self.origin, "id": "test-video"}))
        for language in ("js", "py"):
            self.server.calls.clear()
            result = self.run_cli(language, "resume", str(path))
            self.assertEqual(result.returncode, 1)  # mock job failed, no writes
            self.assertEqual([(c[0], c[1]) for c in self.server.calls], [("GET", "/v1/videos/test-video")])

    def test_uncertain_write_is_not_retried_and_keeps_receipt(self):
        self.server.mode = "create-error"
        for language in ("js", "py"):
            self.server.calls.clear()
            result = self.run_cli(language, "create", str(INPUT), "--confirm")
            self.assertEqual(result.returncode, 1)
            self.assertEqual([c[1] for c in self.server.calls], ["/v1/videos/estimate", "/v1/videos"])
            headers = {k.lower(): v for k, v in self.server.calls[-1][2].items()}
            key = headers["idempotency-key"]
            receipt = json.loads((Path(self.temp.name) / (key + ".receipt.json")).read_text())
            self.assertNotIn("id", receipt)
            self.assertEqual(receipt["idempotency_key"], key)
            self.assertNotIn("mock-secret", result.stderr)

    def test_uncertain_or_foreign_receipt_sends_nothing(self):
        path = Path(self.temp.name) / "job.receipt.json"
        for language in ("js", "py"):
            for receipt in ({"origin": self.origin}, {"origin": "https://example.invalid", "id": "x"}):
                path.write_text(json.dumps(receipt))
                result = self.run_cli(language, "resume", str(path))
                self.assertEqual(result.returncode, 1)
                self.assertEqual(self.server.calls, [])

    def test_python_wait_timeout_completed_and_review(self):
        class Fake:
            def __init__(self, data):
                self.data = data
            def request(self, *args, **kwargs):
                return self.data, 0
        self.assertEqual(example.wait_for(Fake({"status": "completed"}), "id"), {"status": "completed"})
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            example.wait_for(Fake({"status": "processing"}), "id", seconds=0.01, interval=0.005)
        with self.assertRaisesRegex(RuntimeError, "review"):
            example.wait_for(Fake({"stage": "review_ready"}), "id")

    def test_python_download_redirect_and_no_overwrite(self):
        calls = []
        class FakeOpener:
            def open(self, req, **kwargs):
                calls.append(req)
                if len(calls) == 1:
                    raise HTTPError(req.full_url, 302, "Found", {"Location": "https://media.example.invalid/video.mp4"}, io.BytesIO())
                return io.BytesIO(b"fake-video")
        output = Path(self.temp.name) / "test.mp4"
        example.download("https://example.invalid/start", output, FakeOpener())
        self.assertEqual(output.read_bytes(), b"fake-video")
        self.assertTrue(all(not c.has_header("Authorization") for c in calls))
        with self.assertRaises(FileExistsError):
            example.download("https://example.invalid/video", output, FakeOpener())
        self.assertFalse(list(Path(self.temp.name).glob("*.part")))
        self.assertEqual(output.read_bytes(), b"fake-video")

    def test_python_rejects_unsafe_urls(self):
        for value in ("http://example.com", "https://user:pass@example.com", "https://example.com/path", "https://example.com?key=x"):
            with self.assertRaises(ValueError):
                example.api_origin(value)
        for value in ("http://example.com/v.mp4", "https://user:pass@example.com/v.mp4"):
            with self.assertRaises(ValueError):
                example.media_url(value)


if __name__ == "__main__":
    unittest.main()
