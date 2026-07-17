"""Cliente HTTP con scraping ético: robots.txt, rate limiting, UA identificable."""

import time
import urllib.robotparser
from urllib.parse import urlparse

import httpx

from .config import RATE_LIMIT_SECONDS, USER_AGENT


class EthicalClient:
    """Cliente HTTP que respeta robots.txt y aplica rate limiting por dominio."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        )
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._last_request: dict[str, float] = {}

    def _robots_for(self, url: str) -> urllib.robotparser.RobotFileParser:
        domain = urlparse(url).netloc
        if domain not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            robots_url = f"https://{domain}/robots.txt"
            try:
                resp = self._client.get(robots_url)
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                else:
                    rp.parse([])  # sin robots.txt → todo permitido
            except httpx.HTTPError:
                rp.parse([])
            self._robots[domain] = rp
        return self._robots[domain]

    def _throttle(self, url: str) -> None:
        domain = urlparse(url).netloc
        last = self._last_request.get(domain)
        if last is not None:
            elapsed = time.monotonic() - last
            if elapsed < RATE_LIMIT_SECONDS:
                time.sleep(RATE_LIMIT_SECONDS - elapsed)
        self._last_request[domain] = time.monotonic()

    def get(self, url: str) -> httpx.Response:
        if not self._robots_for(url).can_fetch(USER_AGENT, url):
            raise PermissionError(f"robots.txt no permite scrapear {url}")
        self._throttle(url)
        resp = self._client.get(url)
        resp.raise_for_status()
        return resp

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "EthicalClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
