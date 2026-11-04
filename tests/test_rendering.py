"""User-controlled medication notes must remain text inside a rendered card."""
from types import SimpleNamespace

from pages import today
from ui import primitives


def test_dose_card_escapes_user_text_without_markdown_code_blocks(monkeypatch):
    rendered = []
    monkeypatch.setattr(today, "st", SimpleNamespace(markdown=lambda value, **kwargs: rendered.append(value)))
    monkeypatch.setattr(today, "divider", lambda *args: None)
    today._render_dose_card(None, {"id": 1}, 1, {
        "medication": {"id": 1, "name": "<b>Example</b>", "dosage": "<img src=x>", "notes": "<script>bad()</script>"},
        "scheduled_time": "08:00", "display_time": "08:00", "existing_log": None,
        "is_snoozed": False,
    }, can_write=False)
    card = rendered[0]
    assert card.startswith('<div class="med-card"')
    assert "\n" not in card
    assert "<script>" not in card and "<img src=x>" not in card
    assert "&lt;b&gt;Example&lt;/b&gt;" in card
    assert "&lt;script&gt;bad()&lt;/script&gt;" in card


def test_page_headers_escape_profile_text(monkeypatch):
    rendered = []
    monkeypatch.setattr(primitives, "st", SimpleNamespace(markdown=lambda value, **kwargs: rendered.append(value)))
    primitives.page_shell("<img src=x>", eyebrow="<b>Name</b>", subtitle="<script>bad()</script>")
    assert "<img src=x>" not in rendered[0]
    assert "&lt;b&gt;Name&lt;/b&gt;" in rendered[0]
