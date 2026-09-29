"""Connected mode must refuse a weak local-demo configuration."""

import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ConnectedStartupTest(unittest.TestCase):
    def _import_security(self, **overrides: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update({
            "APP_MODE": "CONNECTED",
            "MODEL_MODE": "connected",
            "CONNECTOR_MODE": "connected",
            "INTERNAL_KEY": "i" * 48,
            "WEBHOOK_SECRET": "w" * 48,
            "COOKIE_SECURE": "true",
        })
        env.update(overrides)
        return subprocess.run(
            [sys.executable, "-c", "import apps.api.security"],
            cwd=ROOT, env=env, capture_output=True, text=True, check=False,
        )

    def test_rejects_demo_key(self) -> None:
        result = self._import_security(INTERNAL_KEY="demo-internal-key")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("INTERNAL_KEY", result.stderr)

    def test_requires_secure_cookie(self) -> None:
        result = self._import_security(COOKIE_SECURE="false")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("COOKIE_SECURE", result.stderr)

    def test_requires_distinct_secrets(self) -> None:
        result = self._import_security(WEBHOOK_SECRET="i" * 48)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must differ", result.stderr)

    def test_refuses_demo_model_in_connected_mode(self) -> None:
        result = self._import_security(MODEL_MODE="demo")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("MODEL_MODE", result.stderr)

    def test_accepts_explicit_secure_configuration(self) -> None:
        result = self._import_security()
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
