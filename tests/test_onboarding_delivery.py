from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]


class OnboardingDeliveryTests(unittest.TestCase):
    def test_warehouse_only_discovers_publish_complete_commits(self):
        warehouse = yaml.safe_load((ROOT / 'projects/onboarding/warehouses/services.yaml').read_text())
        sub = warehouse['spec']['subscriptions']
        self.assertEqual(len(sub), 1)
        self.assertEqual(sub[0]['git']['branch'], 'deploy')
        self.assertEqual(sub[0]['git']['repoURL'], 'https://github.com/tesserix/onboarding-service.git')

    def test_only_retained_api_is_promoted(self):
        stage = yaml.safe_load((ROOT / 'projects/onboarding/stages/prod.yaml').read_text())
        promotion = stage['spec']['promotionTemplate']['spec']
        variables = {v['name']: v['value'] for v in promotion['vars']}
        self.assertIn('commitFrom("https://github.com/tesserix/onboarding-service.git").ID', variables['imageTag'])
        self.assertIn('sha-', variables['imageTag'])
        apps = promotion['steps'][0]['config']['apps']
        self.assertEqual([app['name'] for app in apps], ['onboarding-service'])
        images = apps[0]['sources'][0]['helm']['images']
        self.assertEqual({i['key'] for i in images}, {'api.image.tag', 'api.image.repository'})
        self.assertTrue(all(i['value'] == '${{ vars.imageTag }}' for i in images if i['key'].endswith('.tag')))

    def test_recovery_registry_is_scoped_to_one_verified_commit(self):
        stage = yaml.safe_load((ROOT / 'projects/onboarding/stages/prod.yaml').read_text())
        promotion = stage['spec']['promotionTemplate']['spec']
        variables = {v['name']: v['value'] for v in promotion['vars']}
        registry = variables['imageRegistry']
        self.assertIn('== "ad0f3a5dbd4be1006db0db1988eb3cc976a88c42"', registry)
        self.assertIn('? "asia-south1-docker.pkg.dev/tesseracthub-480811/global"', registry)
        self.assertIn(': "asia-south1-docker.pkg.dev/tesseracthub-480811/ghcr-remote/tesserix"', registry)
        images = promotion['steps'][0]['config']['apps'][0]['sources'][0]['helm']['images']
        values = {i['key']: i['value'] for i in images}
        for name in ['api']:
            self.assertEqual(values[f'{name}.image.repository'], '${{ vars.imageRegistry }}/onboarding-' + name)

    def test_project_and_stage_share_namespace_and_auto_promotion(self):
        resources = list(yaml.safe_load_all((ROOT / 'projects/onboarding/project.yaml').read_text()))
        by_kind = {r['kind']: r for r in resources}
        self.assertEqual(by_kind['Namespace']['metadata']['name'], 'kargo-onboarding')
        self.assertEqual(by_kind['Project']['metadata']['name'], 'kargo-onboarding')
        self.assertTrue(by_kind['ProjectConfig']['spec']['promotionPolicies'][0]['autoPromotionEnabled'])


if __name__ == '__main__':
    unittest.main()
