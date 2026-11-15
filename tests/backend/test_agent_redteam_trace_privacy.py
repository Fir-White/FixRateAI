"""Synthetic free-text values must remain digests even when they resemble IDs."""
from uuid import UUID
import pytest
from app.assistant.read_transport import safe_arguments

@pytest.mark.parametrize('key,value',[
    ('q','f'*36),('name','f'*36),('q','-'*36),
    ('q','12345678-1234-5678-abcd-123456789abc'),('title','12345678-1234-5678-abcd-123456789abc'),
])
def test_free_text_is_never_exposed_as_a_convenient_uuid(key,value):
    result=safe_arguments({'query':{key:value}})['query'][key]
    assert isinstance(result,dict) and result['length']==len(value) and 'sha256' in result

def test_actual_resource_id_remains_available_for_authorized_trace():
    value='12345678-1234-5678-abcd-123456789abc'
    assert safe_arguments({'path':{'equipment_id':value}})['path']['equipment_id']==value
