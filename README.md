# Sonoscribe

Local speech-to-text for Apple Silicon Macs. Hold **Fn** to dictate with on-device Whisper. Hold **Fn+⌘** to run a command.

## Install

Download `Sonoscribe-macos-arm64.zip` from [Releases](https://github.com/gvndkrishna/sonoscribe/releases). Unzip, move `Sonoscribe.app` to `/Applications`, then open it.

If macOS blocks the first launch, right-click the app and choose **Open**.

Grant **Microphone** and **Accessibility** to Sonoscribe. If holding Fn never starts listening, set **System Settings → Keyboard → Press Globe key to** to **Do Nothing**.

The first launch downloads the Whisper model into `~/.cache/huggingface/hub`. Later launches reuse it.

## Use

Sonoscribe lives in the menu bar (no Dock icon).

1. Click a text field.
2. Hold **Fn**, speak, release to paste.
3. Hold **Fn+⌘** to run a command or routine.
4. Open **Dashboard** from the menu extra to edit the library.

## Build from source

Requires macOS 14+, Apple Silicon, Python 3.11+, and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/gvndkrishna/sonoscribe.git
cd sonoscribe
uv sync --extra dev
uv run sonoscribe
```

```bash
uv run pytest
uv run pyinstaller sonoscribe.spec --noconfirm
open dist/Sonoscribe.app
```

A source run is a different TCC identity than `Sonoscribe.app`. Grant permissions to whichever you launched.

## Contributing

See the [wiki](https://github.com/gvndkrishna/sonoscribe/wiki), [CONTRIBUTING.md](CONTRIBUTING.md), and [DESIGN.md](DESIGN.md).

## License

[GPL-3.0-only](LICENSE). If you distribute a product that includes this code, that entire product must be open source under GPL-3.0-only, including further derivatives.
