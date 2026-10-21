from pathlib import Path
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class RoamieDeliveryTests(unittest.TestCase):
    def test_only_verified_deploy_tags_can_promote(self):
        warehouse = yaml.safe_load(
            (ROOT / 'projects/roamie/warehouses/services.yaml').read_text()
        )
        image = next(s['image'] for s in warehouse['spec']['subscriptions'] if 'image' in s)
        patterns = image['allowTagsRegexes']
        for tag, allowed in [('deploy-b1a3469', True), ('sha-b1a3469', False),
                             ('main-b1a3469', False), ('latest', False),
                             ('deploy-b1a3469-untested', False)]:
            self.assertEqual(any(re.fullmatch(p, tag) for p in patterns), allowed, tag)

    def test_registry_switch_promotes_repository_tag_and_digest_together(self):
        warehouse = yaml.safe_load(
            (ROOT / 'projects/roamie/warehouses/services.yaml').read_text()
        )
        stage = yaml.safe_load((ROOT / 'projects/roamie/stages/prod.yaml').read_text())
        watched = next(s['image'] for s in warehouse['spec']['subscriptions'] if 'image' in s)
        promotion = stage['spec']['promotionTemplate']['spec']
        variables = {v['name']: v['value'] for v in promotion['vars']}
        self.assertEqual(watched['repoURL'], variables['imageRepo'])
        apps = promotion['steps'][0]['config']['apps']
        self.assertEqual([app['name'] for app in apps], ['roamie-api'])
        images = {i['key']: i['value'] for i in apps[0]['sources'][0]['helm']['images']}
        self.assertEqual(images, {
            'image.repository': '${{ vars.imageRepo }}',
            'image.tag': '${{ imageFrom(vars.imageRepo).Tag }}',
            'image.digest': '${{ imageFrom(vars.imageRepo).Digest }}',
        })
