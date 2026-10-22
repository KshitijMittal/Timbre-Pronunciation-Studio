# Timbre Pronunciation Studio — UI/UX Brief

| Field | Value |
|---|---|
| Document | UI/UX Brief |
| Version | 1.0 |
| Date | 20 October 2026 |
| Status | Approved — binding, amended 22 October 2026 |
| Parent documents | `docs/PRD.md` v1.0, `docs/TRD.md` v1.0, `docs/App Flow.md` v1.0 |
| Owners | [Teammate] — implements this brief in Streamlit; [You] — reviews against it before freeze |
| Scope | Visual design, layout, components, states, responsive behaviour, theming, accessibility |
| Amends | `docs/TRD.md` §14 NFR-09 (see §15.3) |

---

## 1. Purpose and design intent

This brief defines how Timbre Pronunciation Studio **looks and feels**, precisely enough that the frontend can be built without design decisions being made in code.

**Design intent, in one line:**

> A quiet, precise workbench where the only thing that draws the eye is the word that changed.

The product's value is a *difference* — between what was written and what was said. Every visual decision serves that comparison. Anything that competes with it for attention is removed.

### 1.1 What this design is not

| Not this | Because |
|---|---|
| A marketing landing page | There is no landing page; the app opens into the studio |
| A dashboard with charts | There is no metric to chart; the output is audio and text |
| A dark developer console by default | Text comparison is the core screen and reads better on light surfaces |
| A voice-agent demo with animated waves | The claim is precision, not spectacle |

---

## 2. Design principles

| # | Principle | Practical consequence |
|---|---|---|
| 1 | **The diff is the hero** | Substituted spans are the only tinted elements in the preview. Nothing else uses that tint. |
| 2 | **Quiet chrome** | Sidebar, header and borders are neutral and low-contrast. No shadows beyond a single subtle elevation on the drawer and dialogs. |
| 3 | **One accent, used sparingly** | Teal appears on primary actions, active states and focus rings only. Never as decoration. |
| 4 | **State is always visible** | Busy, error, no-op and degraded states each have a distinct, labelled appearance. The user never wonders whether something is happening. |
| 5 | **Honesty is designed in** | The limitation note is permanent UI, not a tooltip. Transformed text is labelled as what is sent to Timbre. |
| 6 | **Legible under compression** | Type sizes and contrast are chosen for screen-recorded video, not for maximum density. |
| 7 | **Nothing surprises on hover** | No content is revealed only on hover; hover only reinforces what is already visible. |
| 8 | **Keyboard is a first-class path** | Every action reachable by Tab, with visible focus. |

---

## 3. Visual direction

**Restrained developer tool.** Off-white surfaces, one accent, generous whitespace, no gradients, no glassmorphism, no illustration.

| Attribute | Direction |
|---|---|
| Mood | Calm, precise, instrument-like |
| Density | Comfortable, not compact |
| Corners | 6px on inputs and buttons, 10px on panels |
| Borders | 1px, low contrast, used to separate rather than decorate |
| Shadows | Only on the mobile drawer and confirm dialog |
| Iconography | Minimal line icons, 16px and 20px, from a single set |
| Imagery | None |

---

## 4. Colour system

All colours are defined as CSS custom properties on `:root` and overridden under `[data-theme="dark"]`. No component may hardcode a hex value.

### 4.1 Light theme (default)

| Token | Value | Use |
|---|---|---|
| `--bg` | `#FAFAF8` | App background |
| `--surface` | `#FFFFFF` | Panels, inputs, cards |
| `--surface-alt` | `#F4F4F0` | Table header, inactive rows |
| `--border` | `#E2E2DC` | Default borders |
| `--border-strong` | `#C8C8C0` | Input borders on focus-within, dividers |
| `--text` | `#1A1A18` | Primary text |
| `--text-secondary` | `#5C5C56` | Labels, helper text |
| `--text-muted` | `#8A8A82` | Meta, placeholders, disabled text |
| `--accent` | `#0F6B63` | Primary buttons, active state, focus ring |
| `--accent-hover` | `#0B544E` | Hover on primary |
| `--accent-subtle` | `#E6F2F0` | Active sidebar item, diff highlight background |
| `--accent-text` | `#FFFFFF` | Text on accent fill |
| `--diff-bg` | `#D9EDE9` | Substituted span background |
| `--diff-border` | `#0F6B63` | Substituted span dashed underline |
| `--success` | `#1E7A4B` | Healthy status dot, success text |
| `--warning` | `#8A5A00` | Limit warning text and border |
| `--warning-bg` | `#FDF4E0` | Limit warning background |
| `--error` | `#B3261E` | Error text and border |
| `--error-bg` | `#FDECEA` | Error banner background |
| `--focus-ring` | `#0F6B63` | 2px ring, 2px offset |

