from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
IMAGE = (
    "asia-south1-docker.pkg.dev/tesseracthub-480811/ghcr-remote/"
    "tesserix/document-intelligence/ocr-service"
)


def test_ocr_delivery_discovers_and_promotes_the_gar_mirror() -> None:
    warehouse = yaml.safe_load(
        (ROOT / "projects/document-intelligence/warehouses/services.yaml").read_text()
    )
    assert warehouse["spec"]["subscriptions"] == [
        {
            "image": {
                "repoURL": IMAGE,
                "imageSelectionStrategy": "NewestBuild",
                "allowTagsRegexes": ["^[a-f0-9]{40}$"],
                "strictSemvers": False,
                "discoveryLimit": 5,
            }
        }
    ]

    for environment in ("sandbox", "prod"):
        stage = yaml.safe_load(
            (ROOT / f"projects/document-intelligence/stages/{environment}.yaml").read_text()
        )
        tag = stage["spec"]["promotionTemplate"]["spec"]["vars"][0]["value"]
        assert tag == f'${{{{ imageFrom("{IMAGE}").Tag }}}}'
