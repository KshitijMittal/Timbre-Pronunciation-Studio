"""Timbre Pronunciation Studio — Streamlit entry point.

One process, no HTTP layer: the UI imports ``backend/app/core/`` directly
(``TRD`` §12.4). It reads and writes ``data/dictionaries/`` through
``DictionaryStore`` and caches audio in ``data/audio/`` through ``AudioCache``.

It never spends a credit on its own. A call happens only when a person presses
**Preview voice** or **Generate comparison**; every clip is cached by its
content key, so a repeat is free.

Run from the project root:

    .venv\\Scripts\\python.exe -m streamlit run streamlit_app/app.py
"""

from __future__ import annotations

import base64
import hashlib
import html
import io
import re
import sys
import wave
from pathlib import Path

import numpy as np
import streamlit as st

_HERE = Path(__file__).resolve()
sys.path[:0] = [str(_HERE.parents[1] / "backend"), str(_HERE.parent)]

from app.catalogue import MODELS  # noqa: E402
from app.config import DEFAULT_DATA_DIR, load_settings  # noqa: E402
from app.core.audio_cache import AudioCache  # noqa: E402
from app.core.dictionary_store import DictionaryStore  # noqa: E402
from app.core.gnani_tts import DEFAULT_AUDIO_CONFIG, TimbreClient  # noqa: E402
from app.core.pronunciation_rules import Rule, apply_rules  # noqa: E402
from app.errors import AppError, ConfigurationError  # noqa: E402
from app.models.schemas import (  # noqa: E402
    MAX_NAME_LENGTH,
    MAX_REPLACEMENT_LENGTH,
    MAX_RULES,
    MAX_SOURCE_LENGTH,
    Dictionary,
)

from csv_io import parse as parse_csv, to_csv  # noqa: E402
from seed import SAMPLE_SCRIPT, SEED_LABEL, ensure_seed, is_seed_dictionary  # noqa: E402

LIMITATION = (
    "This is text substitution, not phoneme control. Your replacement text is "
    "what Timbre receives; the original wording is kept only for display."
)

# A short sample keeps a first preview cheap. Cached forever after one call.
PREVIEW_TEXT = "Namaste. This is a short sample of the selected voice."

WAVE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="#FFFFFF" stroke-width="2.2" stroke-linecap="round">'
    '<path d="M4 10v4M8 7v10M12 4v16M16 7v10M20 10v4"/></svg>'
)
WAVE_URI = "data:image/svg+xml;base64," + base64.b64encode(WAVE_SVG.encode()).decode()

POLICIES: tuple[tuple[str, str], ...] = (
    (
        "Privacy Policy",
        "Everything below lives on this machine.\n\n"
        "- **Your script** is held in memory for the current browser session. "
        "It is not written to disk.\n"
        "- **Dictionaries** are plain JSON files in `data/dictionaries/`, one "
        "file per dictionary.\n"
        "- **Generated audio** is cached as WAV in `data/audio/`, next to a JSON "
        "sidecar recording the text, model, voice, language, speed and timestamp.\n"
        "- **Model and voice choices** last for the session; the defaults come "
        "from `backend/.env`.\n\n"
        "**What leaves this machine.** Only the speech request. When a clip is "
        "not cached, the app sends the text, model, voice, language and speed "
        "over HTTPS to the Gnani/Timbre API (`api.vachana.ai`). There is no "
        "analytics, no account system and no telemetry, and nothing is uploaded "
        "anywhere else.\n\n"
        "**Encryption.** Files are not encrypted. They are protected by your "
        "operating-system account, nothing more.",
    ),
    (
        "Data Usage Policy",
        "**Why the data exists.** The script is used to make audio. Dictionaries "
        "exist so a respelling is applied before synthesis. The audio cache "
        "exists so replaying a clip never costs a second call.\n\n"
        "**Retention.** Nothing expires automatically and there is no in-app "
        "purge.\n\n"
        "- Deleting a dictionary deletes its JSON file. Deleted rules cannot be "
        "recovered.\n"
        "- Cached audio stays in `data/audio/` until you delete the files "
        "yourself, even after the dictionary that produced it is gone.\n\n"
        "**Gnani.** Text sent to the Timbre API is handled under Gnani's terms "
        "and privacy policy, not this application's.",
    ),
    (
        "Terms of Use",
        "- This is a local, single-user tool. It has no accounts, no login and no "
        "server-side copy of your work.\n"
        "- It is provided as-is, without warranty of any kind.\n"
        "- You are responsible for the text you synthesize, for the voices you "
        "use, and for the Gnani credits your account spends.\n"
        "- Do not use it to impersonate a person or to pass generated speech off "
        "as a recording.\n"
        "- Pronunciation rules are yours to author. A rule that makes one word "
        "right can make another wrong.",
    ),
    (
        "Disclaimer",
        "Pronunciation accuracy varies with the model, the voice, the language, "
        "the accent and the respelling you write. Timbre may normalise an "
        "authored respelling before it speaks, so the same rule can sound "
        "different across voices.\n\n"
        "This app does not claim measured accuracy. Its one listening test "
        "covered eight terms with a single model and voice, and it does not "
        "generalise. Listen to every clip before you publish it.",
    ),
    (
        "Project Limitations",
        "- **Text substitution, not phoneme control.** Your replacement text is "
        "what Timbre receives. There is no IPA input and no per-phoneme tuning.\n"
        "- **Whole words only.** A rule for `Ram` will not match inside "
        "`Ramachandran`. Matching ignores case; the replacement keeps the casing "
        "you typed.\n"
        "- **Rules can chain.** If one rule's replacement contains another "
        "rule's term, applying the dictionary twice changes the text again.\n"
        "- **Limits.** 2,000 characters per script, 200 rules per dictionary, "
        "120 characters per term, 200 per replacement.\n"
        "- **Fixed settings.** Language (`en-IN`) and speed (1.0×) are fixed in "
        "this release.\n"
        "- **Audio is never evicted.** The cache grows until you clean "
        "`data/audio/` yourself.",
    ),
)


def spans(text: str, rules: list[tuple[str, str]]) -> list[tuple[int, int, str]]:
    """Display offsets: every whole-word occurrence, exactly as ``apply_rules`` fires.

    Display only — the text actually sent to Timbre comes from ``apply_rules``.
    """
    ordered = sorted(
        (pair for pair in rules if pair[0]), key=lambda pair: -len(pair[0])
    )
    if not ordered:
        return []
    replacement_for = {source.casefold(): replacement for source, replacement in ordered}
    pattern = re.compile(
        r"(?<!\w)(?:" + "|".join(re.escape(source) for source, _ in ordered) + r")(?!\w)",
        re.IGNORECASE,
    )
    return [
        (match.start(), match.end(), replacement_for[match.group(0).casefold()])
        for match in pattern.finditer(text)
    ]


def highlighted(text: str, rules: list[tuple[str, str]]) -> str:
    pieces: list[str] = []
    cursor = 0
    for begin, end, replacement in spans(text, rules):
        pieces.append(html.escape(text[cursor:begin]))
        pieces.append(f"<mark>{html.escape(replacement)}</mark>")
        cursor = end
    pieces.append(html.escape(text[cursor:]))
    return "".join(pieces)