### 4.2 Dark theme

| Token | Value | Use |
|---|---|---|
| `--bg` | `#121413` | App background |
| `--surface` | `#1A1D1C` | Panels, inputs |
| `--surface-alt` | `#222624` | Table header, inactive rows |
| `--border` | `#2C3230` | Default borders |
| `--border-strong` | `#3D4441` | Emphasis borders |
| `--text` | `#ECEDEA` | Primary text |
| `--text-secondary` | `#A8ADA9` | Labels |
| `--text-muted` | `#7A807C` | Meta, placeholders |
| `--accent` | `#4FD1C5` | Primary buttons, active state, focus ring |
| `--accent-hover` | `#6FDDD2` | Hover |
| `--accent-subtle` | `#1E3A36` | Active item, diff background |
| `--accent-text` | `#0B1F1C` | Text on accent fill |
| `--diff-bg` | `#1F3F3A` | Substituted span background |
| `--diff-border` | `#4FD1C5` | Substituted span dashed underline |
| `--success` | `#5FD39A` | Healthy status |
| `--warning` | `#E8B44A` | Limit warning |
| `--warning-bg` | `#2E2513` | Limit warning background |
| `--error` | `#FF8A80` | Error text |
| `--error-bg` | `#33191A` | Error banner background |
| `--focus-ring` | `#4FD1C5` | Focus ring |

### 4.3 Colour rules

1. **The diff tint appears only in the transformed preview.** No other element uses `--diff-bg`.
2. **Warning and error are never used decoratively.** Amber means "you are near a limit"; red means "something failed".
3. **Accent is never used for text on a surface** except in the diff underline and links. Body text is `--text`.
4. **Contrast is verified, not assumed.** Every text/background pair must meet the ratios in §12.1.

---

## 5. Typography

**One family.** System UI stack, no webfont download, no FOUT, no licensing:

```css
--font-sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto,
             "Helvetica Neue", Arial, sans-serif;
--font-mono: ui-monospace, "Cascadia Mono", "SF Mono", Consolas,
             "Liberation Mono", monospace;
```

### 5.1 Scale

| Token | Size / line-height | Weight | Use |
|---|---|---|---|
| `--text-xs` | 13 / 1.5 | 500 | Meta, match counts, settings echo |
| `--text-sm` | 14 / 1.55 | 400 | Labels, helper text, table cells |
| `--text-base` | **16 / 1.65** | 400 | Script input, preview text, body |
| `--text-lg` | 18 / 1.5 | 600 | Panel titles |
| `--text-xl` | 22 / 1.35 | 650 | App title |
| `--text-mono` | 15 / 1.7 | 400 | Transformed preview, diff spans |

### 5.2 Typography rules

- **Base size is 16px, not 14px.** Chosen for legibility in compressed video (principle 6).
- **The script editor uses sans-serif.** It is authored content; it should feel like writing.
- **The transformed preview uses monospace.** It is an inspectable artefact; fixed-width characters make substitutions and punctuation visible.
- **Line length caps at 78 characters** in preview panes for readability.
- **No font weights below 400.** Thin strokes vanish under video compression.
- **No letter-spacing tricks** except `0.02em` on all-caps micro-labels.

---

## 6. Spacing, sizing and layout

### 6.1 Spacing scale

`4 · 8 · 12 · 16 · 24 · 32 · 48` px. All margins and paddings use these values only.

### 6.2 Layout grid

| Property | Value |
|---|---|
| Container max-width | 1280px, centred, horizontal padding 24px |
| Sidebar width | 280px (≥1280px), 240px (900–1279px) |
| Column gap | 24px |
| Main column | Fluid, `min-width: 0` to allow text truncation |
| Panel padding | 20px |
| Panel vertical gap | 16px |
| Panel order | Script → Rules → Preview → Audio |

