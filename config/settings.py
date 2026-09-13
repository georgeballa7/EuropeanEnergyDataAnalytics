from pathlib import Path

import yaml


CONFIG_PATH = Path(__file__).parent / "series_config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)