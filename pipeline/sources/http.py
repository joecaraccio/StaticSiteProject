"""A small, polite HTTP fetcher built on urllib.

Deliberately not `requests`/`httpx`: the pipeline downloads a handful of large
files per month, so the standard library is enough and keeps the dependency list
to DuckDB alone.

Politeness (a hard rule in CLAUDE.md): one request at a time, a delay between
requests, a descriptive User-Agent, and conditional GETs so an unchanged file is
never re-downloaded.
"""

from __future__ import annotations

import hashlib
import shutil
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from pipeline import config

_last_request_at = 0.0


def _throttle() -> None:
    global _last_request_at
    wait = config.DOWNLOAD_DELAY_SECONDS - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


class NotModified(Exception):
    """The server answered 304: the cached copy is still current."""


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]
    url: str


def _request(url: str, method: str, extra_headers: dict[str, str] | None = None):
    headers = {"User-Agent": config.USER_AGENT, "Accept": "*/*"}
    if extra_headers:
        headers.update(extra_headers)
    return urllib.request.Request(url, method=method, headers=headers)


def head(url: str) -> Response:
    """Probe a URL. Falls back to a ranged GET for servers that reject HEAD."""
    _throttle()
    try:
        with urllib.request.urlopen(
            _request(url, "HEAD"), timeout=config.DOWNLOAD_TIMEOUT_SECONDS
        ) as resp:
            return Response(resp.status, dict(resp.headers), resp.url)
    except urllib.error.HTTPError as exc:
        if exc.code not in (403, 405, 501):
            raise
    # Some hosts only answer GET. Ask for the first byte instead of the whole file.
    _throttle()
    with urllib.request.urlopen(
        _request(url, "GET", {"Range": "bytes=0-0"}), timeout=config.DOWNLOAD_TIMEOUT_SECONDS
    ) as resp:
        return Response(resp.status, dict(resp.headers), resp.url)


def download(
    url: str,
    dest: Path,
    *,
    etag: str | None = None,
    last_modified: str | None = None,
) -> Response:
    """Stream `url` to `dest`, atomically.

    Raises NotModified when the server confirms the cached copy is current, so
    the caller can keep the existing raw file untouched.
    """
    conditional: dict[str, str] = {}
    if etag:
        conditional["If-None-Match"] = etag
    if last_modified:
        conditional["If-Modified-Since"] = last_modified

    _throttle()
    tmp = dest.with_suffix(dest.suffix + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with (
            urllib.request.urlopen(
                _request(url, "GET", conditional), timeout=config.DOWNLOAD_TIMEOUT_SECONDS
            ) as resp,
            tmp.open("wb") as out,
        ):
            shutil.copyfileobj(resp, out, length=1024 * 1024)
            response = Response(resp.status, dict(resp.headers), resp.url)
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            raise NotModified(url) from exc
        tmp.unlink(missing_ok=True)
        raise
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise

    tmp.replace(dest)
    return response


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
