from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


class IstioDeliveryTests(unittest.TestCase):
    def test_every_gateway_is_updated_and_ambient_components_sync_in_order(self):
        stage = yaml.safe_load(
            (ROOT / "projects/infra/stages/istio-prod.yaml").read_text()
        )
        steps = stage["spec"]["promotionTemplate"]["spec"]["steps"]
        updates = {
            step["config"]["path"]: step
            for step in steps
            if step["uses"] == "yaml-update"
        }
        self.assertIn(
            "./repo/argocd/prod/infrastructure/zitadel-ingress-gateway.yaml", updates
        )
        shared = updates.get(
            "./repo/argocd/prod/infrastructure/istio-ingress-gateway.yaml"
        )
        self.assertIsNotNone(shared)
        self.assertIn(
            "spec.source.helm.valuesObject.podAnnotations.istioUpgradeVersion",
            [u["key"] for u in shared["config"]["updates"]],
        )
        syncs = [
            step["config"]["apps"] for step in steps if step["uses"] == "argocd-update"
        ]
        self.assertEqual(
            [[app["name"] for app in apps] for apps in syncs[:4]],
            [["istio-base"], ["istio-istiod"], ["istio-cni"], ["istio-ztunnel"]],
        )
        self.assertEqual(
            {app["name"] for app in syncs[4]},
            {
                "istio-egress-gateway",
                "istio-ingress-gateway",
                "istio-ingress-gateway-internal",
                "custom-ingress-gateway",
                "homechef-ingress-gateway",
                "zitadel-ingress-gateway",
            },
        )

    def test_minor_upgrade_requires_manual_promotion(self):
        docs = list(
            yaml.safe_load_all((ROOT / "projects/infra/project.yaml").read_text())
        )
        config = next(doc for doc in docs if doc["kind"] == "ProjectConfig")
        policy = next(
            p for p in config["spec"]["promotionPolicies"] if p["stage"] == "istio-prod"
        )
        self.assertFalse(policy["autoPromotionEnabled"])

    def test_patch_discovery_is_limited_to_the_supported_target_minor(self):
        warehouse = yaml.safe_load(
            (ROOT / "projects/infra/warehouses/istio.yaml").read_text()
        )
        for subscription in warehouse["spec"]["subscriptions"]:
            self.assertEqual(
                subscription["chart"]["semverConstraint"], ">=1.31.4 <1.32.0"
            )

    def test_production_waits_for_a_reviewed_pr_before_checking_health(self):
        stage = yaml.safe_load(
            (ROOT / "projects/infra/stages/istio-prod.yaml").read_text()
        )
        steps = stage["spec"]["promotionTemplate"]["spec"]["steps"]
        push = next(step for step in steps if step["uses"] == "git-push")
        self.assertTrue(push["config"].get("generateTargetBranch"))
        self.assertNotIn("targetBranch", push["config"])
        opened = next(step for step in steps if step["uses"] == "git-open-pr")
        waited = next(step for step in steps if step["uses"] == "git-wait-for-pr")
        self.assertEqual(opened["config"]["targetBranch"], "main")
        self.assertEqual(opened["config"]["sourceBranch"], "${{ outputs.push.branch }}")
        self.assertEqual(
            waited["config"]["prNumber"], "${{ outputs['open-pr'].pr.id }}"
        )
        self.assertLess(steps.index(push), steps.index(opened))
        self.assertLess(steps.index(opened), steps.index(waited))
        self.assertNotIn("git-merge-pr", [step["uses"] for step in steps])
        for step in steps:
            if step["uses"].startswith("argocd-"):
                self.assertLess(steps.index(waited), steps.index(step))


if __name__ == "__main__":
    unittest.main()
