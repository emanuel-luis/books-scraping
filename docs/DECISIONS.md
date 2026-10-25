# Decisions

Low-impact decisions follow the recommended option of the refactor brief; high-impact ones
(history rewrite, licensing, paid services, anything irreversible or outward-facing) need the
owner's answer.

| # | Date | Decision | Choice | Why |
| --- | --- | --- | --- | --- |
| 1 | 2026-10-25 | Rewrite history to purge the leaked currencylayer key | No rewrite | The key is burned and is being rotated, which makes the copy in history useless. A rewrite would break every clone and fork for no security gain. The key is in history since the first commit (`280d2fa`). |
| 2 | 2026-10-25 | `README.md` / `readme.md` case collision | Keep `README.md` (English), drop `readme.md` (2022, pt-BR) from the index | Case-insensitive checkouts wrote one file over the other. The old text stays in history. |
| 3 | 2026-10-25 | Tracked `library.db` | Untrack it and ignore `*.db`, `*.duckdb`, `data/` | It is a run output, not source. |
| 4 | 2026-10-25 | Storage | DuckDB for the serving layer, Parquet for the processed layer | Analytics-friendly, file-based (no server to run), and DuckDB reads and writes Parquet natively. SQLite and Postgres in compose were the alternatives. |
| 5 | 2026-10-25 | Database access | DuckDB's native Python API, no SQLAlchemy | DuckDB gives `INSERT ... ON CONFLICT` upserts and Parquet I/O directly; SQLAlchemy would need the third-party `duckdb_engine` dialect and adds an ORM the pipeline does not need. |
| 6 | 2026-10-25 | Keep FX enrichment | Yes, as an optional `fx` step using Frankfurter (ECB reference rates, free, no key) | Prices are stored as scraped (amount + currency, GBP on this site). Conversion is a separate, re-runnable step, so the core pipeline needs no third-party API. The old code also treated GBP prices as EUR. |
| 7 | 2026-10-25 | HTML parser | selectolax | Fast, small, CSS selectors, ships type hints. BeautifulSoup was the alternative. |
| 8 | 2026-10-25 | Module rename `scrapping` → `scraping` | The legacy `src/scrapping.py` is replaced by the `books_scraping` package (`fetch`, `parse`, `load`, `fx`, `cli`) | Fixes the spelling and splits the work into testable steps. |
| 9 | 2026-10-25 | Default branch `master` → `main` | Yes. Workflows trigger on `main`; the rename on GitHub is a follow-up for the owner | The rename is an outward step on the remote, so it is listed in the PR instead of done by the refactor. |
| 10 | 2026-10-25 | docker compose | None; one image plus `make demo` | The pipeline has no services: DuckDB and Parquet are files. |
| 11 | 2026-10-25 | Coverage gate | 85 % line coverage on `books_scraping` | High enough to keep the offline tests honest; the live-site test stays opt-in behind the `network` marker. |
| 12 | 2026-10-25 | Delivery | One PR | The repo is small; the Step 0 fixes are separate commits inside it. |
