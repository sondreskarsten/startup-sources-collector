# sources/innovasjon_norge

Downloads Innovasjon Norge's live tildelingsrapport CSV — every grant allocation since the start of the rolling window, refreshed nightly.

## What it covers

Innovasjon Norge is the Norwegian government's main innovation/business-development funding agency. They publish a public CSV of all *tildelinger* (grant allocations) — including miljøteknologi, innovasjonstilskudd, bedriftsutviklingstilskudd, and dozens of other virkemidler. The CSV updates nightly and contains:

| Column | Type | Notes |
|---|---|---|
| `Fylkesnavn` | str | County |
| `Kommunenavn` | str | Municipality |
| `Org-nr` | str | **Organisasjonsnummer (9-digit, zero-padded)** |
| `Bedriftsnavn` | str | Company name |
| `Virkemiddelkategori` | str | High-level grant category |
| `Underkategori` | str | Specific virkemiddel |
| `Innvilget beløp` | str | Granted amount in NOK (comma decimal) |
| `Innvilget dato` | str | DD.MM.YYYY |
| `Beslutningsenhet` | str | Decision unit |
| `Næringshovedområde` | str | NACE main area |
| `Næring` | str | NACE detail |
| `Type finansiering` | str | tilskudd / lån / risikolån / etc. |

## Source

**URL:** `https://indatapublic.blob.core.windows.net/tildelingsrapport/Tildelinger.csv`

**Encoding:** latin-1 (Windows-1252-compatible)
**Separator:** `;` (semicolon)
**Authentication:** None (public Azure blob).
**License:** NLOD 2.0.
**Update cadence:** Nightly.

The blob is canonical for current data. Innovasjon Norge also has a historical archive at [`github.com/innovationnorway/analysis-innovation-policy-data`](https://github.com/innovationnorway/analysis-innovation-policy-data) but that one stops at July 2023; the live blob is fresher and richer.

## GCS output

```
gs://sondre_brreg_data/innovasjon_norge/raw/
  2026-04-29.csv     # ~17.4 MB, all tildelinger from rolling window
```

Stored verbatim — no encoding conversion, no parsing. The parser handles latin-1 → UTF-8 conversion and orgnr normalisation.

## Mode

Only `snapshot`. The CSV is re-downloaded on each run; the parser deduplicates by `(Org-nr, Innvilget dato, Underkategori, Innvilget beløp)` since there is no per-tildeling stable ID.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `GCS_BUCKET` | `sondre_brreg_data` | Empty = local-only. |
| `GCS_PREFIX` | `innovasjon_norge` | GCS path prefix. |
| `RUN_MODE` | `snapshot` | Only mode. |
| `DELAY` | `0.3` | Seconds between requests. |

## Cloud Run

| Setting | Value |
|---|---|
| Job name | `innovasjon-norge-collector` |
| Region | `europe-north1` |
| Schedule | `45 6 * * *` Europe/Oslo (daily, 06:45) |
| CPU / Memory | 1 vCPU / 512 MiB |
| Timeout | 600s |
| Env | `SOURCE=innovasjon_norge` |

## Known limitations

- The CSV only includes records within Innovasjon Norge's rolling reporting window — historical grants beyond ~10 years may be dropped without notice. The parser keeps every snapshot dated; the integration ledger in the parser repo handles the longitudinal slice.
- `Org-nr` for foreign companies (rare) is left blank or non-standard. The parser filters to 9-digit Norwegian orgnrs only.
- `Innvilget beløp` is sometimes negative (representing reduktion / reversal of an earlier tildeling). The parser preserves these.
- No stable per-tildeling ID — dedup uses the four-column composite key documented above. Two tildelinger with identical dato + virkemiddel + amount to the same orgnr on the same day collapse into one (acceptable for our purposes).

## Files

| File | Purpose |
|---|---|
| `client.py` | `InnovasjonNorgeClient` — rate-limited HTTP client for the blob CSV |
| `collect.py` | Entrypoint — download CSV, write to GCS |
