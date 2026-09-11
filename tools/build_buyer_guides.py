#!/usr/bin/env python3
"""Rebuild only this repository's source-bound buyer-decision surface."""

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "_source/geo"))
import buyer_job_guides as guides

SITE = "https://alice51849.github.io/awesome-ios-pay-once"
BASELINE = ROOT / "_source/portfolio"
DOCS = ROOT / "docs"
BLOCK = re.compile(r"\n?<!--buyer-decision-guides-->.*?<!--/buyer-decision-guides-->\n?", re.S)


def readme_block(locale):
    if locale == "zh-Hant":
        title = "購買或解鎖前，先看實際成果"
        text = (
            "針對 9 款 App 的購買決策指南：公開成果畫面前置，"
            "分清一次付費下載與免費核心／一次解鎖，不寫死價格，也不假造排名或搜尋量。"
            "由開發者 Lumi Studio 撰寫，並非獨立評測。"
        )
        label, feed = "繁中購買指南", "繁中 RSS"
    else:
        title = "Before you buy or unlock, inspect the result"
        text = (
            "App-specific buying decisions for 9 apps: published result examples first, "
            "paid downloads separated from free-core/one-time-unlock apps, "
            "with no hardcoded prices, invented rankings, or search-volume claims. "
            "Written by the developer, Lumi Studio, not an independent reviewer."
        )
        label, feed = "English buying guides", "English RSS"
    return (
        "\n<!--buyer-decision-guides-->\n"
        f"## {title}\n\n{text}\n\n"
        f"[{label}]({SITE}/buyer-guides/{locale}/index.html) · "
        f"[{feed}]({SITE}/buyer-guides/{locale}/feed.xml)\n"
        "<!--/buyer-decision-guides-->\n"
    )


def readme_output(source, locale):
    clean = BLOCK.sub("", source)
    heading = re.search(r"^# [^\n]+\n", clean, re.M)
    if heading is None:
        raise ValueError("README needs its existing heading before adding owned links")
    cut = heading.end()
    return clean[:cut] + readme_block(locale) + clean[cut:]


def build(check=False):
    result = guides.materialize(DOCS, site=SITE, catalog_pages=BASELINE, standalone=True, check=check)
    changes = []
    for relative, locale in [("README.md", "en-US"), ("en-US/README.md", "en-US"), ("zh-Hant/README.md", "zh-Hant")]:
        path = ROOT / relative
        original = path.read_text(encoding="utf-8")
        output = readme_output(original, locale)
        if output != original:
            changes.append(relative)
            if not check:
                path.write_text(output, encoding="utf-8")
    result["readme_changes"] = changes
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = build(check=args.check)
    print(json.dumps({key: len(value) if isinstance(value, list) else value
                      for key, value in result.items()}, indent=2))
    return int(args.check and bool(result["changed"] or result["removed"] or result["readme_changes"]))


if __name__ == "__main__":
    raise SystemExit(main())
