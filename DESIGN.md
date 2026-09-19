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
- `.glass-box` — dialogs, menus, and playground
- Write text into `.glass-copy`, never `innerHTML` on the glass root
- `html[data-reduce-motion="true"]` turns glass into `--glass-solid` and drops motion

## Layout

- Sticky masthead (~48px): wordmark left, icon views centered, find and gear right. A 4px square marks the active view. Labels overlay on hover. On small screens the bar is fixed at the bottom (six views + settings, no wordmark) with frost bleeding up.
- Masthead search filters the open library page, then other pages if that page is empty; overview searches the library as jump-rows, and recent activity keeps its own box.
- `overflow-x: clip` on the document
- Page heads: `.unit` (`01 / library`) then lowercase `h1`
- Primary actions: `.icon-btn`. Text actions: `.text-btn`
- Recent activity, commands, routines, vocab, briefs, and vocanotes paginate at 30 items. The page size is fixed.
- Overview charts pack into open holes. Drag a tile to the top or bottom of the viewport to scroll. Settings freezes page scroll. Arriving at the top does not open playground. After the page has rested there, a weighted overscroll slides the dashboard (navbar included) down and slowly reveals playground, with a cue to keep scrolling to open it. Command mode is off while it is open.

## Motion

Honor `data-reduce-motion`. Prefer CSS; keep transitions short. Playground snaps without the rubber-band when motion is reduced. No decorative animation on charts or meters. Nav icons play a short press motion. Refresh spins; plus marks turn. Buttons take the accent for a moment on press. Nav labels fade in below the icon on hover. The lock screen padlock stays still. On a successful PIN the shackle opens; the dashboard appears when that motion ends. Turning the lock off asks for the PIN. ss–meter counts scouts with commands, routines, and words. Mix uses those same lifetime totals. A follow-up does not add another scout to the meter; tokens and cost still record. Those totals live in stats and can sync; briefs do not. Spoken `scribe` saves a vocanote (note, to-do, and/or reminder). A title that starts with a verb is a to-do. A clock (including eight o'clock), tonight/tomorrow, Monday / next Monday / weekend / next week, a calendar date (that day at 8:00), or remind without a time (next 8 AM/PM) is a reminder. daily, everyday, every friday, weekdays, and weekends repeat; done or later rolls the next due, and delete stops the series. Scout can add, change, fetch, or delete commands, routines, vocab, and vocanotes; vocanotes ride library sync. If they asked Scout to add a reminder, it must write a vocanote and must not say it did unless it did. A deleted vocanote stays gone on live refresh and library sync. Scribe does not live-overwrite an open vocanote; library save from the dashboard does not write vocanotes. A due reminder hangs off the menu bar with the title until done (deletes) or later (keeps, no second nudge). Spoken `scout` starts a brief (`task` is a silent alias). The dashboard stays put. When the brief finishes, a notice hangs off the menu bar icon for five seconds, then stays as a menu item with a short cue sized to the answer; a click opens that brief's popup and clears the item, and opens a queued page if the brief saved one. Notice actions sit in one row: done and later, insert and dismiss, or run and cancel. A finished brief has no buttons. A run_script confirm grows to show the command unless it is large. Scripts and file writes wait for a yes. Insert is only for a spoken insert ask (`scout insert …`, or `and insert it` at the end). That bubble stays until they insert or dismiss; the brief has the same button. Saying “and insert it” pastes at the cursor without waiting. A command clip is padded so that first word is not dropped, and a leading scout does not steal a real command or routine. A short leftover before Cmd stays on the command so `scout` is not cut off. `open {*}` does not steal a long prompt. If no command or routine matches, command mode does nothing. The menu Dashboard item always opens or raises the page. Spoken `scout` focuses the open dashboard on the scout view. The dashboard loads the page you are on; refresh on overview reloads that page. Overview refreshes while that view is open. Briefs stay live while scout is open. The menu-bar scout notice is skipped when that page is already open. Only the latest dashboard tab stays unlocked; older tabs lock. A short presence ping keeps spoken scout able to focus the window. Briefs list a title plus a short answer; a short answer shows in full, and the complete brief opens in a glass popup. With the popup open, say `scout` and a follow-up. The popup stays open and shows the earlier answer, the follow-up, and the new answer. Close it to start a new brief. Titles come from the model and can be edited. Commands, routines, vocab, and briefs have select all for bulk delete. Briefs stay on this Mac; they are not synced. Done briefs drop after 10 days, errors after 1 day. Search and fetch run on their own. Weather, currency, time, news, prices, and stocks come from live sources (AccuWeather, Google, Bing, DuckDuckGo, and similar); weather uses a wttr.in place the model picks (Queens or Brooklyn, not a sentence), including on the last step after a screen capture. If that misses, the brief keeps a web search link and does not invent numbers. Empty general search still falls back to Wikipedia. Scripts and file writes wait for a yes. Screen capture is off until they turn it on under settings → scout; it waits for a yes unless they skip confirm. The loop is short (three rounds); the last step answers without tools unless weather still needs a place or they asked to save a vocanote. The first user message is stamped with how scout was invoked. Broken model JSON is repaired before a brief is shown. Briefs are numbered sc–01 from the latest, like commands. Say scout 0, scout -1, scout minus one, or scout 01 to continue that brief. open_page queues a site; the browser opens only when the notice is clicked. For a video, trailer, or clip, queue YouTube or the official platform they named. Scout API keys live under settings → scout, after a lock is set. A set key hides behind change api key. Each provider keeps its own model. Tools, confirm, context, MCP servers, and token/duration limits live on that page. Token and duration can be no limit. Auto-lock can be never. Scout token and cost graphs are extra overview charts; they are not on the board by default.
