from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class HelivantaDeliveryTests(unittest.TestCase):
    def test_production_auto_promotes_approved_releases(self):
        docs = list(yaml.safe_load_all((ROOT / "projects/helivanta/project.yaml").read_text()))
        config = next(x for x in docs if x["kind"] == "ProjectConfig")
        self.assertEqual(config["spec"]["promotionPolicies"], [
            {"stage": "prod", "autoPromotionEnabled": True},
        ])

    def test_warehouse_only_sees_approved_releases(self):
        warehouse = yaml.safe_load((ROOT / "projects/helivanta/warehouses/services.yaml").read_text())
        self.assertEqual(warehouse["spec"]["freightCreationPolicy"], "Automatic")
        self.assertEqual(warehouse["spec"]["subscriptions"], [{"git": {
            "repoURL": "https://github.com/tesserix/helivanta.git",
            "branch": "release/prod",
            "commitSelectionStrategy": "NewestFromBranch",
            "discoveryLimit": 20,
        }}])

    def test_image_tag_is_the_promoted_helivanta_commit(self):
        stage = yaml.safe_load((ROOT / "projects/helivanta/stages/prod.yaml").read_text())
        variables = {v["name"]: v["value"] for v in stage["spec"]["promotionTemplate"]["spec"]["vars"]}
        self.assertEqual(variables["imageTag"],
                         '${{ commitFrom("https://github.com/tesserix/helivanta.git").ID }}')

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
