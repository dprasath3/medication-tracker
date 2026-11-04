"""Theme system: font loading, design tokens, 4-theme switching.

The active theme is stored in ``st.session_state['theme']`` (persisted per user
to ``users.theme``). On each render, ``inject()`` writes:

1. The global CSS (typography, buttons, inputs, motion, layout) — always the same.
2. The active theme's color token block, scoped to ``:root``. Switching themes
   just re-injects a different token block; the ``transition`` rules on
   ``.stApp`` make the swap fade smoothly.

Design source of truth: ``design-system/MASTER.md``.
"""

import streamlit as st


THEMES = ("warm-cream", "cool-sage", "twilight", "high-contrast")
DEFAULT_THEME = "warm-cream"

THEME_LABELS = {
    "warm-cream": "Warm Cream",
    "cool-sage": "Cool Sage",
    "twilight": "Twilight",
    "high-contrast": "High Contrast",
}

THEME_DESCRIPTIONS = {
    "warm-cream": "Cream and terracotta. Everyday.",
    "cool-sage": "Sage and caring teal. Calmer tones.",
    "twilight": "Soft warm dark. Evening use.",
    "high-contrast": "High contrast for low vision or bright rooms.",
}


_THEME_TOKENS = {
    "warm-cream": """
        --surface-page: #FBF7EF;
        --surface-card: #FFFFFF;
        --surface-inset: #F3EEE3;
        --text-strong: #2A241D;
        --text: #3F372E;
        --text-muted: #7A6E60;
        --text-subtle: #A69A8C;
        --border: #E8DFCE;
        --border-strong: #D6C9B2;
        --accent: #C2410C;
        --accent-hover: #9A330A;
        --accent-subtle: #FEEEE1;
        --accent-on: #FFFFFF;
        --success: #2F7D5B;
        --success-subtle: #E4F1EA;
        --warning: #B45309;
        --warning-subtle: #FCEFDA;
        --error: #B42318;
        --error-subtle: #FBE9E6;
        --ring: #C2410C;
        --shadow-1: 0 1px 2px rgba(23, 20, 13, 0.04), 0 1px 3px rgba(23, 20, 13, 0.06);
        --shadow-2: 0 2px 4px rgba(23, 20, 13, 0.05), 0 4px 12px rgba(23, 20, 13, 0.08);
        --shadow-3: 0 8px 24px rgba(23, 20, 13, 0.10);
    """,
    "cool-sage": """
        --surface-page: #F1F6F2;
        --surface-card: #FFFFFF;
        --surface-inset: #E7EFE8;
        --text-strong: #17332B;
        --text: #234A3F;
        --text-muted: #62766E;
        --text-subtle: #94A69E;
        --border: #D5E4D8;
        --border-strong: #B9CFBE;
        --accent: #0D9488;
        --accent-hover: #0F766E;
        --accent-subtle: #D8F0EC;
        --accent-on: #FFFFFF;
        --success: #10794A;
        --success-subtle: #DDF0E4;
        --warning: #B45309;
        --warning-subtle: #FBE9CE;
        --error: #B42318;
        --error-subtle: #FBE9E6;
        --ring: #0D9488;
        --shadow-1: 0 1px 2px rgba(15, 40, 30, 0.05), 0 1px 3px rgba(15, 40, 30, 0.06);
        --shadow-2: 0 2px 4px rgba(15, 40, 30, 0.06), 0 4px 12px rgba(15, 40, 30, 0.08);
        --shadow-3: 0 8px 24px rgba(15, 40, 30, 0.10);
    """,
    "twilight": """
        --surface-page: #1B1A22;
        --surface-card: #23222C;
        --surface-inset: #17161D;
        --text-strong: #F4EFE4;
        --text: #E6DFCF;
        --text-muted: #A69C87;
        --text-subtle: #7A7263;
        --border: #35333F;
        --border-strong: #4A4757;
        --accent: #F5A524;
        --accent-hover: #E58F0E;
        --accent-subtle: #3A2E1B;
        --accent-on: #1B1A22;
        --success: #6BB88A;
        --success-subtle: #2A3B33;
        --warning: #F0B24C;
        --warning-subtle: #38301C;
        --error: #F17D6B;
        --error-subtle: #3A2626;
        --ring: #F5A524;
        --shadow-1: 0 1px 3px rgba(0, 0, 0, 0.4);
        --shadow-2: 0 4px 12px rgba(0, 0, 0, 0.5);
        --shadow-3: 0 12px 32px rgba(0, 0, 0, 0.6);
    """,
    "high-contrast": """
        --surface-page: #FFFFFF;
        --surface-card: #FFFFFF;
        --surface-inset: #F2F2F2;
        --text-strong: #000000;
        --text: #000000;
        --text-muted: #262626;
        --text-subtle: #4A4A4A;
        --border: #000000;
        --border-strong: #000000;
        --accent: #B45309;
        --accent-hover: #9A4506;
        --accent-subtle: #FEF3C7;
        --accent-on: #FFFFFF;
        --success: #005F35;
        --success-subtle: #DFF3E5;
        --warning: #7A3B0A;
        --warning-subtle: #FDEACC;
        --error: #7F1D1D;
        --error-subtle: #FBE9E6;
        --ring: #000000;
        --shadow-1: 0 0 0 1px #000000;
        --shadow-2: 0 0 0 2px #000000;
        --shadow-3: 0 0 0 2px #000000;
    """,
}


