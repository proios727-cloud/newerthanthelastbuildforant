# Source policy for this run
SEC EDGAR (sec.gov, data.sec.gov) is blocked by this session's network proxy.
Primary-source substitute: the SEC filing index and the facts extracted from each filing, served by the Robinhood Trading connector (get_sec_filing_index, get_sec_filing, get_sec_filing_facts).
Cite these as type 10-K / 10-Q / 8-K / Form4 with the filing date and filing_id, plus "via Robinhood SEC feed".
Identity: the ticker-to-filer match is confirmed by the filing index for that symbol. CIK stays UNAVAILABLE unless the filing itself states it.
Market data: TradingView (RH_TV_HFT) and Robinhood quotes, each with an as-of time.
