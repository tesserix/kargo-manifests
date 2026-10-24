from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class HelivantaDeliveryTests(unittest.TestCase):
    def test_production_waits_for_country_data_migration_review(self):
        docs = list(yaml.safe_load_all((ROOT / "projects/helivanta/project.yaml").read_text()))
        config = next(x for x in docs if x["kind"] == "ProjectConfig")
        self.assertEqual(config["spec"]["promotionPolicies"], [
            {"stage": "prod", "autoPromotionEnabled": False},
        ])

    def test_product_connector_and_shell_promote_the_same_source_in_order(self):
        stage = yaml.safe_load((ROOT / "projects/helivanta/stages/prod.yaml").read_text())
        steps = stage["spec"]["promotionTemplate"]["spec"]["steps"]
        apps = [app for step in steps for app in step["config"]["apps"]]
        self.assertEqual([app["name"] for app in apps], [
            "helivanta-api", "helivanta-global-api", "helivanta-shell",
        ])
        for app in apps:
            self.assertEqual(app["sources"][0]["helm"]["images"], [
                {"key": "image.tag", "value": "${{ vars.imageTag }}"},
            ])