_GLOBAL_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700&family=Instrument+Sans:wght@400;500;600;700&display=swap');

:root {
    --font-heading: 'Fraunces', 'Iowan Old Style', Georgia, serif;
    --font-body: 'Instrument Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    --font-mono: ui-monospace, 'SF Mono', Menlo, monospace;

    --radius-xs: 8px;
    --radius-sm: 12px;
    --radius-md: 16px;
    --radius-lg: 24px;
    --radius-xl: 32px;
    --radius-pill: 999px;

    --space-1: 4px;
    --space-2: 8px;
    --space-3: 12px;
    --space-4: 16px;
    --space-5: 24px;
    --space-6: 32px;
    --space-7: 48px;
    --space-8: 64px;
    --space-9: 96px;

    --dur-instant: 100ms;
    --dur-fast: 180ms;
    --dur-base: 240ms;
    --dur-slow: 360ms;
    --dur-page: 280ms;

    --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
    --ease-in-out: cubic-bezier(0.65, 0, 0.35, 1);
    --ease-standard: cubic-bezier(0.4, 0, 0.2, 1);

    --icon-sm: 16px;
    --icon-md: 20px;
    --icon-lg: 24px;
    --icon-xl: 32px;
}

/* Global reset + typography */
html, body, .stApp, [class*="css"] {
    font-family: var(--font-body);
    color: var(--text);
    font-feature-settings: 'ss01', 'cv02', 'cv04', 'cv11';
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
}

.stApp {
    background: var(--surface-page);
    background-image:
        radial-gradient(circle at 15% -10%, color-mix(in oklab, var(--accent) 12%, transparent) 0%, transparent 55%),
        radial-gradient(circle at 90% 8%,  color-mix(in oklab, var(--accent) 8%,  transparent) 0%, transparent 45%),
        radial-gradient(circle at 50% 105%, color-mix(in oklab, var(--accent) 6%,  transparent) 0%, transparent 45%);
    background-attachment: fixed;
    transition: background-color var(--dur-slow) var(--ease-standard),
                color var(--dur-slow) var(--ease-standard);
}

.main .block-container {
    background: transparent;
    padding-top: var(--space-7);
    padding-bottom: var(--space-8);
    max-width: 960px;
}

