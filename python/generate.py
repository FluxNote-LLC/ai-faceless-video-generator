#!/usr/bin/env python3
"""Standalone FluxNote API example; Python 3.9+, standard library only."""
import json
import math
import os
import re
import sys
import time
import uuid
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urljoin
from urllib.request import Request, build_opener, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api_origin(value="https://api.fluxnote.io"):
    u = urlparse(value)
    local = u.hostname in ("localhost", "127.0.0.1", "::1")
    if (not u.hostname or u.scheme not in ("https", "http") or
            (u.scheme == "http" and not local) or u.username or u.password or
            u.query or u.fragment or u.params or u.path not in ("", "/", "/v1", "/v1/")):
        raise ValueError("API URL must be an HTTPS origin (HTTP only for local tests).")
    return f"{u.scheme}://{u.netloc}"


def validate(data):
    def text(value):
        return isinstance(value, str) and bool(value.strip())
    if (not isinstance(data, dict) or text(data.get("prompt")) == text(data.get("script")) or
            ("prompt" in data and "script" in data) or
            not all(text(data.get(k)) for k in ("template", "voice", "language")) or
            type(data.get("target_duration")) is not int or data["target_duration"] < 1):
        raise ValueError("Input needs exactly one prompt or script, template, voice, language and a positive integer target_duration.")
    return data


def retry_seconds(value):
    if not value:
        return 0
    try:
        seconds = float(value)
        return max(0, seconds) if math.isfinite(seconds) else 0
    except ValueError:
        try:
            return max(0, parsedate_to_datetime(value).timestamp() - time.time())
        except (TypeError, ValueError, OverflowError):
            return 0


