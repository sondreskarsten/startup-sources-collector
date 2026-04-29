# sources/skattefunn

Downloads the official **SkatteFUNN innsendte søknader** XLSX publications from Forskningsrådet. These are the canonical SkatteFUNN application archives — the data on which all official SkatteFUNN statistics are built.

## What it covers

Two rolling XLSX files published at <https://www.forskningsradet.no/skattefunn/suksesshistorier/>:

| File label (current) | Coverage | Rows | Update cadence |
|---|---|---:|---|
| `skattefunn-innsendte-soknader-2002-2024.xlsx` | All søknader 2002 → end 2024, godkjent + avslått | ~70,599 | Annual when full year closes |
| `skattefunn-innsendte-soknader-per-januar-2026.xlsx` | Søknader from new søknadssystem (May 2024) → most recent month | ~4,958 | Monthly-ish |

Filename labels roll forward (e.g. `per-januar-2026` → `per-mars-2026`). The collector discovers current URLs by scraping the landing page rather than hard-coding filenames.

## Why this source matters

Compared with the Prosjektbanken scrape (`sources/prosjektbanken/` with `Kilde=SKATTEFUNN`), this source is strictly better:

1. **Direct `Organisasjonsnummer`** — no name → orgnr resolution against Enhetsregisteret needed downstream.
2. **Includes avslått søknader** — Prosjektbanken shows only godkjente. The 2002–2024 file carries ~70K rows vs ~53K godkjente in Prosjektbanken; the ~17K rejected søknader recoverable here are an additional cohort of "intent-to-do-R&D" firms.
3. **Stable schema** with auditor-grade column names.

The Prosjektbanken sub-source remains useful for FORISS and EU contracts, but for SkatteFUNN this xlsx source supersedes it.

## Discovery

The asset directory `https://www.forskningsradet.no/siteassets/skattefunn/tall/` returns 404 on listing, so the collector combines two independent passes:

1. **Landing-page scrape.** Fetch `forskningsradet.no/skattefunn/suksesshistorier/` and extract every `href` matching `skattefunn-innsendte-soknader[^"\s]*\.xlsx`. Both absolute (`https://...`) and relative (`/siteassets/...`) hrefs are recognized; relative paths resolve against `forskningsradet.no`. This is the canonical pass — the landing page is the published index.

2. **Bounded HEAD probe.** For a small year window (default `today.year - 2 .. today.year + 1`, all 12 Norwegian months for the rolling cut, all year-end candidates for the historical archive), HEAD-test each candidate at `/siteassets/skattefunn/tall/`. Anything returning HTTP 200 joins the discovered set. ~50 HEAD requests; each takes < 1 s.

The probe is an insurance policy, not the discovery primitive. An exhaustive 14,784-URL probe across 2018–2026 found only the same files as the landing-page scrape, confirming Forskningsrådet's asset directory is tightly curated. The probe matters when:

- A new monthly cut is uploaded (e.g. `per-mars-2026.xlsx`) before the landing page is updated to link it.
- The landing page format changes and the regex temporarily under-extracts.

Discovery returns the deduplicated union.

## Source

**Landing page:** `https://www.forskningsradet.no/skattefunn/suksesshistorier/`

**Direct URL pattern:** `https://www.forskningsradet.no/siteassets/skattefunn/tall/skattefunn-innsendte-soknader-{label}.xlsx`

Discovery regex (case-insensitive): `skattefunn-innsendte-soknader[^"'\s>]*\.xlsx`.

**Authentication:** None.

**License:** NLOD 2.0.

**data.norge.no entry:** UUID `f82d3d4a-b0f8-3220-83ef-15fbd854c54f` (`Innsendte søknader til Skattefunn`).

## GCS output

```
gs://sondre_brreg_data/skattefunn/raw/
  label=2002_2024/2026-04-29.xlsx           # historical archive
  label=per_januar_2026/2026-04-29.xlsx     # current rolling
```

`label` is derived from the filename suffix:
- `skattefunn-innsendte-soknader-2002-2024.xlsx` → `2002_2024`
- `skattefunn-innsendte-soknader-per-januar-2026.xlsx` → `per_januar_2026`

XLSX bodies are stored verbatim — no parsing, no schema unification. The parser handles the (slightly different) column schemas of the two files.

## Schema cheat sheet

The two files share most fields but with different column names and types:

| Concept | Historical file | Current file |
|---|---|---|
| Submission date | `Innsendt dato` (datetime) | `Søknadsdato` (datetime) |
| Søknad number | — | `Søknadsnummer` (int) |
| Project number | `Prosjektnummer` (int) | `Prosjektnummer` (int, nullable) |
| Applicant | `Bedriftsnavn` (str) | `Prosjektansvarlig` (str) |
| Project title | `Prosjekttittel` (str) | `Prosjekttittel` (str) |
| Org number | `Organisasjonsnummer` (str, 9-digit zero-padded) | `Org.nr` (int — needs zero-padding to 9 digits) |
| Fylke | `Fylke` (str) | `Fylke` (str) |
| Kommune | `Kommunenavn` (str) | `Kommune` (str) |
| Result | `Søknad godkjent` / `Søknad avslått` (separate booleans) | `GODKJENT?` (`JA` / `NEI`) |
| Project span | `Prosjektets fra-år` / `Prosjektets til-år` (int) | `Fra-dato` / `Til-dato` (datetime) |
| Decision date | `Vedtaksdato` | `Vedtaksdato` |
| Summary | `Populærvitenskapelig sammendrag` | `Populærvitenskapelig sammendrag` |

## Mode

Only `snapshot`. Both XLSX files are re-downloaded on every run. The parser deduplicates by `Prosjektnummer` / `Søknadsnummer` downstream.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `GCS_BUCKET` | `sondre_brreg_data` | Empty = local-only. |
| `GCS_PREFIX` | `skattefunn` | GCS path prefix. |
| `RUN_MODE` | `snapshot` | Only mode. |
| `DELAY` | `0.3` | Seconds between requests. |

## Cloud Run

| Setting | Value |
|---|---|
| Job name | `skattefunn-collector` |
| Image | `europe-north1-docker.pkg.dev/sondreskarsten-d7d14/brreg-pipelines/startup-sources-collector` |
| Region | `europe-north1` |
| Schedule | `15 6 * * 1` Europe/Oslo (weekly, Mondays 06:15) |
| CPU / Memory | 1 vCPU / 512 MiB |
| Timeout | 600s |
| Env | `SOURCE=skattefunn` |

## Known limitations

- Historical file `Organisasjonsnummer` is a string (zero-padded), current file `Org.nr` is a number — orgnrs starting with `0` lose their leading zero in Excel and must be zero-padded to 9 digits in the parser.
- Two XLSX files have overlapping coverage in 2024 (the historical archive ends end-2024; the rolling file starts May 2024). The parser must dedupe; preferred priority is rolling-file > historical (newer data).
- Filename labels roll forward irregularly. A future label `per_mars_2026` will create a new partition under `label=per_mars_2026/`. The parser must read all `label=*` partitions and dedupe.
- Discovery depends on the landing page's HTML; if Forskningsrådet redesigns the page, the URL extraction regex needs updating. The collector exits non-zero if no URLs are discovered, surfacing the failure.

## Files

| File | Purpose |
|---|---|
| `client.py` | `SkatteFunnInnsendteClient` — landing-page discovery, rate-limited download |
| `collect.py` | Entrypoint — discover URLs, download each, write to GCS |
