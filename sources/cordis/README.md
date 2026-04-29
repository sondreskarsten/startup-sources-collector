# sources/cordis

Downloads the CORDIS bulk CSV exports for the three EU Framework Programmes that carry Norwegian-relevant data: Horizon Europe (2021–2027), Horizon 2020 (2014–2020), and FP7 (2007–2013).

## What it covers

CORDIS (Community Research and Development Information Service) is the European Commission's primary public source of EU-funded research and innovation projects. The Publications Office maintains bulk CSV exports per programme, downloadable as ZIP bundles from `cordis.europa.eu/data/`.

| Programme | Period | ZIP size (Apr 2026) | Total participants | NO participants |
|---|---|---:|---:|---:|
| HORIZON Europe | 2021–2027 (active) | ~30 MB | ~52,918 | ~1,200 (est.) |
| Horizon 2020 | 2014–2020 (closed, corrections still appear) | ~55 MB | ~177,834 | ~3,500 (est.) |
| FP7 | 2007–2013 (closed) | ~33 MB | ~140,008 | ~1,800 (est.) |

The parser filters `organization.csv` to `country == "NO"` to recover Norwegian beneficiaries with VAT number, name, and EC contribution.

## Source

**URL pattern:**
```
https://cordis.europa.eu/data/cordis-{programme}projects-csv.zip
```

with `programme ∈ {HORIZON, h2020, fp7}` (case matters — HORIZON is uppercase, the other two are lowercase).

**Authentication:** None.

**License:** CC BY 4.0.

**Update cadence:** Monthly (Publications Office). Each ZIP carries a `contentUpdateDate` field per row.

## Each ZIP contains

| File | Rows (Apr 2026) | Purpose |
|---|---:|---|
| `project.csv` | ~70K | Project header — id, acronym, dates, totalCost, ecMaxContribution, status |
| `organization.csv` | ~370K | Participations — projectID, organisationID, vatNumber, name, country, role, ecContribution |
| `topics.csv` | ~70K | Project ↔ topic linkage |
| `legalBasis.csv` | ~100K | Project ↔ legal basis (programme/sub-programme codes) |
| `euroSciVoc.csv` | ~210K | Project ↔ EuroSciVoc taxonomy (research field codes) |
| `webLink.csv` | ~190K | Project ↔ external URLs |
| `policyPriorities.csv` | ~50K | Project ↔ policy priority codes |
| `webItem.csv` | small | Reference table |
| `information.zip` | small | Release notes / data dictionary PDFs (nested zip) |

## GCS output

```
gs://sondre_brreg_data/cordis/raw/
  programme=horizon/2026-04-29.zip       # HORIZON Europe ~30 MB
  programme=h2020/2026-04-29.zip         # H2020 ~55 MB
  programme=fp7/2026-04-29.zip           # FP7 ~33 MB
```

ZIPs are stored verbatim. The parser unzips, filters `organization.csv` to `country == "NO"`, extracts orgnr from `vatNumber`, and emits a unified parquet.

## Mode

Only `snapshot`. All three programme ZIPs re-downloaded on each run; the parser deduplicates by `projectID` per programme.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `GCS_BUCKET` | `sondre_brreg_data` | Empty = local-only. |
| `GCS_PREFIX` | `cordis` | GCS path prefix. |
| `RUN_MODE` | `snapshot` | Only mode. |
| `PROGRAMMES` | `horizon,h2020,fp7` | Comma-separated programme codes. |
| `DELAY` | `0.3` | Seconds between requests. |

## Cloud Run

| Setting | Value |
|---|---|
| Job name | `cordis-collector` |
| Region | `europe-north1` |
| Schedule | `30 6 1 * *` Europe/Oslo (monthly, 1st of month, 06:30) |
| CPU / Memory | 1 vCPU / 1 GiB |
| Timeout | 1800s |
| Env | `SOURCE=cordis` |

## Known limitations

- VAT number is the primary orgnr signal for Norwegian rows but is sometimes missing or non-standard. The parser falls back to name match against Enhetsregisteret.
- `vatNumber` formatting varies across rows for NO entities: `NO123456789MVA`, `NO 123 456 789 MVA`, `123456789`, `123 456 789`. The parser strips non-digit characters and validates 9-digit length.
- CORDIS sometimes omits `vatNumber` for HES/REC institutions — these rows are matched on name via Enhetsregisteret.
- The `country` field uses ISO 3166 alpha-2; some old FP7 rows use country names — the parser handles both.

## Files

| File | Purpose |
|---|---|
| `client.py` | `CordisClient` — rate-limited HTTP client for the bulk ZIP endpoint |
| `collect.py` | Entrypoint — download each programme ZIP, write to GCS |