### 6.3 Vertical rhythm

Each panel is a card with: title row (18px/600 + optional action), 12px gap, content. The vertical order is the working order — a user reads top to bottom and never scrolls back up to find a dependency.

---

## 7. Responsive behaviour

> **Superseded for this release.** This section describes the dropped React
> layout. The shipped UI is one Streamlit page; the breakpoint matrix below is
> **not** implemented. See §16.1. Read for intent only.

### 7.1 Breakpoints

| Name | Range | Layout |
|---|---|---|
| Desktop | ≥1280px | 280px sidebar + fluid main; full table |
| Laptop | 900–1279px | 240px sidebar + fluid main; full table |
| Tablet | 600–899px | Sidebar becomes a top bar with a dictionary selector; panels stack full width; table scrolls horizontally |
| Mobile | <600px | Single column; rule table becomes stacked cards |

### 7.2 Behaviour per breakpoint

**Tablet (600–899px)**
- Sidebar collapses into a horizontal bar above the main column containing: dictionary `<select>`, a "New" button, and a settings disclosure.
- The rule table keeps its column layout and gains `overflow-x: auto` with a sticky first column (source term).
- Preview panes stack vertically: Original above Transformed, each full width.
- Audio players stack vertically.

**Mobile (<600px)**
- Header condenses: title truncates, theme toggle and settings become icon buttons.
- All panels full width, 16px horizontal padding.
- **Rule table becomes a card list.** Each rule renders as a card:
  - Line 1: source term (weight 600) → replacement (mono, accent-subtle background)
  - Line 2: match count badge, or "no match" in muted text
  - Line 3: Edit and Delete text buttons, right-aligned
  - Editing replaces lines 1–2 with two stacked inputs and Save/Cancel
- The preview comparison becomes a **toggle** rather than side-by-side: two segmented buttons, "Original" and "Transformed", showing one at a time. Side-by-side at 375px would give each pane ~160px, which is unreadable.
- Generate button becomes full width, 48px tall.
- Audio players full width, stacked, with the settings echo below in `--text-xs`.

### 7.3 Responsive rules

1. **No horizontal page scroll** at any width. Horizontal scroll is permitted only inside the rule table on tablet.
2. **Touch targets ≥44×44px** on all interactive elements below 900px.
3. **The preview toggle is the only content hidden by default** on mobile. Nothing else is behind a tab.
4. **The limitation note is never hidden** at any breakpoint; it moves to the bottom of the sidebar or the top bar's overflow.

---

## 8. Component specifications

> **Superseded for this release — do not implement as written.** These specs
> describe the dropped React build. Where this section and `docs/App Flow.md` §3
> disagree, **`App Flow` wins**: there is no status dot (§8.1), no per-item
> overflow menu (§8.2), no focus-trapped confirm dialog (§8.11 — deletion is
> confirmed in place with a second button), no per-row editing table (§8.6 — it is
> one `st.data_editor`), and no diff-tinted preview pane (§8.7 — dropped, see
> §16.1). Streamlit cannot produce these without `unsafe_allow_html`, which
> `docs/TRD.md` §4.1 rejects. Read this section for intent, not for layout. The
> microcopy in §11 **is** still binding.

Each component lists its states. Every interactive element must define all six: default, hover, focus-visible, active, disabled, loading (where applicable).

### 8.1 Header

- Height 64px, `--surface`, 1px bottom border.
- Left: app title (`--text-xl`, 650). Below 600px, truncates with ellipsis.
- Right: status dot + label, theme toggle, settings button (mobile only).

**Status dot** — 8px circle plus 13px label:

| State | Dot | Label | Meaning |
|---|---|---|---|
| Ready | `--success` | API ready | Key present; the app is running |
| Degraded | `--warning` | API unreachable | Editing and preview still work |
| Error | `--error` | Configuration error | Key missing or rejected |

### 8.2 Sidebar — dictionaries

