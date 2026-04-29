"""Collector entrypoint: SkatteFUNN innsendte søknader XLSX → raw on GCS.

Discovers the current XLSX URLs on Forskningsrådet's
``forskningsradet.no/skattefunn/suksesshistorier/`` page and downloads
each as raw bytes. No parsing, no orgnr canonicalization — raw
immutable archive only. The parser (separate repo) reads these files
downstream.

Output path::

    gs://{GCS_BUCKET}/{GCS_PREFIX}/raw/label={label}/{date}.xlsx

where ``label`` is derived from the filename suffix
(e.g. ``2002_2024``, ``per_januar_2026``). Each XLSX is stored
verbatim.

Modes
-----
This collector has only one mode (``snapshot``). The Forskningsrådet
publication has no incremental "added since" semantic at the file
level — the historical archive is replaced wholesale on update, and
the current rolling file accumulates new søknader. The simplest
correct strategy is to re-download both on every run; the parser
deduplicates by ``Prosjektnummer`` / ``Søknadsnummer`` downstream.

Environment variables
---------------------
GCS_BUCKET : str
    Target GCS bucket. Default ``sondre_brreg_data``. Set to empty
    string for local-only mode (writes to ``./data/raw/``).
GCS_PREFIX : str
    GCS path prefix. Default ``skattefunn``.
RUN_MODE : str
    ``snapshot`` only. Default ``snapshot``. Reserved for future
    expansion.
DELAY : float
    Seconds between requests. Default ``0.3``.

Known limitations
-----------------
- The two XLSX files have different column schemas. The historical
  file uses ``Innsendt dato``, ``Bedriftsnavn``, ``Organisasjonsnummer``,
  ``Søknad godkjent`` (separate boolean column for godkjent and avslått).
  The current rolling file uses ``Søknadsdato``, ``Prosjektansvarlig``,
  ``Org.nr``, ``GODKJENT?`` (single string column). The parser handles
  schema unification.
- ``Org.nr`` in the current rolling file is occasionally stored as a
  numeric Excel value rather than a string, losing leading zeros for
  9-digit orgnrs starting with 0. The parser zero-pads to 9 digits.
- The collector trusts the landing page's HTML to expose direct XLSX
  links; if Forskningsrådet redesigns the page, the regex in
  ``client.discover_xlsx_urls`` will need to be revisited. The
  collector logs and exits non-zero if zero URLs are discovered.
"""

import os
import sys
import tempfile
from datetime import date

from client import SkatteFunnInnsendteClient, label_from_url


GCS_BUCKET = os.environ.get("GCS_BUCKET", "sondre_brreg_data")
GCS_PREFIX = os.environ.get("GCS_PREFIX", "skattefunn")
RUN_MODE = os.environ.get("RUN_MODE", "snapshot")
DELAY = float(os.environ.get("DELAY", "0.3"))


def upload_bytes(body, gcs_path):
    """Upload a bytes body to GCS.

    Parameters
    ----------
    body : bytes
        File contents.
    gcs_path : str
        Full GCS object path (excluding bucket name).
    """
    from google.cloud import storage

    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET)

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp.write(body)
        tmp_path = tmp.name

    blob = bucket.blob(gcs_path)
    blob.upload_from_filename(tmp_path)
    size = os.path.getsize(tmp_path)
    os.unlink(tmp_path)
    print(
        f"  Uploaded {gcs_path} ({size:,} bytes)",
        flush=True,
    )


def write_bytes_local(body, path):
    """Write a bytes body to local disk.

    Parameters
    ----------
    body : bytes
        File contents.
    path : str
        Local file path.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(body)
    print(f"  Wrote {path} ({len(body):,} bytes)", flush=True)


def write_xlsx(body, label, today_str):
    """Write one XLSX to GCS or local fallback.

    Parameters
    ----------
    body : bytes
        XLSX file contents.
    label : str
        Stable label derived from filename (e.g. ``2002_2024``).
    today_str : str
        ISO date string used as filename.
    """
    rel = f"{GCS_PREFIX}/raw/label={label}/{today_str}.xlsx"
    if GCS_BUCKET:
        upload_bytes(body, rel)
    else:
        write_bytes_local(body, f"./data/raw/label={label}/{today_str}.xlsx")


def run_snapshot(client):
    """Discover all XLSX URLs and download each.

    Parameters
    ----------
    client : SkatteFunnInnsendteClient
        API client instance.
    """
    today_str = date.today().isoformat()
    urls = client.discover_xlsx_urls()
    print(f"  Discovered {len(urls)} XLSX URLs:", flush=True)
    for u in urls:
        print(f"    {u}", flush=True)

    if not urls:
        print(
            "  No XLSX URLs discovered — landing page layout may have changed.",
            flush=True,
        )
        sys.exit(2)

    for url in urls:
        label = label_from_url(url)
        print(f"  Downloading label={label} ...", flush=True)
        body = client.download_xlsx(url)
        print(f"  {label}: {len(body):,} bytes", flush=True)
        write_xlsx(body, label, today_str)

    print(f"\n  Snapshot complete: {len(urls)} files", flush=True)


def main():
    """Parse environment variables and dispatch to the snapshot run."""
    print(f"{'=' * 60}", flush=True)
    print(f"  skattefunn-collector — mode: {RUN_MODE}", flush=True)
    print(f"  delay: {DELAY}", flush=True)
    print(f"  {date.today().isoformat()}", flush=True)
    print(f"{'=' * 60}", flush=True)

    client = SkatteFunnInnsendteClient(delay=DELAY)

    if RUN_MODE == "snapshot":
        run_snapshot(client)
    else:
        print(f"Unknown RUN_MODE: {RUN_MODE}")
        sys.exit(1)


if __name__ == "__main__":
    main()
