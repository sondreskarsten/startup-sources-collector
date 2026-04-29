"""HTTP client for Innovasjon Norge's tildelingsrapport CSV.

Innovasjon Norge publishes a live, daily-updated CSV of all
*tildelinger* (grant allocations) at::

    https://indatapublic.blob.core.windows.net/tildelingsrapport/Tildelinger.csv

Encoding is **latin-1** (Windows-1252-compatible), separator is **;**
(semicolon). Columns include::

    Fylkesnavn, Kommunenavn, Org-nr, Bedriftsnavn,
    Virkemiddelkategori, Underkategori, Innvilget beløp,
    Innvilget dato, Beslutningsenhet, Næringshovedområde,
    Næring, Type finansiering

The ``Org-nr`` column carries the orgnr directly (9-digit
zero-padded). ``Innvilget dato`` is in DD.MM.YYYY format.
``Innvilget beløp`` is in NOK with a comma decimal separator.

The blob is updated nightly; ``Last-Modified`` reflects the most
recent refresh.

License: NLOD 2.0.

A historical archive (cut-off July 2023) is also published as a Git
repository at github.com/innovationnorway/analysis-innovation-policy-data.
For current data the indatapublic blob is canonical.
"""

import time

import requests


CSV_URL = (
    "https://indatapublic.blob.core.windows.net/tildelingsrapport/Tildelinger.csv"
)


class InnovasjonNorgeClient:
    """HTTP client for the Innovasjon Norge tildelingsrapport CSV.

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
    >>> c = InnovasjonNorgeClient()
    >>> body = c.download_csv()
    >>> b"Bedriftsnavn" in body[:1000].encode("latin-1") if isinstance(body, str) else b"Bedriftsnavn" in body[:1000]
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

    def _get(self, url, timeout=300):
        """Execute a GET with progressive backoff on HTTP 429 and 5xx.

        Parameters
        ----------
        url : str
            Full URL.
        timeout : int
            Per-request timeout in seconds. Default ``300``.

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

    def download_csv(self):
        """Download the full tildelingsrapport CSV as raw bytes.

        Returns
        -------
        bytes
            CSV body, unmodified. Encoding is latin-1.
        """
        r = self._get(CSV_URL)
        return r.content
