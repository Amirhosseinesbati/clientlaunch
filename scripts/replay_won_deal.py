"""Send a signed synthetic won-deal fixture to the local n8n webhook."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "won_deal_website.json"


def demo_secret() -> str:
    env_path = ROOT / ".env"
    if not env_path.exists():
        raise SystemExit("Run node scripts/demo.mjs first; ignored .env is missing")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("WEBHOOK_SECRET="):
            secret = line.partition("=")[2]
            if secret:
                return secret
    raise SystemExit("WEBHOOK_SECRET is missing from ignored .env")


def send(url: str, payload: dict, secret: str) -> tuple[int, str]:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    request = urllib.request.Request(url, data=canonical, method="POST", headers={
        "Content-Type": "application/json",
        "X-ClientLaunch-Signature": f"sha256={signature}",
    })
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5678/webhook/clientlaunch/won-deal")
    parser.add_argument("--case", default="website-001", help="Unique suffix for an independent synthetic deal")
    parser.add_argument("--repeat", action="store_true", help="Resend identical bytes to check dedupe")
    parser.add_argument("--conflict", action="store_true", help="Resend same event ID with changed scope; expect rejection")
    args = parser.parse_args()
    parsed = urllib.parse.urlparse(args.url)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("This fixture replay accepts only a local HTTP target")
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["event_id"] = f"cl-demo-{args.case}"
    payload["external_deal_id"] = f"qf-demo-{args.case}"
    secret = demo_secret()
    print("initial:", *send(args.url, payload, secret))
    if args.repeat:
        print("duplicate:", *send(args.url, payload, secret))
    if args.conflict:
        changed = dict(payload)
        changed["approved_scope"] += " A conflicting, unapproved change."
        print("conflicting duplicate:", *send(args.url, changed, secret))


if __name__ == "__main__":
    main()
