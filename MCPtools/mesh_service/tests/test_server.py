import base64
import json
import unittest

from mesh_service.server import _contingent_guid_from_token


class TokenClaimsTests(unittest.TestCase):
    def test_reads_contingent_guid_without_exposing_token(self):
        payload = base64.urlsafe_b64encode(json.dumps({"msh": "student-guid"}).encode()).decode().rstrip("=")
        self.assertEqual(_contingent_guid_from_token(f"header.{payload}.signature"), "student-guid")

    def test_invalid_token_returns_none(self):
        self.assertIsNone(_contingent_guid_from_token("not-a-jwt"))


if __name__ == "__main__":
    unittest.main()
