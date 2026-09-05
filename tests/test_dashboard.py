from pathlib import Path
import tempfile
import unittest
from ecosystem.dashboard import build_dashboard

class DashboardTests(unittest.TestCase):
    def test_untrusted_channel_text_is_escaped_and_blocked_visible(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "index.html"
            channel = {"id": "test", "name": "<script>alert(1)</script>", "theme": "A & B", "voice": {"id": "Kore"}, "visual": {"style": "Cartoon"}}
            plan = {"date": "2026-09-05", "channels": [{"channel_id": "test", "ready": False, "blockers": ["<missing>"]}]}
            build_dashboard([channel], plan, target)
            html = target.read_text(encoding="utf-8")
            self.assertNotIn(channel["name"], html)
            self.assertIn("&lt;script&gt;", html)
            self.assertIn("&lt;missing&gt;", html)
            self.assertIn("Pendiente de activar", html)
            self.assertNotIn("{{CARDS}}", html)

if __name__ == "__main__":
    unittest.main()
