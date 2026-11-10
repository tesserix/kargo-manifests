from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]


class ZitadelOperatorPromotionTests(unittest.TestCase):
    def test_operator_promotion_pins_the_freight_digest_for_the_original_image(self):
        stage = yaml.safe_load((ROOT / "projects/zitadel-operator/stages/prod.yaml").read_text())
        steps = stage["spec"]["promotionTemplate"]["spec"]["steps"]
        image = next(step for step in steps if step["uses"] == "kustomize-set-image")["config"]["images"][0]
        self.assertEqual(image["image"], "${{ vars.sourceImageName }}")
        self.assertEqual(image["newName"], "${{ vars.imageRepo }}")
        self.assertEqual(image["digest"], "${{ imageFrom(vars.imageRepo).Digest }}")
        self.assertNotIn("tag", image)

    def test_protected_main_is_reached_only_through_a_merged_pull_request(self):
        stage = yaml.safe_load((ROOT / "projects/zitadel-operator/stages/prod.yaml").read_text())
        steps = stage["spec"]["promotionTemplate"]["spec"]["steps"]
        self.assertEqual([step["uses"] for step in steps], ["git-clone", "kustomize-set-image", "git-commit", "git-push", "git-open-pr", "git-wait-for-pr", "argocd-update"])
        push = steps[3]
        self.assertTrue(push["config"]["generateTargetBranch"])
        self.assertNotIn("targetBranch", push["config"])
        self.assertNotIn("force", push["config"])
        self.assertEqual(steps[4]["config"]["targetBranch"], "main")
        self.assertEqual(steps[4]["config"]["sourceBranch"], "${{ outputs.push.branch }}")
        self.assertEqual(steps[5]["config"]["prNumber"], "${{ outputs['open-pr'].pr.id }}")
        source = steps[6]["config"]["apps"][0]["sources"][0]
        self.assertIn("outputs['wait-for-pr'].commit", source["desiredRevision"])

    def test_retries_skip_pr_creation_when_the_reviewed_digest_already_matches(self):
        stage = yaml.safe_load((ROOT / "projects/zitadel-operator/stages/prod.yaml").read_text())
        steps = stage["spec"]["promotionTemplate"]["spec"]["steps"]
        self.assertEqual(steps[0]["as"], "clone")
        condition = "${{ outputs.commit.commit != outputs.clone.commits['./repo'] }}"
        for step in steps:
            if step["uses"] in ["git-push", "git-open-pr", "git-wait-for-pr"]:
                self.assertEqual(step["if"], condition)
        self.assertIn("outputs.commit.commit", steps[-1]["config"]["apps"][0]["sources"][0]["desiredRevision"])
