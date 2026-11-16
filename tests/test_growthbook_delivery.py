import unittest
import base64
import os
import json
import subprocess
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

class HelivantaGrowthBookDeliveryTests(unittest.TestCase):
    def test_dedicated_stage_cannot_modify_shared_provider_or_chart_defaults(self):
        stage = resource('projects/infra/stages/helivanta-growthbook-prod.yaml')
        steps = stage['spec']['promotionTemplate']['spec']['steps']
        updates = [step['config'] for step in steps if step['uses'] == 'yaml-update']
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0]['path'], './repo/argocd/prod/apps/helivanta/helivanta-growthbook.yaml')
        self.assertEqual({row['key'] for row in updates[0]['updates']}, {'spec.source.helm.parameters.0.value', 'spec.source.helm.parameters.1.value'})
        self.assertEqual(stage['spec']['requestedFreight'][0]['origin']['name'], 'growthbook')
        sync = next(step for step in steps if step['uses'] == 'argocd-update')
        self.assertEqual(sync['config']['apps'][0]['name'], 'helivanta-growthbook')
        self.assertEqual(steps[-1]['config']['apps'][0]['name'], 'helivanta-growthbook')

    def test_initial_request_uses_stage_scoped_authority_and_pinned_freight(self):
        docs = list(yaml.safe_load_all((ROOT / 'projects/infra/promotions/helivanta-growthbook-bootstrap-20261116.yaml').read_text()))
        role = next(doc for doc in docs if doc['kind'] == 'Role')
        self.assertEqual(role['rules'][0]['resourceNames'], ['helivanta-growthbook-prod'])
        self.assertEqual(role['rules'][0]['verbs'], ['get', 'promote'])
        job = next(doc for doc in docs if doc['kind'] == 'Job')
        spec = job['spec']['template']['spec']
        self.assertFalse(spec['automountServiceAccountToken'])
        container = spec['containers'][0]
        self.assertIn('@sha256:', container['image'])
        script = container['args'][0]
        self.assertIn('8006e0409c0b829cfebbad10e9366273a67b52d3', script)
        self.assertIn('steps:stage.spec.promotionTemplate.spec.steps', script)
        self.assertIn("metadata:{namespace:'kargo-infra',annotations:", script)
        self.assertNotIn('rejectUnauthorized:false', script)

    def test_recovery_is_limited_to_the_two_archived_malformed_records(self):
        docs = list(yaml.safe_load_all((ROOT / 'projects/infra/promotions/helivanta-growthbook-recovery-20261116.yaml').read_text()))
        role = next(doc for doc in docs if doc['kind'] == 'Role')
        self.assertEqual(role['rules'][0]['verbs'], ['get', 'patch', 'delete'])
        self.assertEqual(role['rules'][0]['resourceNames'], ['helivanta-growthbook-prod.bootstrap-20261116', 'helivanta-growthbook-bootstrap-d5a84e8-sync-1794831055'])
        self.assertEqual(role['rules'][1]['resourceNames'], ['helivanta-growthbook-prod'])
        self.assertEqual(role['rules'][1]['verbs'], ['promote'])
        job = next(doc for doc in docs if doc['kind'] == 'Job')
        script = job['spec']['template']['spec']['containers'][0]['args'][0]
        self.assertIn("await request('DELETE','promotions/'+encodeURIComponent(name))", script)
        self.assertNotIn("request('POST'", script)


