"""The model proposes calls; only an authenticated person can confirm a stored action."""
from typing import Literal
import json
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,field_validator,model_validator

class Input(BaseModel):
    model_config=ConfigDict(extra='forbid')

class ConversationCreate(Input):
    agent:Literal['assistant','planner','photo']='assistant'
    title:str=Field(default='Новый диалог',min_length=1,max_length=160)

class MessageCreate(Input):
    idempotency_key:UUID
    content:str=Field(default='',max_length=12000)
    # None preserves old clients: their first message includes staged files.
    # An explicit list selects exactly the files the user sent with this turn.
    attachment_ids:list[UUID]|None=Field(default=None,max_length=20)
    model_preference_revision:int|None=Field(default=None,ge=0)
    @model_validator(mode='after')
    def has_message(self):
        self.content=self.content.strip()
        if not self.content and not self.attachment_ids:raise ValueError('Введите сообщение или прикрепите файл')
        if self.attachment_ids and len(set(self.attachment_ids))!=len(self.attachment_ids):raise ValueError('Вложение указано повторно')
        return self

class ChatModelPreference(Input):
    provider:Literal['ollama','aitunnel']
    model:str=Field(min_length=1,max_length=128,pattern=r'^[A-Za-z0-9._][A-Za-z0-9._:/-]*$')
    expected_revision:int=Field(ge=0)

class ConfirmAction(Input):
    payload_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    confirmed:Literal[True]
    secret_values:dict[str,str]=Field(default_factory=dict,max_length=3)

class AgentCall(Input):
    tool:str=Field(min_length=1,max_length=100)
    arguments_json:str=Field(max_length=40000,description='JSON object with tool arguments: path, query, body. For describe_tool: {"name":"tool_name"}.')
    explanation:str=Field(min_length=1,max_length=3000)
    @field_validator('arguments_json')
    @classmethod
    def valid_json(cls,value):
        if not isinstance(json.loads(value),dict):raise ValueError('Arguments must be a JSON object')
        return value
    @property
    def arguments(self):return json.loads(self.arguments_json)

class AgentStep(Input):
    answer:str=Field(max_length=12000)
    calls:list[AgentCall]=Field(max_length=3)

class ToolSelection(Input):
    tools:list[str]=Field(max_length=8)
    workbook_ids:list[UUID]=Field(default_factory=list,max_length=4,description='Previously sent XLSX attachments needed for this question; use only IDs from server context.')

class FinalReply(Input):
    answer:str=Field(min_length=1,max_length=12000)
    @field_validator('answer')
    @classmethod
    def not_blank(cls,value):
        if not value.strip():raise ValueError('A final answer is required')
        return value.strip()

class ResultView(Input):
    path:list[str]=Field(default_factory=list,max_length=6,description='Последовательный путь по ключам одного JSON-результата, не список полей и не поиск оборудования. Обычно []: сначала прочитайте корневой ответ. Не угадывайте ключи.')
    offset:int=Field(default=0,ge=0)
    limit:int=Field(default=25,ge=1,le=25)
    q:str=Field(default='',max_length=200)
    text_offset:int=Field(default=0,ge=0)
    text_limit:int=Field(default=6000,ge=1,le=6000)

ASSISTANT_CONTRACTS=(ConversationCreate,MessageCreate,ChatModelPreference,ConfirmAction,AgentStep,ResultView,ToolSelection,FinalReply)
