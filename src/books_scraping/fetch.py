"""Polite HTTP client and the crawl that writes the raw layer."""

import hashlib
import time
from collections.abc import Callable
from pathlib import PurePosixPath
from types import TracebackType
from typing import Literal, Self
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from books_scraping.config import Settings
from books_scraping.models import ManifestEntry, StepSummary
from books_scraping.parse import parse_listing
from books_scraping.runs import RunPaths, StepError, new_run_id, step_logger, utc_now

RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


class FetchError(StepError):
    """The crawl cannot continue (robots.txt unreachable, run directory taken)."""


class _RetryStatus(Exception):
    def __init__(self, response: httpx.Response) -> None:
        super().__init__(response.status_code)
        self.response = response


class Fetcher:
    """httpx client with a minimum interval between requests and tenacity retries."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": settings.user_agent},
            timeout=settings.timeout_s,
            transport=transport,
            follow_redirects=True,
        )
        self._max_retries = settings.max_retries
        self._sleep = sleep
        self._clock = clock
        self._last: float | None = None
        self.min_interval = settings.min_interval_s

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._client.close()

    def _once(self, url: str) -> httpx.Response:
        if self._last is not None:
            wait = self.min_interval - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
        try:
            response = self._client.get(url)
        finally:
            self._last = self._clock()
        if response.status_code in RETRY_STATUS:
            raise _RetryStatus(response)
        return response

    def get(self, url: str) -> httpx.Response:
        """GET with retries. A retryable status that persists is returned, not raised;
        a transport error that persists is raised as httpx.TransportError."""
        retrying = Retrying(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=1, max=30),
            retry=retry_if_exception_type((httpx.TransportError, _RetryStatus)),
            sleep=self._sleep,
            reraise=True,
        )
        try:
            return retrying(self._once, url)
        except _RetryStatus as exc:
            return exc.response


def url_to_relpath(url: str) -> str:
    """The file path of a URL inside the run dir; ValueError when it could leave the run dir.

    Backslashes and colons are refused too: on Windows they are a separator and a drive marker,
    so `..\\x` or `C:x` would escape even though the POSIX parts look harmless.
    """
    path = urlsplit(url).path.lstrip("/")
    if not path or path.endswith("/"):
        path += "index.html"
    if ".." in PurePosixPath(path).parts or any(c in path for c in "\\:\0"):
        raise ValueError(f"unsafe path in {url}")
    return path


def _safe_path(url: str) -> bool:
    try:
        url_to_relpath(url)
    except ValueError:
        return False
    return True


def _robots(response: httpx.Response, agent: str) -> tuple[RobotFileParser, float]:
    rp = RobotFileParser()
    status = response.status_code
    if 200 <= status < 300:
        rp.parse(response.content.decode("utf-8", errors="replace").splitlines())
    elif status in (401, 403):
        rp.parse(["User-agent: *", "Disallow: /"])
    elif status < 500:
        rp.parse(["User-agent: *", "Allow: /"])
    else:
        raise FetchError(f"robots.txt answered {status}")
    return rp, float(rp.crawl_delay(agent) or 0)


def crawl(
    settings: Settings,
    *,
    limit: int | None = None,
    max_pages: int | None = None,
    run_id: str | None = None,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> StepSummary:
    """Crawl listing pages, then product pages, into a new raw run directory."""
    started = utc_now()
    run_id = run_id or new_run_id(started)
    log = step_logger(run_id, "fetch")
    raw = RunPaths(settings.data_dir).raw_dir(run_id)
    try:
        raw.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise FetchError(f"raw run {run_id} already exists") from None

    counts = {"listing": 0, "product": 0, "failed": 0, "skipped": 0}
    host = urlsplit(settings.base_url).netloc

    with (
        Fetcher(settings, transport=transport, sleep=sleep, clock=clock) as fetcher,
        (raw / "manifest.jsonl").open("a", encoding="utf-8") as manifest,
    ):

        def record(url: str, kind: Literal["listing", "product"]) -> httpx.Response | None:
            """Fetch url, save the body as received and append a manifest line."""
            response: httpx.Response | None
            try:
                response = fetcher.get(url)
            except httpx.TransportError as exc:
                log.warning("%s failed: %s", url, exc)
                response = None
            rel = None
            body = b""
            if response is not None:
                body = response.content
                if response.status_code == 200:
                    rel = f"pages/{url_to_relpath(url)}"
                    target = raw / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(body)
            entry = ManifestEntry(
                url=url,
                kind=kind,
                status=response.status_code if response is not None else 0,
                path=rel,
                sha256=hashlib.sha256(body).hexdigest() if rel else None,
                bytes=len(body) if rel else 0,
                fetched_at=utc_now(),
            )
            manifest.write(entry.model_dump_json() + "\n")
            manifest.flush()
            if response is None or response.status_code != 200:
                counts["failed"] += 1
            return response

        robots_url = urljoin(settings.base_url, "/robots.txt")
        try:
            robots_response = fetcher.get(robots_url)
        except httpx.TransportError as exc:
            raise FetchError(f"robots.txt unreachable: {exc}") from exc
        robots, delay = _robots(robots_response, settings.user_agent)
        manifest.write(
            ManifestEntry(
                url=robots_url,
                kind="robots",
                status=robots_response.status_code,
                path=None,
                sha256=None,
                bytes=0,
                fetched_at=utc_now(),
            ).model_dump_json()
            + "\n"
        )
        manifest.flush()
        fetcher.min_interval = max(fetcher.min_interval, delay)

        def allowed(url: str) -> bool:
            """Same host, a path that stays inside the run dir, and robots.txt allows it."""
            if (
                urlsplit(url).netloc == host
                and _safe_path(url)
                and robots.can_fetch(settings.user_agent, url)
            ):
                return True
            counts["skipped"] += 1
            log.warning("skipping %s (robots.txt, other host or unsafe path)", url)
            return False

        product_urls: list[str] = []
        page_url: str | None = settings.base_url
        while page_url and (max_pages is None or counts["listing"] < max_pages):
            if limit is not None and len(product_urls) >= limit:
                break
            if not allowed(page_url):
                break
            response = record(page_url, "listing")
            if response is None or response.status_code != 200:
                break
            counts["listing"] += 1
            listing = parse_listing(response.content.decode("utf-8"), page_url)
            product_urls.extend(listing.product_urls)
            page_url = listing.next_url
        if limit is not None:
            product_urls = product_urls[:limit]

        for url in product_urls:
            if not allowed(url):
                continue
            response = record(url, "product")
            counts["product"] += response is not None and response.status_code == 200
            log.info("fetched %d/%d products", counts["product"], len(product_urls))

    summary = StepSummary(
        run_id=run_id,
        step="fetch",
        status="ok" if counts["product"] else "failed",
        started_at=started,
        finished_at=utc_now(),
        rows_in=len(product_urls),
        rows_out=counts["product"],
        rows_rejected=len(product_urls) - counts["product"],
        listing_pages=counts["listing"],
        product_pages=counts["product"],
        failed=counts["failed"],
        skipped_robots=counts["skipped"],
    )
    (raw / "run.json").write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    return summary