- Section title "Dictionaries" (`--text-xs`, uppercase, `--text-secondary`, letter-spacing 0.02em).
- List items: 40px min height, 8px padding, 6px radius. Active item: `--accent-subtle` background, `--accent` left border 3px, text weight 600.
- Each item shows the name and a right-aligned rule count (`--text-xs`, `--text-muted`).
- Hover: `--surface-alt` background. Focus-visible: 2px `--focus-ring` ring, 2px offset.
- Overflow menu (⋮) per item: Rename, Delete. Appears on hover on desktop, always visible on touch.
- "+ New dictionary" as a ghost button at the bottom of the list.

**Inline create form:** an input with 6px radius plus Save/Cancel buttons appearing in place. Inline validation message below in `--error` at `--text-xs`. Autofocus on open. Enter submits, Escape cancels.

### 8.3 Sidebar — settings

- Three rows: Model, Voice, Language, plus Speed as a read-only row.
- Model and Voice are native `<select>` elements styled with `--surface`, 1px `--border`, 6px radius, 36px height.
- Language and Speed render as read-only text with a lock icon and a tooltip-free caption: "Fixed for this release".
- Disabled during Busy state, with `--text-muted` and a caption "Locked while generating".

### 8.4 Sidebar — limitation note

Permanent, non-dismissible, `--surface-alt` background, 6px radius, 12px padding, `--text-xs`, `--text-secondary`:

> **This is text substitution, not phoneme control.** Your replacement text is what Timbre receives. The original wording is kept only for display.

This is a designed honesty element (PRD US-09), not a disclaimer buried in a README.

### 8.5 Script editor

- `<textarea>`, full width, min-height 140px, `--font-sans` at 16/1.65, `--surface`, 1px `--border`, 8px radius, 14px padding.
- Resizes vertically only.
- Focus-within: `--border-strong` border plus a 2px `--focus-ring` ring.
- Below it, a row: character counter on the right, limit message on the left when applicable.

**Character counter states:**

| Range | Colour | Text |
|---|---|---|
| ≤800 | `--text-muted` | `412 / 800 characters` |
| 800–2000 | `--warning` | `1,240 characters — long scripts take longer to generate` |
| >2000 | `--error` | `2,140 characters — over the 2,000 limit. Shorten the script.` |

- The counter uses a tabular-nums font feature so it does not jitter while typing.
- Generate is disabled in the >2000 state, with the reason visible.

### 8.6 Rule table (desktop and laptop)

| Column | Width | Content |
|---|---|---|
| Source term | 28% | Editable text input |
| Replacement | 28% | Editable text input, `--font-mono` |
| Matches | 12% | Badge: count, or "0" in muted with a warning dot |
| Actions | 32% | Save / Cancel (when dirty), Delete |

- Header row: `--surface-alt`, `--text-xs`, uppercase, `--text-secondary`.
- Row height 48px minimum; 56px when editing (to accommodate validation text).
- A row in edit mode shows its Save/Cancel inline; a clean row shows only Delete and a subtle Edit affordance on hover.
- **Zero-match rows** show a `--warning` dot next to the count with the caption "term not found in script".
- **Invalid rows** (empty field, duplicate source) get a `--error` left border and a message below the input; Save is disabled.
- **Markup warning** (`<` or `>` present): `--warning` message, Save still enabled.

**Mobile card layout:** see §7.2.

### 8.7 Preview panel

Two panes, side by side at ≥900px, toggled below.

| Pane | Label | Typography | Background |
|---|---|---|---|
| Left | `ORIGINAL — kept for reference` | Sans 16/1.65 | `--surface` |
| Right | `TRANSFORMED — sent to Timbre` | Mono 15/1.7 | `--surface` |

- Labels are `--text-xs`, uppercase, `--text-secondary`. The right label is the load-bearing honesty element and must never be shortened to "Result".
- Panes have equal width, 20px padding, 1px border, 8px radius, and `white-space: pre-wrap` so line breaks in the script are preserved.
- Max line length 78 characters.

**Diff span styling:**

```css
.diff {
  background: var(--diff-bg);
  border-bottom: 1px dashed var(--diff-border);
  border-radius: 3px;
  padding: 0 2px;
}
```

