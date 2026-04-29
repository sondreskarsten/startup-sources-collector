"""HTTP client for SkatteFUNN's "Innsendte søknader" XLSX publications.

Downloads the official SkatteFUNN application XLSX files published by
Forskningsrådet at::

    https://www.forskningsradet.no/skattefunn/suksesshistorier/

The page links to two rolling XLSX files at any given time:

* A historical archive covering all søknader from 2002 through some
  cut-off year (e.g. ``skattefunn-innsendte-soknader-2002-2024.xlsx``).
  Updated rarely — typically once per year when a full year closes.
* A current rolling file covering søknader from the new søknadssystem
  (May 2024 onwards) up to a recent month
  (e.g. ``skattefunn-innsendte-soknader-per-januar-2026.xlsx``).
  Updated periodically as new søknader are submitted and processed.

Both files include columns: ``Innsendt dato / Søknadsdato``,
``Prosjektnummer``, ``Bedriftsnavn / Prosjektansvarlig``,
``Prosjekttittel``, ``Organisasjonsnummer / Org.nr``, ``Fylke``,
``Kommune``, ``Søknad godkjent / GODKJENT?``,
``Prosjektets fra-år / Fra-dato``, ``Prosjektets til-år / Til-dato``,
``Vedtaksdato``, ``Populærvitenskapelig sammendrag``.

Compared with the Prosjektbanken scrape (in
``sources/prosjektbanken/`` of this repo), these files have two
strict advantages:

1. ``Organisasjonsnummer`` is exposed directly — no name → orgnr
   resolution against Enhetsregisteret needed downstream.
2. Both godkjent and avslått søknader are included (Prosjektbanken
   shows only godkjente). The 2002-2024 file carries ~70K rows vs
   ~53K godkjente in Prosjektbanken — i.e. 17K rejected søknader are
   recoverable here that Prosjektbanken hides.

The collector strategy is:

1. Scrape the landing page for ``href`` URLs matching
   ``skattefunn-innsendte-soknader-*.xlsx``.
2. Download each, raw bytes, no parsing.
3. Write to GCS at ``skattefunn/raw/label={label}/{date}.xlsx`` where
   ``label`` is derived from the filename suffix (e.g. ``2002_2024``,
   ``per_januar_2026``).

License: NLOD 2.0.
"""

import re
import time

import requests


FORSKNINGSRADET_BASE = "https://www.forskningsradet.no"
LANDING_URL = f"{FORSKNINGSRADET_BASE}/skattefunn/suksesshistorier/"
XLSX_HREF_RE = re.compile(
    r'(https?://[^"\'\s>\\]*?|/[^"\'\s>\\]*?)skattefunn-innsendte-soknader([^"\'\s>\\]*?)\.xlsx',
    re.IGNORECASE,
)


class SkatteFunnInnsendteClient:
    """HTTP client for the SkatteFUNN innsendte søknader XLSX endpoint.

    Parameters
    ----------
    delay : float
        Seconds to sleep between successful requests. Default ``0.3``.

    Attributes
    ----------
    _request_count : int
        Running count of HTTP requests issued.

    Examples
    --------
    >>> c = SkatteFunnInnsendteClient()
    >>> urls = c.discover_xlsx_urls()
    >>> any("2002" in u for u in urls)
    True
    """

    def __init__(self, delay=0.3):
        self.delay = delay
        self._session = requests.Session()
        self._session.headers["User-Agent"] = (
            "Mozilla/5.0 (compatible; startup-sources-collector; "
            "+https://github.com/sondreskarsten/startup-sources-collector)"
        )
        self._request_count = 0

    def _get(self, url, timeout=120):
        """Execute a GET with progressive backoff on HTTP 429 and 5xx.

        Parameters
        ----------
        url : str
            Full URL to GET.
        timeout : int
            Per-request timeout in seconds. Default ``120``.

        Returns
        -------
        requests.Response

        Raises
        ------
        RuntimeError
            If all 5 retry attempts are exhausted.
        requests.HTTPError
            On any non-200 / non-429 / non-5xx HTTP status.
        """
        backoffs = [5, 10, 20, 30, 60]
        for attempt in range(len(backoffs)):
            self._request_count += 1
            r = self._session.get(url, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                sleep_s = backoffs[attempt]
                print(
                    f"  {r.status_code} at request #{self._request_count}, "
                    f"sleeping {sleep_s}s",
                    flush=True,
                )
                time.sleep(sleep_s)
                continue
            r.raise_for_status()
            time.sleep(self.delay)
            return r
        raise RuntimeError(f"Failed after {len(backoffs)} retries: {url}")

    def discover_xlsx_urls(self):
        """Scrape the landing page for current XLSX download URLs.

        The landing page lists the two rolling files as anchor tags.
        File names change as Forskningsrådet rolls forward
        (e.g. ``per-januar-2026`` → ``per-mars-2026``), so discovery is
        the canonical approach. Both absolute (``https://...``) and
        relative (``/siteassets/...``) hrefs are recognized; relative
        paths are resolved against ``FORSKNINGSRADET_BASE``.

        Returns
        -------
        list of str
            Sorted, deduplicated list of absolute XLSX URLs found on
            the landing page. Returns an empty list if the page
            layout changes such that no URLs match.
        """
        r = self._get(LANDING_URL)
        urls = set()
        for prefix, suffix in XLSX_HREF_RE.findall(r.text):
            href = f"{prefix}skattefunn-innsendte-soknader{suffix}.xlsx"
            if href.startswith("/"):
                href = FORSKNINGSRADET_BASE + href
            urls.add(href)
        return sorted(urls)

    def download_xlsx(self, url):
        """Download one XLSX file as raw bytes.

        Parameters
        ----------
        url : str
            Direct URL to the XLSX file.

        Returns
        -------
        bytes
            The XLSX file body, unmodified.
        """
        r = self._get(url, timeout=300)
        return r.content


def label_from_url(url):
    """Derive a stable label from an XLSX filename.

    Maps ``skattefunn-innsendte-soknader-2002-2024.xlsx`` → ``2002_2024``
    and ``skattefunn-innsendte-soknader-per-januar-2026.xlsx`` →
    ``per_januar_2026``.

    Parameters
    ----------
    url : str
        Full URL ending in an XLSX filename.

    Returns
    -------
    str
        Lowercase label with dashes converted to underscores and
        the common prefix/suffix stripped.
    """
    fname = url.rsplit("/", 1)[-1]
    label = fname.lower()
    label = re.sub(r"^skattefunn-innsendte-soknader-?", "", label)
    label = re.sub(r"\.xlsx$", "", label)
    label = label.replace("-", "_")
    return label or "unlabeled"
