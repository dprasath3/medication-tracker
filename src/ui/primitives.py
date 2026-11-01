"""Reusable UI primitives that compose to full pages.

Every primitive uses design tokens from ``ui.theme`` — no hardcoded colors.
"""

from __future__ import annotations

from html import escape

import streamlit as st

from ui.icons import icon


def page_shell(title: str, eyebrow: str | None = None, subtitle: str | None = None) -> None:
    """Render a standard page header: eyebrow, hero heading, optional subtitle."""
    parts = ['<div class="page-fade">']
    if eyebrow:
        parts.append(f'<p class="eyebrow">{escape(eyebrow)}</p>')
    parts.append(f'<h1 class="hero-heading">{escape(title)}</h1>')
    if subtitle:
        parts.append(f'<p class="muted" style="font-size:1.125rem;margin-bottom:2rem;">{escape(subtitle)}</p>')
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def card(body_html: str, *, extra_class: str = "") -> None:
    """Render a card container. ``body_html`` should be pre-escaped HTML."""
    cls = f"med-card {extra_class}".strip()
    st.markdown(f'<div class="{cls}">{body_html}</div>', unsafe_allow_html=True)


def empty_state(title: str, description: str, illustration: str | None = None) -> None:
    """Render a soft empty state — a subtle blob + friendly copy."""
    blob = illustration or _default_blob_svg()
    st.markdown(
        f"""
        <div class="page-fade" style="
            text-align: center;
            padding: var(--space-8) var(--space-5);
            background: var(--surface-card);
            border: 1px solid var(--border);
            border-radius: var(--radius-lg);
            margin: var(--space-5) 0;">
            <div style="margin: 0 auto var(--space-5); max-width: 160px;">{blob}</div>
            <h3 style="font-family: var(--font-heading); font-size: 1.375rem;
                       color: var(--text-strong); margin: 0 0 var(--space-2) 0;">{escape(title)}</h3>
            <p style="color: var(--text-muted); font-size: 1.0625rem; margin: 0;">{escape(description)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def progress_ring(percent: float, label: str, sublabel: str = "") -> None:
    """Render a circular progress ring with a numeric label."""
    percent = max(0.0, min(1.0, percent))
    circumference = 2 * 3.141592653589793 * 44  # r=44 -> C ~= 276.46
    dash_offset = circumference * (1 - percent)
    st.markdown(
        f"""
        <div class="ring-wrap page-fade">
            <div style="position: relative; width: 120px; height: 120px;">
                <svg width="120" height="120" viewBox="0 0 100 100" style="transform: rotate(-90deg);">
                    <circle cx="50" cy="50" r="44" fill="none"
                        stroke="var(--border)" stroke-width="6" stroke-linecap="round"/>
                    <circle cx="50" cy="50" r="44" fill="none"
                        stroke="var(--accent)" stroke-width="6" stroke-linecap="round"
                        stroke-dasharray="{circumference:.2f}"
                        stroke-dashoffset="{dash_offset:.2f}"
                        style="transition: stroke-dashoffset var(--dur-slow) var(--ease-out);"/>
                </svg>
                <div style="position: absolute; inset: 0; display: flex;
                            align-items: center; justify-content: center;
                            flex-direction: column;">
                    <div class="tabular" style="
                        font-family: var(--font-heading);
                        font-size: 1.75rem;
                        color: var(--text-strong);
                        font-weight: 600;
                        line-height: 1;">{label}</div>
                    {f'<div class="muted" style="font-size: 0.75rem; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.05em;">{sublabel}</div>' if sublabel else ""}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_pill(text: str, kind: str = "default") -> str:
    """Return HTML for an inline status pill. ``kind`` = default|success|warning|error|muted."""
    palette = {
        "default": ("var(--accent-subtle)", "var(--accent)"),
        "success": ("var(--success-subtle)", "var(--success)"),
        "warning": ("var(--warning-subtle)", "var(--warning)"),
        "error": ("var(--error-subtle)", "var(--error)"),
        "muted": ("var(--surface-inset)", "var(--text-muted)"),
    }
    bg, fg = palette.get(kind, palette["default"])
    return (
        f'<span style="display:inline-flex;align-items:center;gap:0.375rem;'
        f'background:{bg};color:{fg};padding:0.25rem 0.75rem;'
        f'border-radius:var(--radius-pill);font-size:0.8125rem;font-weight:500;'
        f'font-variant-numeric:tabular-nums;">{escape(text)}</span>'
    )


def divider(space: int = 6) -> None:
    """Render vertical whitespace (multiples of --space-1)."""
    st.markdown(f'<div style="height: var(--space-{space});"></div>', unsafe_allow_html=True)


def stack_open(extra_class: str = "") -> None:
    """Open a container that staggers its immediate children on entrance."""
    st.markdown(f'<div class="stagger {extra_class}">', unsafe_allow_html=True)


def stack_close() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def _default_blob_svg() -> str:
    return (
        '<svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">'
        '<path fill="var(--accent-subtle)" d="M45.6,-52.9C58.4,-40.6,67.4,-24.2,68.9,-6.7C70.4,10.8,64.4,29.4,52.5,42C40.5,54.7,22.6,61.4,4.6,58.9C-13.4,56.5,-31.6,44.8,-44.1,29.5C-56.5,14.2,-63.4,-4.7,-59.5,-21C-55.6,-37.2,-40.9,-50.8,-24.7,-59.7C-8.6,-68.6,9,-72.8,24.5,-68.1C40,-63.5,53.3,-49.9,45.6,-52.9Z" transform="translate(100 100)"/>'
        f'<g transform="translate(78 78)" style="color: var(--accent);">{icon("sparkle", "xl")}</g>'
        "</svg>"
    )
