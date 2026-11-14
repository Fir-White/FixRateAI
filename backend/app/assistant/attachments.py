"""Private immutable staging; model arguments contain IDs, never local paths or bytes."""
from contextvars import ContextVar
from hashlib import sha256
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from app.storage import safe_storage_path

SCOPE=ContextVar('assistant_attachment_scope',default=None)
COOKIE_EFFECTS=ContextVar('assistant_cookie_effects',default=None)
HUMAN_SECRET='__human_secret__'
MAX_FILE=10485760

def owned(app,identity):
    try:identity=UUID(str(identity))
    except (ValueError,TypeError):raise HTTPException(422,'В поле файла нужен ID вложения этого диалога') from None
    scope=SCOPE.get()
    if not scope:raise HTTPException(422,'Файл должен принадлежать выбранному диалогу')
    with app.state.factory() as session:
        row=session.execute(text('''SELECT a.* FROM assistant_attachments a JOIN assistant_conversations c USING(conversation_id)
            WHERE a.attachment_id=:id AND c.conversation_id=:conversation AND c.user_id=:user AND c.site_id=:site AND c.role=:role'''),
            dict(id=identity,conversation=scope[0],user=scope[1],site=scope[2],role=scope[3])).mappings().first()
    if row is None:raise HTTPException(404,'Вложение не найдено в этом диалоге')
    return dict(row)

def content(app,identity):
    row=owned(app,identity);path=safe_storage_path(app.state.settings.photo_storage_root,row['storage_key'])
    try:
        with path.open('rb') as stream:blob=stream.read(MAX_FILE+1)
    except OSError:raise HTTPException(404,'Файл вложения недоступен') from None
    if len(blob)!=row['size_bytes'] or sha256(blob).hexdigest()!=row['sha256']:raise HTTPException(409,'Содержимое вложения изменилось. Прикрепите файл повторно.')
    return row,blob

def public(row):return {k:row[k] for k in ('attachment_id','original_name','mime_type','size_bytes','sha256','created_at')}
