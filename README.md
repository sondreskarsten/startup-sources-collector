# prosjektbanken-collector

Scrapes [Forskningsrådet's Prosjektbanken](https://prosjektbanken.forskningsradet.no/) for the three project sources (FORISS, EU, SKATTEFUNN) and writes gzipped JSONL files to GCS. No parsing, no state — raw immutable archive only.

The parser ([prosjektbanken-parser](https://github.com/sondreskarsten/prosjektbanken-parser)) reads these files downstream in an airgapped environment and resolves company names to organisasjonsnummer against Enhetsregisteret.

## What is Prosjektbanken?

Prosjektbanken is Forskningsrådet's open project database, harvested daily on `data.norge.no` (UUID `f22fcb84-be00-39f3-bf34-2b1585ded227`). Three sources are exposed:

| Source code | What it covers | Volume (Apr 2026) |
|---|---|---:|
| `FORISS` | Forskningsrådet competitive grants from 2004 (Programmer, Frittstående prosjekter, Infrastruktur, Nettverkstiltak) | 44,604 |
| `EU` | EU projects with Norwegian participation (FP7, Horizon 2020, Horizon Europe). Funding amounts are the Norwegian-only share, distributed across project years. Sourced from eCorda. | 5,098 |
| `SKATTEFUNN` | Approved SkatteFUNN tax-deduction projects from 2002. Per-project funding is suppressed (`totalFunding == -1`); aggregate statistics with samples below 5 are also suppressed. | 53,387 |

Together: ~103K project records covering 22 years of Norwegian R&D financing.

## Source

**Listing URL:** `https://prosjektbanken.forskningsradet.no/explore/projects`

**Server-rendered HTML** with the project list embedded in a `__NEXT_DATA__` JSON blob. The collector parses this blob — no underlying REST API is exposed.

**Pagination:** `offset` stride. The response carries `pagination.totalHits`. Iterate until a page returns fewer records than `resultCount`.

**No authentication.** Public license: NLOD 2.0.

**Empirical sweet spot:** `resultCount=2000` ⇒ ~3.3 MB per response.

## GCS output

```
gs://sondre_brreg_data/prosjektbanken/raw/
  source=foriss/2026-04-29.jsonl.gz       # ~44.6K records, ~9 MB
  source=eu/2026-04-29.jsonl.gz           # ~5.1K records, ~2 MB
  source=skattefunn/2026-04-29.jsonl.gz   # ~53.4K records, ~5 MB
```

Each `.jsonl.gz` line is one project record from the listing JSON, preserving:

```
id, title, teaser, source, currentActivity{activity, year},
yearsActive[], organisations[][sector_label, type, name, ...],
totalFunding, duration{startYear, endYear}, geographies[][fylke],
disciplines[][fagomraade, fag, fagdisiplin],
leadName, popSciDescription, projectSummary,    # FORISS, EU only
_kilde                                          # added by collector
```

`_kilde` carries the source code (`FORISS` / `EU` / `SKATTEFUNN`) for downstream provenance.

## Modes

### `snapshot`

Re-fetch the full archive of every selected source. Used for bootstrap and weekly full refresh. The Prosjektbanken page has no incremental "added since" filter, so the simplest correct strategy is to dump everything on each run; the parser deduplicates by `id`. ~30 page fetches per source × 3 sources = ~50 GETs total. ~5 minutes wall time at `delay=0.3`.

### `daily`

Fetch the most recent `DAILY_MAX_RECORDS` records sorted by `date desc` per source. Captures recently approved projects without re-paginating the full archive. ~1 page fetch per source.

## Environment variables

| Variable | Description | Default |
|---|---|---|
| `GCS_BUCKET` | Target GCS bucket. Empty = local-only. | `sondre_brreg_data` |
| `GCS_PREFIX` | GCS path prefix | `prosjektbanken` |
| `RUN_MODE` | `snapshot` or `daily` | `snapshot` |
| `KILDER` | Comma-separated source codes | `FORISS,EU,SKATTEFUNN` |
| `DAILY_MAX_RECORDS` | Cap per source in daily mode | `2000` |
| `PAGE_SIZE` | `resultCount` per HTTP request | `2000` |
| `DELAY` | Seconds between requests | `0.3` |

## Cloud Run

| Setting | Value |
|---|---|
| Job name | `prosjektbanken-collector` |
| Image | `europe-north1-docker.pkg.dev/sondreskarsten-d7d14/brreg-pipelines/prosjektbanken-collector` |
| Region | `europe-north1` |
| Schedule | `0 6 * * 1` Europe/Oslo (weekly snapshot, Mondays 06:00) |
| CPU / Memory | 1 vCPU / 1 GiB |
| Timeout | 1800s |

## Known limitations

- **Funding suppression on SkatteFUNN.** `totalFunding == -1` for all SkatteFUNN records. Per-project budgets and approved skattefradrag are not exposed.
- **No orgnr in source data.** Listing JSON exposes the company name (third element of each `organisations` tuple) but no `organisasjonsnummer`. Resolution happens in the parser via case-insensitive name match against Enhetsregisteret.
- **No incremental added-since filter.** The page does not expose a "registered after" filter. `daily` mode relies on `sortBy=date sortOrder=desc` and trusting the per-page truncation; older modifications to existing projects are missed. The weekly `snapshot` run catches these.
- **`organisations` flattening.** Listing records collapse multi-organisation projects into a single `organisations` list of nested tuples; the first tuple is treated as primary. Multi-partner consortia (common in EU and FORISS) carry secondary partners only on the project detail page, which the parser must fetch separately if needed.

## Files

| File | Purpose |
|---|---|
| `client.py` | `ProsjektbankenClient` — HTTP client with rate limiting, `__NEXT_DATA__` extraction, paginated fetch |
| `collect.py` | Entrypoint — orchestrates snapshot/daily collection and GCS upload |

## Local testing

```bash
# Daily, single source, local-only
GCS_BUCKET="" RUN_MODE=daily KILDER=SKATTEFUNN DAILY_MAX_RECORDS=200 \
  python3 collect.py

# Full snapshot, local-only
GCS_BUCKET="" RUN_MODE=snapshot python3 collect.py

# Snapshot to GCS
RUN_MODE=snapshot python3 collect.py
```