def slug(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return cleaned or "dictionary"


# --- styling ---------------------------------------------------------------

BASE_CSS = """
<style>
html, body, [data-testid="stAppViewContainer"], .stApp, .stMarkdown, .stMarkdown p,
.stButton button, .stTextArea textarea, .stTextInput input, .stSelectbox div[data-baseweb="select"],
[data-testid="stWidgetLabel"] p, h1, h2, h3, h4, h5, .stBadge
  { font-family: "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif !important; }
/* Never restyle the icon font: Streamlit draws :material/* glyphs with ligatures. */
[data-testid="stIconMaterial"] { font-family: "Material Symbols Rounded" !important; }
code, pre, .stCode { font-family: "Cascadia Code", ui-monospace, monospace !important; }

[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebar"] { background: #FFFFFF; border-right: 1px solid #E4E7EC; }
[data-testid="stSidebar"] h3 { font-size: 1rem; letter-spacing: 0.02em; color: #344054; }

/* Layered surfaces: tinted page, white cards. Streamlit themes only the page and
   the sidebar, so per-container contrast has to come from CSS. */
[data-testid="stVerticalBlockBorderWrapper"] {
  background: #FFFFFF; border-radius: 0.75rem;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04), 0 10px 24px -20px rgba(16, 24, 40, 0.5);
}

.block-container { padding-bottom: 2.5rem !important; }

.hero-head { display: flex; gap: 1rem; align-items: center; }
.hero-mark { width: 44px; height: 44px; border-radius: 12px; flex: 0 0 44px;
  display: flex; align-items: center; justify-content: center; }
.hero h1 { margin: 0; line-height: 1.06; letter-spacing: -0.02em; }
/* Subtitle starts under the first letter of the title, not under the icon. */
.hero p { margin: 0.5rem 0 0 calc(64px + 1rem); }

.panel-title { display: flex; align-items: baseline; gap: 0.5rem; margin: 0 0 0.4rem; }
.panel-title .label { font-size: 1.02rem; font-weight: 600; }
.panel-title .help { display: inline-flex; align-items: center; justify-content: center;
  width: 15px; height: 15px; border-radius: 50%; border: 1px solid #C9BFAC;
  color: #8A6A3B; font-size: 0.6rem; font-weight: 600; line-height: 1;
  cursor: help; user-select: none; }

/* The element toolbar (download / search / fullscreen) is developer chrome. */
[data-testid="stElementToolbar"] { display: none !important; }

/* Widget surfaces: pin them to the sand palette. Streamlit paints inputs with
   the theme's secondary colour (blue-grey by default), which is not ours. */
[data-testid="stTextInputRootElement"], [data-testid="stTextAreaRootElement"],
[data-testid="stSelectbox"] .react-aria-ComboBox > div {
  background: #FFFFFF !important; border-color: #E6DCCB !important; }
[data-testid="stTextInputRootElement"]:focus-within,
[data-testid="stTextAreaRootElement"]:focus-within { border-color: #8A6A3B !important; }

/* Per-row delete: hidden until the row is hovered. Streamlit puts a container's
   key on the DOM as st-key-<key>, which is what makes the reveal possible. */
[class*="st-key-rule_row_"] .stButton { opacity: 0; transition: opacity 0.12s ease; }
[class*="st-key-rule_row_"]:hover .stButton,
[class*="st-key-rule_row_"] .stButton:focus-within { opacity: 1; }
[class*="st-key-rule_row_"] .stButton button { background: transparent !important;
  border: none !important; color: #B42318 !important; }
[class*="st-key-rule_row_"] .stButton button:hover { background: #FEF3F2 !important; }

/* The generate action gets air of its own: it sits between two panels. */
[class*="st-key-generate_row"] { margin: 1.2rem 0; }

/* Sidebar: dictionary list, icon-only settings pinned bottom-left. */
[class*="st-key-dict_list"] { display: flex; flex-direction: column; gap: 0.05rem; }
[class*="st-key-dict_list"] button { justify-content: flex-start;
  padding: 0.35rem 0.6rem !important; }
[class*="st-key-dict_list"] button > div { justify-content: flex-start; }
/* Hovering a row must not turn its name into a link. */
[class*="st-key-dict_list"] button:hover { color: #241B10 !important; }
[class*="st-key-dict_menu_"] { opacity: 0; transition: opacity 0.12s ease; }
/* Drop the popover's expand_more arrow: the dots alone say "menu". */
[class*="st-key-dict_menu_"] button > div > div:last-child { display: none; }
/* The dots are an affordance, not a button: no fill, no ring, no border. */
[class*="st-key-dict_menu_"] button { background: transparent !important;
  border: none !important; box-shadow: none !important; }
[class*="st-key-dict_menu_"] button:hover { background: transparent !important;
  color: #6B4E24 !important; }
[class*="st-key-dict_row_"]:hover [class*="st-key-dict_menu_"],
[class*="st-key-dict_menu_"]:has(:focus-visible) { opacity: 1; }
/* New-dictionary plus: same bare affordance as the row dots. */
[class*="st-key-dict_add"] { display: flex; justify-content: flex-end; }
[class*="st-key-dict_add"] button { background: transparent !important;
  border: none !important; box-shadow: none !important; padding: 0.1rem; }
[class*="st-key-dict_add"] button:hover { background: transparent !important;
  color: #6B4E24 !important; }
[class*="st-key-dict_add"] [data-testid="stIconMaterial"] { font-size: 1.35rem;
  font-variation-settings: "wght" 600; }
[class*="st-key-dict_row_current"] button:not([data-testid="stPopoverButton"]) {
  background: rgba(138, 106, 59, 0.1) !important;
  color: #6B4E24 !important; font-weight: 600; }
[class*="st-key-sidebar_footer"] { position: absolute; bottom: 1.2rem; left: 1rem; }
[class*="st-key-sidebar_footer"] button { padding: 0.4rem; }
[class*="st-key-sidebar_footer"] [data-testid="stIconMaterial"] { font-size: 1.55rem; }

/* Popovers: fit the content instead of the default 320 px slab. */
[data-testid="stPopoverBody"] { min-width: 0; padding: 0.5rem; }

/* Model + voice readout: typography instead of another box. */
.voice-block { border-left: 2px solid #E6DCCB; padding: 0.15rem 0 0.15rem 0.8rem; }
.voice-block .model { font-size: 0.68rem; letter-spacing: 0.09em;
  text-transform: uppercase; color: #8A7B63; }
.voice-block .name { font-size: 1.05rem; font-weight: 600; color: #241B10;
  margin-top: 0.15rem; }
.voice-block .meta { font-size: 0.78rem; color: #6B5B45; margin-top: 0.15rem; }

/* Settings dialog: category rail as a list, separated by a line, page blurred. */
[class*="st-key-settings_nav"] { border-right: 1px solid #EBE2D2;
  padding-right: 0.6rem; min-height: 16rem; }
[class*="st-key-settings_nav"] [data-testid="stElementContainer"],
[class*="st-key-settings_nav"] [data-testid="stRadio"],
[class*="st-key-settings_nav"] [data-testid="stRadio"] > div { width: 100%; }
[class*="st-key-settings_nav"] [role="radiogroup"] { width: 100%; gap: 0.1rem;
  align-items: stretch; }
[class*="st-key-settings_nav"] [role="radiogroup"] label { display: flex; width: 100%;
  padding: 0.5rem 0.7rem; border-radius: 8px; font-size: 1.05rem;
  cursor: pointer; transition: background 0.12s ease; }
[class*="st-key-settings_nav"] [role="radiogroup"] label:hover {
  background: rgba(138, 106, 59, 0.08); }
[class*="st-key-settings_nav"] [role="radiogroup"] label:has(input:checked) {
  background: rgba(138, 106, 59, 0.12); font-weight: 600; color: #6B4E24; }
[class*="st-key-settings_nav"] [role="radiogroup"] label > div > div:first-child {
  display: none; }
/* Keep the overlay's native flex-start: centring a tall dialog clips its top
   above the scroll origin, which strands the settings rail off-screen. */
[data-testid="stDialog"] { backdrop-filter: blur(5px);
  background: rgba(36, 27, 16, 0.3); }
/* Long policy text needs a line length you can read. */
[data-testid="stDialog"] [data-testid="stMarkdownContainer"] p,
[data-testid="stDialog"] [data-testid="stMarkdownContainer"] li {
  line-height: 1.6; font-size: 0.92rem; }
[data-testid="stDialog"] h5 { margin: 1.1rem 0 0.35rem; }

/* Empty audio cards: an empty state, not a broken player. */
.audio-empty { color: #8A7B63; font-size: 0.86rem; padding: 1.5rem 0.5rem;
  text-align: center; }

/* Focus ring for the bare icon affordances; native widgets keep theirs. */
[class*="st-key-dict_add"] button:focus-visible,
[class*="st-key-dict_menu_"] button:focus-visible,
[class*="st-key-sidebar_footer"] button:focus-visible {
  outline: 2px solid #8A6A3B; outline-offset: 2px; border-radius: 6px; }

/* Save rules: white label always; disabled state is an obvious flat grey. */
[class*="st-key-save_rules"] button { color: #FFFFFF !important; }
[class*="st-key-save_rules"] button:disabled {
  background: #B3AA9B !important;
  box-shadow: none !important;
  border: none !important;
  cursor: not-allowed;
}

/* The ⋮ menu: bare, left-aligned rows — a menu, not a stack of buttons.
   The popover body lives in a portal, so scope on a keyed container inside it. */
[class*="st-key-menu_body_"] { gap: 0.05rem !important; }
[class*="st-key-menu_body_"] .stButton button,
[class*="st-key-menu_body_"] [data-testid="stDownloadButton"] button {
  background: transparent !important; border: none !important; box-shadow: none !important;
  color: #3D3222 !important; justify-content: flex-start;
  text-align: left; padding: 0.3rem 0.5rem !important; min-height: 0;
}
[class*="st-key-menu_body_"] button > div { justify-content: flex-start; }
/* Keep the name field readable while the actions stay tight. */
[class*="st-key-menu_body_"] [data-testid="stCaptionContainer"] { padding-bottom: 0.2rem; }
[class*="st-key-menu_body_"] [data-testid="stTextInput"] { padding-bottom: 0.45rem; }

/* Delete reads as destructive inside the ⋮ menu — red text only, no hover fill. */
[class*="st-key-menu_body_"] [class*="st-key-ask_delete_"] button {
  color: #B42318 !important;
}
[class*="st-key-menu_body_"] [class*="st-key-ask_delete_"] button:hover {
  color: #912018 !important;
  background: transparent !important;
}

mark { background: #CCFBF1; color: #0F172A; padding: 0 2px; border-radius: 3px; }

@media (max-width: 900px) {
  .hero h1 { font-size: 2.6rem !important; }
}
@media (max-width: 760px) {
  .block-container { padding-left: 1rem !important; padding-right: 1rem !important; }
  .hero { padding: 1.2rem 1.2rem; border-radius: 14px; }
  .hero h1 { font-size: 2.1rem !important; line-height: 1.12; }
  .hero p { margin-left: 0; font-size: 0.92rem; }
  .hero-mark { width: 46px; height: 46px; flex-basis: 46px; border-radius: 12px; }
  .hero-mark img { width: 34px; height: 34px; }
}
</style>
"""

SAND_CSS = """
<style>
.block-container { padding-top: 2.2rem !important; max-width: 1180px; }
.stApp { background: #FAF6EE !important; }

[data-testid="stSidebar"] { background: #F3EDE1; border-right: 1px solid #E6DCCB; }
[data-testid="stSidebar"] h3 { color: #7A5C33; }

.hero {
  background: linear-gradient(135deg, #FFFDF8 0%, #F8F0E2 100%);
  border: 1px solid #EBE0CC; border-radius: 18px; padding: 1.7rem 1.9rem;
  box-shadow: 0 1px 2px rgba(60, 40, 10, 0.04), 0 18px 40px -28px rgba(60, 40, 10, 0.55);
}
.hero-mark { width: 64px; height: 64px; border-radius: 16px; flex: 0 0 64px;
  background: linear-gradient(145deg, #8A6A3B, #C08A45);
  box-shadow: 0 10px 22px -10px rgba(138, 106, 59, 0.55); }
.hero h1 { font-size: 2.05rem; color: #241B10; }
.hero p { color: #6B5B45; font-size: 1rem; }

[data-testid="stVerticalBlockBorderWrapper"] {
  background: #FFFFFF; padding: 0.7rem 0.9rem; border-radius: 12px !important;
  border: 1px solid #EBE2D2 !important;
  box-shadow: 0 1px 2px rgba(60, 40, 10, 0.04), 0 8px 20px -20px rgba(60, 40, 10, 0.3);
}
.panel-title .label { color: #8A6A3B; }
mark { background: #F3E3C4; color: #241B10; }
.stButton button[kind="primary"] {
  background: linear-gradient(135deg, #8A6A3B, #B5834A) !important; border: none !important;
  box-shadow: 0 8px 18px -10px rgba(138, 106, 59, 0.8);
}
</style>
"""

# Appended last so it wins on equal specificity. Streamlit's theme paints the page,
# widgets and text; these are only the surfaces the theme has no token for.
DARK_CSS = """
<style>
[data-testid="stSidebar"] { background: #0E1917; border-right-color: #223330; }
[data-testid="stSidebar"] h3 { color: #C7D8D4; }
[data-testid="stVerticalBlockBorderWrapper"] {
  background: #131F1D;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.45), 0 10px 24px -20px rgba(0, 0, 0, 0.9);
}
.hero h1 { color: #E6F2EF; }
.hero p { color: #9BB3AE; }
.panel-title .label { color: #5EEAD4; }
.panel-title .hint { color: #8AA5A0; }
mark { background: rgba(20, 184, 166, 0.32); color: #E6F2EF; }
.stTextArea textarea, .stTextInput input { background: #0F1A18 !important; color: #E6F2EF !important; }
</style>
"""

# --- page ------------------------------------------------------------------

st.set_page_config(
    page_title="Timbre Pronunciation Studio",
    page_icon=":material/record_voice_over:",
    layout="wide",
)


def _css_body(block: str) -> str:
    return block.replace("<style>", "").replace("</style>", "")


# One <style> element: Streamlit's HTML sanitizer keeps only one per st.html call.
style = _css_body(BASE_CSS) + _css_body(SAND_CSS)
if st.get_option("theme.base") == "dark":
    style += _css_body(DARK_CSS)
st.markdown(f"<style>{style}</style>", unsafe_allow_html=True)


# Services ------------------------------------------------------------------


@st.cache_resource
def services():
    """One store, cache and client per process, like ``app.py``.

    A missing key is not fatal: the app still reads and writes dictionaries,
    and only the two paid actions are disabled.
    """
    try:
        settings = load_settings()
        client = TimbreClient(
            settings.api_key, settings.base_url, settings.timeout_seconds
        )
        data_dir = settings.data_dir
        key_error = None
    except ConfigurationError as exc:
        settings, client, key_error = None, None, exc.message
        data_dir = DEFAULT_DATA_DIR

    return (
        settings,
        DictionaryStore(data_dir),
        AudioCache(data_dir / "audio"),
        client,
        key_error,
    )


settings, store, cache, client, key_error = services()
LANGUAGE = settings.language if settings else "en-IN"
SPEED = settings.speed if settings else 1.0
SCRIPT_LIMIT = settings.script_block_chars if settings else 2000

# Session state -------------------------------------------------------------

st.session_state.setdefault("active_id", None)
st.session_state.setdefault("draft_rows", [])
st.session_state.setdefault("drafts_for", None)
st.session_state.setdefault("draft_seq", 0)
st.session_state.setdefault("add_seq", 0)
st.session_state.setdefault("new_seq", 0)
st.session_state.setdefault("csv_seq", 0)
st.session_state.setdefault("script_text", "")
st.session_state.setdefault("audio_result", None)
st.session_state.setdefault("voice_preview", None)
st.session_state.setdefault("seeded", False)
# The configured default model wins, exactly like the shipped app's settings.
default_model = (
    next((m for m in MODELS if m.id == settings.default_model), None) if settings else None
) or MODELS[0]
st.session_state.setdefault("model_pick", default_model.label)
st.session_state.setdefault("voice_pick", default_model.default_voice)
# Drafts hold the pending choice; the sidebar reads only the applied *_pick keys.
st.session_state.setdefault("model_draft", st.session_state.model_pick)
st.session_state.setdefault("voice_draft", st.session_state.voice_pick)

# First run only: seed the three verified Gate B rules and preload the sample
# script (App Flow §5). A later session starts with an empty editor but keeps
# the dictionary, because dictionaries are files on disk.
if not st.session_state.seeded:
    try:
        created = ensure_seed(store)
    except AppError as exc:
        # Left unseeded so the next rerun retries instead of leaving the app
        # with no dictionary and no explanation.
        st.session_state.seed_error = exc.message
    else:
        st.session_state.seeded = True
        if created is not None:
            st.session_state.script_text = SAMPLE_SCRIPT
            st.session_state.active_id = created.id


def _load_drafts(dictionary: Dictionary) -> None:
    """Mirror the stored rules into editable drafts and reset their widget keys."""
    st.session_state.draft_rows = [
        {"id": rule.id, "source": rule.source, "replacement": rule.replacement}
        for rule in dictionary.rules
    ]
    st.session_state.drafts_for = dictionary.id
    st.session_state.draft_seq += 1


def _select(dictionary_id: str) -> None:
    if dictionary_id == st.session_state.active_id:
        return
    st.session_state.active_id = dictionary_id
    _load_drafts(store.get(dictionary_id))


def _remove_draft(index: int) -> None:
    st.session_state.draft_rows.pop(index)
    st.session_state.draft_seq += 1


def _ask_new() -> None:
    st.session_state.pending_new = True


def _ask_import(dictionary_id: str | None) -> None:
    st.session_state.pending_import = dictionary_id


def _ask_delete(dictionary_id: str) -> None:
    st.session_state.pending_delete = dictionary_id


# Waveform player ------------------------------------------------------------
# st.audio is the browser's native control: a straight bar with no shape. This
# draws the same clip as a real waveform you can click or arrow-key to seek.

WAVE_BARS = 96
WAVE_WIDTH = 288  # viewBox units; the SVG stretches to the column
WAVE_HEIGHT = 40


@st.cache_data(show_spinner=False, max_entries=64)
def _wave_peaks(audio: bytes) -> list[float]:
    with wave.open(io.BytesIO(audio)) as clip:
        rate, channels = clip.getframerate(), clip.getnchannels()
        width = clip.getsampwidth()
        frames = clip.readframes(min(clip.getnframes(), rate * 120))
    if width != 2 or not frames:
        return [0.35] * WAVE_BARS
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    edges = np.linspace(0, len(samples), WAVE_BARS + 1).astype(int)
    peaks = np.array(
        [np.abs(samples[a:b]).max(initial=0.0) for a, b in zip(edges, edges[1:])]
    )
    return (peaks / (peaks.max() or 1.0)).tolist()


def _wave_bars(peaks: list[float]) -> str:
    step = WAVE_WIDTH / len(peaks)
    bar = max(1.0, step * 0.6)
    middle = WAVE_HEIGHT / 2
    return "".join(
        f'<rect x="{i * step + (step - bar) / 2:.2f}" '
        f'y="{middle - max(1.2, p * (middle - 2)):.2f}" width="{bar:.2f}" '
        f'height="{max(1.2, p * (middle - 2)) * 2:.2f}" rx="{bar / 2:.2f}"/>'
        for i, p in enumerate(peaks)
    )


def _media_url(audio: bytes) -> str | None:
    # shortcut: the media manager is semi-private Streamlit API; if it moves,
    # waveform_player falls back to the native st.audio control.
    try:
        from streamlit.runtime.runtime import Runtime

        return Runtime.instance().media_file_mgr.add(
            audio, "audio/wav", f"waveform:{hashlib.sha1(audio).hexdigest()[:12]}"
        )
    except Exception:  # noqa: BLE001 — a player must never break playback
        return None


def waveform_player(audio: bytes) -> None:
    url = _media_url(audio)
    if url is None:
        st.audio(audio, format="audio/wav")
        return
    bars = _wave_bars(_wave_peaks(audio))
    st.components.v1.html(
        f"""
<style>
  html, body {{ margin: 0; background: transparent; }}
  .row {{ display: flex; align-items: center; gap: 0.65rem;
    font-family: ui-sans-serif, system-ui, sans-serif; }}
  .play {{ flex: 0 0 auto; width: 2.1rem; height: 2.1rem; border-radius: 50%;
    border: none; cursor: pointer; background: #8A6A3B; color: #FFFFFF;
    font-size: 0.72rem; line-height: 1; display: flex; align-items: center;
    justify-content: center; transition: background 0.12s ease; }}
  .play:hover {{ background: #6B4E24; }}
  .play:focus-visible, .wave:focus-visible {{ outline: 2px solid #8A6A3B;
    outline-offset: 2px; }}
  .wave {{ flex: 1 1 auto; min-width: 0; cursor: pointer; border-radius: 6px; }}
  .wave svg {{ display: block; width: 100%; height: {WAVE_HEIGHT}px; }}
  .time {{ flex: 0 0 auto; font-size: 0.72rem; color: #8A7B63;
    font-variant-numeric: tabular-nums; }}
</style>
<div class="row">
  <button class="play" aria-label="Play">&#9654;</button>
  <div class="wave" role="slider" tabindex="0" aria-label="Seek"
       aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
    <svg viewBox="0 0 {WAVE_WIDTH} {WAVE_HEIGHT}" preserveAspectRatio="none">
      <defs><clipPath id="played">
        <rect id="clip" x="0" y="0" width="0" height="{WAVE_HEIGHT}"/>
      </clipPath></defs>
      <g fill="#DCD1BC">{bars}</g>
      <g fill="#8A6A3B" clip-path="url(#played)">{bars}</g>
    </svg>
  </div>
  <span class="time" id="time">0:00</span>
  <audio id="sound" src="{url}" preload="metadata"></audio>
</div>
<script>
  const audio = document.getElementById('sound');
  const play = document.querySelector('.play');
  const wave = document.querySelector('.wave');
  const clip = document.getElementById('clip');
  const time = document.getElementById('time');
  const fmt = s => isFinite(s)
    ? Math.floor(s / 60) + ':' + String(Math.floor(s % 60)).padStart(2, '0')
    : '0:00';
  function paint() {{
    const total = audio.duration || 0;
    const done = total ? audio.currentTime / total : 0;
    clip.setAttribute('width', (done * {WAVE_WIDTH}).toFixed(2));
    time.textContent = fmt(audio.currentTime) + ' / ' + fmt(total);
    wave.setAttribute('aria-valuenow', Math.round(done * 100));
  }}
  play.onclick = () => {{ audio.paused ? audio.play() : audio.pause(); }};
  audio.onplay = () => {{
    play.innerHTML = '&#10074;&#10074;';
    play.setAttribute('aria-label', 'Pause');
  }};
  audio.onpause = () => {{
    play.innerHTML = '&#9654;';
    play.setAttribute('aria-label', 'Play');
  }};
  audio.ontimeupdate = paint;
  audio.onloadedmetadata = paint;
  audio.onended = paint;
  wave.onclick = event => {{
    if (!audio.duration) return;
    const box = wave.getBoundingClientRect();
    const at = (event.clientX - box.left) / box.width;
    audio.currentTime = Math.min(1, Math.max(0, at)) * audio.duration;
  }};
  wave.onkeydown = event => {{
    if (!audio.duration) return;
    if (event.key === 'ArrowRight') audio.currentTime = Math.min(
      audio.duration, audio.currentTime + 2);
    if (event.key === 'ArrowLeft') audio.currentTime = Math.max(
      0, audio.currentTime - 2);
    if (event.key === ' ') {{ event.preventDefault(); audio.paused
      ? audio.play() : audio.pause(); }}
  }};
  paint();
</script>
""",
        height=46,
        scrolling=False,
    )



# Settings dialog -----------------------------------------------------------


@st.dialog("Settings", width="large")
def settings_dialog() -> None:
    nav, body = st.columns([0.3, 0.7], gap="large")
    with nav, st.container(key="settings_nav"):
        section = st.radio(
            "Section",
            ["Model", "Voice", "Policies", "About"],
            key="settings_section",
            label_visibility="collapsed",
        )

    with body:
        if section == "Model":
            st.markdown("#### Model")
            st.caption("The Timbre model used for every clip in this session.")
            st.selectbox("Model", [m.label for m in MODELS], key="model_draft")
            st.caption("Language · en-IN  ·  Speed · 1.0×  —  fixed for this release.")
            if st.session_state.model_draft != st.session_state.model_pick:
                st.session_state.model_note = None
            save_col, note_col = st.columns([0.3, 0.7], vertical_alignment="center")
            if save_col.button("Save model", type="primary", key="save_model"):
                chosen = next(
                    m for m in MODELS if m.label == st.session_state.model_draft
                )
                if chosen.label == st.session_state.model_pick:
                    st.session_state.model_note = f"{chosen.label} is already selected."
                else:
                    st.session_state.model_pick = chosen.label
                    st.session_state.voice_pick = chosen.default_voice
                    st.session_state.voice_draft = chosen.default_voice
                    st.session_state.model_note = None
                    st.toast(f"Model saved · {chosen.label}")
                    st.session_state.settings_requested = True
                    st.rerun(scope="app")
            if st.session_state.get("model_note"):
                note_col.caption(st.session_state.model_note)
        elif section == "Voice":
            st.markdown("#### Voice")
            st.caption("Voices belong to a model, so this list follows your model choice.")
            chosen = next(m for m in MODELS if m.label == st.session_state.model_pick)
            ids = [v.id for v in chosen.voices]
            labels = {v.id: f"{v.id} · {v.gender} · {v.persona}" for v in chosen.voices}
            if st.session_state.voice_draft not in ids:
                st.session_state.voice_draft = chosen.default_voice
            st.selectbox("Voice", ids, key="voice_draft", format_func=labels.get)
            voice = next(v for v in chosen.voices if v.id == st.session_state.voice_draft)
            st.caption(f"{voice.gender.capitalize()} · {voice.persona}")

            st.divider()
            st.markdown("###### Preview")
            st.caption(
                "A short sample of the selected voice. The first preview of a "
                "voice makes one Timbre call; every later preview is free."
            )
            if client is None:
                st.caption("Add GNANI_API_KEY to backend/.env to enable previews.")
            elif st.button(
                "Preview voice",
                icon=":material/play_circle:",
                key="preview_voice",
                width="content",
            ):
                with st.spinner("Generating one sample…"):
                    try:
                        clip = cache.get_or_synthesize(
                            client,
                            text=PREVIEW_TEXT,
                            model=chosen.id,
                            voice=voice.id,
                            language=LANGUAGE,
                            speed=SPEED,
                            audio_config=DEFAULT_AUDIO_CONFIG,
                        )
                    except AppError as exc:
                        st.error(exc.message)
                    except Exception as exc:  # noqa: BLE001 — surface, never crash
                        st.error(f"Preview failed: {exc}")
                    else:
                        st.session_state.voice_preview = {
                            "voice": voice.id,
                            "model": chosen.id,
                            "audio": clip.audio,
                            "cached": clip.cached,
                        }

            preview = st.session_state.voice_preview
            if preview and (preview["voice"], preview["model"]) == (
                voice.id,
                chosen.id,
            ):
                waveform_player(preview["audio"])
                st.caption(
                    "Replayed from the cache — no call, no credits."
                    if preview["cached"]
                    else "Generated once and cached. Replaying it is free."
                )

            st.divider()
            if st.session_state.voice_draft != st.session_state.voice_pick:
                st.session_state.voice_note = None
            save_col, note_col = st.columns([0.3, 0.7], vertical_alignment="center")
            if save_col.button("Save voice", type="primary", key="save_voice"):
                if st.session_state.voice_draft == st.session_state.voice_pick:
                    st.session_state.voice_note = (
                        f"{st.session_state.voice_pick} is already selected."
                    )
                else:
                    st.session_state.voice_pick = st.session_state.voice_draft
                    st.session_state.voice_note = None
                    st.toast(f"Voice saved · {st.session_state.voice_pick}")
                    st.session_state.settings_requested = True
                    st.rerun(scope="app")
            if st.session_state.get("voice_note"):
                note_col.caption(st.session_state.voice_note)
        elif section == "Policies":
            st.markdown("#### Policies & Privacy")
            st.caption("What this app stores, where it goes, and what it cannot do.")
            for title, body in POLICIES:
                st.markdown(f"##### {title}")
                st.markdown(body)
                st.divider()
            st.caption("Last reviewed against the code on this machine, not a template.")
        else:
            st.markdown("#### About")
            st.markdown(
                "**Timbre Pronunciation Studio**\n\n"
                "A local studio for the names text-to-speech usually gets wrong. "
                "Write the script once, keep a dictionary of respellings, and "
                "compare the original and adjusted clips side by side.\n\n"
                "This preview reads and writes the same `data/dictionaries/` files "
                "as the app and caches audio in the same `data/audio/` folder."
            )
            st.divider()
            st.caption("Policies & Privacy")
            st.write("Open the **Policies** tab for storage, usage and limitations.")
            st.divider()
            st.caption("Limitations")
            st.write(LIMITATION)


def _open_settings() -> None:
    # Opening the dialog discards any draft left over from a cancelled edit.
    st.session_state.model_draft = st.session_state.model_pick
    st.session_state.voice_draft = st.session_state.voice_pick
    st.session_state.model_note = None
    st.session_state.voice_note = None
    st.session_state.settings_requested = True


# Dictionary dialogs --------------------------------------------------------


@st.dialog("New dictionary")
def new_dialog() -> None:
    name = st.text_input(
        "Name",
        max_chars=MAX_NAME_LENGTH,
        placeholder="Brand names",
        key=f"new_name_{st.session_state.new_seq}",
    )
    st.caption("A dictionary holds up to 200 rules. Nothing else is created.")
    if st.button("Create dictionary", type="primary", width="stretch", key="create_dictionary"):
        try:
            created = store.create(name)
        except AppError as exc:
            st.error(exc.message)
        else:
            st.session_state.active_id = created.id
            st.session_state.new_seq += 1
            _load_drafts(created)
            st.rerun(scope="app")

    st.divider()
    st.caption("Already have a spreadsheet? Two columns: `term,says`.")
    if st.button("Import CSV", width="stretch", key="new_import"):
        _ask_import(None)
        st.rerun(scope="app")


@st.dialog("Import CSV")
def import_dialog(dictionary: Dictionary | None) -> None:
    dictionaries, _ = store.list_all()

    if dictionary is None:
        st.caption("Choose a dictionary to import into, or create a new one from the CSV.")
        dict_names = {d.name: d.id for d in dictionaries}
        choice = st.radio(
            "Target",
            ["Existing dictionary"] + (["Create new from CSV"] if dictionaries else []),
            key="import_target_choice",
            horizontal=False,
        )
        if choice == "Existing dictionary":
            if not dictionaries:
                st.warning("No dictionaries exist yet. Create one first.")
                return
            selected_name = st.selectbox("Dictionary", list(dict_names.keys()), key="import_target_dict")
            target_id = dict_names[selected_name]
            dictionary = store.get(target_id)
        else:
            # Create new from CSV - will be handled after upload
            dictionary = None
    else:
        st.caption(f"Into **{dictionary.name}** · {len(dictionary.rules)} rules now")

    upload = st.file_uploader(
        "CSV file",
        type=["csv"],
        key=f"csv_upload_{dictionary.id if dictionary else 'new'}_{st.session_state.csv_seq}",
    )
    if upload is None:
        st.caption("Two columns: `term,says`, with a header row. UTF-8.")
        return

    rows, errors = parse_csv(
        upload.getvalue(),
        max_source=MAX_SOURCE_LENGTH,
        max_replacement=MAX_REPLACEMENT_LENGTH,
    )
    if errors:
        with st.expander(f"{len(errors)} problem(s) found", expanded=True):
            for problem in errors:
                st.markdown(f"- {problem}")
    if not rows:
        st.warning("Nothing in this file can be imported.")
        return

    st.markdown(f"**{len(rows)} row(s) ready**")
    st.dataframe(
        {"Term": [row.source for row in rows], "Says": [row.replacement for row in rows]},
        hide_index=True,
        width="stretch",
        height=220,
    )

    if dictionary is not None:
        # Import into existing dictionary
        mode = st.radio(
            "When a term already exists",
            ["Merge — keep existing rules", "Replace — start from the CSV"],
            key="import_mode",
        )
        existing = {rule.source.casefold() for rule in dictionary.rules}
        new_rows = [row for row in rows if row.source.casefold() not in existing]

        if mode.startswith("Merge"):
            payload: list[tuple[str | None, str, str]] = [
                (rule.id, rule.source, rule.replacement) for rule in dictionary.rules
            ] + [(None, row.source, row.replacement) for row in new_rows]
            skipped = len(rows) - len(new_rows)
            if not new_rows:
                st.info("Every term in this file is already in this dictionary.")
                return
            st.caption(
                f"{len(new_rows)} rule(s) added, {skipped} skipped as duplicates. "
                f"{len(payload)} rules after import."
            )
        else:
            payload = [(None, row.source, row.replacement) for row in rows]
            st.caption(
                f"All {len(dictionary.rules)} existing rule(s) are replaced by "
                f"{len(rows)} from the file."
            )

        if len(payload) > MAX_RULES:
            st.error(f"That would exceed the {MAX_RULES}-rule limit for one dictionary.")
            return

        if st.button(f"Import {len(rows) if mode.startswith('Replace') else len(new_rows)} rules",
                     type="primary", width="stretch", key="confirm_import"):
            try:
                updated = store.set_rules(dictionary.id, payload)
            except AppError as exc:
                st.error(exc.message)
            else:
                st.session_state.csv_seq += 1
                _load_drafts(updated)
                st.toast(f"Imported into {updated.name}")
                st.rerun(scope="app")
    else:
        # Create new dictionary from CSV
        name = st.text_input(
            "New dictionary name", max_chars=MAX_NAME_LENGTH,
            placeholder="Brand names", key=f"import_new_name_{st.session_state.new_seq}",
        )
        st.caption(f"Will create **{name or '(unnamed)'}** with {len(rows)} rule(s).")
        if len(rows) > MAX_RULES:
            st.error(f"CSV has {len(rows)} rows; limit is {MAX_RULES} rules per dictionary.")
            return

        if st.button(f"Create dictionary with {len(rows)} rules", type="primary",
                     width="stretch", key="confirm_import_new"):
            if not name.strip():
                st.error("Please enter a dictionary name.")
                return
            try:
                payload = [(None, row.source, row.replacement) for row in rows]
                created = store.create(name.strip())
                updated = store.set_rules(created.id, payload)
            except AppError as exc:
                st.error(exc.message)
            else:
                st.session_state.csv_seq += 1
                st.session_state.active_id = updated.id
                _load_drafts(updated)
                st.toast(f"Created {updated.name} from CSV")
                st.rerun(scope="app")


@st.dialog("Delete dictionary")
def delete_dialog(dictionary: Dictionary) -> None:
    st.write(
        f"Delete **{dictionary.name}** and its {len(dictionary.rules)} rule(s)? "
        "This cannot be undone."
    )
    st.caption("Cached audio is not deleted — it stays in data/audio/.")
    if st.button("Delete dictionary", type="primary", width="stretch", key="confirm_delete"):
        try:
            store.delete(dictionary.id)
        except AppError as exc:
            st.error(exc.message)
        else:
            st.session_state.active_id = None
            st.session_state.drafts_for = None
            st.rerun(scope="app")


# Sidebar rail --------------------------------------------------------------

dictionaries, store_warnings = store.list_all()
if st.session_state.active_id not in {d.id for d in dictionaries}:
    st.session_state.active_id = dictionaries[0].id if dictionaries else None
dictionary = next(
    (d for d in dictionaries if d.id == st.session_state.active_id), None
)

with st.sidebar:
    head_col, add_col = st.columns([1, 0.16], vertical_alignment="center")
    head_col.markdown("### :material/library_books: Dictionaries")
    with add_col, st.container(key="dict_add"):
        st.button(
            "", icon=":material/add:", help="New dictionary", width="content",
            type="tertiary", key="dict_new", on_click=_ask_new,
        )
    with st.container(key="dict_list"):
        for item in dictionaries:
            current = item.id == st.session_state.active_id
            row_key = "dict_row_current" if current else f"dict_row_{item.id}"
            with st.container(key=row_key):
                name_col, menu_col = st.columns([1, 0.16], vertical_alignment="center")
                name_col.button(
                    item.name,
                    icon=":material/menu_book:" if current else None,
                    type="tertiary", width="stretch", key=f"dict_pick_{item.id}",
                    on_click=_select, args=(item.id,),
                )
                with menu_col, st.container(key=f"dict_menu_{item.id}"):
                    with st.popover("", icon=":material/more_vert:"):
                        with st.container(key=f"menu_body_{item.id}"):
                            st.caption(item.name)
                            name = st.text_input(
                                "Name", value=item.name, key=f"name_{item.id}",
                                label_visibility="collapsed", max_chars=MAX_NAME_LENGTH,
                            )
                            if st.button(
                                "Rename", width="stretch",
                                type="tertiary", key=f"rename_{item.id}",
                            ):
                                try:
                                    store.rename(item.id, name)
                                except AppError as exc:
                                    st.error(exc.message)
                                else:
                                    st.toast("Renamed")
                                    st.rerun()

                            st.download_button(
                                "Export CSV",
                                data=to_csv([(r.source, r.replacement) for r in item.rules]),
                                file_name=f"{slug(item.name)}-dictionary.csv",
                                mime="text/csv",
                                width="stretch",
                                type="tertiary",
                                key=f"export_{item.id}",
                            )
                            st.download_button(
                                "Backup (JSON)",
                                data=item.model_dump_json(indent=2).encode("utf-8"),
                                file_name=f"{slug(item.name)}-backup.json",
                                mime="application/json",
                                width="stretch",
                                type="tertiary",
                                key=f"backup_{item.id}",
                            )
                            st.button(
                                "Delete", width="stretch",
                                type="tertiary", key=f"ask_delete_{item.id}",
                                on_click=_ask_delete, args=(item.id,),
                            )

    if not dictionaries:
        st.caption("No dictionaries yet. Use + to create the first one.")
    if dictionary and is_seed_dictionary(dictionary):
        st.badge(
            "Sample", icon=":material/verified:", color="green", help=SEED_LABEL
        )
    if store_warnings:
        st.caption(f"{len(store_warnings)} dictionary file(s) could not be read.")
    if st.session_state.get("seed_error"):
        st.error(st.session_state.seed_error)

    st.space("small")
    st.markdown("### :material/graphic_eq: Voice")
    shown_model = next(
        (m for m in MODELS if m.label == st.session_state.model_pick), MODELS[0]
    )
    shown_voice = (
        shown_model.voice(st.session_state.voice_pick)
        or shown_model.voice(shown_model.default_voice)
        or shown_model.voices[0]
    )
    st.html(
        f"""
<div class="voice-block">
  <div class="model">{shown_model.label}</div>
  <div class="name">{shown_voice.id}</div>
  <div class="meta">{shown_voice.gender.capitalize()} · {shown_voice.persona}</div>
</div>
"""
    )

    st.space("small")

    with st.container(key="sidebar_footer"):
        st.button(
            "", icon=":material/settings:", help="Settings", width="content",
            type="tertiary", key="open_settings", on_click=_open_settings,
        )

# Pending dialogs: one flag, one dialog, rendered after the sidebar that set it.
if st.session_state.pop("settings_requested", False):
    settings_dialog()
elif st.session_state.pop("pending_new", False):
    new_dialog()
elif (pending := st.session_state.pop("pending_import", ...)) is not ...:
    # pending is either a dictionary_id (str) or None (means show picker)
    import_dialog(store.get(pending) if pending else None)
elif (pending := st.session_state.pop("pending_delete", None)):
    delete_dialog(store.get(pending))

# Hero ----------------------------------------------------------------------

st.html(
    f"""
<div class="hero">
  <div class="hero-head">
    <div class="hero-mark"><img src="{WAVE_URI}" width="50" height="50" alt=""></div>
    <h1 style="font-size: 64px; font-weight: 670;">Timbre Pronunciation Studio</h1>
  </div>
  <p>Rewrite the names Timbre gets wrong, then hear the difference in one click.</p>
</div>
"""
)

st.space("small")

if dictionary is None:
    with st.container(border=True):
        st.markdown("#### No dictionary yet")
        st.write("Create one to start writing rules and comparing clips.")
        if st.button("New dictionary", icon=":material/add:", type="primary"):
            new_dialog()
    st.stop()

# Script --------------------------------------------------------------------

st.html(
    '<div class="panel-title"><span class="label">Script</span>'
    '<span class="help" title="The text Timbre will read aloud.">?</span></div>'
)
st.text_area(
    "Script", height=150, label_visibility="collapsed",
    placeholder=SAMPLE_SCRIPT, key="script_text",
)
script = st.session_state.script_text
st.caption(f"{len(script)} / {SCRIPT_LIMIT} characters")
if len(script) > SCRIPT_LIMIT:
    st.error(f"This script is {len(script)} characters; the limit is {SCRIPT_LIMIT}.")

# An empty script shows the worked example: ghost text, its rules and its
# preview. The first typed word clears all of it, so nothing demo-only is ever
# mistaken for the user's own data.
demo = not script.strip()
text = SAMPLE_SCRIPT if demo else script

# Drafts --------------------------------------------------------------------

if st.session_state.drafts_for != dictionary.id:
    _load_drafts(dictionary)
drafts = st.session_state.draft_rows
seq = st.session_state.draft_seq

preview_pairs = [
    (row["source"], row["replacement"]) for row in drafts if row["source"].strip()
]
draft_rules = tuple(
    Rule(source=source, replacement=replacement, rule_id=f"draft-{index}")
    for index, (source, replacement) in enumerate(preview_pairs)
)
transform = apply_rules(text, draft_rules)
counts = {match.source: match.count for match in transform.matches}

# Rules ---------------------------------------------------------------------

st.html(
    '<div class="panel-title"><span class="label">Rules</span>'
    '<span class="help" title="Edits stay in the browser until you press Save rules.">?</span>'
    "</div>"
)

add_seq = st.session_state.add_seq
with st.form("add_rule", border=True):
    term_col, says_col, button_col = st.columns([1, 1, 0.5], vertical_alignment="bottom")
    new_source = term_col.text_input(
        "Term", placeholder="e.g. Coimbatore", key=f"add_term_{add_seq}"
    )
    new_says = says_col.text_input(
        "Says", placeholder="e.g. Ko-yam-ba-toor", key=f"add_says_{add_seq}"
    )
    submitted = button_col.form_submit_button(
        "Add rule", icon=":material/add:", width="stretch"
    )

if submitted:
    if not new_source.strip() or not new_says.strip():
        st.error("Both a term and a pronunciation are needed.")
    elif any(
        row["source"].strip().casefold() == new_source.strip().casefold()
        for row in drafts
    ):
        st.error(f'"{new_source.strip()}" is already in this draft.')
    else:
        drafts.append(
            {"id": None, "source": new_source.strip(), "replacement": new_says.strip()}
        )
        st.session_state.add_seq += 1
        st.session_state.draft_seq += 1
        st.rerun()

header = st.columns([0.06, 1, 1, 0.28], vertical_alignment="center")
header[1].caption("Term")
header[2].caption("Says")
header[3].caption("Status")

for index, row in enumerate(drafts):
    with st.container(key=f"rule_row_{index}"):
        cells = st.columns([0.06, 1, 1, 0.28], vertical_alignment="center")
        cells[0].button(
            "",
            icon=":material/delete:",
            help=f"Remove '{row['source']}' from this draft",
            key=f"delete_rule_{seq}_{index}",
            on_click=_remove_draft,
            args=(index,),
        )
        row["source"] = cells[1].text_input(
            "Term", value=row["source"], key=f"rule_{seq}_{index}_source",
            label_visibility="collapsed",
        )
        row["replacement"] = cells[2].text_input(
            "Says", value=row["replacement"], key=f"rule_{seq}_{index}_says",
            label_visibility="collapsed",
        )
        count = counts.get(row["source"], 0)
        cells[3].badge(
            str(count) if count else "not found",
            icon=":material/check_circle:" if count else ":material/warning:",
            color="green" if count else "orange",
        )

if not drafts:
    st.caption("No rules yet — add your first respelling above.")

stored_rows = [(rule.id, rule.source, rule.replacement) for rule in dictionary.rules]
draft_key = [(row["id"], row["source"], row["replacement"]) for row in drafts]
dirty = draft_key != stored_rows

save_col, cancel_col, note_col = st.columns(
    [0.22, 0.18, 0.6], vertical_alignment="center"
)
if save_col.button("Save rules", type="primary", disabled=not dirty, key="save_rules"):
    try:
        updated = store.set_rules(dictionary.id, draft_key)
    except AppError as exc:
        st.error(exc.message)
    else:
        _load_drafts(updated)
        st.toast(f"Saved {len(updated.rules)} rule(s)")
        st.rerun()
if cancel_col.button("Cancel", disabled=not dirty, key="cancel_rules"):
    _load_drafts(dictionary)
    st.rerun()
if dirty:
    note_col.caption("Unsaved changes — the preview below uses them.")

# Preview -------------------------------------------------------------------

st.html(
    '<div class="panel-title"><span class="label">Preview</span>'
    '<span class="help" title="What Timbre receives. Computed locally — no credits spent.">?</span>'
    "</div>"
)

original_col, transformed_col = st.columns(2, gap="medium")
with original_col, st.container(border=True):
    st.badge("Original", icon=":material/notes:", color="gray")
    st.write(text)
with transformed_col, st.container(border=True):
    st.badge("Sent to Timbre", icon=":material/send:", color="primary")
    st.html(f'<div style="line-height:1.65">{highlighted(text, preview_pairs)}</div>')

# Action --------------------------------------------------------------------

model = next(
    (m for m in MODELS if m.label == st.session_state.model_pick), MODELS[0]
)
voice = (
    model.voice(st.session_state.voice_pick)
    or model.voice(model.default_voice)
    or model.voices[0]
)
sig = (text, transform.transformed_text, model.id, voice.id)

if st.session_state.audio_result and st.session_state.audio_result.get("sig") != sig:
    st.session_state.audio_result = None

no_change = transform.transformed_text == text

with st.container(key="generate_row"):
    generate = st.button(
        "Generate comparison",
        icon=":material/play_arrow:",
        type="primary",
        key="generate",
        disabled=client is None or no_change,
    )
    if client is None:
        st.caption("Add GNANI_API_KEY to backend/.env to generate audio.")
    elif no_change:
        st.caption("No rules matched — nothing to compare.")

if generate and client is not None and not no_change:
    with st.spinner("Generating — a few seconds per clip."):
        try:
            original = cache.get_or_synthesize(
                client,
                text=text,
                model=model.id,
                voice=voice.id,
                language=LANGUAGE,
                speed=SPEED,
                audio_config=DEFAULT_AUDIO_CONFIG,
            )
            if transform.transformed_text == text:
                adjusted = original
            else:
                adjusted = cache.get_or_synthesize(
                    client,
                    text=transform.transformed_text,
                    model=model.id,
                    voice=voice.id,
                    language=LANGUAGE,
                    speed=SPEED,
                    audio_config=DEFAULT_AUDIO_CONFIG,
                )
        except AppError as exc:
            st.error(exc.message)
        except Exception as exc:  # noqa: BLE001 — surface, never crash
            st.error(f"Generation failed: {exc}")
        else:
            st.session_state.audio_result = {
                "sig": sig,
                "original": original.audio,
                "adjusted": adjusted.audio,
                "original_cached": original.cached,
                "adjusted_cached": adjusted.cached,
            }

# Audio ---------------------------------------------------------------------

st.html(
    '<div class="panel-title"><span class="label">Audio</span>'
    '<span class="help" title="Two clips: the original wording and your respelled version.">?</span>'
    "</div>"
)

result = st.session_state.audio_result
audio_columns = st.columns(2, gap="medium")
for column, label, audio_key, cached_key in (
    (audio_columns[0], "Original", "original", "original_cached"),
    (audio_columns[1], "Adjusted", "adjusted", "adjusted_cached"),
):
    with column, st.container(border=True):
        head = st.container(horizontal=True, vertical_alignment="center", gap="small")
        head.markdown(f"**{label}**")
        if result and result["sig"] == sig:
            head.badge(
                "cached" if result[cached_key] else "fresh",
                icon=":material/check_circle:",
                color="gray" if result[cached_key] else "green",
            )
            waveform_player(result[audio_key])
        else:
            st.html(
                '<div class="audio-empty">Generate the comparison to hear this clip.</div>'
            )