/* Decorative blobs floating in the page background — pure decoration, aria-hidden implied by pseudo. */
.stApp::before, .stApp::after {
    content: "";
    position: fixed;
    pointer-events: none;
    border-radius: 50%;
    filter: blur(80px);
    opacity: 0.35;
    z-index: 0;
}
.stApp::before {
    width: 480px; height: 480px;
    top: -120px; left: -140px;
    background: var(--accent);
    animation: blobFloat 24s var(--ease-in-out) infinite;
}
.stApp::after {
    width: 380px; height: 380px;
    bottom: -100px; right: -100px;
    background: color-mix(in oklab, var(--accent) 60%, var(--success));
    animation: blobFloat 32s var(--ease-in-out) infinite reverse;
}
@keyframes blobFloat {
    0%, 100% { transform: translate(0, 0) scale(1); }
    50%      { transform: translate(40px, 20px) scale(1.1); }
}
@media (prefers-reduced-motion: reduce) {
    .stApp::before, .stApp::after { animation: none; }
}
/* Keep app content above decorative blobs */
[data-testid="stMain"], section[data-testid="stSidebar"] { position: relative; z-index: 1; }

/* Typography */
h1, h2, h3, h4 {
    font-family: var(--font-heading);
    color: var(--text-strong);
    font-weight: 600;
    letter-spacing: -0.015em;
    font-optical-sizing: auto;
}
h1 { font-size: 2rem; line-height: 1.15; margin-bottom: 0.5rem; }
h2 { font-size: 1.5rem; line-height: 1.2; margin-bottom: 0.5rem; }
h3 { font-size: 1.25rem; line-height: 1.3; margin-bottom: 0.5rem; }
h4 { font-size: 1.0625rem; line-height: 1.4; margin-bottom: 0.5rem; }
p, li { font-size: 1.0625rem; line-height: 1.6; color: var(--text); }

.hero-heading {
    font-family: var(--font-heading);
    font-size: 2.75rem;
    line-height: 1.05;
    font-weight: 600;
    color: var(--text-strong);
    letter-spacing: -0.02em;
    font-optical-sizing: auto;
    margin-bottom: 0.5rem;
}
.eyebrow {
    font-family: var(--font-body);
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.25rem;
}
.muted { color: var(--text-muted); }
.subtle { color: var(--text-subtle); }
.tabular { font-variant-numeric: tabular-nums; }

/* Buttons */
.stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {
    background: var(--surface-card);
    color: var(--text-strong);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 0.625rem 1.25rem;
    font-family: var(--font-body);
    font-size: 0.9375rem;
    font-weight: 500;
    box-shadow: none;
    transition: background-color var(--dur-fast) var(--ease-standard),
                border-color var(--dur-fast) var(--ease-standard),
                transform var(--dur-fast) var(--ease-out);
    min-height: 44px;
}
.stButton > button:hover,
.stFormSubmitButton > button:hover,
.stDownloadButton > button:hover {
    background: var(--surface-inset);
    border-color: var(--border-strong);
    color: var(--text-strong);
    transform: translateY(-1px);
}
.stButton > button:active,
.stFormSubmitButton > button:active { transform: scale(0.98); }
.stButton > button:focus-visible,
.stFormSubmitButton > button:focus-visible {
    outline: none;
    border-color: var(--ring);
    box-shadow: 0 0 0 4px color-mix(in oklab, var(--ring) 25%, transparent);
}
.stButton > button[kind="primary"],
.stFormSubmitButton > button[kind="primary"] {
    background: var(--accent);
    color: var(--accent-on);
    border-color: var(--accent);
}
.stButton > button[kind="primary"]:hover,
.stFormSubmitButton > button[kind="primary"]:hover {
    background: var(--accent-hover);
    border-color: var(--accent-hover);
    color: var(--accent-on);
}

/* Inputs */
.stTextInput input, .stNumberInput input, .stTextArea textarea,
.stDateInput input, .stTimeInput input {
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
    background: var(--surface-card) !important;
    color: var(--text-strong) !important;
    font-family: var(--font-body) !important;
    font-size: 1rem !important;
    min-height: 48px;
    box-shadow: none !important;
    transition: border-color var(--dur-fast) var(--ease-standard),
                box-shadow var(--dur-fast) var(--ease-standard) !important;
}
.stTextInput input::placeholder, .stTextArea textarea::placeholder {
    color: var(--text-subtle) !important;
}
.stTextInput input:focus, .stNumberInput input:focus,
.stTextArea textarea:focus, .stDateInput input:focus,
.stTimeInput input:focus {
    border-color: var(--ring) !important;
    box-shadow: 0 0 0 4px color-mix(in oklab, var(--ring) 25%, transparent) !important;
}
.stSelectbox > div > div {
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
    background: var(--surface-card) !important;
    min-height: 48px;
}
label, .stTextInput label, .stSelectbox label, .stNumberInput label,
.stDateInput label, .stTimeInput label, .stTextArea label {
    color: var(--text) !important;
    font-family: var(--font-body) !important;
    font-size: 0.9375rem !important;
    font-weight: 500 !important;
}

