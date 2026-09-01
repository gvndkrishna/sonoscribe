from __future__ import annotations

import argparse
import platform
import sys


def main(argv: list[str] | None = None) -> None:
    if sys.platform != "darwin":
        sys.exit("Sonoscribe requires macOS.")
    if platform.machine() != "arm64":
        sys.exit("Sonoscribe requires Apple Silicon (MLX).")

    parser = argparse.ArgumentParser(
        prog="sonoscribe",
        description="Hold Fn to dictate with on-device Whisper. Hold Cmd with Fn for commands.",
    )
    parser.add_argument(
        "--model",
        choices=["large-v3-turbo", "small", "base"],
        default="large-v3-turbo",
        help="mlx-whisper model (default: large-v3-turbo)",
    )
    parser.add_argument(
        "--no-fillers",
        action="store_true",
        help="Paste the raw Whisper transcript without stripping um/uh/you know/etc.",
    )
    parser.add_argument(
        "--copy-only",
        action="store_true",
        help="Copy the transcript instead of pasting into the focused app.",
    )
    parser.add_argument(
        "--worker",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)

    if args.worker:
        from sonoscribe.worker import run_worker

        raise SystemExit(run_worker(args.model))

    from sonoscribe.runtime import attach_log_if_needed

    log_path = attach_log_if_needed()
    if log_path is not None:
        print(f"Logging to {log_path}", flush=True)

    from sonoscribe.app import App

    raise SystemExit(
        App(
            model=args.model,
            remove_fillers=not args.no_fillers,
            copy_only=args.copy_only,
        ).run()
    )


if __name__ == "__main__":
    main()
