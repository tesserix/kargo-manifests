from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]


class QuestionnaireDelivery(unittest.TestCase):
    def test_public_and_console_images_resolve_the_verified_freight_digest(self):
        stage = yaml.safe_load((ROOT / 'projects/tesserix-home/stages/prod.yaml').read_text())
        apps = stage['spec']['promotionTemplate']['spec']['steps'][0]['config']['apps']
        for name in ('company', 'console'):
            app = next(a for a in apps if a['name'] == name)
            value = next(i['value'] for i in app['sources'][0]['helm']['images'] if i['key'] == 'image.tag')
            self.assertIn('.Tag + "@" + ', value, name)
            self.assertIn('.Digest', value, name)
            self.assertNotIn('ghcr.io/', value, name)

    def test_platform_api_keeps_its_existing_promotion_contract(self):
        stage = yaml.safe_load((ROOT / 'projects/tesserix-home/stages/prod.yaml').read_text())
        apps = stage['spec']['promotionTemplate']['spec']['steps'][0]['config']['apps']
        api = next(a for a in apps if a['name'] == 'platform-api')
        value = next(i['value'] for i in api['sources'][0]['helm']['images'] if i['key'] == 'image.tag')
        self.assertNotIn('.Digest', value)
