import os
import unittest
from unittest.mock import patch

from app.api import _parse_cors_allow_origins, _validate_security_bootstrap


class ApiSecurityTest(unittest.TestCase):
    def test_cors_rejects_wildcard_when_credentials_enabled(self):
        with patch.dict(os.environ, {"CORS_ALLOW_ORIGINS": "https://example.com,*"}, clear=False):
            with self.assertRaises(RuntimeError):
                _parse_cors_allow_origins()

    def test_security_bootstrap_rejects_missing_auth_config(self):
        with patch.dict(
            os.environ,
            {
                "SIMPLYPARSE_API_TOKEN": "",
                "API_AUTH_SECRET": "",
                "API_LOGIN_USER": "",
                "API_LOGIN_PASSWORD": "",
            },
            clear=False,
        ):
            with self.assertRaises(RuntimeError):
                _validate_security_bootstrap()

    def test_security_bootstrap_accepts_static_token_mode(self):
        with patch.dict(
            os.environ,
            {
                "SIMPLYPARSE_API_TOKEN": "token-value",
                "API_AUTH_SECRET": "",
                "API_LOGIN_USER": "",
                "API_LOGIN_PASSWORD": "",
            },
            clear=False,
        ):
            _validate_security_bootstrap()


if __name__ == "__main__":
    unittest.main()
