"""Shared fixtures: a tiny fake site served from the saved HTML, and a crawled raw run."""

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from books_scraping.config import Settings
from books_scraping.fetch import crawl
from books_scraping.models import StepSummary

FIXTURES = Path(__file__).parent / "fixtures"
SITE = FIXTURES / "site"
BASE = "https://books.toscrape.com/"
A_LIGHT = "catalogue/a-light-in-the-attic_1000/index.html"
IN_HER_WAKE = "catalogue/in-her-wake_980/index.html"
NO_DESC = "catalogue/no-description_999/index.html"
RUN_ID = "20260101T000000Z"


def site_file(rel: str) -> bytes:
    return (SITE / rel).read_bytes()


def listing_html(links: list[str], next_link: str | None = None) -> bytes:
    pods = "".join(
        f'<article class="product_pod"><h3><a href="{link}">t</a></h3></article>' for link in links
    )
    nxt = f'<li class="next"><a href="{next_link}">next</a></li>' if next_link else ""
    return f"<html><body>{pods}<ul class='pager'>{nxt}</ul></body></html>".encode()


# Two listing pages (2 + 1 products) built from the saved product pages.
PAGES: dict[str, bytes] = {
    "/": listing_html([A_LIGHT, IN_HER_WAKE], "catalogue/page-2.html"),
    "/catalogue/page-2.html": listing_html(["no-description_999/index.html"]),
    "/" + A_LIGHT: site_file(A_LIGHT),
    "/" + IN_HER_WAKE: site_file(IN_HER_WAKE),
    "/" + NO_DESC: site_file(NO_DESC),
}


class FakeSite:
    """httpx.MockTransport handler; records the requested paths."""

    def __init__(
        self,
        robots: tuple[int, str] = (404, ""),
        pages: dict[str, bytes] | None = None,
        overrides: dict[str, Callable[[], httpx.Response]] | None = None,
    ) -> None:
        self.robots = robots
        self.pages = PAGES if pages is None else pages
        self.overrides = overrides or {}
        self.requests: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.requests.append(path)
        if path in self.overrides:
            return self.overrides[path]()
        if path == "/robots.txt":
            return httpx.Response(self.robots[0], text=self.robots[1])
        if path in self.pages:
            return httpx.Response(
                200, content=self.pages[path], headers={"content-type": "text/html"}
            )
        return httpx.Response(404)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data", min_interval_s=0.5, max_retries=3, _env_file=None)  # type: ignore[call-arg]


def crawl_site(
    settings: Settings, site: FakeSite | None = None, run_id: str = RUN_ID, **kwargs: int
) -> StepSummary:
    return crawl(
        settings,
        run_id=run_id,
        transport=(site or FakeSite()).transport,
        sleep=lambda _s: None,
        clock=lambda: 0.0,
        **kwargs,
    )


@pytest.fixture
def raw_run(settings: Settings) -> str:
    """A complete raw run with 3 distinct products."""
    assert crawl_site(settings).rows_out == 3
    return RUN_ID
