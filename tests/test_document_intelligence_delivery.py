from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
IMAGE = (
    "asia-south1-docker.pkg.dev/tesseracthub-480811/ghcr-remote/"
    "tesserix/document-intelligence/ocr-service"
)


def stage(environment):
    return yaml.safe_load(
        (ROOT / f"projects/document-intelligence/stages/{environment}.yaml").read_text()
    )


class DocumentIntelligenceDeliveryTests(unittest.TestCase):
    def test_ocr_delivery_discovers_and_promotes_the_gar_mirror(self):
        warehouse = yaml.safe_load(
            (ROOT / "projects/document-intelligence/warehouses/services.yaml").read_text()
        )
        self.assertEqual(
            warehouse["spec"]["subscriptions"],
            [
                {
                    "image": {
                        "repoURL": IMAGE,
                        "imageSelectionStrategy": "NewestBuild",
                        "allowTagsRegexes": ["^[a-f0-9]{40}$"],
                        "strictSemvers": False,
                        "discoveryLimit": 5,
                    }
                }
            ],
        )
        for environment in ("sandbox", "prod"):
            tag = stage(environment)["spec"]["promotionTemplate"]["spec"]["vars"][0]["value"]
            self.assertEqual(tag, f'${{{{ imageFrom("{IMAGE}").Tag }}}}', environment)

    def test_prod_promotes_every_document_intelligence_release(self):
        (step,) = stage("prod")["spec"]["promotionTemplate"]["spec"]["steps"]
        apps = {app["name"]: app for app in step["config"]["apps"]}
        self.assertEqual(
            sorted(apps),
            [
                "document-intelligence-homechef-prod",
                "document-intelligence-prod",
                "document-intelligence-roamie-prod",
            ],
        )
        for name, app in apps.items():
            self.assertEqual(
                app["sources"],
                [
                    {
                        "repoURL": "https://github.com/tesserix/tesserix-k8s.git",
                        "helm": {"images": [{"key": "image.tag", "value": "${{ vars.tag }}"}]},
                    }
                ],
                name,
            )