- Applied only to substituted spans, not to the whole pane.
- On hover, a `title` attribute shows `original → replacement`. No custom tooltip; the native one is accessible and costs nothing.
- Below 600px, hover is unavailable, so the match report carries the mapping instead.

**Match report** (below the panes):

- A compact list, one row per rule that matched: `source → replacement` in mono, then `×3` count.
- Zero-match rules listed below under "Not found in this script" in `--text-muted`.
- If nothing matched, the report is replaced by a single line: "No rules matched. Nothing would change." — and Generate is disabled.

### 8.8 Generate control

- Primary button, `--accent` fill, `--accent-text` label, 40px height, 8px radius, 16px horizontal padding.
- Label: **"Generate comparison"**.
- Disabled states, each with the reason rendered adjacent in `--text-xs`:

| Condition | Label | Reason shown |
|---|---|---|
| No rules matched | Generate comparison | No rules matched — nothing to compare |
| Over limit | Generate comparison | Script is over the 2,000 character limit |
| Busy | Generating… | Spinner + `1 of 2` progress |
| Ready | Generate comparison | — |

- During Busy, a determinate progress line under the button reads "Generating original…" then "Generating adjusted…". No indeterminate spinner alone; the user should know which half is running.

### 8.9 Audio panel

- Two blocks, stacked below 900px and side by side above.
- Each block: label ("Original" / "Adjusted"), native `<audio controls>` at full width, and the settings echo below.
- **Settings echo** (`--text-xs`, `--text-muted`): `timbre-v3.0 · Lakshmi · en-IN · 1.0×`. Identical text under both blocks, so a viewer can see the comparison was fair.
- Before generation, blocks show a placeholder: dashed 1px border, 72px height, centred muted text "Not generated yet".
- After a settings change, blocks reset to the placeholder with the caption "Settings changed — regenerate to compare".

### 8.10 Error banner

- Full width of the main column, `--error-bg` background, 1px `--error` border, 8px radius, 14px padding.
- Structure: bold one-line cause, then a plain-language explanation, then the HTTP status and upstream `error.type` in `--text-xs` mono, then a dismiss × on the right.
- **Never auto-dismisses.**
- **Never replaces existing results.** It appears above them.
- Example:

> **API key rejected**
> Timbre did not accept the key in your `.env`. Check that it was copied in full, then restart the backend.
> `401 · FORBIDDEN`

### 8.11 Confirm dialog

- Used only for delete actions. 6px radius, `--surface`, single elevation shadow, max-width 420px, centred, `--bg` scrim at 40% opacity.
- Title names the object: "Delete 'My Brand'?" Body states the consequence: "This removes 4 rules. It cannot be undone."
- Actions: "Cancel" (ghost) and "Delete" (`--error` fill). Focus trapped; Escape cancels; focus returns to the trigger on close.

### 8.12 Empty and loading states

| State | Appearance |
|---|---|
| No dictionaries | Centred in main column: muted heading "No dictionaries yet", one sentence, primary "Create a dictionary" button |
| Loading dictionaries | Three skeleton rows in sidebar at 60% opacity, `--surface-alt` fill, no shimmer animation |
| Transform in flight | Preview panes retain the previous text at 70% opacity with a 2px top progress line |
| Audio not generated | Dashed placeholder block (§8.9) |

---

## 9. Theming

> **Superseded for this release.** No theme toggle, no `[data-theme]` attribute,
> no `localStorage` preference. Streamlit owns its own theming and dark mode is
> dropped (§16.1). Read for intent only.

### 9.1 Implementation

```html
<html data-theme="light">   <!-- or "dark" -->
```

- Toggle button in the header, 36×36px, icon-only, `aria-label="Switch to dark theme"` / `"Switch to light theme"`.
- Preference persisted to `localStorage` under `theme` — **not shipped**; the UI is Streamlit (§16.1).
- On first load, if no stored preference, use `prefers-color-scheme` to choose the initial value, then persist it on first toggle.
- The `data-theme` attribute is set on `<html>` **before first paint** via a tiny inline script in `index.html`, preventing a flash of the wrong theme.
- All colours come from tokens; a component with a literal hex value fails review.

### 9.2 Theme rules

