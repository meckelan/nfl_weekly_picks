"""Logging in to the pool site and pulling down the week's sheet.

The login form is *discovered* rather than hardcoded: the client loads the
login page, finds the form that contains a password input, and reposts every
field that form declares (including hidden CSRF tokens) with the credentials
filled in. A pool site that renames its fields, or adds a token, keeps working.

Credentials come from the environment, never from the repo:

    POOLHOST_URL       the pool's picks page, e.g. https://www.poolhost.com/...
    POOLHOST_USERNAME
    POOLHOST_PASSWORD
    POOLHOST_LOGIN_URL optional, if the login page is not the picks page

Every fetch archives the raw HTML under data/pool/html/. That archive is the
evidence of what the pool's line actually was at pick time, which is the whole
basis of the edge — worth keeping even when the parse succeeds.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[3]
HTML_ARCHIVE = ROOT / "data" / "pool" / "html"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

# Field names a pool site is likely to use, checked in order when the form
# does not make the username field obvious.
_USERNAME_HINTS = ("user", "email", "login", "name", "account", "member")
_PASSWORD_HINTS = ("pass", "pwd", "pin", "code")


class PoolAuthError(RuntimeError):
    """Login did not take."""


class PoolHostClient:
    def __init__(
        self,
        url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        login_url: str | None = None,
        timeout: int = 30,
    ):
        self.url = url or os.environ.get("POOLHOST_URL", "")
        self.username = username or os.environ.get("POOLHOST_USERNAME", "")
        self.password = password or os.environ.get("POOLHOST_PASSWORD", "")
        self.login_url = login_url or os.environ.get("POOLHOST_LOGIN_URL") or self.url
        self.timeout = timeout

        if not self.url:
            raise ValueError("set POOLHOST_URL (or pass url=) to the pool's picks page")

        import requests  # imported here so parsing works without the dependency

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    # ── login ────────────────────────────────────────────────────────────────
    def _find_login_form(self, html: str, page_url: str) -> tuple[str, str, dict]:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        for form in soup.find_all("form"):
            password_input = form.find("input", {"type": "password"})
            if password_input is None:
                continue

            fields: dict[str, str] = {}
            username_field = None
            for field in form.find_all(("input", "select", "textarea")):
                name = field.get("name")
                if not name:
                    continue
                kind = (field.get("type") or "text").lower()
                if kind in ("submit", "button", "image"):
                    continue
                fields[name] = field.get("value", "") or ""
                if kind in ("text", "email") and username_field is None:
                    username_field = name

            password_field = password_input.get("name")
            if username_field is None:
                username_field = next(
                    (n for n in fields if any(h in n.lower() for h in _USERNAME_HINTS)
                     and n != password_field),
                    None,
                )
            if username_field is None or password_field is None:
                continue

            fields[username_field] = self.username
            fields[password_field] = self.password
            action = urljoin(page_url, form.get("action") or page_url)
            return action, (form.get("method") or "post").lower(), fields

        raise PoolAuthError(
            f"no login form (no password input) found at {page_url}. "
            "If the pool page is public, skip login and fetch it directly."
        )

    def login(self) -> None:
        """Authenticate, following whatever form the login page declares."""
        if not self.password:
            raise PoolAuthError("POOLHOST_PASSWORD is not set")

        page = self.session.get(self.login_url, timeout=self.timeout)
        page.raise_for_status()

        action, method, fields = self._find_login_form(page.text, page.url)
        send = self.session.post if method == "post" else self.session.get
        response = send(action, data=fields, timeout=self.timeout, allow_redirects=True)
        response.raise_for_status()

        if self._looks_like_login_wall(response.text):
            raise PoolAuthError(
                "still on a login page after posting credentials — check "
                "POOLHOST_USERNAME / POOLHOST_PASSWORD"
            )

    @staticmethod
    def _looks_like_login_wall(html: str) -> bool:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        return soup.find("input", {"type": "password"}) is not None

    # ── fetching ─────────────────────────────────────────────────────────────
    def fetch(self, url: str | None = None, *, archive: bool = True) -> str:
        """Fetch a page, optionally archiving the raw HTML."""
        target = url or self.url
        response = self.session.get(target, timeout=self.timeout)
        response.raise_for_status()
        if archive:
            self.archive(response.text)
        return response.text

    @staticmethod
    def archive(html: str, directory: Path = HTML_ARCHIVE) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = directory / f"pool_{stamp}.html"
        path.write_text(html, encoding="utf-8")
        return path
