# Design

Dashboard UI. Tokens and components live in `src/sonoscribe/dashboard/static/styles.css`.

## Type

- `--font`: Helvetica Neue, weight 300
- `--mono`: SF Mono, for `<kbd>` and IDs
- Sentence case is not used. Labels, nav, headings, and placeholders are lowercase
- Wide letter-spacing on the wordmark (`0.22em`); tighter on body (`0.01em`–`0.04em`)

## Color

Use CSS variables. Do not introduce one-off hex in new UI.

| Token | Role |
| --- | --- |
| `--ink` / `--muted` | Text |
| `--canvas` / `--panel` | Page / raised surface |
| `--line` / `--hairline` / `--stroke` | Rules |
| `--accent` / `--accent-ink` | User accent (amber default) |
| `--status-on` / `--status-off` / `--status-wait` | Status, muted not traffic-light |
| `--type-*` | Command type marks |

Themes: `html[data-theme="light"|"dark"]`. Accents: `html[data-accent]`. Check both themes.

## Shape

`--radius` is `0`. No pills, no rounded cards, no drop shadows as decoration.

## Glass

`.glass` is for overlays only: masthead, `<dialog>`, menus, toasts, tips.

```html
<div class="glass glass-box">
  <div class="glass-fill" aria-hidden="true"></div>
  <div class="glass-copy">…</div>
</div>
```

- `.glass-down` — sticky masthead (blur bleeds below)
- `.glass-box` — dialogs and menus
- Write text into `.glass-copy`, never `innerHTML` on the glass root
- `html[data-reduce-motion="true"]` turns glass into `--glass-solid` and drops motion

## Layout

- Sticky masthead, `overflow-x: clip` on the document
- Page heads: `.unit` (`01 / library`) then lowercase `h1`
- Primary actions: `.icon-btn`. Text actions: `.text-btn`
- Filters and nav are unstyled text, active = ink + underline

## Motion

Honor `data-reduce-motion`. Prefer CSS; keep transitions short. No decorative animation on charts or meters.