1. **Both themes are first-class.** Every screenshot in the README and every state in the checklist is verified in both.
2. **Dark mode is not an inversion.** Surfaces are near-black with a green cast to match the teal accent, not pure `#000`.
3. **The diff tint must remain distinguishable in both themes.** This is verified visually, not by calculation alone.
4. **Native `<audio>` controls** follow the OS/browser theme and are not restyled. Accepted inconsistency; a custom player is out of scope.
5. **No image or icon assets are theme-specific.** Icons use `currentColor`.

---

## 10. Motion

| Interaction | Duration | Easing |
|---|---|---|
| Hover, focus | 120ms | `ease-out` |
| Panel expand, inline form reveal | 180ms | `ease-out` |
| Drawer open/close | 220ms | `cubic-bezier(0.2, 0, 0, 1)` |
| Progress line | 240ms | `ease-in-out` |

**Rules**

- Nothing animates on page load. No entrance animations, no staggered reveals.
- No animation on the diff spans; they appear as static tint.
- `@media (prefers-reduced-motion: reduce)` sets all durations to `0ms`.
- No looping animations except the Busy progress line, which stops when the request completes.

---

## 11. Microcopy

Copy is part of the design. These strings are canonical; the implementation must not paraphrase them.

| Location | String |
|---|---|
| App title | Timbre Pronunciation Studio |
| Primary action | Generate comparison |
| Busy | Generating original… / Generating adjusted… |
| No-op guard | No rules matched — nothing to compare |
| Transformed pane label | TRANSFORMED — sent to Timbre |
| Original pane label | ORIGINAL — kept for reference |
| Limitation note | This is text substitution, not phoneme control. Your replacement text is what Timbre receives. The original wording is kept only for display. |
| Seed label | Sample — verified in the Gate B listening test; replace with your own terms |
| Zero-match caption | term not found in script |
| Markup warning | Timbre strips angle-bracket markup, so this replacement may not be spoken as written. |
| Settings changed | Settings changed — regenerate to compare |
| Empty audio | Not generated yet |
| Missing key (startup) | GNANI_API_KEY is not set. Add it to backend/.env and restart. |
| 403 banner | **Permission or credits** / Timbre refused the request. Check your key's permissions and remaining credits in the Gnani dashboard. |
| 429 banner | **Rate limited** / Too many requests. Wait a moment, then generate again. |
| 502/503 banner | **Timbre unavailable** / The speech service is temporarily unavailable. Try again shortly. |
| 504 banner | **Request timed out** / The script may be too long. Shorten it, or try again. |
| Degraded mode | **API unreachable** / Editing and preview still work. Generation is unavailable. |

**Voice and tone:** plain, specific, never apologetic, never cute. No exclamation marks. No "Oops". Every error names a cause and a next action.

---

## 12. Accessibility

### 12.1 Contrast requirements

| Pair | Minimum ratio |
|---|---|
| `--text` on `--bg` / `--surface` | 7:1 (AAA for body) |
| `--text-secondary` on `--surface` | 4.5:1 |
| `--text-muted` on `--surface` | 4.5:1 for text; 3:1 for non-text |
| `--accent-text` on `--accent` | 4.5:1 |
| `--diff-border` on `--diff-bg` | 3:1 (non-text, but must be perceivable) |
| Focus ring against adjacent surface | 3:1 |

Both themes are measured. A token that fails is changed, not waived.

### 12.2 Keyboard operation

| Key | Action |
|---|---|
| `Tab` / `Shift+Tab` | Move through controls in visual order |
| `Enter` | Submit inline form; activate focused button |
| `Escape` | Cancel inline edit; close dialog or drawer |
| `Space` | Toggle theme button, native audio play |
| `Arrow keys` | Native select navigation |

- Focus order follows visual order: sidebar → script → rules → preview → audio.
- Focus is never trapped except in the confirm dialog.
- A visible focus ring (2px, 2px offset) appears on `:focus-visible` only.

### 12.3 Screen reader support

| Element | Requirement |
|---|---|
| Panels | `<section aria-labelledby>` with a real heading |
| Script textarea | `<label>` with visible text, not placeholder-only |
| Rule inputs | `aria-label` combining row position and column: "Rule 2 source term" |
| Match count | `aria-label="Matched 3 times"` |
| Error banner | `role="alert"` so it is announced on appearance |
| Generation progress | `aria-live="polite"` region announcing "Generating original" then "Generating adjusted" |
| Diff spans | `<span>` with `title`; the match report provides the same information as text |
| Theme toggle | `aria-label` states the action, not the state |
| Decorative icons | `aria-hidden="true"` |

