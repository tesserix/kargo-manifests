from pathlib import Path
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / 'projects/civiclens'


class CivicLensDeliveryTests(unittest.TestCase):
    def test_only_smoke_tested_deploy_tags_can_promote(self):
        warehouse = yaml.safe_load((PROJECT / 'warehouses/services.yaml').read_text())
        image = next(s['image'] for s in warehouse['spec']['subscriptions'] if 'image' in s)
        for tag, allowed in [('deploy-90a2774', True), ('sha-90a2774', False),
                             ('main-90a2774', False), ('latest', False),
                             ('deploy-90a2774-untested', False)]:
            self.assertEqual(any(re.fullmatch(p, tag) for p in image['allowTagsRegexes']), allowed, tag)
        self.assertEqual(image['imageSelectionStrategy'], 'NewestBuild')
        self.assertEqual(image['platform'], 'linux/amd64')

    def test_promotion_moves_repository_tag_and_digest_together(self):
        warehouse = yaml.safe_load((PROJECT / 'warehouses/services.yaml').read_text())
        stage = yaml.safe_load((PROJECT / 'stages/prod.yaml').read_text())
        watched = next(s['image'] for s in warehouse['spec']['subscriptions'] if 'image' in s)
        promotion = stage['spec']['promotionTemplate']['spec']
        variables = {v['name']: v['value'] for v in promotion['vars']}
        self.assertEqual(watched['repoURL'],
                         'asia-south1-docker.pkg.dev/tesseracthub-480811/global/civiclens-api')
        self.assertEqual(watched['repoURL'], variables['imageRepo'])
        apps = promotion['steps'][0]['config']['apps']
        self.assertEqual([(a['name'], a['namespace']) for a in apps], [('civiclens-api', 'argocd')])
        images = {i['key']: i['value'] for i in apps[0]['sources'][0]['helm']['images']}
        self.assertEqual(images, {
            'image.repository': '${{ vars.imageRepo }}',
            'image.tag': '${{ imageFrom(vars.imageRepo).Tag }}',
            'image.digest': '${{ imageFrom(vars.imageRepo).Digest }}',
        })

    def test_chart_changes_create_freight(self):
        warehouse = yaml.safe_load((PROJECT / 'warehouses/services.yaml').read_text())
        git = next(s['git'] for s in warehouse['spec']['subscriptions'] if 'git' in s)
        self.assertEqual(git['repoURL'], 'https://github.com/tesserix/tesserix-k8s.git')
        self.assertIn('regex:^charts/apps/civiclens-api/', git['includePaths'])
        self.assertIn('argocd/prod/apps/civiclens/civiclens-api.yaml', git['includePaths'])

    def test_project_auto_promotes_only_prod(self):
        docs = list(yaml.safe_load_all((PROJECT / 'project.yaml').read_text()))
        config = next(d for d in docs if d['kind'] == 'ProjectConfig')
        self.assertEqual(config['metadata']['namespace'], 'kargo-civiclens')
        self.assertEqual(config['spec']['promotionPolicies'],
                         [{'stage': 'prod', 'autoPromotionEnabled': True}])


if __name__ == '__main__':
    unittest.main()
