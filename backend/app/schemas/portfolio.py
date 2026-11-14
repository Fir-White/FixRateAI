"""General draft input preserves the existing reviewed requirements scope."""
from typing import Literal
from pydantic import model_validator
from app.schemas.draft_plans import Model,DraftPolicy,GenerationPreview,SaveDraft
from app.schemas.requirements import RequirementsRequest

class PortfolioInput(Model):
    kind: Literal['portfolio'] = 'portfolio'
    requirements: RequirementsRequest
    policy: DraftPolicy

    @property
    def starts_on(self):return self.requirements.starts_on
    @property
    def ends_on(self):return self.requirements.ends_on
    @property
    def import_id(self):return None
    @property
    def row_numbers(self):return self.requirements.catalog.row_numbers if self.requirements.catalog else []

    @model_validator(mode='after')
    def complete_scope(self):
        if self.requirements.q or self.requirements.state!='all' or self.requirements.offset or self.requirements.issue_offset:
            raise ValueError('В план сохраняется весь выбранный состав, а не страница или результат поиска')
        if self.policy.format_version!=2:raise ValueError('Для общего плана нужны параметры версии 2')
        if self.requirements.catalog and (self.policy.day_start_minute,self.policy.night_start_minute)!=(self.requirements.catalog.policy.day_start_minute,self.requirements.catalog.policy.night_start_minute):
            raise ValueError('Границы событий должны совпадать с проверенным источником')
        return self

class PortfolioPreview(GenerationPreview):
    excluded_occurrences: int
    requirements_sha256: str

class SavePortfolio(SaveDraft):
    input: PortfolioInput

PORTFOLIO_CONTRACTS=(PortfolioInput,PortfolioPreview,SavePortfolio)

def planning_input(value):
    from app.schemas.draft_plans import GenerationInput
    return PortfolioInput.model_validate(value) if value.get('kind')=='portfolio' else GenerationInput.model_validate(value)
