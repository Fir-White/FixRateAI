"""Real RF loading and rejection before deserialization of incompatible manifests."""
import json
from pathlib import Path
import shutil
import pytest
from ml_service.app.core.config import settings
from ml_service.app.forecast.runtime import load_verified_forecaster


def test_packaged_rf_is_loaded_with_its_manifest():
    model=load_verified_forecaster()
    manifest=json.loads((settings.artifacts_path/'artifact_manifest.json').read_text(encoding='utf-8'))
    assert model.is_fitted and model.artifact_sha256==manifest['artifact_sha256']


@pytest.mark.parametrize('field,value',[('schema_version','future-99'),('method_version','unknown'),
    ('feature_schema_version','rf-features-v999'),('data_origin','customer'),('model_ref','unknown'),
    ('artifact_sha256','0'*64)])
def test_incompatible_manifest_is_rejected_before_joblib_loading(tmp_path,monkeypatch,field,value):
    shutil.copyfile(settings.artifacts_path/'rf_model.joblib',tmp_path/'rf_model.joblib')
    manifest=json.loads((settings.artifacts_path/'artifact_manifest.json').read_text(encoding='utf-8'))
    manifest[field]=value
    (tmp_path/'artifact_manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    def forbidden(*args): pytest.fail('Incompatible manifest reached deserialization')
    monkeypatch.setattr('ml_service.app.forecast.runtime.RandomForestForecaster.from_file',forbidden)
    with pytest.raises(ValueError,match='incompatible'):
        load_verified_forecaster(tmp_path)
