"""Regression checks for the local AI's first-load status wording (#323)."""

from pathlib import Path
import unittest


WEB = Path(__file__).resolve().parents[2] / "web"


class LocalAiFirstLoadCopy(unittest.TestCase):
    def test_chat_stopped_status_describes_first_load(self):
        source = (WEB / "chat.js").read_text(encoding="utf-8")
        self.assertIn("stopped: [true, 'Local AI available · your first question loads it and may take a while']", source)
        self.assertNotIn("Local AI ready · it starts when you ask", source)

    def test_settings_stopped_status_describes_first_load_and_idle_stop(self):
        source = (WEB / "app.js").read_text(encoding="utf-8")
        self.assertIn("available; your first question loads it and may take a while; it stops after 15 minutes unused", source)
        self.assertNotIn("ready; it starts when you ask and stops after 15 minutes unused", source)

    def test_running_and_loading_states_remain_distinct(self):
        chat = (WEB / "chat.js").read_text(encoding="utf-8")
        settings = (WEB / "app.js").read_text(encoding="utf-8")
        self.assertIn("ready: [true, 'Local AI ready']", chat)
        self.assertIn("loading: [true, `Starting the local AI", chat)
        self.assertIn("ready: 'running now'", settings)
        self.assertIn("loading: 'starting'", settings)


if __name__ == "__main__":
    unittest.main()