### 12.4 Additional requirements

- Text is never conveyed by colour alone: zero-match uses a dot plus a caption; errors use an icon plus text.
- Zoom to 200% without horizontal scrolling at 1280px.
- `prefers-reduced-motion` honoured.
- No content behind hover-only interaction.
- Language declared as `en` on `<html>`.

---

## 13. Demo and recording considerations

The demo video is a scored deliverable (Demo Day Drop, Crowd Favourite). The UI is optimised for it:

| Consideration | Decision |
|---|---|
| Base type | 16px, so text survives video compression |
| Background | Off-white `#FAFAF8`, not pure white — reduces compression banding |
| Font weights | ≥400 only; no thin strokes |
| Diff visibility | Tinted background plus dashed underline, so the change reads even at low resolution |
| Settings echo | Visible under both players, so fairness is provable on screen |
| Panels | Ordered so one screen contains script, rule, diff and audio without scrolling at 1280×800 |
| Motion | None on load; the recording starts on a stable frame |
| Theme for recording | Light. Higher contrast under compression and matches the restrained direction. |
| Limitation note | Visible in the sidebar during the demo, not cut out |

**Target viewport for recording:** 1280×800 browser window, 100% zoom.

---

## 14. Iconography and assets

| Item | Decision |
|---|---|
| Icon set | Inline SVG, 16px and 20px, 1.5px stroke, `currentColor` |
| Required icons | Plus, edit (pencil), trash, overflow (⋮), chevron, sun, moon, alert-triangle, check, lock, spinner |
| Icon source | Hand-authored minimal SVG paths, committed inline. No icon-font dependency. |
| Logos | None. No Gnani logo is used; the app is an independent project. |
| Illustrations | None. |

**Rationale for no Gnani logo:** the project is not an official Gnani product, and using their mark would imply endorsement. The README and demo state the relationship accurately instead.

---

## 15. Acceptance checklist

**Scope note (22 October 2026):** the custom visual system in §4–§13 was dropped
with the React plan (`TRD` §12). §16.1 lists what the Streamlit build actually
ships. Items below that depend on the dropped system — the token/theme pass, the
responsive breakpoints, the mobile card list and the preview toggle — are kept
for the record and must **not** be ticked.

### 15.1 Visual

- [ ] Every colour comes from a token; no literal hex in components.
- [ ] Both themes verified on every screen and every state.
- [ ] Diff tint appears only in the transformed preview.
- [ ] No shadows except the drawer and confirm dialog.
- [ ] No animation on page load.
- [ ] Base text is 16px; no weight below 400.

### 15.2 Responsive

What is still checked:

- [ ] At 1024px and 1280px the sidebar and main column render without overlap or clipping.
- [ ] The rule table scrolls horizontally rather than breaking the page.
- [ ] The limitation note is visible at every width the app is viewed at.

Dropped with the React plan — do not tick: the 390/768/820px layout checks, the
mobile card list, the preview toggle, the 44px touch target rule and the tablet
top bar.

### 15.3 Accessibility

- [ ] Contrast measured in both themes against §12.1.
- [ ] Full workflow completes using keyboard only.
- [ ] Focus ring visible on every interactive element.
- [ ] Error banner announces via `role="alert"`.
- [ ] Generation progress announced via `aria-live`.
- [ ] 200% zoom at 1280px without horizontal scroll.
- [ ] `prefers-reduced-motion` disables all transitions.

### 15.4 State coverage

- [ ] All six states defined for every interactive component.
- [ ] Empty, loading, no-op, busy, error and degraded states each rendered and checked.
- [ ] Error banner never auto-dismisses and never removes results.
- [ ] Generate disabled reasons match §8.8 exactly.

### 15.5 Copy

- [ ] All §11 strings used verbatim.
- [ ] No exclamation marks, no "Oops", no apology language.
- [ ] Transformed pane label reads exactly "TRANSFORMED — sent to Timbre".

---

