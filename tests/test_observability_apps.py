import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


class ObservabilityAppsPromotionTest(unittest.TestCase):
    def test_discovery_ignores_broken_historical_manifests(self):
        warehouse = yaml.safe_load(
            (ROOT / "projects/infra/warehouses/observability-apps.yaml").read_text()
        )

        for subscription in warehouse["spec"]["subscriptions"]:
            self.assertEqual(subscription["image"]["discoveryLimit"], 1)

    def test_promotion_uses_a_protected_branch_pull_request(self):
        stage = yaml.safe_load(
            (ROOT / "projects/infra/stages/observability-apps-prod.yaml").read_text()
        )
        steps = stage["spec"]["promotionTemplate"]["spec"]["steps"]
        by_name = {step.get("as", step["uses"]): step for step in steps}

        self.assertTrue(by_name["push"]["config"]["generateTargetBranch"])
        self.assertEqual(by_name["open-pr"]["uses"], "git-open-pr")
        self.assertEqual(by_name["merge-pr"]["uses"], "git-merge-pr")
        self.assertTrue(by_name["merge-pr"]["config"]["wait"])
        self.assertEqual(
            by_name["argocd-update"]["config"]["apps"][0]["sources"][0][
                "desiredRevision"
            ],
            "${{ outputs['merge-pr'].commit }}",
        )


if __name__ == "__main__":
    unittest.main()
