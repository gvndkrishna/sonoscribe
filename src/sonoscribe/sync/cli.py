"""Talk to AWS, gcloud, and Azure CLIs already installed on this Mac."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

OBJECT_NAME = "sonoscribe-sync.json"
PROVIDERS = ("aws", "gcs", "azure")
_TIMEOUT = 45
_EXTRA_DIRS = (
    "/usr/local/bin",
    "/opt/homebrew/bin",
    "/usr/local/google-cloud-sdk/bin",
)


@dataclass(frozen=True)
class Destination:
    provider: str
    bucket: str
    prefix: str = ""
    account: str = ""
    project: str = ""


class SyncError(RuntimeError):
    def __init__(self, message: str, details: str = "", kind: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        self.kind = kind


_RAPID_BUCKET_MESSAGE = (
    "This Google Cloud bucket is Rapid (zonal). Those only accept a special write that gcloud can’t do from this Mac. "
    "Create a regular Standard bucket with location type Region — not Zone — and use that name."
)


def object_key(prefix: str) -> str:
    clean = prefix.strip().strip("/")
    return f"{clean}/{OBJECT_NAME}" if clean else OBJECT_NAME


def which(name: str) -> str | None:
    found = shutil.which(name, path=_search_path())
    return found


def probe_providers() -> dict[str, dict[str, object]]:
    return {
        "aws": _probe_aws(),
        "gcs": _probe_gcs(),
        "azure": _probe_azure(),
    }


def upload(destination: Destination, payload: bytes) -> None:
    _validate_destination(destination)
    with tempfile.TemporaryDirectory() as folder:
        local = Path(folder) / OBJECT_NAME
        local.write_bytes(payload)
        if destination.provider == "aws":
            _run(
                "aws",
                [_require("aws"), "s3", "cp", str(local), _s3_uri(destination)],
            )
            return
        if destination.provider == "gcs":
            _gcs_reject_rapid(destination)
            _run("gcs", _gcs_cp_args(destination, str(local), _gs_uri(destination)))
            return
        _run("azure", _azure_upload_args(destination, local))


def verify_destination(destination: Destination) -> bool:
    """Return True if a sync object already exists. Missing is OK; bad access is not."""
    _validate_destination(destination)
    if destination.provider == "gcs":
        _gcs_reject_rapid(destination)
    raw = download(destination)
    return raw is not None


def download(destination: Destination) -> bytes | None:
    _validate_destination(destination)
    with tempfile.TemporaryDirectory() as folder:
        local = Path(folder) / OBJECT_NAME
        try:
            if destination.provider == "aws":
                _run(
                    "aws",
                    [_require("aws"), "s3", "cp", _s3_uri(destination), str(local)],
                )
            elif destination.provider == "gcs":
                _run("gcs", _gcs_cp_args(destination, _gs_uri(destination), str(local)))
            else:
                _run("azure", _azure_download_args(destination, local))
        except SyncError as exc:
            if _is_missing(exc.details):
                return None
            raise
        if not local.is_file():
            return None
        return local.read_bytes()


def _validate_destination(destination: Destination) -> None:
    if destination.provider not in PROVIDERS:
        raise SyncError("Choose Amazon S3, Google Cloud, or Azure.")
    if not destination.bucket:
        raise SyncError("Add a bucket or container name.")
    if destination.provider == "azure" and not destination.account:
        raise SyncError("Azure also needs a storage account name.")


def _probe_aws() -> dict[str, object]:
    if not which("aws"):
        return _unavailable("The AWS CLI isn’t on this Mac, so S3 isn’t available.")
    return _available("Amazon S3")


def _probe_gcs() -> dict[str, object]:
    if which("gcloud") or which("gsutil"):
        return _available("Google Cloud Storage")
    return _unavailable("The Google Cloud CLI isn’t on this Mac, so this option isn’t available.")


def _probe_azure() -> dict[str, object]:
    if not which("az"):
        return _unavailable("The Azure CLI isn’t on this Mac, so this option isn’t available.")
    return _available("Azure Blob Storage")


def _available(label: str) -> dict[str, object]:
    return {"available": True, "label": label, "message": ""}


def _unavailable(message: str) -> dict[str, object]:
    return {"available": False, "label": "", "message": message}


def _require(name: str) -> str:
    path = which(name)
    if not path:
        raise SyncError(_unavailable_message(name))
    return path


def _unavailable_message(name: str) -> str:
    if name == "aws":
        return "The AWS CLI isn’t on this Mac, so S3 isn’t available."
    if name in {"gcloud", "gsutil"}:
        return "The Google Cloud CLI isn’t on this Mac, so this option isn’t available."
    return "The Azure CLI isn’t on this Mac, so this option isn’t available."


def _gcs_tool() -> tuple[str, list[str]]:
    gcloud = which("gcloud")
    if gcloud:
        return gcloud, ["storage", "cp"]
    gsutil = which("gsutil")
    if gsutil:
        return gsutil, ["cp"]
    raise SyncError(_unavailable_message("gcloud"))


def _gcs_reject_rapid(destination: Destination) -> None:
    info = _gcs_bucket_describe(destination)
    if info and _is_rapid_gcs_bucket(info):
        raise SyncError(_RAPID_BUCKET_MESSAGE)


def _is_rapid_gcs_bucket(info: dict[str, object]) -> bool:
    storage_class = str(info.get("default_storage_class") or info.get("storageClass") or "").upper()
    location_type = str(info.get("location_type") or info.get("locationType") or "").lower()
    return storage_class == "RAPID" or location_type == "zone"


def _gcs_bucket_describe(destination: Destination) -> dict[str, object] | None:
    gcloud = which("gcloud")
    if not gcloud:
        return None
    args = [gcloud]
    project = destination.project.strip()
    if project:
        args.extend(["--project", project])
    args.extend(["storage", "buckets", "describe", f"gs://{destination.bucket}", "--format=json"])
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _gcs_cp_args(destination: Destination, source: str, target: str) -> list[str]:
    tool, verb = _gcs_tool()
    project = destination.project.strip()
    if Path(tool).name == "gsutil":
        args = [tool]
        if project:
            args.extend(["-o", f"GSUtil:default_project_id={project}"])
        return [*args, *verb, source, target]
    args = [tool]
    if project:
        args.extend(["--project", project])
    return [*args, *verb, source, target]


def _s3_uri(destination: Destination) -> str:
    return f"s3://{destination.bucket}/{object_key(destination.prefix)}"


def _gs_uri(destination: Destination) -> str:
    return f"gs://{destination.bucket}/{object_key(destination.prefix)}"


def _azure_upload_args(destination: Destination, local: Path) -> list[str]:
    return [
        _require("az"),
        "storage",
        "blob",
        "upload",
        "--auth-mode",
        "login",
        "--account-name",
        destination.account,
        "--container-name",
        destination.bucket,
        "--name",
        object_key(destination.prefix),
        "--file",
        str(local),
        "--overwrite",
        "true",
    ]


def _azure_download_args(destination: Destination, local: Path) -> list[str]:
    return [
        _require("az"),
        "storage",
        "blob",
        "download",
        "--auth-mode",
        "login",
        "--account-name",
        destination.account,
        "--container-name",
        destination.bucket,
        "--name",
        object_key(destination.prefix),
        "--file",
        str(local),
    ]


def _run(provider: str, args: list[str]) -> None:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            check=False,
        )
    except FileNotFoundError as exc:
        raise SyncError(_unavailable_message(provider), str(exc)) from exc
    except subprocess.TimeoutExpired as exc:
        raise SyncError("The cloud CLI took too long. You can try again in a bit.", str(exc)) from exc
    except OSError as exc:
        raise SyncError("Couldn’t start the cloud CLI on this Mac.", str(exc)) from exc
    if result.returncode == 0:
        return
    details = ((result.stderr or result.stdout) or "").strip()
    message, kind = classify_error(provider, details)
    raise SyncError(message, details, kind)


LOGIN_COMMANDS = {
    "aws": ["aws", "sso", "login"],
    "gcs": ["gcloud", "auth", "login"],
    "azure": ["az", "login"],
}

_AUTH_MARKERS = (
    "unable to locate credentials",
    "no credentials",
    "not logged in",
    "please run",
    "please log in",
    "login required",
    "sso",
    "gcloud auth",
    "az login",
    "aws sso login",
    "reauthentication",
    "expiredtoken",
    "expired token",
    "invalid_grant",
    "refresh token",
    "unauthenticated",
    "could not find default credentials",
    "no active account",
)


def login_command(provider: str) -> list[str]:
    args = LOGIN_COMMANDS.get(provider)
    if not args:
        raise SyncError("Choose Amazon S3, Google Cloud, or Azure.")
    return list(args)


def open_login_terminal(command: list[str]) -> None:
    line = " ".join(command)
    escaped = line.replace("\\", "\\\\").replace('"', '\\"')
    try:
        result = subprocess.run(
            ["osascript", "-e", f'tell application "Terminal" to do script "{escaped}"'],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SyncError("Couldn’t open Terminal to sign in.", str(exc)) from exc
    if result.returncode != 0:
        details = ((result.stderr or result.stdout) or "").strip()
        raise SyncError("Couldn’t open Terminal to sign in.", details)


def classify_error(provider: str, details: str) -> tuple[str, str]:
    text = details.lower()
    label = {"aws": "AWS", "gcs": "Google Cloud", "azure": "Azure"}.get(provider, "the cloud")
    if any(part in text for part in _AUTH_MARKERS):
        return f"{label} is here, but it isn’t signed in. Sign in from Terminal, then try again.", "auth"
    if any(part in text for part in ("access denied", "forbidden", "notauthorized", "authorizationfailed", "403")):
        return "This Mac can reach the bucket, but it doesn’t have permission to write there.", "permission"
    if "appendable object" in text:
        return _RAPID_BUCKET_MESSAGE, "rapid"
    if _is_missing(details):
        return "That bucket or path wasn’t found. Check the name and try again.", "missing"
    if "command not found" in text:
        return _unavailable_message(provider), "unavailable"
    return f"Couldn’t sync with {label} just now. You can try again in a bit.", ""


def friendly_error(provider: str, details: str) -> str:
    message, _kind = classify_error(provider, details)
    return message


def _is_missing(details: str) -> bool:
    text = details.lower()
    return any(
        part in text
        for part in (
            "nosuchbucket",
            "nosuchkey",
            "not found",
            "blobnotfound",
            "containernotfound",
            "404",
            "does not exist",
            "nomatch",
            "matched no objects",
            "matched no object",
            "one or more urls matched no objects",
        )
    )


def _search_path() -> str:
    extras = [str(Path.home() / "bin"), str(Path.home() / "google-cloud-sdk" / "bin"), *_EXTRA_DIRS]
    current = os.environ.get("PATH", "")
    parts = [item for item in extras if item]
    if current:
        parts.append(current)
    return os.pathsep.join(parts)
