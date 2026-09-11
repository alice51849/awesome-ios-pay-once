#!/usr/bin/env python3
"""Build additive, evidence-bound buyer guides without changing the 47×50 catalog.

    GEO_PAGES=/path/to/guide python3 geo/buyer_job_guides.py
    GEO_PAGES=/path/to/guide python3 geo/buyer_job_guides.py --check

Only public listing evidence is consumed. This producer never accesses ASC,
publishes a social post, quotes a price, or invents a downloadable output sample.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import html
import json
import os
from pathlib import Path
import re
from typing import Any
from urllib.parse import parse_qs, urlsplit
from xml.sax.saxutils import escape as xml_escape

from official_locales import OFFICIAL_LOCALES
from site_config import PUBLIC_SITE


HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
PAGES = Path(os.environ.get("GEO_PAGES", HERE / "pages"))
SITE = os.environ.get("GEO_SITE", PUBLIC_SITE).rstrip("/")
ROOT = "buyer-guides"
CATALOG = "data/buyer-job-guides/catalog.json"
MANIFEST = "data/buyer-job-guides/manifest.json"
JSON_FEED = "data/buyer-job-guides/feed.json"
DEVTO_QUEUE = ".github/scripts/devto_buyer_job_articles.json"
BASELINE = "data/app-install-decision-routes.json"
BLOCK = re.compile(r"\n?<!--iag-buyer-job-->.*?<!--/iag-buyer-job-->\n?", re.S)
SHA = re.compile(r"[0-9a-f]{64}")
KEY = re.compile(r"[a-z0-9]+")
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
COUNTRIES = {"en-US": "us", "zh-Hant": "tw"}
COPY_FIELDS = {
    "title", "buyer_job", "result", "included", "free_core", "unlock",
    "steps", "proof_caption", "limits", "alternative", "faq", "queries", "purchase_summary",
}
UI_FIELDS = {
    "hub_title", "hub_intro", "disclosure", "job", "result", "payment",
    "paid_label", "free_label", "paid_cta", "free_cta", "steps", "proof",
    "proof_note", "checked", "version", "limits", "alternative", "faq",
    "buy_question", "buy_paid", "buy_free", "price_note", "related",
    "app_details", "all_guides", "rss", "markdown", "backlink_heading", "support", "proof_badge",
}
DECISION_TERMS = {
    "en-US": {"paid_upfront": ("buy", "paid", "purchase"), "free_with_lifetime_unlock": ("free", "unlock", "upgrade", "premium", "one-time")},
    "zh-Hant": {"paid_upfront": ("購買", "買斷", "付費"), "free_with_lifetime_unlock": ("免費", "解鎖", "升級", "買斷", "購買")},
}
CURRENCIES = r"USD|TWD|NTD|JPY|CNY|RMB|HKD|EUR|GBP|CAD|AUD|NZD|KRW|INR"
PRICE = re.compile(
    rf"(?:US\$|NT\$|HK\$|R\$|{CURRENCIES}|[$€£¥￥₹₩₺₽₪฿₴₫₦₱])\s*\d|"
    rf"\d+(?:[.,]\d+)?\s*(?:{CURRENCIES}|元|圓|円|[$€£¥￥₹₩])",
    re.I,
)
UNSUPPORTED_CLAIM = re.compile(
    r"#1\b|no\.\s*1\b|top-rated|rated\s+\d|five-star|5[- ]star|"
    r"\d[\d,]*\s+(?:monthly searches|searches per month)|search volume of|"
    r"五星好評|排名第一|好評第一|每月搜尋量|每月搜尋次數",
    re.I,
)
FREE_DOWNLOAD = re.compile(
    r"free (?:trial|download|core)|(?:start|try|download) (?:for )?free|"
    r"免費(?:試用|下載|核心|開始|體驗)",
    re.I,
)
STYLE = """\
:root{color-scheme:light dark;--ink:#301737;--bg:#fffaf8;--card:#fff;--brand:#78316b;--line:#e9cce0}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.55 system-ui,sans-serif}
a{color:var(--brand);text-underline-offset:.18em}a:focus-visible,summary:focus-visible{outline:3px solid #a852a7;outline-offset:4px}
header,main,footer{width:min(96%,1080px);margin:auto}header{padding:18px 0}nav{display:flex;gap:10px 24px;flex-wrap:wrap}
nav a,footer a{display:inline-flex;align-items:center;min-height:44px}h1{font-size:clamp(1.55rem,3.7vw,2.55rem);line-height:1.16;font-weight:550;margin:.35em 0}
h2{font-size:1.3rem;font-weight:550;margin:.2em 0 .65em}p{margin:.65em 0}section{margin:22px 0;padding:22px;border:1px solid var(--line);border-radius:18px;background:var(--card)}
.hero{padding:24px}.kicker{font-size:.85rem;color:var(--brand)}.result{font-weight:550}.payment{padding:12px 0}
.cta{display:inline-flex;align-items:center;justify-content:center;min-height:48px;padding:12px 18px;border-radius:12px;background:linear-gradient(110deg,#973868,#704d9c);color:white;text-decoration:none;font-weight:550}
.disclosure,.note{font-size:.88rem;line-height:1.55}.disclosure{margin:14px 0}.steps li,.limits li{margin:12px 0}
figure{margin:0;display:flex;align-items:center;gap:28px}figure img{max-width:100%;height:auto;max-height:480px;object-fit:contain}figcaption{flex:1;min-width:0}
.hero-proof{display:grid;grid-template-columns:120px minmax(0,1fr);gap:18px;margin:14px 0}.hero-proof img{width:100%;max-height:260px;align-self:start}.hero-proof .note{font-size:.8rem}
details{border-top:1px solid var(--line);padding:10px 0}summary{min-height:44px;cursor:pointer;display:list-item;padding:8px 0}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:16px}.cards article{padding:18px;background:var(--card);border:1px solid var(--line);border-radius:14px}
.cards a{display:inline-block;min-height:44px}footer{padding:24px 0 36px}li,a,p,h1,h2{overflow-wrap:anywhere}
@media(max-width:600px){body{font-size:16px}.hero,section{padding:16px}header{padding:8px 0}.cta{width:100%;font-size:.93rem}.hero-proof{grid-template-columns:92px minmax(0,1fr);gap:12px}.buyer-guide-page{padding-bottom:90px}.buyer-guide-page .purchase-action{position:fixed;bottom:0;left:0;right:0;z-index:2;background:var(--card);border-top:1px solid var(--line);padding:10px max(12px,2vw) max(10px,env(safe-area-inset-bottom))}}
@media(prefers-color-scheme:dark){:root{--ink:#fff1f9;--bg:#281131;--card:#35163e;--brand:#ffc2e3;--line:#74416c}}
"""


class ContractError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def guide_path(app: dict, locale: str) -> str:
    return f"{ROOT}/{locale}/{app['key']}-{app['job']}.html"


def store_url(record: dict, app: dict, locale: str) -> str:
    value = record["app_store_url"]
    parsed = urlsplit(value)
    query = parse_qs(parsed.query, keep_blank_values=True)
    require(
        parsed.scheme == "https"
        and parsed.netloc == "apps.apple.com"
        and parsed.path == f"/{COUNTRIES[locale]}/app/id{app['app_store_id']}"
        and not parsed.fragment,
        f"Wrong App Store identity or storefront: {app['key']}/{locale}",
    )
    require(
        set(query) == {"pt", "ct", "mt"}
        and all(len(values) == 1 for values in query.values())
        and re.fullmatch(r"\d{1,20}", query["pt"][0]) is not None
        and re.fullmatch(r"[A-Za-z0-9_.-]{1,30}", query["ct"][0]) is not None
        and query["mt"] == ["8"],
        "A complete existing Apple campaign URL is required",
    )
    return value


def validate(config: dict, copies: dict, evidence: dict, baseline: dict) -> dict:
    require(config.get("schema_version") == 1, "Unsupported buyer-guide contract")
    require(config.get("scope") == "first_party_outreach_only", "Wrong scope")
    require(config.get("traffic_scope") == "buyer_decision_only", "Generic information traffic is outside this increment")
    locales = config["locales"]
    require(
        set(locales) == set(COUNTRIES) and len(locales) == len(COUNTRIES),
        "Only the fully authored en-US and zh-Hant increment is supported",
    )
    require(set(locales).issubset(OFFICIAL_LOCALES), "Nonofficial locale")
    require(config["baseline"] == {
        "app_count": 47, "locale_count": 50,
        "paid_upfront": 13, "free_with_lifetime_unlock": 34,
    }, "The 47×50, 13/34 baseline must remain intact")
    require(set(copies) == set(locales), "No locale fallback is allowed")
    apps = config["apps"]
    keys = {app["key"] for app in apps}
    require(len(keys) == len(apps) > 0, "Duplicate or empty app set")
    require(len({app["app_store_id"] for app in apps}) == len(apps), "Duplicate App ID")
    require(not keys.intersection(config["excluded_conversion_apps"]), "Conversion app overlap")
    require(evidence.get("schema_version") == 1, "Unsupported evidence")
    require(evidence.get("scope") == "published_app_store_interface_only", "Unsupported proof claim")
    require(set(evidence["apps"]) == keys, "Every selected app needs evidence")
    require(set(evidence["lookup_receipts"]) == set(locales), "Missing lookup receipts")

    indexed: dict = defaultdict(dict)
    for record in baseline["records"]:
        key, locale = record["app_key"], record["locale"]
        require(locale in OFFICIAL_LOCALES and locale not in indexed[key], "Duplicate/invalid baseline locale")
        indexed[key][locale] = record
    require(
        len(indexed) == baseline["app_count"] == 47
        and baseline["locale_count"] == 50
        and len(baseline["records"]) == baseline["record_count"] == 2350
        and all(set(rows) == set(OFFICIAL_LOCALES) for rows in indexed.values()),
        "Baseline is not exactly 47×50",
    )
    models = Counter()
    for key, rows in indexed.items():
        variants = {row["purchase_model"] for row in rows.values()}
        ids = {row["app_store_id"] for row in rows.values()}
        require(len(variants) == len(ids) == 1, f"Inconsistent baseline identity: {key}")
        models[next(iter(variants))] += 1
    require(models == {"paid_upfront": 13, "free_with_lifetime_unlock": 34}, "Wrong baseline payment mix")

    for locale in locales:
        copy = copies[locale]
        require(copy.get("locale") == locale, "Wrong copy locale")
        require(set(copy["apps"]) == keys and set(copy["ui"]) == UI_FIELDS, "Incomplete native copy")
        for text in strings(copy["ui"]):
            require(bool(text.strip()), "Empty UI text")
            if locale == "zh-Hant":
                require(re.search(r"[\u3400-\u9fff]", text) is not None, "Non-native Traditional Chinese UI")
        receipt = evidence["lookup_receipts"][locale]
        require(receipt["method"] == "GET" and receipt["http_status"] == 200, "No successful public GET")
        require(SHA.fullmatch(receipt["sha256"]) is not None, "Invalid lookup digest")
        lookup_url = urlsplit(receipt["url"])
        require(lookup_url.netloc == "itunes.apple.com" and lookup_url.scheme == "https", "Not public Apple evidence")
        require(parse_qs(lookup_url.query).get("country") == [COUNTRIES[locale]], "Wrong lookup country")

    for app in apps:
        key, model = app["key"], app["purchase_model"]
        require(KEY.fullmatch(key) is not None and SLUG.fullmatch(app["job"]) is not None, "Unsafe path component")
        require(re.fullmatch(r"\d{10}", app["app_store_id"]) is not None, "Invalid App ID")
        require(model in models, "Unknown purchase model")
        require(isinstance(app.get("intent_name"), str) and bool(app["intent_name"].strip()), "Missing buyer identity")
        require(
            len(app.get("exclude_intents", [])) >= 2
            and all(re.fullmatch(r"[a-z0-9_]+", value) for value in app["exclude_intents"]),
            "Explicit excluded information intents are required",
        )
        require(set(app["related"]).issubset(keys - {key}), "Invalid related app")
        require(type(app["devto"]) is bool, "Invalid syndication choice")
        require(set(evidence["apps"][key]) == set(locales), "Missing localized screenshot")
        for locale in locales:
            require(key in indexed, f"App not in current baseline: {key}")
            record = indexed[key][locale]
            require(
                record["app_store_id"] == app["app_store_id"]
                and record["purchase_model"] == model
                and record["verified_live"] is True,
                f"Unverified app or payment-model drift: {key}/{locale}",
            )
            store_url(record, app, locale)
            proof = evidence["apps"][key][locale]
            image_url = urlsplit(proof["screenshot_url"])
            require(
                proof["app_store_id"] == app["app_store_id"]
                and proof["download_is_free"] is (model == "free_with_lifetime_unlock")
                and isinstance(proof["app_version"], str) and bool(proof["app_version"]),
                "Evidence identity or payment mismatch",
            )
            require(
                image_url.scheme == "https"
                and image_url.netloc == "is1-ssl.mzstatic.com"
                and image_url.path.startswith("/image/thumb/PurpleSource")
                and SHA.fullmatch(proof["screenshot_sha256"]) is not None
                and len(proof["screenshot_dimensions"]) == 2
                and all(type(n) is int and n > 0 for n in proof["screenshot_dimensions"]),
                "Invalid published screenshot proof",
            )
            require(datetime.fromisoformat(proof["checked_at"]).tzinfo is not None, "Undated proof")
            text = copies[locale]["apps"][key]
            require(set(text) == COPY_FIELDS, "Missing or unrecognized copy fields")
            for heading in [text["title"], *text["queries"]]:
                require(
                    app["intent_name"].casefold() in heading.casefold()
                    and any(term in heading.casefold() for term in DECISION_TERMS[locale][model]),
                    f"{key}/{locale}: title/query must name the app and a purchase/unlock decision: {heading}",
                )
            require(3 <= len(text["steps"]) <= 5 and len(text["limits"]) >= 2, "Incomplete workflow/limits")
            require(len(text["faq"]) >= 2 and len(text["queries"]) >= 2, "Missing decision questions")
            require(all(set(faq) == {"q", "a"} for faq in text["faq"]), "Malformed FAQ")
            if model == "paid_upfront":
                require(
                    isinstance(text["included"], str)
                    and text["free_core"] is None and text["unlock"] is None,
                    "Paid downloads cannot have a free core or IAP unlock",
                )
                require(not any(FREE_DOWNLOAD.search(s) for s in strings(text)), "Free-trial claim on paid app")
            else:
                require(
                    text["included"] is None
                    and isinstance(text["free_core"], str) and isinstance(text["unlock"], str),
                    "Freemium must name both the free core and one-time unlock",
                )
            for value in strings(text):
                require(bool(value.strip()) and not PRICE.search(value), "Empty copy or hardcoded price")
                require(not UNSUPPORTED_CLAIM.search(value), "Unsupported rating, ranking, or search-volume claim")
                require(not any(ord(c) < 32 and c not in "\n\t" for c in value), "Control characters in copy")
                if locale == "zh-Hant":
                    require(re.search(r"[\u3400-\u9fff]", value) is not None, "English fallback in Traditional Chinese copy")
    return indexed


def load_contract(pages: Path, data: Path = DATA):
    config = json.loads((data / "buyer_job_guides_v1.json").read_text(encoding="utf-8"))
    copies = {
        locale: json.loads((data / f"buyer_job_copy_{locale}.json").read_text(encoding="utf-8"))
        for locale in config["locales"]
    }
    evidence = json.loads((data / "buyer_job_evidence_v1.json").read_text(encoding="utf-8"))
    baseline = json.loads((pages / BASELINE).read_text(encoding="utf-8"))
    indexed = validate(config, copies, evidence, baseline)
    return config, copies, evidence, indexed


def payment(copy: dict, ui: dict) -> str:
    return (copy["included"] or f"{copy['free_core']} {copy['unlock']}") + " " + ui["price_note"]


def faqs(app: dict, copy: dict, ui: dict) -> list[dict]:
    key = "buy_paid" if app["purchase_model"] == "paid_upfront" else "buy_free"
    return [*copy["faq"], {"q": ui["buy_question"], "a": ui[key].format(name=app["name"])}]


def schema(app: dict, copy: dict, ui: dict, locale: str, url: str, cta: str, proof: dict, site: str) -> str:
    payload = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Article", "@id": url + "#article", "url": url,
                "headline": copy["title"], "description": copy["buyer_job"],
                "inLanguage": locale, "isAccessibleForFree": True,
                "dateModified": proof["checked_at"],
                "author": {"@type": "Organization", "name": "Lumi Studio", "url": f"{site}/about.html"},
                "about": {"@id": url + "#app"},
                "citation": [cta, proof["screenshot_url"]],
                "keywords": copy["queries"],
            },
            {
                "@type": "SoftwareApplication", "@id": url + "#app",
                "name": app["name"], "identifier": app["app_store_id"],
                "operatingSystem": "iOS", "applicationCategory": app["category"],
                "installUrl": cta, "url": cta,
                "isAccessibleForFree": app["purchase_model"] == "free_with_lifetime_unlock",
                "description": payment(copy, ui),
            },
            {
                "@type": "FAQPage", "@id": url + "#faq", "inLanguage": locale,
                "mainEntity": [
                    {"@type": "Question", "name": item["q"],
                     "acceptedAnswer": {"@type": "Answer", "text": item["a"]}}
                    for item in faqs(app, copy, ui)
                ],
            },
        ],
    }
    return json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def render_guide(app: dict, copy: dict, ui: dict, proof: dict, locale: str, cta: str,
                 apps: dict, copies: dict, source_digest: str, site: str, details_site: str) -> str:
    e = html.escape
    url = f"{site}/{guide_path(app, locale)}"
    alternate = "\n".join(
        f'<link rel="alternate" hreflang="{loc}" href="{e(site + "/" + guide_path(app, loc), quote=True)}">'
        for loc in copies
    )
    alternate += f'\n<link rel="alternate" hreflang="x-default" href="{site}/{guide_path(app, "en-US")}">'
    model_key = "paid" if app["purchase_model"] == "paid_upfront" else "free"
    steps = "".join(f"<li>{e(step)}</li>" for step in copy["steps"])
    limits = "".join(f"<li>{e(item)}</li>" for item in copy["limits"])
    questions = "".join(
        f'<details><summary>{e(item["q"])}</summary><p>{e(item["a"])}</p></details>'
        for item in faqs(app, copy, ui)
    )
    related = "".join(
        f'<li><a href="{site}/{guide_path(apps[key], locale)}">{e(copies[locale]["apps"][key]["title"])}</a></li>'
        for key in app["related"]
    )
    width, height = proof["screenshot_dimensions"]
    return f"""<!doctype html>
<html lang="{locale}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(copy["title"])} | Lumi Studio</title>
<meta name="description" content="{e(copy["buyer_job"], quote=True)}">
<meta name="buyer-guide-source" content="{source_digest}">
<link rel="canonical" href="{url}">{alternate}
<link rel="alternate" type="application/rss+xml" href="{site}/{ROOT}/{locale}/feed.xml" title="{e(ui["rss"], quote=True)}">
<link rel="stylesheet" href="{site}/{ROOT}/style.css">
<script type="application/ld+json">{schema(app, copy, ui, locale, url, cta, proof, details_site)}</script>
</head><body class="buyer-guide-page"><header><nav><a href="{site}/{ROOT}/{locale}/index.html">{e(ui["all_guides"])}</a>
<a href="{details_site}/{locale}/{app["key"]}.html">{e(ui["app_details"])}</a></nav></header>
<main data-app-id="{app["app_store_id"]}" data-purchase-model="{app["purchase_model"]}" data-intent="buyer-decision">
<section class="hero"><p class="kicker">{e(ui[model_key + "_label"])}</p>
<h1>{e(copy["title"])}</h1><p>{e(copy["buyer_job"])}</p>
<figure class="hero-proof"><img src="{e(proof["screenshot_url"], quote=True)}" width="{width}" height="{height}" loading="eager" decoding="async" referrerpolicy="no-referrer" alt="{e(copy["proof_caption"], quote=True)}">
<figcaption><p class="result">{e(copy["result"])}</p><p class="note">{e(ui["proof_badge"])}</p>
<p class="note">{e(ui["checked"])}: {e(proof["checked_at"][:10])} · {e(ui["version"])}: {e(proof["app_version"])}</p></figcaption></figure>
<p class="payment">{e(copy["purchase_summary"])}</p>
<div class="purchase-action"><a class="cta" href="{e(cta, quote=True)}">{e(ui[model_key + "_cta"])}</a></div></section>
<p class="disclosure">{e(ui["disclosure"])}</p>
<section><h2>{e(ui["payment"])}</h2><p>{e(payment(copy, ui))}</p>
<h2>{e(ui["proof"])}</h2><p>{e(copy["proof_caption"])}</p><p class="note">{e(ui["proof_note"])}</p></section>
<section><h2>{e(ui["steps"])}</h2><ol class="steps">{steps}</ol></section>
<section><h2>{e(ui["limits"])}</h2><ul class="limits">{limits}</ul><h2>{e(ui["alternative"])}</h2><p>{e(copy["alternative"])}</p></section>
<section><h2>{e(ui["faq"])}</h2>{questions}</section>
<section><h2>{e(ui["related"])}</h2><ul>{related}</ul></section>
</main><footer><nav><a href="{site}/{ROOT}/{locale}/feed.xml">{e(ui["rss"])}</a>
<a href="{url[:-5]}.md">{e(ui["markdown"])}</a><a href="{details_site}/about.html">{e(ui["support"])}</a></nav></footer></body></html>
"""


def markdown(app: dict, copy: dict, ui: dict, proof: dict, locale: str,
             cta: str, apps: dict, copies: dict, site: str) -> str:
    url = f"{site}/{guide_path(app, locale)}"
    rows = [f"# {copy['title']}", ui["disclosure"], copy["buyer_job"],
            f"## {ui['result']}", copy["result"],
            f"![{ui['proof']}]({proof['screenshot_url']})", ui["proof_badge"],
            f"{ui['checked']}: {proof['checked_at'][:10]} · {ui['version']}: {proof['app_version']}",
            f"## {ui['payment']}", copy["purchase_summary"],
            payment(copy, ui), f"[{ui['paid_cta'] if app['purchase_model'] == 'paid_upfront' else ui['free_cta']}]({cta})",
            f"## {ui['steps']}"]
    rows.extend(f"{index}. {step}" for index, step in enumerate(copy["steps"], 1))
    rows.extend([f"## {ui['proof']}", copy["proof_caption"],
                 ui["proof_note"],
                 f"## {ui['limits']}"])
    rows.extend(f"- {item}" for item in copy["limits"])
    rows.extend([f"## {ui['alternative']}", copy["alternative"], f"## {ui['faq']}"])
    for item in faqs(app, copy, ui):
        rows.extend([f"### {item['q']}", item["a"]])
    rows.append(f"## {ui['related']}")
    rows.extend(f"- [{copies[locale]['apps'][key]['title']}]({site}/{guide_path(apps[key], locale)})"
                for key in app["related"])
    rows.append(f"[{ui['all_guides']}]({site}/{ROOT}/{locale}/index.html)")
    rows.append(f"[{copy['title']}]({url})")
    return "\n\n".join(rows) + "\n"


def render_hub(locale: str, ui: dict, apps: list[dict], copies: dict, site: str, details_site: str) -> str:
    e = html.escape
    cards = "".join(
        f'<article><h2><a href="{site}/{guide_path(app, locale)}">{e(copies[locale]["apps"][app["key"]]["title"])}</a></h2>'
        f'<p>{e(copies[locale]["apps"][app["key"]]["result"])}</p>'
        f'<p class="note">{e(ui["paid_label"] if app["purchase_model"] == "paid_upfront" else ui["free_label"])}</p></article>'
        for app in apps
    )
    alternates = "".join(
        f'<link rel="alternate" hreflang="{loc}" href="{site}/{ROOT}/{loc}/index.html">'
        for loc in copies
    )
    return f"""<!doctype html>
<html lang="{locale}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(ui["hub_title"])} | Lumi Studio</title><meta name="description" content="{e(ui["hub_intro"], quote=True)}">
<link rel="canonical" href="{site}/{ROOT}/{locale}/index.html">{alternates}
<link rel="alternate" type="application/rss+xml" href="{site}/{ROOT}/{locale}/feed.xml" title="{e(ui["rss"], quote=True)}">
<link rel="stylesheet" href="{site}/{ROOT}/style.css"></head><body>
<header><a href="{site}/{ROOT}/index.html">English · 繁體中文</a></header><main>
<h1>{e(ui["hub_title"])}</h1><p>{e(ui["hub_intro"])}</p><p class="disclosure">{e(ui["disclosure"])}</p>
<div class="cards">{cards}</div></main><footer><nav><a href="{site}/{ROOT}/{locale}/feed.xml">{e(ui["rss"])}</a>
<a href="{details_site}/about.html">{e(ui["support"])}</a></nav></footer></body></html>
"""


def rss(locale: str, ui: dict, records: list[dict], site: str) -> str:
    x = xml_escape
    items = "".join(
        f"<item><title>{x(row['title'])}</title><link>{x(row['url'])}</link>"
        f'<guid isPermaLink="true">{x(row["url"])}</guid>'
        f"<description>{x(row['content_text'])}</description></item>"
        for row in records if row["language"] == locale
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>
<title>{x(ui["hub_title"])}</title><link>{site}/{ROOT}/{locale}/index.html</link>
<description>{x(ui["disclosure"])}</description><language>{locale}</language>
<atom:link href="{site}/{ROOT}/{locale}/feed.xml" rel="self" type="application/rss+xml"/>
{items}</channel></rss>
"""


def backlink(source: str, app: dict, locale: str, copy: dict, ui: dict, site: str) -> str:
    require(source.count("<!--iag-buyer-job-->") <= 1, "Duplicate owned backlink block")
    cleaned = BLOCK.sub("", source)
    require("</main>" in cleaned, "App page has no safe backlink anchor")
    related_end = re.search(r"<!--/iag-app-related-->\n?", cleaned)
    cut = related_end.end() if related_end else cleaned.rfind("</main>") + len("</main>")
    block = (
        '\n<!--iag-buyer-job-->\n<section class="wrap buyer-job-related">'
        f'<h2>{html.escape(ui["backlink_heading"])}</h2>'
        f'<p><a href="{site}/{guide_path(app, locale)}">{html.escape(copy["title"])}</a></p>'
        '</section>\n<!--/iag-buyer-job-->\n'
    )
    return cleaned[:cut] + block + cleaned[cut:]


def owned(path: str) -> bool:
    parts = Path(path).parts
    return (
        not Path(path).is_absolute() and ".." not in parts
        and (path.startswith(ROOT + "/") or path.startswith("data/buyer-job-guides/")
             or path == DEVTO_QUEUE)
    )


def build_outputs(pages: Path, *, data: Path = DATA, site: str = SITE,
                  catalog_pages: Path | None = None, standalone: bool = False):
    site = site.rstrip("/")
    parsed = urlsplit(site)
    require(parsed.scheme == "https" and parsed.netloc and not parsed.query and not parsed.fragment,
            "Canonical site must be an HTTPS origin/path")
    if standalone:
        require(catalog_pages is not None and Path(catalog_pages).resolve() != pages.resolve(),
                "Standalone output must be separate from the read-only catalog")
        require(site != PUBLIC_SITE.rstrip("/"), "Standalone output cannot impersonate the portfolio site")
    source_pages = Path(catalog_pages) if catalog_pages is not None else pages
    config, copies, evidence, indexed = load_contract(source_pages, data)
    details_site = PUBLIC_SITE.rstrip("/") if standalone else site
    apps = {app["key"]: app for app in config["apps"]}
    source_files = ["buyer_job_guides_v1.json", "buyer_job_evidence_v1.json"] + [
        f"buyer_job_copy_{locale}.json" for locale in config["locales"]
    ]
    source_identity = {
        "producer": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "files": {name: hashlib.sha256((data / name).read_bytes()).hexdigest() for name in source_files},
        "site": site,
        "surface": "standalone" if standalone else "portfolio",
        "details_site": details_site,
        "store_urls": {
            f"{key}:{locale}": store_url(indexed[key][locale], app, locale)
            for key, app in apps.items() for locale in config["locales"]
        },
    }
    source_digest = digest(json_text(source_identity))
    generated = {f"{ROOT}/style.css": STYLE}
    backlinks, records, catalog_rows, drafts = {}, [], [], []
    for locale, localized in copies.items():
        ui = localized["ui"]
        generated[f"{ROOT}/{locale}/index.html"] = render_hub(locale, ui, config["apps"], copies, site, details_site)
        for key, app in apps.items():
            copy, proof = localized["apps"][key], evidence["apps"][key][locale]
            cta = store_url(indexed[key][locale], app, locale)
            path = guide_path(app, locale)
            url = f"{site}/{path}"
            body = render_guide(app, copy, ui, proof, locale, cta, apps, copies, source_digest, site, details_site)
            md = markdown(app, copy, ui, proof, locale, cta, apps, copies, site)
            generated[path], generated[path[:-5] + ".md"] = body, md
            app_page = f"{locale}/{key}.html"
            if not standalone:
                original = (pages / app_page).read_text(encoding="utf-8")
                require(f"id{app['app_store_id']}" in original, f"Wrong backlink target identity: {app_page}")
                backlinks[app_page] = backlink(original, app, locale, copy, ui, site)
            records.append({"id": url, "url": url, "title": copy["title"], "language": locale, "content_text": md})
            catalog_rows.append({
                "app_key": key, "app_store_id": app["app_store_id"], "locale": locale,
                "url": url, "app_store_url": cta, "purchase_model": app["purchase_model"],
                "source_digest": source_digest, "proof_scope": evidence["scope"],
                "traffic_scope": config["traffic_scope"], "excluded_intents": app["exclude_intents"],
                "query_evidence": "editorial_candidate_not_measured",
                "evidence": proof, "measured_search_volume": None, "is_ranking": False,
            })
            if app["devto"] and locale == "en-US" and not standalone:
                drafts.append({
                    "title": copy["title"], "body": md, "tags": ["privacy", "security", "productivity"],
                    "canonical_url": url, "source_sha256": digest(body),
                })
        generated[f"{ROOT}/{locale}/feed.xml"] = rss(locale, ui, records, site)
    generated[f"{ROOT}/index.html"] = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Buyer job guides · 需求指南 | Lumi Studio</title><link rel="canonical" href="{site}/{ROOT}/index.html">
<link rel="stylesheet" href="{site}/{ROOT}/style.css"></head><body><main>
<h1>Buyer job guides · 需求指南</h1><p>First-party guides by the developer · 開發者撰寫的用途指南</p>
<nav><a href="{site}/{ROOT}/en-US/index.html" lang="en-US">English</a>
<a href="{site}/{ROOT}/zh-Hant/index.html" lang="zh-Hant">繁體中文</a></nav></main></body></html>
"""
    if not standalone:
        generated[DEVTO_QUEUE] = json_text(drafts)
    else:
        generated["index.html"] = generated[f"{ROOT}/index.html"].replace(
            f'href="{site}/{ROOT}/index.html"', f'href="{site}/index.html"'
        )
        generated[".nojekyll"] = ""
    generated[CATALOG] = json_text({
        "schema_version": 1, "source_digest": source_digest,
        "scope": "additive_first_party_buyer_jobs", "traffic_scope": config["traffic_scope"],
        "baseline_preserved": config["baseline"],
        "locales": config["locales"], "app_count": len(apps), "record_count": len(catalog_rows),
        "publication_status": "not_asserted_by_generator",
        "publisher": "Lumi Studio", "items": catalog_rows,
    })
    generated[JSON_FEED] = json_text({
        "version": "https://jsonfeed.org/version/1.1",
        "title": "Lumi Studio buyer job guides · 需求指南",
        "home_page_url": f"{site}/{ROOT}/index.html", "feed_url": f"{site}/{JSON_FEED}",
        "description": "First-party authored guides; no independent rankings or measured conversion claims.",
        "items": records,
    })
    locations = [path for path in generated if path.endswith(".html")
                 and (path.startswith(ROOT + "/") or (standalone and path == "index.html"))]
    generated[f"{ROOT}/sitemap.xml"] = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(f"<url><loc>{xml_escape(site + '/' + path)}</loc></url>" for path in sorted(locations))
        + "</urlset>\n"
    )
    generated[MANIFEST] = json_text({
        "schema_version": 1, "source_digest": source_digest, "source_identity": source_identity,
        "generated": {path: digest(text) for path, text in sorted(generated.items())},
        "backlink_targets": sorted(backlinks),
        "guide_count": len(records), "rss_count": len(copies), "devto_drafts": len(drafts),
        "publication_status": "not_asserted_by_generator",
    })
    require(all(owned(path) or (standalone and path in {"index.html", ".nojekyll"})
                for path in generated), "Producer escaped its owned surfaces")
    return generated, backlinks


def materialize(pages: Path = PAGES, *, check: bool = False, data: Path = DATA, site: str = SITE,
                catalog_pages: Path | None = None, standalone: bool = False) -> dict:
    pages = Path(pages).resolve()
    generated, backlinks = build_outputs(pages, data=data, site=site,
                                         catalog_pages=catalog_pages, standalone=standalone)
    expected = {**generated, **backlinks}
    stale = []
    prior = pages / MANIFEST
    if prior.exists():
        previous = json.loads(prior.read_text(encoding="utf-8"))
        for relative, sha in previous["generated"].items():
            require(owned(relative) or (standalone and relative in {"index.html", ".nojekyll"}),
                    "Previous manifest contains an unowned path")
            if relative not in generated and (pages / relative).exists():
                require(digest((pages / relative).read_text(encoding="utf-8")) == sha,
                        "Refusing to remove a modified former output")
                stale.append(relative)
    changed = []
    for relative, text in expected.items():
        target = pages / relative
        require(target.resolve().is_relative_to(pages), "Output follows a symlink outside the site")
        if not target.exists() or target.read_text(encoding="utf-8") != text:
            changed.append(relative)
    if not check:
        for relative in changed:
            target = pages / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(expected[relative], encoding="utf-8")
        for relative in stale:
            (pages / relative).unlink()
    manifest = json.loads(generated[MANIFEST])
    return {
        "changed": sorted(changed), "removed": sorted(stale),
        "guide_count": manifest["guide_count"], "rss_count": manifest["rss_count"],
        "devto_drafts": manifest["devto_drafts"], "source_digest": manifest["source_digest"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=Path, default=PAGES)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--catalog-pages", type=Path, help="Read-only portfolio catalog root")
    parser.add_argument("--standalone", action="store_true", help="Export an independent site without modifying portfolio pages")
    args = parser.parse_args()
    result = materialize(args.pages, check=args.check,
                         catalog_pages=args.catalog_pages, standalone=args.standalone)
    print(json_text({key: len(value) if key in {"changed", "removed"} else value
                     for key, value in result.items()}).strip())
    return int(args.check and bool(result["changed"] or result["removed"]))


if __name__ == "__main__":
    raise SystemExit(main())
