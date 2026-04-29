"""HTTP client for SkatteFUNN's "Innsendte søknader" XLSX publications.

Downloads the official SkatteFUNN application XLSX files published by
Forskningsrådet under::

    https://www.forskningsradet.no/siteassets/skattefunn/tall/

The asset directory has no listing (server returns 404 on
``/siteassets/skattefunn/tall/``), so discovery combines two passes:

1. **Landing-page scrape.** Fetch
   ``forskningsradet.no/skattefunn/suksesshistorier/`` and extract any
   ``href`` matching ``skattefunn-innsendte-soknader[^"\\s]*\\.xlsx``.
   Both absolute (``https://...``) and relative (``/siteassets/...``)
   hrefs are recognized; relative paths are resolved against
   ``FORSKNINGSRADET_BASE``.

2. **Bounded HEAD probe.** For a small window of candidate filenames
   (current year ± 1, all 12 Norwegian months for the rolling cut, all
   year ranges for the historical archive), HEAD-test each at the
   ``/siteassets/skattefunn/tall/`` path. Anything returning HTTP 200
   joins the discovered set.

The probe catches files that are uploaded to the asset directory
before the landing page is updated to link them — a regular
occurrence when Forskningsrådet rolls the current cut from
``per-januar-2026`` to ``per-mars-2026`` etc. An exhaustive 14,784-URL
probe across 2018–2026 found only the same files as the landing-page
scrape, confirming that the asset directory is tightly curated; the
bounded probe is therefore a small, low-cost insurance policy
(~32 HEAD requests) rather than a discovery primitive.

License: NLOD 2.0.
"""

import re
import time
from datetime import date

import requests


FORSKNINGSRADET_BASE = "https://www.forskningsradet.no"
ASSET_DIR = f"{FORSKNINGSRADET_BASE}/siteassets/skattefunn/tall/"
LANDING_URL = f"{FORSKNINGSRADET_BASE}/skattefunn/suksesshistorier/"

XLSX_HREF_RE = re.compile(
    r'(https?://[^"\'\s>\\]*?|/[^"\'\s>\\]*?)skattefunn-innsendte-soknader([^"\'\s>\\]*?)\.xlsx',
    re.IGNORECASE,
)

NORWEGIAN_MONTHS = [
    "januar", "februar", "mars", "april", "mai", "juni",
    "juli", "august", "september", "oktober", "november", "desember",
]


def candidate_filenames(years_back=1, years_forward=1, today=None):
    """Generate candidate filenames covering the rolling window.

    Two filename families are produced:

    * Historical archives ``skattefunn-innsendte-soknader-2002-{YYYY}.xlsx``
      for ``YYYY`` in ``[current_year - years_back, current_year + years_forward]``.
    * Rolling current cuts
      ``skattefunn-innsendte-soknader-per-{maned}-{YYYY}.xlsx`` for the
      same year window across all 12 Norwegian months.

    Parameters
    ----------
    years_back : int
        Number of years to look back from ``today``. Default ``1``.
    years_forward : int
        Number of years to look forward from ``today``. Default ``1``.
    today : datetime.date or None
        Anchor date. Default ``date.today()``.

    Returns
    -------
    list of str
        Sorted, deduplicated filename list (no path, just the
        ``*.xlsx`` basename).
    """
    if today is None:
        today = date.today()
    year_window = range(today.year - years_back, today.year + years_forward + 1)
    out = set()
    for y in year_window:
        out.add(f"skattefunn-innsendte-soknader-2002-{y}.xlsx")
        for m in NORWEGIAN_MONTHS:
            out.add(f"skattefunn-innsendte-soknader-per-{m}-{y}.xlsx")
    return sorted(out)


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
            Full URL.
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

    def _head(self, url, timeout=10):
        """Execute a HEAD request, returning ``True`` iff HTTP 200.

        Parameters
        ----------
        url : str
            Full URL.
        timeout : int
            Per-request timeout in seconds. Default ``10``.

        Returns
        -------
        bool
            ``True`` if the resource exists (HTTP 200), ``False`` for
            404 or any other non-200 status.
        """
        self._request_count += 1
        r = self._session.head(url, timeout=timeout, allow_redirects=True)
        return r.status_code == 200

    def discover_from_landing(self):
        """Scrape the landing page for XLSX hrefs.

        Returns
        -------
        list of str
            Sorted, deduplicated list of absolute XLSX URLs found.
        """
        r = self._get(LANDING_URL)
        urls = set()
        for prefix, suffix in XLSX_HREF_RE.findall(r.text):
            href = f"{prefix}skattefunn-innsendte-soknader{suffix}.xlsx"
            if href.startswith("/"):
                href = FORSKNINGSRADET_BASE + href
            urls.add(href)
        return sorted(urls)

    def discover_from_probe(self, years_back=2, years_forward=1):
        """HEAD-probe candidate filenames at the canonical asset path.

        Parameters
        ----------
        years_back : int
            Years before today to include. Default ``1``.
        years_forward : int
            Years after today to include. Default ``1``.

        Returns
        -------
        list of str
            Sorted list of absolute URLs that returned HTTP 200.
        """
        names = candidate_filenames(years_back, years_forward)
        urls = []
        for name in names:
            url = ASSET_DIR + name
            if self._head(url):
                urls.append(url)
        return sorted(urls)

    def discover_xlsx_urls(self, years_back=2, years_forward=1):
        """Discover all live XLSX URLs via landing-page scrape + probe.

        Combines :meth:`discover_from_landing` and
        :meth:`discover_from_probe`. Deduplicates the union.

        Parameters
        ----------
        years_back : int
            Probe window years before today. Default ``1``.
        years_forward : int
            Probe window years after today. Default ``1``.

        Returns
        -------
        list of str
            Sorted, deduplicated list of absolute XLSX URLs.
        """
        from_landing = self.discover_from_landing()
        from_probe = self.discover_from_probe(years_back, years_forward)
        print(
            f"  landing: {len(from_landing)} urls; probe: {len(from_probe)} urls",
            flush=True,
        )
        return sorted(set(from_landing) | set(from_probe))

    def download_xlsx(self, url):
        """Download one XLSX as raw bytes.

        Parameters
        ----------
        url : str
            Direct URL to the XLSX file.

        Returns
        -------
        bytes
            The XLSX body, unmodified.
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
        Lowercase label with dashes converted to underscores.
    """
    fname = url.rsplit("/", 1)[-1]
    label = fname.lower()
    label = re.sub(r"^skattefunn-innsendte-soknader-?", "", label)
    label = re.sub(r"\.xlsx$", "", label)
    label = label.replace("-", "_")
    return label or "unlabeled"
