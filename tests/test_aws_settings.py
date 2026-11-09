"""Phase B: AWS-Konfiguration und Credential-Chain der Transformationen."""

from unittest.mock import MagicMock

import pytest

from config import settings
from src.catalog import glue_catalog
from src.transformation import run_gold_transformation, run_silver_transformation


def test_aws_settings_come_from_yaml(monkeypatch):
    monkeypatch.setattr(settings, "load_config", lambda: {
        "project": {"bucket": "test-bucket", "region": "eu-west-1"}
    })
    assert settings.get_aws_settings() == ("test-bucket", "eu-west-1")


def test_transformation_and_catalog_use_the_same_project_settings():
    bucket, region = settings.get_aws_settings()
    for module in (run_silver_transformation, run_gold_transformation, glue_catalog):
        assert module.BUCKET_NAME == bucket
        assert module.REGION_NAME == region


@pytest.mark.parametrize("module", [run_silver_transformation, run_gold_transformation])
def test_s3_client_does_not_force_local_profile(monkeypatch, module):
    session = MagicMock()
    factory = MagicMock(return_value=session)
    monkeypatch.setattr(module.boto3, "Session", factory)
    assert module.get_s3_client() is session.client.return_value
    factory.assert_called_once_with(region_name=module.REGION_NAME)
    session.client.assert_called_once_with("s3")


def test_glue_client_without_explicit_profile_uses_credential_chain(monkeypatch):
    session = MagicMock()
    factory = MagicMock(return_value=session)
    monkeypatch.setattr(glue_catalog.boto3, "Session", factory)
    glue_catalog.get_glue_client()
    factory.assert_called_once_with(region_name=glue_catalog.REGION_NAME)
    session.client.assert_called_once_with("glue")


def test_glue_client_can_still_use_explicit_profile(monkeypatch):
    session = MagicMock()
    factory = MagicMock(return_value=session)
    monkeypatch.setattr(glue_catalog.boto3, "Session", factory)
    glue_catalog.get_glue_client(aws_profile="local-profile")
    factory.assert_called_once_with(profile_name="local-profile", region_name=glue_catalog.REGION_NAME)
