"""The licence: the official PolyForm Shield text with SBR's notice, at the top of the repository and in every Product."""

from hashlib import sha256
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
NOTICE = b"Required Notice: Copyright 2026 Simply Better Reports Limited, trading as SBR (https://github.com/SBR-NZ/pace)\n\n"
# PolyForm-Shield-1.0.0.md from github.com/polyformproject/polyform-licenses at 76a278c (2023-11-20).
OFFICIAL_SHIELD_SHA256 = "56328093d57c87dcf2811ddcc824caf2723a07ffc332e6fbe4f9f108a2893a91"


class LicenceTests(unittest.TestCase):
    def test_every_product_carries_the_same_licence_as_the_repository(self):
        self.assertEqual((ROOT / "PACE/Product/LICENSE.md").read_bytes(), (ROOT / "LICENSE").read_bytes())

    def test_it_is_the_official_shield_text_after_sbrs_notice(self):
        text = (ROOT / "LICENSE").read_bytes()
        self.assertTrue(text.startswith(NOTICE), text[:200])
        body = text[len(NOTICE):]
        self.assertTrue(body.startswith(b"# PolyForm Shield License 1.0.0\n"))
        self.assertEqual(sha256(body).hexdigest(), OFFICIAL_SHIELD_SHA256)
        self.assertEqual(text.count(b"Required Notice: Copyright 2026"), 1)

    def test_the_readme_names_the_licence_and_where_folders_carry_it(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("[PolyForm Shield License 1.0.0](LICENSE)", readme)
        self.assertIn("`Product/LICENSE.md`", readme)
        self.assertIn("the licence text is what applies", readme)
        self.assertNotIn("All rights reserved", readme)


if __name__ == "__main__":
    unittest.main()
