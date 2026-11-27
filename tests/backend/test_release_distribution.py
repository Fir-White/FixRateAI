"""Package integrity and data-preservation behavior, without fake install claims."""
import io
import json
from pathlib import Path
import tarfile
from zipfile import ZipFile

import pytest

from scripts.release_package import build,verify
from scripts.release_runtime import files_export,files_restore
from scripts.release_publish import validate_release_environment


def package(path,**changes):
    values=dict(version='0.1.0',source_sha='a'*40,app_image='ghcr.io/example/app@sha256:'+'1'*64,
        web_image='ghcr.io/example/web@sha256:'+'2'*64,channel='test',allow_dirty=True)
    values.update(changes)
    return build(path,**values)


def test_single_file_payloads_are_deterministic_and_verify(tmp_path):
    a,b=tmp_path/'a',tmp_path/'b'
    package(a);package(b)
    assert verify(a) and verify(b)
    for name in ('FixRateAI-Setup.ps1','fixrate-install.sh','release-manifest.json','SHA256SUMS'):
        assert (a/name).read_bytes()==(b/name).read_bytes()


def test_quick_start_contains_only_verified_public_inputs(tmp_path):
    package(tmp_path)
    archive=tmp_path/'FixRateAI-QuickStart-0.1.0.zip'
    with ZipFile(archive) as bundle:
        assert set(bundle.namelist())=={'README.md','.env.example','compose.yaml','compose.cloud.yaml','images.env',
                                      'release.json','SHA256SUMS'}
        sample=bundle.read('.env.example').decode()
        assert 'POSTGRES_PASSWORD=\n' in sample and 'FIXRATE_BOOTSTRAP_TOKEN_SHA256=\n' in sample
        assert 'FIXRATE_BIND=127.0.0.1' in sample
        assert b'@sha256:' in bundle.read('images.env')
        assert b'FIXRATE_ASSISTANT_AGENT_VERSION:-v4' in bundle.read('compose.yaml')
        assert b'${AITUNNEL_API_KEY:?' in bundle.read('compose.cloud.yaml')
        assert b'compose.cloud.yaml' in bundle.read('SHA256SUMS')
        assert b'.env.example' in bundle.read('SHA256SUMS')
    assert archive.name in (tmp_path/'SHA256SUMS').read_text()
    archive.write_bytes(archive.read_bytes()+b'unexpected')
    with pytest.raises(ValueError,match='checksum'):
        verify(tmp_path)


def test_package_tampering_and_unsafe_image_metadata_are_rejected(tmp_path):
    package(tmp_path)
    (tmp_path/'fixrate-install.sh').write_text('tampered',encoding='utf-8')
    with pytest.raises(ValueError):verify(tmp_path)
    with pytest.raises(ValueError):package(tmp_path/'other',version='../../release')
    with pytest.raises(ValueError):package(tmp_path/'tags',channel='release',app_image='app:latest')
    with pytest.raises(ValueError,match='Dirty source'):
        package(tmp_path/'dirty',channel='release')
    assert 'Test package only' in (tmp_path/'RELEASE-NOTES.md').read_text(encoding='utf-8')


def test_database_major_and_upgrade_allowlist_are_explicit(tmp_path):
    result=package(tmp_path,compatible_from=['0.0.9'])
    assert result['database_major']==18 and result['compatible_from']==['0.0.9']
    assert result['schema_migration']==max(path.name for path in Path('database/migrations').glob('*.sql'))
    assert json.loads((tmp_path/'release-manifest.json').read_text())['images_pinned']


def test_release_publication_requires_independent_review_and_no_admin_bypass():
    for value in ({},{'protection_rules':[]},{'can_admins_bypass':True,'protection_rules':[{'type':'required_reviewers','reviewers':[{'id':1}],'prevent_self_review':True}]}):
        with pytest.raises(ValueError):validate_release_environment(value)
    validate_release_environment({'can_admins_bypass':False,'protection_rules':[{'type':'required_reviewers','reviewers':[{'id':1}],'prevent_self_review':True}]})


def test_file_backup_restores_bytes_into_another_environment(tmp_path):
    original=tmp_path/'original';original.mkdir()
    (original/'photo.jpg').write_bytes(bytes(range(256))*20)
    (original/'nested').mkdir();(original/'nested/report.pdf').write_bytes(b'private test fixture\x00\xff')
    stream=io.BytesIO();files_export(original,stream);stream.seek(0)
    restored=tmp_path/'restored';restored.mkdir();(restored/'obsolete').write_text('old')
    files_restore(restored,stream)
    assert not (restored/'obsolete').exists()
    for path in original.rglob('*'):
        if path.is_file():assert path.read_bytes()==(restored/path.relative_to(original)).read_bytes()


@pytest.mark.parametrize('name,kind',[('../escape',tarfile.REGTYPE),('/absolute',tarfile.REGTYPE),('link',tarfile.SYMTYPE)])
def test_malicious_backup_does_not_touch_existing_files(tmp_path,name,kind):
    root=tmp_path/'files';root.mkdir();(root/'keep').write_text('unchanged')
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w:gz') as archive:
        item=tarfile.TarInfo(name);item.type=kind;item.linkname='../escape';archive.addfile(item)
    stream.seek(0)
    with pytest.raises(ValueError):files_restore(root,stream)
    assert (root/'keep').read_text()=='unchanged'
