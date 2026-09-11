from copy import deepcopy
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_buyer_guides as build
guides = build.guides


class Links(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.targets = []
        self.images = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "a":
            self.targets.append(values["href"])
        elif tag == "img":
            self.images.append(values)


class BuyerSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config, cls.copies, cls.evidence, _ = guides.load_contract(build.BASELINE)
        cls.baseline = json.loads((build.BASELINE / guides.BASELINE).read_text())
        cls.outputs, cls.backlinks = guides.build_outputs(
            build.DOCS, site=build.SITE, catalog_pages=build.BASELINE, standalone=True
        )

    def test_complete_native_increment_preserves_baseline(self):
        self.assertEqual({"en-US", "zh-Hant"}, set(self.copies))
        self.assertEqual(9, len(self.config["apps"]))
        self.assertEqual(47, self.baseline["app_count"])
        self.assertEqual(2350, self.baseline["record_count"])
        self.assertEqual({"app_count": 47, "locale_count": 50, "paid_upfront": 13, "free_with_lifetime_unlock": 34},
                         self.config["baseline"])
        self.assertFalse(self.backlinks)
        self.assertNotIn(guides.DEVTO_QUEUE, self.outputs)

    def test_committed_site_is_source_reproducible(self):
        for relative, content in self.outputs.items():
            with self.subTest(path=relative):
                self.assertEqual(content, (build.DOCS / relative).read_text())
        self.assertFalse(build.build(check=True)["readme_changes"])

    def test_buying_intent_and_model_specific_ctas(self):
        for app in self.config["apps"]:
            for locale in self.config["locales"]:
                copy = self.copies[locale]["apps"][app["key"]]
                body = self.outputs[guides.guide_path(app, locale)]
                self.assertIn(app["intent_name"].casefold(), copy["title"].casefold())
                self.assertTrue(any(term in copy["title"].casefold()
                                    for term in guides.DECISION_TERMS[locale][app["purchase_model"]]))
                page = Links(body)
                ctas = [url for url in page.targets if url.startswith("https://apps.apple.com/")]
                self.assertEqual(1, len(ctas))
                self.assertIn(f"/id{app['app_store_id']}?", ctas[0])
                ui = self.copies[locale]["ui"]
                self.assertIn(ui["paid_cta" if app["purchase_model"] == "paid_upfront" else "free_cta"], body)

    def test_evidence_is_real_and_before_the_purchase_action(self):
        for app in self.config["apps"]:
            for locale in self.config["locales"]:
                body = self.outputs[guides.guide_path(app, locale)]
                self.assertLess(body.index('<img '), body.index('<a class="cta"'))
                image = Links(body).images
                self.assertEqual(1, len(image))
                self.assertEqual(self.evidence["apps"][app["key"]][locale]["screenshot_url"], image[0]["src"])
                self.assertEqual("eager", image[0]["loading"])
                self.assertIn(self.copies[locale]["ui"]["proof_badge"], body)

    def test_generic_information_is_rejected_at_source(self):
        config, copies, evidence, baseline = deepcopy((self.config, self.copies, self.evidence, self.baseline))
        copies["en-US"]["apps"]["gmoney"]["queries"] = ["currency rates today", "how to save money"]
        with self.assertRaises(guides.ContractError):
            guides.validate(config, copies, evidence, baseline)

    def test_paid_app_cannot_gain_a_trial_or_unlock(self):
        for field, value in [("free_core", "Free trial"), ("unlock", "Upgrade once")]:
            config, copies, evidence, baseline = deepcopy((self.config, self.copies, self.evidence, self.baseline))
            copies["en-US"]["apps"]["gmoney"][field] = value
            with self.assertRaises(guides.ContractError):
                guides.validate(config, copies, evidence, baseline)

    def test_prices_and_invented_rankings_are_rejected(self):
        for text in ["Buy for $4.99", "The #1 app", "10,000 monthly searches"]:
            config, copies, evidence, baseline = deepcopy((self.config, self.copies, self.evidence, self.baseline))
            copies["en-US"]["apps"]["gmoney"]["steps"].append(text)
            with self.assertRaises(guides.ContractError):
                guides.validate(config, copies, evidence, baseline)

    def test_feeds_only_contain_the_native_buying_guides(self):
        feed = json.loads(self.outputs[guides.JSON_FEED])
        self.assertEqual(18, len(feed["items"]))
        for locale in self.config["locales"]:
            rss = ET.fromstring(self.outputs[f"buyer-guides/{locale}/feed.xml"])
            self.assertEqual(locale, rss.findtext("./channel/language"))
            items = rss.findall("./channel/item")
            self.assertEqual(9, len(items))
            for item in items:
                self.assertTrue(item.findtext("link").startswith(f"{build.SITE}/buyer-guides/{locale}/"))
                self.assertIn(item.findtext("title"), [row["title"] for row in feed["items"] if row["language"] == locale])

    def test_internal_links_resolve_and_details_keep_the_original_owner(self):
        for path, body in self.outputs.items():
            if not path.endswith(".html"):
                continue
            for link in Links(body).targets:
                if link.startswith(build.SITE + "/"):
                    self.assertIn(link.removeprefix(build.SITE + "/"), self.outputs)
            if "-reconcile-" in path:
                self.assertIn(f'{guides.PUBLIC_SITE}/en-US/gmoney.html' if "/en-US/" in path
                              else f'{guides.PUBLIC_SITE}/zh-Hant/gmoney.html', body)

    def test_schema_never_invents_prices_reviews_or_search_volume(self):
        for app in self.config["apps"]:
            for locale in self.config["locales"]:
                body = self.outputs[guides.guide_path(app, locale)]
                graph = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', body, re.S)[1])["@graph"]
                application = next(item for item in graph if item["@type"] == "SoftwareApplication")
                self.assertNotIn("offers", application)
                self.assertNotIn("aggregateRating", application)
                self.assertEqual(app["purchase_model"] == "free_with_lifetime_unlock", application["isAccessibleForFree"])
        catalog = json.loads(self.outputs[guides.CATALOG])
        self.assertTrue(all(row["measured_search_volume"] is None and row["is_ranking"] is False for row in catalog["items"]))
        self.assertTrue(all(row["traffic_scope"] == "buyer_decision_only" and row["excluded_intents"] for row in catalog["items"]))

    def test_readme_block_is_idempotent_and_preserves_existing_content(self):
        original = "# Existing list\n\nKeep this original content.\n"
        result = build.readme_output(original, "en-US")
        self.assertEqual(original, build.BLOCK.sub("", result))
        self.assertEqual(result, build.readme_output(result, "en-US"))
        self.assertIn("paid downloads separated from free-core", result)
        self.assertIn("由開發者", build.readme_block("zh-Hant"))
        prefixed = "<!-- Original source provenance -->\n\n" + original
        self.assertEqual(prefixed, build.BLOCK.sub("", build.readme_output(prefixed, "zh-Hant")))

    def test_public_baseline_matches_its_receipt(self):
        proof = json.loads((build.BASELINE / "provenance.json").read_text())
        self.assertEqual(proof["sha256"], hashlib.sha256((build.BASELINE / guides.BASELINE).read_bytes()).hexdigest())
        self.assertTrue(proof["public_source"].startswith(guides.PUBLIC_SITE + "/data/"))

    def test_deployment_follows_the_repository_default_branch(self):
        workflow = (ROOT / ".github/workflows/buyer-guides.yml").read_text()
        self.assertNotIn("refs/heads/main", workflow)
        self.assertNotIn("branches: [main]", workflow)
        self.assertEqual(2, workflow.count(
            "github.event_name != 'pull_request' && github.ref_type == 'branch' && github.ref_name == github.event.repository.default_branch"
        ))
        self.assertIn("path: docs", workflow)

    def test_tags_and_non_default_branches_cannot_deploy(self):
        workflow = (ROOT / ".github/workflows/buyer-guides.yml").read_text()
        conditions = re.findall(r"^\s+if:\s*(.+)$", workflow, re.M)
        cases = [
            ("push", "branch", "master", True),
            ("workflow_dispatch", "branch", "master", True),
            ("pull_request", "branch", "master", False),
            ("push", "tag", "master", False),
            ("push", "branch", "feature", False),
            ("push", "branch", "main", False),
        ]
        for event, kind, name, expected in cases:
            context = {"github.event_name": event, "github.ref_type": kind,
                       "github.ref_name": name, "github.event.repository.default_branch": "master"}
            for condition in conditions:
                checks = []
                for clause in condition.split(" && "):
                    left, operator, right = clause.split()
                    a = context[left]
                    b = right[1:-1] if right.startswith("'") else context[right]
                    self.assertIn(operator, {"==", "!="})
                    checks.append(a == b if operator == "==" else a != b)
                self.assertEqual(expected, all(checks), (event, kind, name))


if __name__ == "__main__":
    unittest.main()
