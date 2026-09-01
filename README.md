# Sonoscribe

Hold **Fn** (Globe) to dictate with on-device [mlx-whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) (OpenAI Whisper on Apple Silicon). Hold **Cmd** with Fn to run spoken commands. Release Fn to finish.

This is a **menu extra**: **Sonoscribe** appears in the menu bar. Click **Dashboard** for the local command library and stats, or **Quit**. No Dock icon. You can also run it from a terminal, or wrap the PyInstaller build as an unsigned **Sonoscribe.app** (no Apple Developer account).

## Requirements

- Apple Silicon Mac
- macOS 14 or later
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (`brew install uv`)

## Run from source

```bash
uv sync --extra dev
uv run sonoscribe
```

First launch downloads **whisper-large-v3-turbo** into `~/.cache/huggingface/hub` (hundreds of MB). Later launches reuse that cache — the binary does not re-download the weights. Whisper runs in a **child process** so MLX/Metal is never initialized after AppKit (that combination fails with “Encountered an error while initializing the extension”). Smaller models:

```bash
uv run sonoscribe --model small
uv run sonoscribe --model base
```

`--no-fillers` keeps the raw transcript. `--copy-only` copies instead of pasting.

## Permissions

Grant both or Fn-hold will no-op:

1. **Microphone**
2. **Accessibility** (so the process can see Fn globally and paste into other apps)

If you use `uv run`, add **Terminal** (or iTerm / Cursor) under Privacy & Security. If you use **Sonoscribe.app**, add **Sonoscribe** — those are different TCC identities.

System Settings → Keyboard → **Press Globe key to**: if holding Fn never starts listening, set this to **Do Nothing** so macOS does not steal the hold.

## Usage

1. Start `sonoscribe` (or open **Sonoscribe.app**) and wait for `Ready.` **Sonoscribe** appears in the menu bar.
2. Click a text field in Notes, Mail, a browser, etc.
3. Hold **Fn**, speak, release to paste. Hold **Cmd** as well while speaking a command.
4. Open **Dashboard** from the menu extra (`http://127.0.0.1:8741/`) to edit commands, routines, and see stats.
5. Click **Quit** in the menu extra to stop.

Short taps (&lt;250 ms) cancel. **Fn+Shift / Option / Control** and other keys (volume, Globe-E, letters) still cancel that take. **Cmd does not cancel** — it is command mode.

Spoken **punctuation** is dictation (Fn only): **period**, **comma**, **question mark**, **new line**, **new paragraph**, **slash**, **at sign**, **google dot com** (→ `google.com`). Hostnames stay lowercase so an address bar treats them as URLs. Saying **enter** with Fn only pastes the word “Enter”.

Spoken **commands** run only while **Fn and Cmd** are both held. The whole utterance must match a phrase (aliases allowed). Press Cmd mid-hold to paste what you already said, speak the command, release Cmd to run it, then keep dictating until you release Fn.

| Hold | You say | What happens |
|---|---|---|
| Fn | `google dot com` | Pastes `google.com` |
| Fn | `you may enter` | Pastes those words |
| Fn+Cmd | **enter** | Return (Keyboard command) |
| Fn, then Cmd | (after dictating a URL) **enter** | Pastes first, then Return |
| Fn+Cmd | **android** / **github android** | Opens the mapped repo (Website command) |
| Fn+Cmd | **routine work** | Runs the *work* routine |

Paste uses ⌘V plus a space/delete nudge so Return actually registers in Chrome/Safari.

### Commands and routines

Edit everything in the **Dashboard**. The file on disk is:

`~/Library/Application Support/Sonoscribe/library.json`

It is re-read on every Fn+Cmd take. Types:

- **Keyboard** — enter, backspace, delete last word, delete last sentence, scratch that (⌘Z)
- **Website** — spoken phrases open an `http(s)` URL
- **App** — phrases launch a macOS app (`open -a`)
- **File** — phrases open a file or folder
- **System** — mute, volume, media keys, lock, sleep, display sleep, screenshot

A phrase may be several words. It must not start with **routine**.

**Routines** are sequences of existing commands. Say **routine** plus the routine name (or an alias), for example **routine work**. Just **routine** does nothing. Each step has an optional delay in milliseconds *before* that step runs.

An older `routines.json` github map is migrated once into Website commands (`android`, `github android`, `git hub android`) and left on disk.

Stats (average WPM from pasted dictation, command operations, routine runs) live in `~/Library/Application Support/Sonoscribe/stats.json`.

Whisper is primed with the name **Sonoscribe**, and common mishearings (`sono scribe`, `sunoscribe`, …) are rewritten to **Sonoscribe**.

## Binary / app bundle

```bash
uv sync --extra dev
uv run pyinstaller sonoscribe.spec --noconfirm
open dist/Sonoscribe.app
```

This is an **onedir** build inside `dist/Sonoscribe.app` — MLX’s `.dylib` / `.metallib` files do not freeze reliably with `--onefile`. Weights are **not** baked in; they live in the Hugging Face cache and survive restarts.

**No Team ID, no Developer ID, no notarization.** You do not need an Apple Developer account. On Apple Silicon, PyInstaller still **ad-hoc** signs the Mach-O binaries so the kernel will run them. That is a local anonymous signature, not “signing with a team.” Do not `codesign` with a Developer ID unless you want hardened runtime + microphone entitlements.

The `.app` has no Dock icon. Click **Sonoscribe** in the menu bar for **Dashboard** or **Quit**. Finder launches have no terminal; logs go to `~/Library/Logs/Sonoscribe/sonoscribe.log`.

Gatekeeper: a local build is fine. If macOS blocks a copy you moved/downloaded, right-click the app → **Open**. Keep the app in a stable path (for example `/Applications`); unsigned TCC grants are tied to that bundle path.

Add **Sonoscribe** to Microphone and Accessibility (not Terminal).

TLS uses the **macOS Keychain** (so a Zscaler or other corporate root is trusted). If the first download still fails, export the proxy CA and point Python at it:

```bash
export SSL_CERT_FILE=/path/to/zscaler-root.pem
```

## Layout

| Path | Role |
| --- | --- |
| `src/sonoscribe/fn_monitor.py` | Fn hold / Cmd command-mode / cancel (Quartz tap) |
| `src/sonoscribe/recorder.py` | 16 kHz mono capture, live slice copy |
| `src/sonoscribe/transcriber.py` | mlx-whisper load + batch ASR |
| `src/sonoscribe/cleaner.py` | Filler / artifact cleanup, URL casing |
| `src/sonoscribe/commands.py` | Spoken punctuation and “dot com” |
| `src/sonoscribe/actions.py` | Keyboard action ids (enter, backspace, …) |
| `src/sonoscribe/catalog.py` | `library.json` — commands, aliases, routines |
| `src/sonoscribe/executor.py` | Run keyboard / website / app / file / system |
| `src/sonoscribe/audio_device.py` | Core Audio mute and volume |
| `src/sonoscribe/stats.py` | WPM and command counters |
| `src/sonoscribe/dashboard/` | Local dashboard (127.0.0.1:8741) |
| `src/sonoscribe/lexicon.py` | “Sonoscribe” name corrections |
| `src/sonoscribe/inserter.py` | ⌘V paste, Return, delete keys |
| `src/sonoscribe/runtime.py` | Frozen / `.app` detection, Finder log file |
| `sonoscribe.spec` | PyInstaller onedir → `Sonoscribe.app` |
