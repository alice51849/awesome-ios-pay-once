from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import unittest
from urllib.parse import urljoin, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_buyer_guides as build
guides = build.guides


class ReaderHTML(HTMLParser):
    """Semantic stand-in for sanitized HTML displayed by a feed reader."""

    def __init__(self, text):
        super().__init__()
        self.tags, self.links, self.images, self.text = [], [], [], []
        self.canonical = None
        self.feed(text)
        self.close()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        if tag == "a":
            self.links.append(attrs.get("href"))
        elif tag == "img":
            self.images.append(attrs)
        elif tag == "link" and attrs.get("rel") == "canonical":
            self.canonical = attrs.get("href")

    def handle_data(self, value):
        self.text.append(value)


def netnewswire_proxy(xml):
    root = ET.fromstring(xml)
    return {
        item.findtext("guid"): {
            "link": item.findtext("link"),
            "date": parsedate_to_datetime(item.findtext("pubDate")),
            "html": item.findtext("description"),
            "rendered": ReaderHTML(item.findtext("description")),
        }
        for item in root.findall("./channel/item")
    }


def feedly_json_proxy(payload):
    return {
        item["id"]: {
            "link": item["url"],
            "date": datetime.fromisoformat(item["date_published"]),
            "html": item["content_html"],
            "rendered": ReaderHTML(item["content_html"]),
            "plain": item["content_text"],
        }
        for item in payload["items"]
    }


class CanonicalAndFeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config, cls.copies, cls.evidence, cls.indexed = guides.load_contract(build.BASELINE)
        cls.outputs, _ = guides.build_outputs(
            build.DOCS, site=build.SITE, catalog_pages=build.BASELINE, standalone=True
        )
        cls.feed = json.loads(cls.outputs[guides.JSON_FEED])
        cls.catalog = json.loads(cls.outputs[guides.CATALOG])

    def test_root_index_is_an_alias_of_the_buyer_index(self):
        target = f"{build.SITE}/buyer-guides/index.html"
        self.assertEqual(target, ReaderHTML(self.outputs["index.html"]).canonical)
        self.assertEqual(target, ReaderHTML(self.outputs["buyer-guides/index.html"]).canonical)

    def test_duplicate_gateway_content_has_only_one_canonical_identity(self):
        groups = defaultdict(list)
        for path, content in self.outputs.items():
            if path.endswith(".html"):
                groups[hashlib.sha256(content.encode()).hexdigest()].append(path)
        for paths in groups.values():
            if len(paths) > 1:
                self.assertEqual({"index.html", "buyer-guides/index.html"}, set(paths))
                self.assertEqual(1, len({ReaderHTML(self.outputs[path]).canonical for path in paths}))

    def test_all_local_canonical_targets_resolve(self):
        for path, content in self.outputs.items():
            if not path.endswith(".html"):
                continue
            canonical = ReaderHTML(content).canonical
            self.assertTrue(canonical.startswith(build.SITE + "/"))
            relative = canonical.removeprefix(build.SITE + "/")
            self.assertIn(relative, self.outputs)
            if path != "index.html":
                self.assertEqual(path, relative)

    def test_sitemap_only_lists_its_own_path_scope(self):
        root = ET.fromstring(self.outputs["buyer-guides/sitemap.xml"])
        locations = [item.text for item in root.findall("{*}url/{*}loc")]
        scope = urljoin(f"{build.SITE}/buyer-guides/sitemap.xml", ".")
        self.assertEqual(21, len(locations))
        self.assertEqual(len(locations), len(set(locations)))
        self.assertNotIn(f"{build.SITE}/index.html", locations)
        self.assertIn(f"{build.SITE}/buyer-guides/index.html", locations)
        for location in locations:
            self.assertTrue(location.startswith(scope), location)
            parsed = urlsplit(location)
            self.assertFalse(parsed.query or parsed.fragment)
            self.assertIn(location.removeprefix(build.SITE + "/"), self.outputs)

    def test_gateway_internal_links_only_use_canonical_targets(self):
        for path in ("index.html", "buyer-guides/index.html"):
            for link in ReaderHTML(self.outputs[path]).links:
                self.assertNotEqual(build.SITE + "/index.html", link)
                relative = link.removeprefix(build.SITE + "/")
                self.assertIn(relative, self.outputs)
                self.assertEqual(link, ReaderHTML(self.outputs[relative]).canonical)

    def test_json_dates_come_from_the_corresponding_proof(self):
        for record in self.catalog["items"]:
            expected = record["evidence"]["checked_at"]
            self.assertEqual(expected, record["date_published"])
            item = next(item for item in self.feed["items"] if item["url"] == record["url"])
            self.assertEqual(expected, item["date_published"])
            self.assertIsNotNone(datetime.fromisoformat(item["date_published"]).tzinfo)

    def test_rss_dates_are_rfc822_compatible(self):
        for locale in self.config["locales"]:
            root = ET.fromstring(self.outputs[f"buyer-guides/{locale}/feed.xml"])
            for item in root.findall("./channel/item"):
                value = item.findtext("pubDate")
                self.assertRegex(value, r"^[A-Z][a-z]{2}, \d{2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2}:\d{2} GMT$")
                source = next(row for row in self.feed["items"] if row["id"] == item.findtext("guid"))
                expected = datetime.fromisoformat(source["date_published"]).astimezone(timezone.utc).replace(microsecond=0)
                self.assertEqual(expected, parsedate_to_datetime(value))

    def test_last_build_date_is_the_maximum_for_that_channel(self):
        for locale in self.config["locales"]:
            root = ET.fromstring(self.outputs[f"buyer-guides/{locale}/feed.xml"])
            dates = [parsedate_to_datetime(item.findtext("pubDate")) for item in root.findall("./channel/item")]
            self.assertEqual(max(dates), parsedate_to_datetime(root.findtext("./channel/lastBuildDate")))

    def test_timezone_offsets_are_compared_as_instants(self):
        records = deepcopy([row for row in self.feed["items"] if row["language"] == "en-US"][:2])
        records[0]["date_published"] = "2026-09-11T14:00:00+08:00"
        records[1]["date_published"] = "2026-09-11T08:00:00+00:00"
        root = ET.fromstring(guides.rss("en-US", self.copies["en-US"]["ui"], records, build.SITE))
        self.assertEqual(datetime(2026, 9, 11, 8, tzinfo=timezone.utc),
                         parsedate_to_datetime(root.findtext("./channel/lastBuildDate")))

    def test_naive_publication_dates_fail_closed(self):
        records = deepcopy([row for row in self.feed["items"] if row["language"] == "en-US"])
        records[0]["date_published"] = "2026-09-11T08:00:00"
        with self.assertRaises(ValueError):
            guides.rss("en-US", self.copies["en-US"]["ui"], records, build.SITE)

    def test_rss_and_json_readers_receive_the_same_rich_article(self):
        json_reader = feedly_json_proxy(self.feed)
        for locale in self.config["locales"]:
            rss_reader = netnewswire_proxy(self.outputs[f"buyer-guides/{locale}/feed.xml"])
            self.assertEqual(9, len(rss_reader))
            for identity, item in rss_reader.items():
                self.assertEqual(json_reader[identity]["html"], item["html"])
                self.assertEqual(json_reader[identity]["link"], item["link"])

    def test_readers_have_a_clickable_correct_app_store_cta_and_real_image(self):
        json_reader = feedly_json_proxy(self.feed)
        for record in self.catalog["items"]:
            rendered = json_reader[record["url"]]["rendered"]
            store_links = [url for url in rendered.links if url.startswith("https://apps.apple.com/")]
            self.assertEqual([record["app_store_url"]], store_links)
            self.assertEqual([record["evidence"]["screenshot_url"]], [image["src"] for image in rendered.images])
            self.assertIn(self.copies[record["locale"]]["ui"]["disclosure"], " ".join(rendered.text))
            rich = json_reader[record["url"]]["html"]
            self.assertLess(rich.index("<img "), rich.index("<a "))

    def test_plain_text_is_not_markdown_or_html(self):
        for item in self.feed["items"]:
            plain = item["content_text"]
            self.assertNotRegex(plain, r"(?m)^#{1,6} ")
            self.assertNotRegex(plain, r"!?\[[^\]]+\]\(https?://")
            self.assertNotRegex(plain, r"</?(?:p|a|img|h[1-6]|script|figure)\b")
            self.assertIn("https://apps.apple.com/", plain)
            row = next(row for row in self.catalog["items"] if row["url"] == item["url"])
            copy = self.copies[row["locale"]]["apps"][row["app_key"]]
            self.assertIn(copy["purchase_summary"], plain)

    def test_feeds_preserve_purchase_boundaries_and_native_disclosures(self):
        for item in self.feed["items"]:
            row = next(row for row in self.catalog["items"] if row["url"] == item["url"])
            locale, key = row["locale"], row["app_key"]
            rendered = " ".join(ReaderHTML(item["content_html"]).text)
            copy = self.copies[locale]["apps"][key]
            self.assertIn(guides.payment(copy, self.copies[locale]["ui"]), rendered)
            self.assertIn(copy["proof_caption"], rendered)
            self.assertIn(self.copies[locale]["ui"]["proof_note"], rendered)

    def test_stable_guid_identity_deduplicates_reader_refreshes(self):
        for locale in self.config["locales"]:
            xml = self.outputs[f"buyer-guides/{locale}/feed.xml"]
            state = netnewswire_proxy(xml)
            state.update(netnewswire_proxy(xml))
            self.assertEqual(9, len(state))
            for item in ET.fromstring(xml).findall("./channel/item"):
                self.assertEqual("true", item.find("guid").get("isPermaLink"))
                self.assertEqual(item.findtext("link"), item.findtext("guid"))
        state = feedly_json_proxy(self.feed)
        state.update(feedly_json_proxy(self.feed))
        self.assertEqual(18, len(state))

    def test_duplicate_guids_fail_before_emitting_rss(self):
        records = deepcopy([row for row in self.feed["items"] if row["language"] == "en-US"])
        records.append(deepcopy(records[0]))
        with self.assertRaises(ValueError):
            guides.rss("en-US", self.copies["en-US"]["ui"], records, build.SITE)

    def test_html_text_and_attribute_injection_remain_inert(self):
        app = self.config["apps"][0]
        copy = deepcopy(self.copies["en-US"]["apps"][app["key"]])
        payload = '<script>alert("x")</script><img src=x onerror="alert(1)">]]>&'
        copy["buyer_job"] = payload
        copy["proof_caption"] = payload
        proof = self.evidence["apps"][app["key"]]["en-US"]
        cta = self.indexed[app["key"]]["en-US"]["app_store_url"]
        rich, plain = guides.feed_content(app, copy, self.copies["en-US"]["ui"], proof, "en-US", cta, build.SITE)
        parsed = ReaderHTML(rich)
        self.assertEqual(1, len(parsed.images))
        self.assertNotIn("script", [tag for tag, _ in parsed.tags])
        self.assertFalse(any(name.lower().startswith("on") for _, attrs in parsed.tags for name in attrs))
        self.assertIn(payload, " ".join(parsed.text))
        self.assertIn(payload, plain)
        row = deepcopy(self.feed["items"][0])
        row.update(language="en-US", content_html=rich, content_text=plain, title="CDATA ]]> & literal")
        xml = guides.rss("en-US", self.copies["en-US"]["ui"], [row], build.SITE)
        self.assertNotIn("<![CDATA[", xml)
        self.assertEqual(rich, ET.fromstring(xml).findtext("./channel/item/description"))

    def test_unsafe_feed_cta_is_rejected(self):
        app = self.config["apps"][0]
        with self.assertRaises(ValueError):
            guides.feed_content(app, self.copies["en-US"]["apps"][app["key"]], self.copies["en-US"]["ui"],
                                self.evidence["apps"][app["key"]]["en-US"], "en-US",
                                "javascript:alert(1)", build.SITE)

    def test_unsafe_feed_image_is_rejected(self):
        app = self.config["apps"][0]
        proof = deepcopy(self.evidence["apps"][app["key"]]["en-US"])
        proof["screenshot_url"] = "data:image/svg+xml,<svg onload=alert(1)>"
        with self.assertRaises(ValueError):
            guides.feed_content(app, self.copies["en-US"]["apps"][app["key"]], self.copies["en-US"]["ui"],
                                proof, "en-US", self.indexed[app["key"]]["en-US"]["app_store_url"], build.SITE)

    def test_unsafe_article_link_is_rejected(self):
        app = self.config["apps"][0]
        with self.assertRaises(ValueError):
            guides.feed_content(app, self.copies["en-US"]["apps"][app["key"]], self.copies["en-US"]["ui"],
                                self.evidence["apps"][app["key"]]["en-US"], "en-US",
                                self.indexed[app["key"]]["en-US"]["app_store_url"], "javascript:alert(1)")

    def test_image_attribute_injection_is_rejected(self):
        app = self.config["apps"][0]
        proof = deepcopy(self.evidence["apps"][app["key"]]["en-US"])
        proof["screenshot_dimensions"] = ['1" onerror="alert(1)', 480]
        with self.assertRaises(ValueError):
            guides.feed_content(app, self.copies["en-US"]["apps"][app["key"]], self.copies["en-US"]["ui"],
                                proof, "en-US", self.indexed[app["key"]]["en-US"]["app_store_url"], build.SITE)


if __name__ == "__main__":
    unittest.main()