class HelivantaPromotionFinalizerTests(unittest.TestCase):
    def run_case(self, assertions, source_file="helivanta-growthbook-finalize-20261117.yaml"):
        docs = list(yaml.safe_load_all((ROOT / 'projects/infra/promotions' / source_file).read_text()))
        job = next(doc for doc in docs if doc['kind'] == 'Job')
        source = job['spec']['template']['spec']['containers'][0]['args'][0]
        module = 'data:text/javascript;base64,' + base64.b64encode(source.encode()).decode()
        code = "import assert from 'node:assert/strict'; const {finalizeApprovedPromotions,approvedTargets}=await import(" + json.dumps(module) + ");" + assertions
        result = subprocess.run(['node', '--input-type=module', '-'], input=code, text=True, capture_output=True, env={**os.environ, 'HELIVANTA_FINALIZE_RUN': 'false'})
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_removes_only_the_archived_uid_hook_finalizer_and_verifies_deletion(self):
        self.run_case("""
          let patched=false;const calls=[];const target=approvedTargets[1];
          await finalizeApprovedPromotions(async(method,path,body)=>{
            calls.push({method,path,body});
            if(path.endsWith(approvedTargets[0].name))return null;
            assert.ok(path.endsWith(target.name));
            if(method==='GET')return patched?null:{spec:{stage:'helivanta-growthbook-prod'},metadata:{uid:target.uid,resourceVersion:'17',deletionTimestamp:'2026-11-16T22:12:26Z',finalizers:['argocd.argoproj.io/hook-finalizer']}};
            assert.equal(method,'PATCH');
            assert.deepEqual(body,[{op:'test',path:'/metadata/uid',value:target.uid},{op:'test',path:'/metadata/resourceVersion',value:'17'},{op:'test',path:'/metadata/finalizers',value:['argocd.argoproj.io/hook-finalizer']},{op:'replace',path:'/metadata/finalizers',value:[]}]);patched=true;return {};
          });
          assert.equal(calls.filter(row=>row.method==='PATCH').length,1);
          assert.equal(calls.at(-1).method,'GET');
        """)

    def test_recreated_record_or_unexpected_finalizer_fails_closed(self):
        self.run_case("""
          for(const scenario of ['uid','stage','finalizer']) {
            await assert.rejects(finalizeApprovedPromotions(async(method)=>{
              assert.equal(method,'GET');return {spec:{stage:scenario==='stage'?'another-stage':'helivanta-growthbook-prod'},metadata:{uid:scenario==='uid'?'another-object':approvedTargets[0].uid,resourceVersion:'17',deletionTimestamp:'now',finalizers:['another-controller/retention']}};
            }),/Unexpected approved record|Unexpected finalizer/);
          }
        """)

    def test_already_removed_records_are_an_idempotent_read_only_success(self):
        self.run_case("""
          let count=0;await finalizeApprovedPromotions(async(method)=>{assert.equal(method,'GET');count++;return null;});assert.equal(count,2);
        """)


    def test_name_repair_preflights_the_exact_uid_before_finalization(self):
        self.run_case("""
          let patched=false;const calls=[];const target=approvedTargets[1];
          await finalizeApprovedPromotions(async(method,path,body)=>{
            calls.push({method,path,body});
            const key=path.split('?')[0];
            if(key.endsWith(approvedTargets[0].name))return null;
            assert.ok(key.endsWith(target.name));
            if(method==='GET')return patched?null:{spec:{stage:'helivanta-growthbook-prod'},metadata:{name:target.objectName,uid:target.uid,resourceVersion:'17',deletionTimestamp:'now',finalizers:['argocd.argoproj.io/hook-finalizer']}};
            assert.equal(method,'PATCH');
            assert.deepEqual(body,[{op:'test',path:'/metadata/uid',value:target.uid},{op:'test',path:'/metadata/resourceVersion',value:'17'},{op:'test',path:'/metadata/finalizers',value:['argocd.argoproj.io/hook-finalizer']},{op:'test',path:'/metadata/name',value:target.objectName},{op:'replace',path:'/metadata/name',value:target.name},{op:'replace',path:'/metadata/finalizers',value:[]}]);
            if(!path.includes('?dryRun=All'))patched=true;
            return {};
          });
          const writes=calls.filter(row=>row.method==='PATCH');assert.equal(writes.length,2);assert.ok(writes[0].path.endsWith('?dryRun=All'));assert.ok(!writes[1].path.includes('?'));assert.equal(calls.at(-1).method,'GET');
        """,source_file='helivanta-growthbook-finalize-name-20261117.yaml')


def test_reconciliation_repromotes_the_verified_patch_without_new_privileges():
    job = resource("projects/infra/promotions/helivanta-growthbook-reconcile-20261117.yaml")
    assert job["kind"] == "Job"
    spec = job["spec"]["template"]["spec"]
    assert spec["serviceAccountName"] == "helivanta-growthbook-promoter"
    assert spec["automountServiceAccountToken"] is False
    container = spec["containers"][0]
    assert container["image"] == "growthbook/growthbook:5.2.1@sha256:0da8afcb9ed92d8e09abca3ea9d9531e29b7e39b0bccba03d9a3d4cc47f1f60d"
    script = container["args"][0]
    assert "20261117-reconcile" in script
    assert "freight:'4f99919758a9c5e15c3f65bc9f416870dbb062aa'" in script
    assert "steps:stage.spec.promotionTemplate.spec.steps" in script
    assert "metadata:{namespace:'kargo-infra',annotations:" in script
    assert "metadata:{name:" not in script
    assert "rejectUnauthorized:false" not in script


def test_dedicated_provider_pins_the_promoted_chart_revision():
    stage = resource("projects/infra/stages/helivanta-growthbook-prod.yaml")
    step = next(row for row in stage["spec"]["promotionTemplate"]["spec"]["steps"] if row["uses"] == "argocd-update")
    assert step["config"]["apps"][0]["sources"][0]["updateTargetRevision"] is True
