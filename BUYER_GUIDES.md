# App-specific buying decisions

These guides are published by Lumi Studio, the developer, not an independent
reviewer. The English and Traditional Chinese increment covers nine apps with
dated public App Store interface evidence. It does not replace the existing
50-language list or the portfolio's 47 × 50 catalog.

- [English buyer guides](https://alice51849.github.io/awesome-ios-pay-once/buyer-guides/en-US/index.html)
- [繁中購買指南](https://alice51849.github.io/awesome-ios-pay-once/buyer-guides/zh-Hant/index.html)
- [English RSS](https://alice51849.github.io/awesome-ios-pay-once/buyer-guides/en-US/feed.xml)
- [繁中 RSS](https://alice51849.github.io/awesome-ios-pay-once/buyer-guides/zh-Hant/feed.xml)

## Source contract

`_source/geo/data/buyer_job_guides_v1.json` defines the stable App IDs, distinct
purchase models, buyer identities, and excluded information intents. The two
native copy files supply purchase-specific headings, queries, summaries, and
full free/paid boundaries. Public screenshot provenance is kept separately.
No prices, ratings, rankings, search volumes, or conversion lifts are invented.

```sh
python3 tools/build_buyer_guides.py
python3 tools/build_buyer_guides.py --check
python3 -m unittest discover -s tests -p 'test_*.py' -q -b
```

The source renderer is mirrored from the independently reviewed GrowthEngine
buyer-guide source. Its standalone mode reads the public catalog snapshot but
never edits the portfolio's App pages, conversion contracts, gitlink, deployment
workflow, or Dev.to queue. Only `docs/` is deployed. The three README discovery
blocks are source-generated; their original content is preserved.

Published interface screenshots are not independent runtime tests, downloadable
output samples, learning-gain evidence, or security/compliance certifications.
The GitHub Actions deployment and exact public GET receipts establish publication,
not impressions, attributed downloads, purchases, or causal improvement.
