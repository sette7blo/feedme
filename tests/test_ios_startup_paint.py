import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "frontend" / "index.html"
APP_CSS = ROOT / "frontend" / "app.css"


class IosStartupPaintTests(unittest.TestCase):
    def test_index_has_inline_startup_paint_before_blocking_stylesheet(self):
        html = INDEX.read_text()
        style_pos = html.index('<style id="startup-paint"')
        css_pos = html.index('<link rel="stylesheet" href="/app.css">')
        body_pos = html.index('<body>')
        boot_pos = html.index('id="boot-paint"')

        self.assertLess(style_pos, css_pos)
        self.assertGreater(boot_pos, body_pos)
        self.assertIn('background:#faf7f2', html)
        self.assertIn('body.app-ready #boot-paint', html)

    def test_startup_script_marks_app_ready_after_first_paint(self):
        html = INDEX.read_text()
        self.assertIn("requestAnimationFrame", html)
        self.assertIn("document.body.classList.add('app-ready')", html)

    def test_no_external_google_font_dependency(self):
        combined = INDEX.read_text() + APP_CSS.read_text()
        self.assertNotIn('fonts.googleapis.com', combined)
        self.assertNotIn('fonts.gstatic.com', combined)
        self.assertIn('font-display: swap', combined)


if __name__ == "__main__":
    unittest.main()