## 16. Amendments to the TRD

**Superseded 21 October 2026 by the Streamlit decision** (`TRD` §12). This
section used to require three TRD amendments before freeze. Streamlit cannot
deliver them, so none was made and the TRD stands as written:

| TRD item | Was | Now |
|---|---|---|
| NFR-09 | "Latest Chrome and Edge on Windows" | **Unchanged.** The wider browser matrix and the four-width layout verification belong to the dropped custom layout. The app is one Streamlit page, checked at desktop width (`TRD` §12.5). |
| NFR-11 Responsive | — | **Not adopted.** No horizontal-scroll guarantee and no mobile card layout (dropped below). |
| NFR-12 Theming | — | **Not adopted.** No dark-mode toggle ships. |
| NFR-04 | Bundle ≤500 KB gzipped | **Not applicable.** Streamlit ships no bundle and no build step; `TRD` §14 records this as N/A. |

### 16.1 Streamlit scope — what ships and what does not

**Reading order — binding precedence for anyone building the UI.** This document
was written for the React layout that was dropped on 21 October 2026. When two
documents disagree, resolve in this order and do not reopen the question:

| Rank | Source | Authority |
|---|---|---|
| 1 | `docs/App Flow.md` | Behaviour, screen model, states, flows, guardrails. Written **for** Streamlit (rewritten 22 Oct 2026) and the only doc that describes what the framework actually does |
| 2 | `docs/UI-UX Brief.md` §11 | Canonical microcopy. Use the strings verbatim, never paraphrase |
| 3 | `docs/UI-UX Brief.md` §16.1 (this table) | What is dropped. Absence here is final |
| 4 | `docs/UI-UX Brief.md` §4–§13 | Historical design record. Read for intent (restraint, one accent, honesty as UI, 16 px base type). **Never** as an implementation spec |

Anything in §7, §8 or §9 that Streamlit cannot do without `unsafe_allow_html` is
dropped by definition — `docs/TRD.md` §4.1 rejects that API on XSS grounds, and
no visual gain justifies reopening it.

The UI is Streamlit, decided 21 October 2026 (`TRD` §12). This brief still owns
the **behaviour** (states, wording, order of work) but the framework cannot
deliver all of the visual spec:

| Feature | Status |
|---|---|
| Dark mode toggle | Dropped — Streamlit theming is limited and version-dependent |
| Mobile rule cards | Dropped — the table renders as Streamlit's data editor |
| Exact visual direction (five-panel, 1280 px shell) | Approximated with a sidebar plus a main column |
| Diff tinting inside the transformed pane | Dropped — no safe way to tint substrings without `unsafe_allow_html` |
| Restoring the active dictionary and script after a refresh | Dropped — Streamlit has no browser storage (`TRD` §12.6) |

**Must survive anyway:** readable contrast and visible focus, the limitation
note, the canonical/transformed labels, the identical settings echo under both
players, and errors that state the HTTP status. These are the honesty and
fairness elements of the product, not decoration.

---

## 17. Open questions

| # | Question | Resolves by |
|---|---|---|
| U1 | Does the native `<audio>` control clash badly with the restrained palette in dark mode? | M7 visual check |
| U2 | Is a dashed underline sufficient to signal a substitution at low video resolution, or is a stronger treatment needed? | M9, reviewed on a phone screen |
| U3 | Does the mobile preview toggle lose the before/after impact that makes the demo work? | M9; if so, the demo is recorded at desktop width only |
| U4 | Is 78-character line length comfortable in the mono preview pane, or does it need to be narrower? | M7 |
| U5 | Does the inline create form in the sidebar feel cramped at 240px? | M7 |

---

## 18. Approval

Approved when both builders confirm:

- [ ] The restrained light-first direction with a teal accent is accepted.
- [ ] Full responsive scope, including mobile rule cards and the preview toggle, is accepted with its cost.
- [ ] Dark mode as a first-class theme with a persisted toggle is accepted.
- [ ] WCAG 2.1 AA is accepted as a commitment, with both themes measured.
- [ ] The canonical microcopy in §11 is accepted as non-negotiable.
- [ ] The dropped scope in §16.1 is accepted, and §16 is understood to record that no TRD amendment was made.
