"""Prepare only fully specified, explicit commands if the model stops at prose.

This never executes a mutation. Target, literal value and current metadata come
from the user's command and an authorized backend read, not invented results.
"""
import re
from .intents import _MUTATION,literal_rename,explicit_revision

_UUID=r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}'
_ROLES=r'admin|chief_engineer|engineer|dispatcher|director|executor'


def simple_tail(text):
    parts=[part.strip(' ,;:') for part in re.split(r'[.!?\n,;]',text) if part.strip(' ,;:')]
    return all(re.fullmatch(r'(?:остальные поля не (?:меняй|изменяй)|не меняй других сотрудников|он оста[её]тся активен|я администратор текущего объекта|подготовь предложение(?: для (?:моего )?подтверждения)?)',part,re.I) for part in parts)


def specification(question):
    parts=re.split(r'\b(?:затем|после этого|then)\b',question,maxsplit=1,flags=re.I)
    action=parts[-1]
    if explicit_revision(action) or re.search(r'\b(?:объясни|расскажи|пример|как|если|когда|предварительно|how|example|if|when)\b',action,re.I):return None
    verbs=[match[0].casefold() for match in _MUTATION.finditer(action) if not re.search(r"\b(?:не|not|don't)\s+$",action[max(0,match.start()-20):match.start()],re.I)]
    if len(verbs)!=1:return None
    if verbs[0] in ('переименуй','переименуйте','rename'):
        ids=set(re.findall(r'\bequipment_id\s*[:=]\s*('+_UUID+')',action,re.I));name=literal_rename(action)
        if len(ids)==1 and name is not None:
            ends=[action.rfind(left+name+right) for left,right in (('«','»'),('"','"'),("'","'"))]
            end=max(ends)
            if end<0 or not simple_tail(action[end+len(name)+2:]):return None
            return dict(tool='equipment_edit',before='equipment_read',path=dict(equipment_id=next(iter(ids))),changes=dict(name=name))
    if verbs[0] in ('измени','измените','change') and re.search(r'\b(?:роль|role)\b',action,re.I):
        if re.search(r'дат|employed|активир|деактивир|статус',action,re.I):return None
        ids=set(re.findall(r'\buser_id\s*[:=]\s*('+_UUID+')',action,re.I))
        roles=list(re.finditer(r'\b(?:на|to)\s+('+_ROLES+r')\b',action,re.I))
        if len(ids)==1 and len(roles)==1 and simple_tail(action[roles[0].end():]):return dict(tool='staff_edit',before='staff_read',path=dict(user_id=next(iter(ids))),changes=dict(role=roles[0][1].casefold()),must_be_active=bool(re.search(r'оста[её]тся актив',action,re.I)))
    return None


def arguments(spec,before):
    if not isinstance(before,dict) or type(before.get('revision')) is not int or before['revision']<=0:return None
    if any(str(before.get(key,'')).casefold()!=identity.casefold() for key,identity in spec['path'].items()):return None
    body=dict(spec['changes'],expected_revision=before['revision'])
    if spec['tool']=='staff_edit':
        if type(before.get('membership_is_active')) is not bool:return None
        if spec.get('must_be_active') and before.get('is_active') is not True:return None
        body['is_active']=before['membership_is_active']
    return dict(path=spec['path'],body=body)
