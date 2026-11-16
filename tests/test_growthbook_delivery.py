import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "docker.io/growthbook/growthbook"


def resource(path):
    return yaml.safe_load((ROOT / path).read_text())


class GrowthBookDeliveryTests(unittest.TestCase):
    def test_discovers_only_supported_stable_patches_in_an_independent_lane(self):
        warehouse = resource("projects/infra/warehouses/growthbook.yaml")
        self.assertEqual(warehouse["metadata"]["namespace"], "kargo-infra")
        self.assertEqual(len(warehouse["spec"]["subscriptions"]), 1)
        image = warehouse["spec"]["subscriptions"][0]["image"]
        self.assertEqual(image["repoURL"], IMAGE)
        self.assertEqual(image["imageSelectionStrategy"], "SemVer")
        self.assertEqual(image["semverConstraint"], ">=5.2.0 <5.3.0")
        self.assertEqual(image["allowTagsRegexes"], [r"^[0-9]+\.[0-9]+\.[0-9]+$"])

    def test_promotes_the_same_version_and_digest_to_the_effective_helm_values(self):
        stage = resource("projects/infra/stages/growthbook-prod.yaml")
        self.assertEqual(
            stage["spec"]["requestedFreight"][0]["origin"]["name"], "growthbook"
        )
        updates = {
            step["config"]["path"]: {
                item["key"]: item["value"] for item in step["config"]["updates"]
            }
            for step in stage["spec"]["promotionTemplate"]["spec"]["steps"]
            if step["uses"] == "yaml-update"
        }
        tag = '${{ imageFrom("' + IMAGE + '").Tag }}'
        digest = '${{ imageFrom("' + IMAGE + '").Digest }}'
        self.assertEqual(
            updates["./repo/argocd/prod/infrastructure/growthbook.yaml"],
            {
                "spec.source.helm.parameters.0.value": tag,
                "spec.source.helm.parameters.1.value": digest,
            },
        )
        self.assertEqual(
            updates["./repo/charts/thirdparty/growthbook/values.yaml"],
            {
                "image.tag": tag,
                "image.digest": digest,
            },
        )
        self.assertEqual(
            updates["./repo/charts/thirdparty/growthbook/Chart.yaml"],
            {"appVersion": tag},
        )
        self.assertEqual(len(updates), 3)

    def test_protected_main_requires_a_merged_proposal_then_argo_health(self):
        stage = resource("projects/infra/stages/growthbook-prod.yaml")
        steps = stage["spec"]["promotionTemplate"]["spec"]["steps"]
        push = next(step for step in steps if step["uses"] == "git-push")
        self.assertTrue(push["config"]["generateTargetBranch"])
        self.assertNotIn("targetBranch", push["config"])
        self.assertNotIn("force", push["config"])
        proposal = next(step for step in steps if step["uses"] == "git-open-pr")
        self.assertEqual(proposal["config"]["targetBranch"], "main")
        self.assertEqual(
            proposal["config"]["sourceBranch"], "${{ outputs.push.branch }}"
        )
        self.assertIn("git-wait-for-pr", [step["uses"] for step in steps])
        sync = next(step for step in steps if step["uses"] == "argocd-update")
        app = sync["config"]["apps"][0]
        self.assertEqual(app["name"], "growthbook")
        self.assertIn(
            "outputs['wait-for-pr'].commit", app["sources"][0]["desiredRevision"]
        )
        self.assertFalse(app["sources"][0].get("updateTargetRevision", False))
        self.assertEqual(steps[-1]["uses"], "argocd-wait")
        self.assertEqual(
            set(steps[-1]["config"]["apps"][0]["waitFor"]),
            {"health", "sync", "operation"},
        )

    def test_automatic_proposals_do_not_share_freight_with_other_tools(self):
        project = list(
            yaml.safe_load_all((ROOT / "projects/infra/project.yaml").read_text())
        )
        config = next(item for item in project if item["kind"] == "ProjectConfig")
        policy = next(
            p
            for p in config["spec"]["promotionPolicies"]
            if p["stage"] == "growthbook-prod"
        )
        self.assertTrue(policy["autoPromotionEnabled"])
        stage = resource("projects/infra/stages/growthbook-prod.yaml")
        self.assertEqual(len(stage["spec"]["requestedFreight"]), 1)
