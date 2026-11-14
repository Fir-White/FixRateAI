"""The model proposes calls; only an authenticated person can confirm a stored action."""
from typing import Literal
import json
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,field_validator

class Input(BaseModel):
    model_config=ConfigDict(extra='forbid')

class ConversationCreate(Input):
    agent:Literal['assistant','planner','photo']='assistant'
    title:str=Field(default='Новый диалог',min_length=1,max_length=160)

class MessageCreate(Input):
    idempotency_key:UUID
    content:str=Field(min_length=1,max_length=12000)
    @field_validator('content')
    @classmethod
    def not_blank(cls,value):
        if not value.strip():raise ValueError('Введите сообщение')
        return value.strip()

class ConfirmAction(Input):
    payload_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    confirmed:Literal[True]

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

ASSISTANT_CONTRACTS=(ConversationCreate,MessageCreate,ConfirmAction,AgentStep)
