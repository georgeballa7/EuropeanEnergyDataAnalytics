import io
import json
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from src.ingestion.ingestion_state import IngestionState
from src.ingestion import run_ingestion as ingestion


def make_state():
    state = IngestionState.__new__(IngestionState)
    state.bucket_name = "test-bucket"
    state.s3 = MagicMock()
    return state


def aws_error(code):
    return ClientError({"Error": {"Code": code, "Message": "test"}}, "GetObject")


def test_missing_state_triggers_initial_load():
    state = make_state()
    state.s3.get_object.side_effect = aws_error("NoSuchKey")
    assert state.get_last_source_date("generation") is None


def test_access_denied_is_not_swallowed():
    state = make_state()
    state.s3.get_object.side_effect = aws_error("AccessDenied")
    with pytest.raises(ClientError):
        state.get_last_source_date("generation")


def test_existing_state_is_read_from_s3():
    state = make_state()
    state.s3.get_object.return_value = {
        "Body": io.BytesIO(b'{"last_source_date":"2026-08-01"}')
    }
    assert state.get_last_source_date("generation") == "2026-08-01"
    state.s3.get_object.assert_called_once_with(
        Bucket="test-bucket", Key="control/ember/generation.json"
    )


def test_state_update_writes_expected_json():
    state = make_state()
    state.update("generation", "2026-09-01")
    kwargs = state.s3.put_object.call_args.kwargs
    assert kwargs["Bucket"] == "test-bucket"
    assert kwargs["Key"] == "control/ember/generation.json"
    assert kwargs["ContentType"] == "application/json"
    assert json.loads(kwargs["Body"]) == {
        "dataset": "generation", "last_source_date": "2026-09-01"
    }


@pytest.fixture
def ingestion_dependencies(monkeypatch):
    config = {
        "countries": ["DEU"],
        "datasets": {
            "generation": {"endpoint": "generation", "api_dataset": "electricity-generation"}
        },
        "source": {"start_date": "2015-01"},
        "project": {"bucket": "test-bucket", "region": "eu-central-1"},
        "aws": {"profile_name": None},
        "storage": {"bronze_prefix": "bronze/ember"},
    }
    client, writer, state = MagicMock(), MagicMock(), MagicMock()
    client.get_latest_available_date.return_value = "2026-09-01"
    state.get_last_source_date.return_value = "2026-08-01"
    client.fetch_dataset.return_value = {
        "data": [{"entity_code": "DEU"}],
        "stats": {"query_value_range": {"date": {"max": "2026-09-01"}}},
    }
    writer.upload_raw_json.return_value = "s3://test-bucket/bronze/ember/generation/test.json"
    monkeypatch.setattr(ingestion, "load_config", lambda: config)
    monkeypatch.setattr(ingestion, "EmberClient", lambda: client)
    monkeypatch.setattr(ingestion, "S3Writer", lambda **kwargs: writer)
    monkeypatch.setattr(ingestion, "IngestionState", lambda **kwargs: state)
    return client, writer, state


def test_no_new_month_skips_download_and_upload(ingestion_dependencies):
    client, writer, state = ingestion_dependencies
    state.get_last_source_date.return_value = "2026-09-01"
    ingestion.run_ingestion()
    client.fetch_dataset.assert_not_called()
    writer.upload_raw_json.assert_not_called()
    state.update.assert_not_called()


def test_failed_bronze_upload_does_not_advance_state(ingestion_dependencies):
    client, writer, state = ingestion_dependencies
    writer.upload_raw_json.side_effect = RuntimeError("S3 upload failed")
    with pytest.raises(RuntimeError, match="S3 upload failed"):
        ingestion.run_ingestion()
    state.update.assert_not_called()


def test_empty_api_response_does_not_advance_state(ingestion_dependencies):
    client, writer, state = ingestion_dependencies
    client.fetch_dataset.return_value = {"data": []}
    ingestion.run_ingestion()
    writer.upload_raw_json.assert_not_called()
    state.update.assert_not_called()


def test_successful_upload_advances_state_after_write(ingestion_dependencies):
    client, writer, state = ingestion_dependencies
    calls = []
    writer.upload_raw_json.side_effect = lambda **kwargs: (
        calls.append("upload") or "s3://test-bucket/bronze/ember/generation/test.json"
    )
    state.update.side_effect = lambda **kwargs: calls.append("state")
    ingestion.run_ingestion()
    assert calls == ["upload", "state"]
    assert client.fetch_dataset.call_args.kwargs["start_date"] == "2026-09-01"
    state.update.assert_called_once_with(
        dataset="generation", last_source_date="2026-09-01"
    )


def test_missing_api_date_rejects_response_without_state_change(ingestion_dependencies):
    client, writer, state = ingestion_dependencies
    client.fetch_dataset.return_value = {"data": [{"entity_code": "DEU"}], "stats": {}}
    with pytest.raises(ValueError, match="Kein Quelldatum"):
        ingestion.run_ingestion()
    writer.upload_raw_json.assert_not_called()
    state.update.assert_not_called()