/* Metrics */
[data-testid="metric-container"] {
    background: var(--surface-card);
    border: 1px solid var(--border);
    padding: var(--space-5);
    border-radius: var(--radius-md);
    box-shadow: none;
}
[data-testid="metric-container"] label {
    color: var(--text-muted);
    font-size: 0.8125rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.03em;
}

/* Expander */
.streamlit-expanderHeader, [data-testid="stExpander"] summary {
    background: var(--surface-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text-strong);
    font-family: var(--font-body);
    font-weight: 500;
}

/* Progress bar */
.stProgress > div > div > div { background: var(--accent) !important; }
.stProgress > div > div { background: var(--border) !important; border-radius: var(--radius-pill) !important; }

/* Sidebar */
section[data-testid="stSidebar"] {
    background: var(--surface-card);
    border-right: 1px solid var(--border);
    transition: background-color var(--dur-slow) var(--ease-standard);
}
section[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    justify-content: flex-start;
    text-align: left;
}
section[data-testid="stSidebar"] hr {
    border-color: var(--border);
    margin: var(--space-4) 0;
}

hr { border-color: var(--border); }

/* Alerts */
div[data-testid="stAlert"] {
    border-radius: var(--radius-sm) !important;
    border-width: 1px !important;
    font-family: var(--font-body) !important;
    padding: var(--space-4) var(--space-5) !important;
}

/* Hide branding */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; height: 0; }

/* Card primitive */
.med-card, .surface-card, .patient-card {
    background: var(--surface-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: var(--space-6);
    transition: border-color var(--dur-base) var(--ease-standard),
                box-shadow var(--dur-base) var(--ease-standard),
                transform var(--dur-base) var(--ease-out);
    box-shadow: var(--shadow-1);
}
.med-card:hover, .patient-card:hover {
    border-color: var(--border-strong);
    box-shadow: var(--shadow-2);
    transform: translateY(-2px);
}

/* Motion (reduced-motion safe) */
@media (prefers-reduced-motion: no-preference) {
    .fade-in { animation: fadeIn var(--dur-page) var(--ease-out) both; }
    .fade-slide-up { animation: fadeSlideUp var(--dur-page) var(--ease-out) both; }
    .stagger > * { animation: fadeSlideUp var(--dur-slow) var(--ease-out) both; }
    .stagger > *:nth-child(1) { animation-delay: 0ms; }
    .stagger > *:nth-child(2) { animation-delay: 40ms; }
    .stagger > *:nth-child(3) { animation-delay: 80ms; }
    .stagger > *:nth-child(4) { animation-delay: 120ms; }
    .stagger > *:nth-child(5) { animation-delay: 160ms; }
    .stagger > *:nth-child(6) { animation-delay: 200ms; }
    .stagger > *:nth-child(7) { animation-delay: 240ms; }
    .stagger > *:nth-child(8) { animation-delay: 280ms; }
    .stagger > *:nth-child(9) { animation-delay: 320ms; }
    .stagger > *:nth-child(10) { animation-delay: 360ms; }
    .shimmer {
        background: linear-gradient(90deg,
            var(--surface-inset) 0%,
            var(--border) 50%,
            var(--surface-inset) 100%);
        background-size: 200% 100%;
        animation: shimmer 1.4s var(--ease-in-out) infinite;
    }
}
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes fadeSlideUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

.page-fade { animation: fadeIn var(--dur-page) var(--ease-out) both; }

/* Progress ring container */
.ring-wrap {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--space-5) 0;
}

