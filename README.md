# startup-sources-collector

Collect-stage repo for startup-domain external data sources. Scrapes raw data from a growing list of providers (Prosjektbanken first, more to follow) and writes gzipped JSONL files to GCS. No parsing, no name-resolution, no state — raw immutable archive only.

The companion parser lives in [startup-sources-parser](https://github.com/sondreskarsten/startup-sources-parser) (TODO) and resolves company names to organisasjonsnummer against Enhetsregisteret in an airgapped environment.

## Why a multi-source repo

Most existing collectors in the platform target a single API or registry (one source per repo: `kunngjoring-collector`, `doffin-collector`, `stotteregisteret-collector`, etc.). Startup-ecosystem data is fragmented across many small providers — each with its own scrape pattern but similar shape (web-based, no API key, JSON-rendered pages or paginated catalogs). One repo per startup source would proliferate boilerplate, so they share this collect-stage repo with a per-source subfolder.

## Sources

| Source | Status | Subfolder | Description |
|---|---|---|---|
| Prosjektbanken | live | `sources/prosjektbanken/` | Forskningsrådet open project data. Three sub-sources via `KILDER`: `FORISS` (44.6K competitive grants), `EU` (5.1K Horizon contracts), `SKATTEFUNN` (53.4K approved tax-deduction projects). |
| Investinor | planned | `sources/investinor/` | Direct portfolio holdings from `investinor.no`. |
| StartupLab | planned | `sources/startuplab/` | Member firms and alumni from `startuplab.no`. |
| Katapult | planned | `sources/katapult/` | Cohort listings. |
| Dealroom | planned | `sources/dealroom/` | Norwegian-flagged startup directory. |
| The Hub | planned | `sources/thehub/` | Norwegian startup directory. |
| Shifter | planned | `sources/shifter/` | Funding round announcements with company names. |

## Layout

```
startup-sources-collector/
  collect.py               # top-level dispatcher (selects by SOURCE env var)
  Dockerfile               # builds one image used for all sources
  requirements.txt         # union of all sources' deps
  README.md
  sources/
    prosjektbanken/
      client.py
      collect.py           # per-source main()
      README.md            # per-source notes
    {next_source}/
      client.py
      collect.py
      ...
```

## Usage

The top-level `collect.py` reads `SOURCE` from the environment and invokes that source's `collect.py main()`. All other environment variables pass through to the source.

```bash
# Local: run Prosjektbanken in daily mode against a single sub-source
SOURCE=prosjektbanken GCS_BUCKET="" RUN_MODE=daily KILDER=SKATTEFUNN \
  DAILY_MAX_RECORDS=200 python3 collect.py

# Production: run a full Prosjektbanken snapshot to GCS
SOURCE=prosjektbanken RUN_MODE=snapshot python3 collect.py
```

## Common environment variables

| Variable | Default | Description |
|---|---|---|
| `SOURCE` | `prosjektbanken` | Which source under `sources/` to run. |
| `GCS_BUCKET` | `sondre_brreg_data` | Empty = local-only. |
| `GCS_PREFIX` | source-defined | Per-source default; rooted at `{source_name}/`. |
| `RUN_MODE` | source-defined | `snapshot` / `daily` / source-specific modes. |

Per-source flags are documented in each source's own `README.md`.

## Cloud Run

Each source runs as its own Cloud Run job to allow independent scheduling and resource allocation. They share a single image (this repo) but differ on `SOURCE` env var.

| Source | Job name | Schedule (Europe/Oslo) | CPU / Mem |
|---|---|---|---|
| Prosjektbanken | `prosjektbanken-collector` | `0 6 * * 1` weekly Mondays | 1 vCPU / 1 GiB |

Image: `europe-north1-docker.pkg.dev/sondreskarsten-d7d14/brreg-pipelines/startup-sources-collector:latest`

## Repo conventions

- **Collect stage only.** No parsing, no orgnr resolution, no dedup, no state. Each run produces an immutable dated archive at the canonical path `{source_name}/raw/...`. The parser repo (downstream) takes care of everything else.
- **One Dockerfile, one image, many sources.** Each source's `collect.py` exposes a `main()` that the top-level dispatcher calls. Sources share `requirements.txt` to keep image-rebuild churn down.
- **Per-source README required.** Every `sources/{name}/` folder must include a `README.md` documenting the API, GCS output paths, modes, env vars, Cloud Run config, and known limitations — same template as Prosjektbanken's.
- **No authentication-secrets in source code.** All sources currently work without auth. If a future source requires keys, use Secret Manager and document in the per-source README.
