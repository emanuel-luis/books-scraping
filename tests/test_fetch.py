import hashlib
import json
from pathlib import Path

import httpx
import pytest
from conftest import A_LIGHT, IN_HER_WAKE, FakeSite, crawl_site

from books_scraping.config import Settings
from books_scraping.fetch import Fetcher, FetchError, crawl, url_to_relpath
from books_scraping.models import ManifestEntry


def manifest(settings: Settings, run_id: str = "20260101T000000Z") -> list[ManifestEntry]:
    path = settings.data_dir / "raw" / run_id / "manifest.jsonl"
    return [ManifestEntry.model_validate_json(x) for x in path.read_text("utf-8").splitlines()]


def test_full_crawl_writes_raw_layer(settings: Settings) -> None:
    summary = crawl_site(settings)
    run = settings.data_dir / "raw" / summary.run_id
    assert (summary.listing_pages, summary.product_pages, summary.failed) == (2, 3, 0)
    assert json.loads((run / "run.json").read_text("utf-8"))["step"] == "fetch"
    products = [e for e in manifest(settings) if e.kind == "product"]
    assert len(products) == 3
    for entry in products:
        assert entry.path is not None
        assert hashlib.sha256((run / entry.path).read_bytes()).hexdigest() == entry.sha256
    # saved exactly as received
    assert (run / "pages" / A_LIGHT).read_bytes() == (
        Path(__file__).parent / "fixtures/site" / A_LIGHT
    ).read_bytes()


def test_limit_stops_pagination_early(settings: Settings) -> None:
    site = FakeSite()
    summary = crawl_site(settings, site, limit=1)
    assert summary.product_pages == 1
    assert "/catalogue/page-2.html" not in site.requests


def test_max_pages(settings: Settings) -> None:
    site = FakeSite()
    summary = crawl_site(settings, site, max_pages=1)
    assert (summary.listing_pages, summary.product_pages) == (1, 2)
    assert "/catalogue/page-2.html" not in site.requests


def test_robots_disallow_skips_urls(settings: Settings) -> None:
    site = FakeSite(robots=(200, "User-agent: *\nDisallow: /catalogue/\n"))
    summary = crawl_site(settings, site)
    assert summary.status == "failed"
    assert summary.skipped_robots == 3  # page 2 and both products
    assert not any(p.endswith("index.html") for p in site.requests)


def test_robots_disallow_all_on_403(settings: Settings) -> None:
    site = FakeSite(robots=(403, ""))
    summary = crawl_site(settings, site)
    assert summary.skipped_robots == 1
    assert site.requests == ["/robots.txt"]


def test_missing_robots_allows_everything(settings: Settings) -> None:
    summary = crawl_site(settings, FakeSite(robots=(404, "")))
    assert summary.skipped_robots == 0 and summary.product_pages == 3


def test_robots_server_error_aborts(settings: Settings) -> None:
    with pytest.raises(FetchError, match="robots.txt answered 503"):
        crawl_site(settings, FakeSite(robots=(503, "")))


def test_robots_unreachable_aborts(settings: Settings) -> None:
    def boom(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(FetchError, match="unreachable"):
        crawl(settings, transport=httpx.MockTransport(boom), sleep=lambda _s: None)


def test_retry_then_success(settings: Settings) -> None:
    calls = {"n": 0}

    def flaky() -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, content=b"<html>ok</html>")

    site = FakeSite(overrides={"/" + IN_HER_WAKE: flaky})
    summary = crawl_site(settings, site)
    assert calls["n"] == 2
    assert summary.product_pages == 3 and summary.failed == 0


def test_persistent_failure_is_recorded_and_crawl_continues(settings: Settings) -> None:
    site = FakeSite(
        overrides={
            "/" + IN_HER_WAKE: lambda: httpx.Response(503),
            "/" + A_LIGHT: lambda: (_ for _ in ()).throw(httpx.ReadTimeout("slow")),
        }
    )
    summary = crawl_site(settings, site)
    assert (summary.product_pages, summary.failed, summary.rows_rejected) == (1, 2, 2)
    by_url = {e.url.rsplit("/", 2)[-2]: e for e in manifest(settings) if e.kind == "product"}
    assert by_url["in-her-wake_980"].status == 503 and by_url["in-her-wake_980"].path is None
    assert by_url["a-light-in-the-attic_1000"].status == 0
    assert site.requests.count("/" + IN_HER_WAKE) == 3  # max_retries attempts


def test_failed_first_listing_stops_crawl(settings: Settings) -> None:
    summary = crawl_site(settings, FakeSite(pages={}))
    assert summary.status == "failed" and summary.rows_in == 0


def test_rate_limiter_sleeps_the_interval(settings: Settings) -> None:
    sleeps: list[float] = []
    site = FakeSite()
    crawl(settings, run_id="r1", transport=site.transport, sleep=sleeps.append, clock=lambda: 0.0)
    assert sleeps == [0.5] * (len(site.requests) - 1)


def test_crawl_delay_raises_the_interval(settings: Settings) -> None:
    sleeps: list[float] = []
    site = FakeSite(robots=(200, "User-agent: *\nCrawl-delay: 2\n"))
    crawl(settings, run_id="r1", transport=site.transport, sleep=sleeps.append, clock=lambda: 0.0)
    assert set(sleeps) == {2.0}


def test_interval_already_elapsed_does_not_sleep(settings: Settings) -> None:
    sleeps: list[float] = []
    ticks = iter(range(0, 1000, 10))
    with Fetcher(
        settings, transport=FakeSite().transport, sleep=sleeps.append, clock=lambda: next(ticks)
    ) as fetcher:
        fetcher.get("https://books.toscrape.com/")
        fetcher.get("https://books.toscrape.com/")
    assert sleeps == []


def test_existing_run_dir_is_refused(settings: Settings) -> None:
    crawl_site(settings)
    with pytest.raises(FetchError, match="already exists"):
        crawl_site(settings)


def test_other_hosts_are_skipped(settings: Settings) -> None:
    pages = {
        "/": b'<article class="product_pod"><h3><a href="https://evil.example/x">t</a></h3></article>'
    }
    summary = crawl_site(settings, FakeSite(pages=pages))
    assert summary.skipped_robots == 1


@pytest.mark.parametrize(
    ("url", "rel"),
    [
        ("https://books.toscrape.com/", "index.html"),
        ("https://books.toscrape.com", "index.html"),
        ("https://books.toscrape.com/catalogue/page-2.html", "catalogue/page-2.html"),
        ("https://books.toscrape.com/catalogue/", "catalogue/index.html"),
    ],
)
def test_url_to_relpath(url: str, rel: str) -> None:
    assert url_to_relpath(url) == rel


def test_url_to_relpath_rejects_traversal() -> None:
    with pytest.raises(ValueError, match="unsafe"):
        url_to_relpath("https://books.toscrape.com/../x")


@pytest.mark.network
def test_live_site(tmp_path: Path) -> None:
    live = Settings(data_dir=tmp_path, _env_file=None)  # type: ignore[call-arg]
    summary = crawl(live, limit=2, max_pages=1)
    assert summary.product_pages == 2
