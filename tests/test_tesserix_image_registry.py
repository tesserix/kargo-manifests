from pathlib import Path
import unittest
import yaml


class TesserixRegistryTests(unittest.TestCase):
    def test_promotions_restore_registry_after_recovery_release(self):
        stage = yaml.safe_load((Path(__file__).resolve().parents[1] / 'projects/tesserix-home/stages/prod.yaml').read_text())
        apps = stage['spec']['promotionTemplate']['spec']['steps'][0]['config']['apps']
        for name in ['console', 'platform-api']:
            app = next(a for a in apps if a['name'] == name)
            images = {i['key']: i['value'] for i in app['sources'][0]['helm']['images']}
            self.assertEqual(f'asia-south1-docker.pkg.dev/tesseracthub-480811/ghcr-remote/tesserix/tesserix-{name}', images.get('image.repository'))
