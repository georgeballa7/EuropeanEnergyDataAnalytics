"""Lade die zentrale YAML-Konfiguration des Projekts.

Das Modul stellt den Zugriff auf ``config/series_config.yaml`` bereit und
hält damit die technische Konfiguration an einer zentralen Stelle.
"""

from pathlib import Path

import yaml


CONFIG_PATH = Path(__file__).parent / "series_config.yaml"


def load_config() -> dict:
    """
    Lade die Projektkonfiguration aus der YAML-Datei.

    Rückgabe
    --------
    dict
        Eingelesene Projektkonfiguration als Python-Dictionary.
    """
    with open(CONFIG_PATH, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)
