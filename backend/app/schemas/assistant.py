"""The model proposes calls; only an authenticated person can confirm a stored action."""
from typing import Literal
from datetime import date
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
    resume_turn_id:UUID|None=None
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
    goal_id:str|None=Field(default=None,max_length=40,description='ID of the planned user objective served by this call.')
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

class GoalSelector(Input):
    equipment_code:str|None=Field(default=None,max_length=128)
    equipment_id:UUID|None=None
    user_id:UUID|None=None
    attachment_ids:list[UUID]=Field(default_factory=list,max_length=20)
    starts_on:date|None=None
    ends_on:date|None=None
    current_only:bool|None=None
    draft_id:UUID|None=None
    run_id:UUID|None=None
    proposal_id:UUID|None=None
    component_id:UUID|None=None

class GoalSpec(Input):
    id:str=Field(min_length=1,max_length=40,pattern=r'^[a-zA-Z0-9_-]+$')
    title:str=Field(min_length=1,max_length=400,description='One independently verifiable user objective, preserving its exact scope and values.')
    tool:str=Field(max_length=100,description='REQUIRED exact final outcome tool name from the authorized catalog, not a prerequisite search. Use empty string ONLY when capability or required user decision is genuinely unavailable.')
    kind:Literal['read','change','conversation','unavailable']|None=None
    selector:GoalSelector=Field(default_factory=GoalSelector,description='Business selectors stated by the user. Resolve technical UUIDs on the server; never invent them. Distinguish calendar cycle dates from actual-history year.')
    changes:dict[str,str|int|float|bool|None]=Field(default_factory=dict,max_length=12,description='Only exact field values requested for this change, e.g. name. Empty for reads. Technical revisions are supplied by server code.')
    depends_on:list[str]=Field(default_factory=list,max_length=12)
    requires_full_list:bool=False
    response_style:Literal['facts','analysis']='facts'
    workflow_kind:Literal['readiness','calendar','materials','whatif','create','compare','optimize','prepare_approval','approve','publish','publication','impossible','bypass']|None=None

class ToolSelection(Input):
    tools:list[str]=Field(max_length=8)
    goals:list[GoalSpec]=Field(default_factory=list,max_length=12,description='Every objective in the latest request, including unavailable and dependent objectives. Do not omit an objective after selecting a report tool.')
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