class Client:
    def __init__(self, key, origin="https://api.fluxnote.io"):
        if not key or key == "YOUR_FLUXNOTE_API_KEY":
            raise ValueError("Set FLUXNOTE_API_KEY first.")
        self.key = key
        self.origin = api_origin(origin)
        self.opener = build_opener(NoRedirect())

    def request(self, method, path, body=None, key=None, timeout=30):
        if not re.fullmatch(r"/(videos(?:/estimate|/[A-Za-z0-9_-]+)?|options|voices)", path):
            raise ValueError("Invalid API path.")
        headers = {"Authorization": "Bearer " + self.key, "Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if key:
            headers["Idempotency-Key"] = key
        req = Request(self.origin + "/v1" + path, method=method, headers=headers,
                      data=json.dumps(body).encode() if body is not None else None)
        try:
            with self.opener.open(req, timeout=max(0.001, timeout)) as response:
                return json.load(response), retry_seconds(response.headers.get("Retry-After"))
        except HTTPError as error:
            hints = {401: "Check your API key.", 403: "Check key scopes and plan access.",
                     402: "Insufficient credits.", 409: "Idempotency conflict; keep the receipt.",
                     422: "Invalid input. Check the current catalog and narration format.",
                     429: "Rate limited; retry later."}
            retry = error.headers.get("Retry-After", "")
            message = f"API HTTP {error.code}. " + hints.get(error.code, "Request failed; check FluxNote before retrying a write.")
            if retry.isdigit():
                message += f" Retry after {retry} seconds."
            error.close()
            raise RuntimeError(message) from None
        except (URLError, OSError, TimeoutError):
            raise RuntimeError("API connection failed or timed out. Keep any receipt; a submitted job may still be running.") from None
        except (ValueError, UnicodeError):
            raise RuntimeError("API returned invalid JSON. Keep any existing receipt.") from None


def resource_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Response is missing a valid video ID. Keep the receipt.")
    return value


def wait_for(client, video_id, seconds=900, interval=5):
    resource_id(video_id)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        data, retry = client.request("GET", "/videos/" + video_id, timeout=min(30, deadline - time.monotonic()))
        if data.get("status") in ("failed", "cancelled", "canceled", "deleted", "uncertain"):
            raise RuntimeError("Video failed or stopped. Check credit settlement before creating another job.")
        if data.get("stage") in ("review_ready", "storyboard"):
            raise RuntimeError("Open FluxNote to review this video before continuing.")
        if data.get("status") == "completed":
            return data
        time.sleep(max(0, min(max(interval, retry), deadline - time.monotonic())))
    raise RuntimeError("Wait timed out. The server job continues. Resume with the saved receipt.")


def media_url(value):
    u = urlparse(value)
    if u.scheme != "https" or not u.hostname or u.username or u.password:
        raise ValueError("Downloads require HTTPS without URL credentials.")
    return value


def private_write(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)


def download(value, output, opener=None):
    url = media_url(value)
    opener = opener or build_opener(NoRedirect())
    temp = str(output) + "." + str(uuid.uuid4()) + ".part"
    deadline = time.monotonic() + 900
    try:
        for n in range(6):
            try:
                # No API Authorization header, including on redirected requests.
                response = opener.open(Request(url), timeout=30)
            except HTTPError as error:
                location = error.headers.get("Location")
                code = error.code
                error.close()
                if code not in (301, 302, 303, 307, 308) or not location or n == 5:
                    raise RuntimeError("Download failed. Resume to obtain a fresh media URL.") from None
                url = media_url(urljoin(url, location))
                continue
            with response:
                fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    while True:
                        if time.monotonic() >= deadline:
                            raise RuntimeError("Download timed out. Resume to try again.")
                        chunk = response.read(64 * 1024)
                        if not chunk:
                            break
                        stream.write(chunk)
            os.link(temp, output)  # Atomic no-overwrite, including symlinks.
            return
    finally:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass


def main(args=None):
    args = sys.argv[1:] if args is None else args
    if not args or args[0] not in ("catalog", "estimate", "create", "resume"):
        print("Usage: python3 python/generate.py catalog | estimate INPUT.json | create INPUT.json --confirm | resume JOB.receipt.json")
        return
    command = args[0]
    if ((command == "catalog" and len(args) != 1) or
            (command != "catalog" and (len(args) < 2 or
             (len(args) > 2 and (command != "create" or args[2:] != ["--confirm"]))))):
        raise ValueError("Invalid arguments. Run without arguments for usage.")
    client = Client(os.environ.get("FLUXNOTE_API_KEY"), os.environ.get("FLUXNOTE_API_URL", "https://api.fluxnote.io"))
    if command == "catalog":
        for path in ("/options", "/voices"):
            print(json.dumps(client.request("GET", path)[0], indent=2))
        return
    content = json.loads(Path(args[1]).read_text(encoding="utf-8"))
    if command == "resume":
        if content.get("origin") != client.origin:
            raise ValueError("Receipt belongs to a different API origin.")
        if not content.get("id"):
            raise ValueError("Receipt has an uncertain submission. Check FluxNote; see docs/recovery.md. No write was sent.")
        video_id = resource_id(content["id"])
    else:
        data = validate(content)
        print("Current estimate:", json.dumps(client.request("POST", "/videos/estimate", data)[0], indent=2))
        if command == "estimate" or "--confirm" not in args[2:]:
            print("No video created. Review the estimate, then use create INPUT.json --confirm to spend credits.")
            return
        key = str(uuid.uuid4())
        receipt_path = key + ".receipt.json"
        receipt = {"origin": client.origin, "idempotency_key": key, "input": data, "created_at": time.time()}
        private_write(receipt_path, receipt)
        print("Keep this private receipt:", receipt_path, flush=True)
        created = client.request("POST", "/videos", data, key, timeout=120)[0]
        video_id = resource_id(created.get("id") or created.get("video_id"))
        receipt["id"] = video_id
        private_write(receipt_path + ".part", receipt)
        os.replace(receipt_path + ".part", receipt_path)
        print(f"Video: {video_id}. Resume with: python3 python/generate.py resume {receipt_path}", flush=True)
    result = wait_for(client, video_id)
    download(result.get("media_url"), video_id + ".mp4")
    print(f"Saved {video_id}.mp4")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped waiting. Any submitted job continues on the server; keep its receipt.", file=sys.stderr)
        sys.exit(130)
    except Exception as error:
        key = os.environ.get("FLUXNOTE_API_KEY")
        message = str(error)
        print(message.replace(key, "[redacted]") if key else message, file=sys.stderr)
        sys.exit(1)