/* Legacy class compatibility layer.
   Kept until every screen has been rewritten to use the primitives.
   All rules re-express old class names in terms of the new tokens. */
.main-header {
    font-family: var(--font-heading);
    font-size: 2rem;
    color: var(--text-strong);
    font-weight: 600;
    letter-spacing: -0.015em;
    margin-bottom: var(--space-2);
}
.welcome-header {
    font-family: var(--font-heading);
    font-size: 2.5rem;
    line-height: 1.1;
    color: var(--text-strong);
    font-weight: 600;
    letter-spacing: -0.02em;
    margin-bottom: var(--space-2);
    font-optical-sizing: auto;
}
.welcome-subheader {
    font-family: var(--font-body);
    font-size: 1.125rem;
    color: var(--text-muted);
    margin-bottom: var(--space-6);
    font-weight: 400;
}
.feature-card {
    background: var(--surface-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: var(--space-6);
    margin: var(--space-3) 0;
    box-shadow: var(--shadow-1);
    transition: border-color var(--dur-base) var(--ease-standard),
                box-shadow var(--dur-base) var(--ease-standard);
}
.feature-card:hover {
    border-color: var(--border-strong);
    box-shadow: var(--shadow-2);
}
.empty-state {
    text-align: center;
    padding: var(--space-7) var(--space-5);
    background: var(--surface-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    margin: var(--space-5) 0;
}
.empty-state h3 {
    font-family: var(--font-heading);
    font-size: 1.375rem;
    color: var(--text-strong);
    margin: 0 0 var(--space-2) 0;
}
.empty-state p {
    color: var(--text-muted);
    font-size: 1.0625rem;
    margin: 0;
}
.alert-warning {
    background: var(--warning-subtle);
    color: var(--warning);
    border: 1px solid color-mix(in oklab, var(--warning) 25%, transparent);
    border-radius: var(--radius-sm);
    padding: var(--space-4) var(--space-5);
    margin: var(--space-3) 0;
    font-family: var(--font-body);
}
.alert-success {
    background: var(--success-subtle);
    color: var(--success);
    border: 1px solid color-mix(in oklab, var(--success) 25%, transparent);
    border-radius: var(--radius-sm);
    padding: var(--space-4) var(--space-5);
    margin: var(--space-3) 0;
    font-family: var(--font-body);
}
.success-message {
    background: var(--success-subtle);
    color: var(--success);
    border: 1px solid color-mix(in oklab, var(--success) 25%, transparent);
    border-radius: var(--radius-md);
    padding: var(--space-5);
    margin: var(--space-5) 0;
    font-weight: 500;
    font-family: var(--font-body);
}
.med-log-card {
    background: var(--surface-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: var(--space-5);
    margin: var(--space-3) 0;
    box-shadow: var(--shadow-1);
}
</style>
"""


def get_current_theme() -> str:
    """Return the active theme slug, defaulting to warm-cream."""
    theme = st.session_state.get("theme")
    if theme not in THEMES:
        theme = DEFAULT_THEME
        st.session_state["theme"] = theme
    return theme


def set_theme(theme: str, *, persist: bool = True) -> None:
    """Set the active theme in session state and optionally persist to the user's row."""
    if theme not in THEMES:
        theme = DEFAULT_THEME
    st.session_state["theme"] = theme

    if persist and st.session_state.get("user_profile"):
        try:
            from utils.db_factory import get_database

            db = get_database()
            user_id = st.session_state["user_profile"]["id"]
            if hasattr(db, "update_user"):
                db.update_user(user_id, theme=theme)
        except Exception:
            # Best-effort — session state remains authoritative for this render.
            pass


def _theme_css(theme: str) -> str:
    tokens = _THEME_TOKENS.get(theme, _THEME_TOKENS[DEFAULT_THEME])
    return f"<style>:root {{{tokens}}}</style>"


def inject() -> None:
    """Inject fonts, global CSS, and active theme tokens. Call once per page render."""
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)
    st.markdown(_theme_css(get_current_theme()), unsafe_allow_html=True)
