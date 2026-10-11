"""Optional, bounded GitHub metadata lookup. No assets are downloaded or executed."""
import json
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from functools import total_ordering
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, unquote
from urllib.request import Request, build_opener, HTTPRedirectHandler

API_URL = "https://api.github.com/repos/jarrnz/BloxBinds/releases?per_page=100"


@total_ordering
@dataclass(frozen=True)
class Version:
    numbers: tuple[int, int, int]
    prerelease: tuple[str, ...] = ()

    @classmethod
    def parse(cls, value):
        if not isinstance(value, str):
            raise ValueError("Invalid version.")
        match = re.fullmatch(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?", value)
        if not match:
            raise ValueError("Invalid semantic version.")
        pre = tuple(match[4].split(".")) if match[4] else ()
        if any(not p or (p.isdigit() and len(p) > 1 and p.startswith("0")) for p in pre):
            raise ValueError("Invalid prerelease version.")
        return cls(tuple(map(int, match.group(1, 2, 3))), pre)

    def __lt__(self, other):
        if self.numbers != other.numbers:
            return self.numbers < other.numbers
        if not self.prerelease or not other.prerelease:
            return bool(self.prerelease) and not other.prerelease
        for a, b in zip(self.prerelease, other.prerelease):
            if a == b:
                continue
            if a.isdigit() and b.isdigit():
                return int(a) < int(b)
            if a.isdigit() != b.isdigit():
                return a.isdigit()
            return a < b
        return len(self.prerelease) < len(other.prerelease)


def valid_release_url(value):
    if not isinstance(value, str) or any(ord(c) <= 32 for c in value):
        return False
    try:
        url = urlsplit(value)
    except ValueError:
        return False
    prefix = "/jarrnz/BloxBinds/releases/tag/"
    path = unquote(url.path)
    return (url.scheme == "https" and url.netloc == "github.com" and not url.query and not url.fragment
            and path.startswith(prefix) and bool(path[len(prefix):]) and
            not any(p in (".", "..") for p in path.split("/")) and "\\" not in path)


@dataclass(frozen=True)
class UpdateResult:
    message: str
    url: str | None = None


def select_release(data, current):
    if not isinstance(data, list):
        raise ValueError("Malformed release response.")
    candidates = []
    for release in data:
        if not isinstance(release, dict) or release.get("draft") is not False or type(release.get("prerelease")) is not bool:
            continue
        try:
            version = Version.parse(release.get("tag_name"))
        except ValueError:
            continue
        if release["prerelease"] and not version.prerelease:
            version = Version(version.numbers, ("beta",))
        if version.prerelease and not current.prerelease:
            continue
        if valid_release_url(release.get("html_url")):
            candidates.append((version, release))
    if not candidates:
        return UpdateResult("No applicable releases available.")
    version, release = max(candidates, key=lambda item: item[0])
    if version <= current:
        return UpdateResult("You're up to date.")
    date = ""
    try:
        date = " — " + datetime.fromisoformat(release.get("published_at", "").replace("Z", "+00:00")).date().isoformat()
    except (ValueError, TypeError, AttributeError):
        pass
    return UpdateResult(f"Update available: {release['tag_name']}{date}", release["html_url"])


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise URLError("Release API redirects are not accepted.")


def check_updates(current, opener=None):
    try:
        request = Request(API_URL, headers={"Accept": "application/vnd.github+json", "User-Agent": "BloxBinds-update-checker",
                                            "X-GitHub-Api-Version": "2022-11-28"})
        with (opener or build_opener(NoRedirects()).open)(request, timeout=8) as response:
            if response.geturl() != API_URL:
                raise ValueError("Unexpected release API URL.")
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise ValueError("Release response too large.")
        return select_release(json.loads(raw), current)
    except HTTPError as error:
        return UpdateResult("GitHub rate limit or access restriction; try later." if error.code in (403, 429)
                            else "GitHub releases unavailable; try later.")
    except (TimeoutError, URLError, OSError):
        return UpdateResult("Could not check updates: offline or request timed out.")
    except (ValueError, TypeError):
        return UpdateResult("Could not check updates: invalid release response.")


class UpdateChecker:
    def __init__(self, events, current):
        self.events, self.current = events, current
        self.thread = None
        self.closed = threading.Event()
        self.auto_checked = False

    def automatic(self, enabled):
        if enabled and not self.auto_checked:
            self.auto_checked = True
            return self.check()
        return False

    def check(self):
        if self.closed.is_set() or (self.thread and self.thread.is_alive()):
            return False
        def work():
            result = check_updates(self.current)
            if not self.closed.is_set():
                self.events.put(("update", result))
        self.thread = threading.Thread(target=work, name="BloxBinds-updates", daemon=True)
        self.thread.start()
        return True

    def close(self):
        self.closed.set()  # A pending bounded HTTP request may finish; it never touches Tk.
