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
| 13 | 2026-10-27 | Diagrams as code | D2 sources in `docs/diagrams/`, rendered to SVG and committed next to them; the README shows the SVGs. The README's only Mermaid block (Architecture) became `data-flow`. | Portfolio-wide choice: Mermaid grows hard to read and to debug. Committed SVGs render on GitHub with no build, and the CI `diagrams` job proves they match their sources. |
| 14 | 2026-10-27 | D2 version, engine and settings | D2 v0.9.0 (latest stable on 2026-10-27, released 2026-09-07), pinned in the Makefile with the sha256 of `d2-v0.9.0-linux-amd64.tar.gz` from the release's `SHA256SUMS`; `make d2-install` checks it with `sha256sum --check`. ELK layout, never TALA. Engine, themes and padding live in `vars.d2-config` of `_style.d2` (copied from the other portfolio repos); the Makefile adds `--scale 1` and runs d2 under `env -i`. | The same version, flags and environment give the same bytes in CI and in WSL, so `make diagrams-check` can compare files. `D2_*` and `SCALE` variables would override `d2-config`. Colors come from shapes plus theme overrides, so the SVGs follow GitHub's dark mode. |
| 15 | 2026-10-27 | Diagram set | Three diagrams: `data-flow` (architecture and data flow in one picture), `user-flows-run` (sequence of `run --fx`), `data-model` (the DuckDB tables and view). | The pipeline is one CLI with no services: a separate architecture diagram would repeat the operator, the site and Frankfurter around the same steps. Group labels stay one word because ELK routes edges through container labels. |
| 16 | 2026-10-27 | Data-model arrows | Every column of the four tables, primary keys marked; dashed arrows for the logical relationships (same UPC, same run) and the joins of the view, with the rules (first and last seen run, latest rate per quote) in the note. | The DDL declares primary keys only, so a solid foreign-key arrow would claim a constraint DuckDB does not enforce. All columns fit at about 1,100 px. |
| 17 | 2026-10-27 | Makefile shell | `SHELL := bash` with `-eu -o pipefail` for every recipe. | The diagram targets use bash features (`shopt`, `${f%.d2}`); the existing targets run unchanged under it. |
