"""Tests that need no site. They run under pytest and under `bench run-tests`."""

import unittest
from zoneinfo import ZoneInfo

from flux_helpdesk.ai import clean_sources
from flux_helpdesk.discord import build_payload, escape_markdown, message_link
from flux_helpdesk.importer import mapping
from flux_helpdesk.theme import MARKER, add_theme_tags, is_helpdesk_page
from flux_helpdesk.utils import html_to_text, parse_products, truncate

PAGE = "<html><head><title>Helpdesk</title></head><body><div id=app></div></body></html>"


class TestTheme(unittest.TestCase):
    def test_adds_stylesheet_and_dark_default_before_head_end(self):
        html = add_theme_tags(PAGE, default_dark=True, version="9")
        self.assertIn('href="/assets/flux_helpdesk/css/flux-theme.css?v=9"', html)
        self.assertIn('localStorage.setItem("theme","dark")', html)
        self.assertLess(html.index(MARKER), html.index("</head>"))

    def test_light_default_adds_no_script(self):
        html = add_theme_tags(PAGE, default_dark=False)
        self.assertIn("flux-theme.css", html)
        self.assertNotIn("localStorage", html)

    def test_idempotent_and_safe_without_head(self):
        once = add_theme_tags(PAGE, default_dark=True)
        self.assertIs(add_theme_tags(once, default_dark=True), once)
        self.assertEqual(add_theme_tags("<p>fragment</p>", default_dark=True), "<p>fragment</p>")

    def test_only_helpdesk_paths(self):
        self.assertTrue(is_helpdesk_page("/helpdesk"))
        self.assertTrue(is_helpdesk_page("/helpdesk/tickets/12"))
        self.assertFalse(is_helpdesk_page("/helpdesk-old"))
        self.assertFalse(is_helpdesk_page("/api/method/x"))


class TestDiscord(unittest.TestCase):
    def payload(self, **overrides):
        args = {
            "name": "15942",
            "subject": "Server stuck on starting",
            "excerpt": "Hi @everyone, see [this](https://evil.example)",
            "url": "https://support.example/helpdesk/tickets/15942",
            "team": "Flux Games",
            "priority": "High",
        }
        args.update(overrides)
        return build_payload("new", **args)

    def test_customer_text_cannot_ping_or_link(self):
        payload = self.payload()
        self.assertEqual(payload["allowed_mentions"], {"parse": [], "roles": []})
        self.assertNotIn("content", payload)
        description = payload["embeds"][0]["description"]
        self.assertIn(r"\[this\]\(https://evil.example\)", description)

    def test_urgent_pings_only_the_configured_role(self):
        payload = build_payload("urgent", name="1", subject="s", excerpt="", url="https://x", role_id="123")
        self.assertEqual(payload["content"], "<@&123>")
        self.assertEqual(payload["allowed_mentions"], {"parse": [], "roles": ["123"]})

    def test_limits_and_empty_fields(self):
        payload = self.payload(subject="x" * 400, excerpt="", team=None)
        embed = payload["embeds"][0]
        self.assertLessEqual(len(embed["title"]), 256)
        self.assertNotIn("description", embed)
        self.assertEqual([f["name"] for f in embed["fields"]], ["Priority"])

    def test_message_link(self):
        message = {"channel_id": "2", "id": "3"}
        self.assertEqual(message_link("1", message), "https://discord.com/channels/1/2/3")
        self.assertIsNone(message_link(None, message))

    def test_escape_markdown(self):
        self.assertEqual(escape_markdown("**bold** _x_"), r"\*\*bold\*\* \_x\_")


class TestUtils(unittest.TestCase):
    def test_html_to_text_drops_quotes_and_scripts(self):
        html = "<p>Hello</p><script>x()</script><blockquote>old thread</blockquote><p>Bye<br>now</p>"
        self.assertEqual(html_to_text(html), "Hello\nBye\nnow")

    def test_truncate(self):
        self.assertEqual(truncate("abcdef", 4), "abc…")
        self.assertEqual(truncate("abc", 4), "abc")

    def test_products(self):
        self.assertEqual(parse_products(" A \n\nB "), ["A", "B"])
        self.assertIn("FluxCloud", parse_products(""))


class TestAiSources(unittest.TestCase):
    def test_keeps_http_links_once(self):
        sources = [
            {"heading": "Nodes", "url": "https://docs.example/nodes"},
            {"source": "dup", "url": "https://docs.example/nodes"},
            {"heading": "No link"},
            {"heading": "Bad", "url": "javascript:alert(1)"},
        ]
        self.assertEqual(clean_sources(sources), [{"title": "Nodes", "url": "https://docs.example/nodes"}])


class TestImportMapping(unittest.TestCase):
    def test_status_and_priority(self):
        self.assertEqual(mapping.status(3), "Replied")
        self.assertEqual(mapping.status(5), "Closed")
        self.assertEqual(mapping.status(12), "Open")
        self.assertEqual(mapping.priority(4), "Urgent")
        self.assertEqual(mapping.priority(None), "Medium")

    def test_times_become_naive_site_time(self):
        value = mapping.to_site_time("2026-10-13T19:44:57Z", ZoneInfo("Asia/Makassar"))
        self.assertEqual(value.isoformat(), "2026-10-14T03:44:57")
        self.assertIsNone(mapping.to_site_time(None, ZoneInfo("UTC")))

    def test_ticket_name_keeps_freshdesk_number(self):
        self.assertEqual(mapping.ticket_name(15919), "15919")
        self.assertEqual(mapping.ticket_name(87), "0087")

    def test_article_status(self):
        self.assertEqual(mapping.article_status(2), "Published")
        self.assertEqual(mapping.article_status(1), "Draft")
