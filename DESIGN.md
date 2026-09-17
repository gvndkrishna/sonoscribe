# Design

Dashboard UI. Tokens and components live in `src/sonoscribe/dashboard/static/styles.css`.

## Type

- `--font`: Helvetica Neue, weight 300
- `--mono`: SF Mono, for `<kbd>` and IDs
- Sentence case is not used. Labels, nav, headings, and placeholders are lowercase
- Wide letter-spacing on the wordmark (`0.22em`); tighter on body (`0.01em`–`0.04em`)

## Color

Use CSS variables. Do not introduce one-off hex in new UI.

Accent is a light, not a paint fill. `--accent` is the tube. `--light-core` is a slightly hotter filament. `--light-wash` is a short, dim throw. Illumination stays quiet: no neon bloom, no outer glow on buttons or chips.

| Token | Role |
| --- | --- |
| `--ink` / `--muted` | Text |
| `--canvas` / `--panel` | Page / raised surface |
| `--line` / `--hairline` / `--stroke` | Rules |
| `--accent` / `--accent-ink` | User accent (amber default) |
| `--light-core` / `--light-wash` | Emitter and falloff |
| `--status-on` / `--status-off` / `--status-wait` | Status lamps |
| `--type-*` | Command type marks |

Themes: `html[data-theme="light"|"dark"]`. Accents: `html[data-accent]`. Check both themes. Light uses muted gray surfaces.

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

- `.glass-down` — sticky masthead. Barely-there frost, strongest in the bar.
- `.glass-box` — dialogs and menus
- Write text into `.glass-copy`, never `innerHTML` on the glass root
- `html[data-reduce-motion="true"]` turns glass into `--glass-solid` and drops motion

## Layout

- Sticky masthead (~48px): wordmark left, icon views centered, gear right. A 4px square marks the active view. Labels overlay on hover. On small screens the bar is fixed at the bottom (four views + settings, no wordmark) with frost bleeding up.
- `overflow-x: clip` on the document
- Page heads: `.unit` (`01 / library`) then lowercase `h1`
- Primary actions: `.icon-btn`. Text actions: `.text-btn`
- Overview charts pack into open holes. Drag a tile to the top or bottom of the viewport to scroll. Settings freezes page scroll.

## Motion

Honor `data-reduce-motion`. Prefer CSS; keep transitions short. No decorative animation on charts or meters. Nav icons play a short press motion. Refresh spins; plus marks turn. Buttons take the accent for a moment on press. Nav labels fade in below the icon on hover. The lock screen padlock stays still. On a successful PIN the shackle opens; the dashboard appears when that motion ends.
