from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
GIT = "https://github.com/tesserix/helivanta.git"
API = "ghcr.io/tesserix/helivanta/helivanta-api"
SHELL = "ghcr.io/tesserix/helivanta/helivanta-shell"


def load(path):
    return yaml.safe_load((ROOT / path).read_text())


def stage_vars():
    stage = load("projects/helivanta/stages/prod.yaml")
    return {v["name"]: v["value"] for v in stage["spec"]["promotionTemplate"]["spec"]["vars"]}


class HelivantaDeliveryTests(unittest.TestCase):
    def test_production_auto_promotes_approved_releases(self):
        docs = list(yaml.safe_load_all((ROOT / "projects/helivanta/project.yaml").read_text()))
        config = next(x for x in docs if x["kind"] == "ProjectConfig")
        self.assertEqual(config["spec"]["promotionPolicies"], [
            {"stage": "prod", "autoPromotionEnabled": True},
        ])

    def test_warehouse_only_sees_approved_releases(self):
        warehouse = load("projects/helivanta/warehouses/services.yaml")
        self.assertEqual(warehouse["spec"]["freightCreationPolicy"], "Automatic")
        self.assertEqual(warehouse["spec"]["subscriptions"], [
            {"git": {
                "repoURL": GIT,
                "branch": "release/prod",
                "commitSelectionStrategy": "NewestFromBranch",
                "discoveryLimit": 20,
            }},
            # Digest reads the one release-prod tag, never the >100-tag list.
            {"image": {
                "repoURL": API,
                "imageSelectionStrategy": "Digest",
                "constraint": "release-prod",
                "discoveryLimit": 1,
            }},
            {"image": {
                "repoURL": SHELL,
                "imageSelectionStrategy": "Digest",
                "constraint": "release-prod",
                "discoveryLimit": 1,
            }},
        ])

    def test_freight_requires_both_images_built_from_the_release_commit(self):
        expression = load("projects/helivanta/warehouses/services.yaml")["spec"]["freightCreationCriteria"]["expression"]
        revision = "?.Annotations?.['org.opencontainers.image.revision'] ?? ''"
        self.assertEqual(expression.splitlines(), [
            f"let commit = commitFrom('{GIT}')?.ID ?? '';",
            f"let api = imageFrom('{API}'){revision};",
            f"let shell = imageFrom('{SHELL}'){revision};",
            "commit != '' && api == commit && shell == commit",
        ])

    def test_each_image_is_pinned_to_its_freight_digest(self):
        variables = stage_vars()
        self.assertEqual(variables["commit"], f'${{{{ commitFrom("{GIT}").ID }}}}')
        self.assertEqual(variables["apiDigest"], f'${{{{ imageFrom("{API}")?.Digest ?? "" }}}}')
        self.assertEqual(variables["shellDigest"], f'${{{{ imageFrom("{SHELL}")?.Digest ?? "" }}}}')
        for name in ("api", "shell"):
            self.assertEqual(
                variables[f"{name}Tag"],
                f'${{{{ vars.{name}Digest == "" ? vars.commit : vars.commit + "@" + vars.{name}Digest }}}}',
            )

    def test_product_connector_and_shell_promote_the_same_source_in_order(self):
        stage = load("projects/helivanta/stages/prod.yaml")
        steps = stage["spec"]["promotionTemplate"]["spec"]["steps"]
        apps = [app for step in steps for app in step["config"]["apps"]]
        self.assertEqual([
            (app["name"], app["sources"][0]["helm"]["images"]) for app in apps
        ], [
            # The Global API and the migrate hook run from the API image.
            ("helivanta-api", [{"key": "image.tag", "value": "${{ vars.apiTag }}"}]),
            ("helivanta-global-api", [{"key": "image.tag", "value": "${{ vars.apiTag }}"}]),
            ("helivanta-shell", [{"key": "image.tag", "value": "${{ vars.shellTag }}"}]),
        ])


if __name__ == "__main__":
    unittest.main()
