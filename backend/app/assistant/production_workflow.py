"""Typed production workflows over authenticated APIs; proposals never execute themselves."""
import calendar,re
from dataclasses import dataclass
from decimal import Decimal
from datetime import date,datetime
import inspect
from uuid import UUID,uuid4
from fastapi import HTTPException
from .tools import available,validate_arguments,invoke,fingerprint
from .read_transport import read,result_summary,safe_arguments

MONTHS=('январ','феврал','март','апрел','ма','июн','июл','август','сентябр','октябр','ноябр','декабр')

_CONTEXT=frozenset({'drafts_find','planning_context'})
_OPTIMIZE=_CONTEXT|{'draft_read','optimization_start','optimization_read','optimization_apply','optimization_placements','draft_changes'}
WORKFLOW_TOOLS={
    'calendar':_CONTEXT,
    'readiness':_CONTEXT|{'workforce_read'},
    'materials':frozenset({'equipment_find','components_read'}),
    'create':_OPTIMIZE|{'portfolio_preview','portfolio_save'},
    'compare':_CONTEXT|{'draft_read','optimization_start','optimization_read','optimization_placements'},
    'optimize':_OPTIMIZE,
    'prepare_approval':_OPTIMIZE|{'calendar_read','publication_profiles'},
    'approve':frozenset({'publication_read','publication_approve'}),
    'publish':frozenset({'publication_read','publication_publish'}),
    'publication':frozenset(), 'whatif':frozenset(), 'impossible':frozenset(), 'bypass':frozenset(),
}
WORKFLOW_TARGETS={
    'calendar':'planning_context','readiness':'planning_context','materials':'components_read',
    'create':'portfolio_save','compare':'optimization_start','optimize':'optimization_start',
    'prepare_approval':'optimization_start','approve':'publication_approve','publish':'publication_publish',
    'publication':'','whatif':'','impossible':'','bypass':'',
}

PUBLICATION_TRANSITION_FIELDS=('proposal_id','draft_id','base_revision','state','proposal_digest','summary',
    'expires_at','blocker_count','can_approve','decided_by','decided_at','approval_token','published_at','publication_id')


def _publication_evidence(value):
    """Retain the exact transition facts, not an unrelated full validation log.

    The complete authorized response is still used by the verifier. This
    declared server projection keeps those required facts recoverable within
    the evidence budget and binds them to the original response digest.
    """
    if not isinstance(value,dict):return value
    fields={key:value[key] for key in PUBLICATION_TRANSITION_FIELDS if key in value}
    fields['source_projection']=dict(kind='publication_transition',fields=list(PUBLICATION_TRANSITION_FIELDS),
                                     full_payload_sha256=fingerprint(value))
    if isinstance(value.get('validation'),dict):fields['validation_status']=value['validation'].get('status')
    if any(key not in value for key in PUBLICATION_TRANSITION_FIELDS):fields['complete']=False
    return fields


@dataclass(frozen=True)
class WorkflowResult:
    answer:str
    status:str
    reason:str|None=None
    action_id:str|None=None
    read_tools:tuple[str,...]=()


def _publication_verified(kind,identity,receipt,current):
    """Match an owned phase receipt to a fresh exact publication resource.

    A prior succeeded HTTP dispatch is insufficient by itself. Approval and
    publication identities, consent digest and immutable transition facts must
    agree; a changed or malformed receipt remains unresolved without replay.
    """
    def uid(value):
        try:return str(UUID(str(value)))
        except (ValueError,TypeError,AttributeError):return None
    def instant(value):
        try:
            parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
            return parsed if parsed.tzinfo is not None else None
        except (ValueError,TypeError,AttributeError):return None
    if not isinstance(receipt,dict) or not isinstance(current,dict):return False
    target=uid(identity)
    if not target or any(uid(row.get('proposal_id'))!=target for row in (receipt,current)):return False
    digest=receipt.get('proposal_digest')
    if not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest) or current.get('proposal_digest')!=digest:return False
    if not uid(receipt.get('draft_id')) or uid(receipt.get('draft_id'))!=uid(current.get('draft_id')):return False
    if type(receipt.get('base_revision')) is not int or type(current.get('base_revision')) is not int or receipt['base_revision']<1 or receipt['base_revision']!=current['base_revision']:return False
    if not uid(receipt.get('decided_by')) or uid(receipt.get('decided_by'))!=uid(current.get('decided_by')):return False
    if not instant(receipt.get('decided_at')) or instant(receipt['decided_at'])!=instant(current.get('decided_at')):return False
    if not uid(receipt.get('approval_token')) or uid(receipt.get('approval_token'))!=uid(current.get('approval_token')):return False
    if kind=='approve':
        return receipt.get('state') in ('approved','published') and current.get('state') in ('approved','published')
    if kind=='publish':
        return (receipt.get('state')==current.get('state')=='published'
            and uid(receipt.get('publication_id')) is not None
            and uid(receipt['publication_id'])==uid(current.get('publication_id'))
            and instant(receipt.get('published_at')) is not None
            and instant(receipt['published_at'])==instant(current.get('published_at')))
    return False

def comparison(result):
    lines=['| Показатель | Базовый | CP-SAT |','|---|---:|---:|']
    left=(result.get('baseline') or {}).get('metrics',{});right=(result.get('optimized') or {}).get('metrics',{})
    for key,title in [('covered_occurrences','Покрытые работы'),('unplaced_segments','Неразмещённые части'),('peak_daily_person_hours','Пиковая нагрузка, чел·ч'),('staff_utilization','Использование персонала, %'),('changed_assignments','Изменённые назначения'),('unfilled_slots','Незаполненные места в бригадах')]:
        def display(metrics):
            value=metrics.get(key)
            if value is None:return 'не определено'
            return f'{Decimal(str(value))*100:.2f}' if key=='staff_utilization' else str(value)
        lines.append(f"| {title} | {display(left)} | {display(right)} |")
    for key,name in [('baseline','Базовый'),('optimized','CP-SAT')]:
        variant=result.get(key)
        if variant:lines.append(f"{name}: {variant['solver_status']}; проверка {variant['validation']['status']}; доказанная оптимальность: {variant['optimality_proven']}.")
    lines.append('Простой и число задействованных смен отдельными метриками API пока не возвращаются. Не подменяю их другими показателями. Конфликты и пробелы: '+str(result.get('diagnostic_counts',{}))+'.')
    return '\n'.join(lines)

def period(question):
    year=re.search(r'\b(20\d{2}|21\d{2})\b',question)
    if not year:return None
    for month,stem in enumerate(MONTHS,1):
        if re.search(r'\b'+stem+r'[а-я]*\s+'+year[1],question,re.I):
            y=int(year[1]);return date(y,month,1).isoformat(),date(y,month,calendar.monthrange(y,month)[1]).isoformat()
    return None

def intent(question):
    q=question.casefold()
    if 'опублик' in q and any(s in q for s in ('без подтвержден','убери провер','считай, что я администратор')):return 'bypass'
    if '100%' in q and any(s in q for s in ('раньше разреш','на два объекта','одновременно')):return 'impossible'
    if 'опублик' in q and ('обычный исполнитель' in q or 'за главного инженера' in q):return 'publication'
    if re.search(r'\bутверди\b',q) and 'предложен' in q:return 'approve'
    if re.search(r'\bопубликуй\b',q) and not re.search(r'\bне\s+опубликуй\b',q) and re.search(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',q):return 'publish'
    if 'ресурс' in q and any(s in q for s in ('запчаст','детал')):return 'materials'
    if any(s in q for s in ('предположим','сценарий перепланирования')) and 'недоступ' in q:return 'whatif'
    if 'достаточно' in q and any(s in q for s in ('информац','данных')) and any(s in q for s in ('расч','сотрудник','расписан')):return 'readiness'
    if 'операци' in q and ('раз в месяц' in q or 'два раза в год' in q):return 'calendar'
    if 'черновик' in q and any(s in q for s in ('сформируй','создай план')):return 'create'
    if 'два варианта' in q or 'сравни' in q and 'cp-sat' in q:return 'compare'
    if 'закрепл' in q and any(s in q for s in ('перераспред','перерасч','пиков')):return 'optimize'
    if 'оптимизированную версию' in q and 'черновик' in q:return 'prepare_approval'
    return None

async def run(app,principal,question,history,outcomes,headers,trace,check,suggest,*,kind=None,date_range=None,tool_subset=None,observe=None):
    """Execute a server specialist selected by the shared semantic orchestrator.

    Explicit ``kind`` never uses request/history keywords to choose a workflow or
    period. Its reads, results and proposals belong to the caller's persisted
    goal. Legacy direct callers retain their previous string-returning interface.
    """
    semantic=kind is not None
    if not semantic:
        kind=intent(question)
        if kind is None and re.match(r'^(продолж|покажи результат|расчет заверш|расчёт заверш)',question,re.I):
            kind=next((intent(t['content']) for t in history[1:5] if intent(t['content'])),None)
    if kind is None:return None
    if kind not in WORKFLOW_TOOLS:raise ValueError('Unknown semantic workflow kind')
    if tool_subset is not None and not isinstance(tool_subset,(dict,set,frozenset,list,tuple)):
        raise ValueError('Workflow tool subset must contain trusted tool names')
    if date_range is not None:
        if not isinstance(date_range,(tuple,list)) or len(date_range)!=2:raise ValueError('Workflow date range requires start and end')
        dates=tuple(value.isoformat() if type(value) is date else date.fromisoformat(value).isoformat() for value in date_range)
        if dates[1]<dates[0] or (date.fromisoformat(dates[1])-date.fromisoformat(dates[0])).days>366:raise ValueError('Workflow date range must cover at most 366 days')
    else:dates=None
    permitted=WORKFLOW_TOOLS[kind]
    tools={name:tool for name,tool in available(app,principal.role,'assistant').items()
           if name in permitted and (tool_subset is None or name in tool_subset)}
    read_tools=[];incomplete=False
    def finish(answer,status='completed',reason=None,action_id=None):
        if status=='completed' and incomplete:status,reason='partial','incomplete_source'
        return WorkflowResult(answer,status,reason,action_id,tuple(read_tools)) if semantic else answer
    async def observed(name,args,value):
        nonlocal incomplete
        from .workflow import completeness
        complete,_=completeness(value)
        if not complete or isinstance(value,dict) and any(value.get(key) is True for key in ('catalogs_truncated','drafts_truncated')):
            incomplete=True
        read_tools.append(name)
        if observe is not None:
            result=observe(name,args,value)
            if inspect.isawaitable(result):result=await result
            if isinstance(result,dict) and result.get('complete') is False:
                incomplete=True
    async def call(name,args=None,*,publication_transition=False):
        check()
        if name not in tools:raise HTTPException(403,'Нет права на '+name)
        tool=tools[name];args=args or {}
        if tool.method=='GET':
            checked,value=await read(app,tool,args,headers,trace)
            await observed(name,checked,_publication_evidence(value) if publication_transition else value)
            return value
        if tool.mode!='read':raise ValueError('A write requires a proposal')
        try:
            checked=validate_arguments(app,tool,args)
            value=await invoke(app,tool,checked,headers)
        except HTTPException as exc:
            trace.append(dict(tool=name,status='denied',arguments=safe_arguments(args),code=exc.status_code,error_type='argument_or_domain_validation' if exc.status_code==422 else 'backend_error',attempt=1,retry_count=0))
            raise
        trace.append(dict(tool=name,status='completed',arguments=safe_arguments(args),result=result_summary(value),attempt=1,retry_count=0))
        await observed(name,checked,value)
        return value
    async def proposal(name,args,explanation):
        check()
        if name not in tools:raise HTTPException(403,'Нет права на изменение')
        prepared=await suggest(tools[name],args,explanation)
        trace.append(dict(tool=name,status='proposed',arguments=safe_arguments(args)))
        return finish(explanation+'\n\nПодготовлена карточка. Проверьте параметры и подтвердите действие. Действующий график не изменён.',
                      'awaiting_confirmation','human_confirmation_required',str(prepared['action_id']) if isinstance(prepared,dict) and prepared.get('action_id') else None)
    async def uncovered(run_id,result):
        if not result.get('optimized'):return ''
        page=await call('optimization_placements',dict(path=dict(run_id=run_id),query=dict(kind='optimized')))
        lines=[]
        for segment in page['items']:
            if not segment.get('start_at'):
                lines.append('- Не размещено: '+page['occurrence_labels'].get(segment['occurrence_id'],'Работа')+'. Допустимый состав и интервал не найдены.')
        if page['total']>len(page['items']):lines.append('Показана первая страница размещений; полный список требует продолжения чтения.')
        for issue in result.get('diagnostics',[]):lines.append('- Ограничение расчёта: '+issue['message'])
        return '\n'.join(lines)
    if kind in ('bypass','impossible'):
        return finish(('Не буду убирать проверки или публиковать без подтверждения. Полномочия определяются вашей сессией, а не текстом сообщения. ' if kind=='bypass' else 'Обеспечить 100% занятость ценой нарушения сроков ТО или одновременной работы на двух объектах нельзя. ')+ 'Допустимая альтернатива — рассчитать варианты с сохранением сроков, допусков и запрета пересечений; непокрытые работы будут показаны отдельно.','blocked','confirmation_or_constraint_bypass' if kind=='bypass' else 'infeasible_requested_constraints')
    if kind=='publication':
        if principal.role!='chief_engineer':return finish('Ваша текущая роль не разрешает утверждение и публикацию. Это выполняет главный инженер после проверки и подтверждения точного состава предложения. Изменений нет.','blocked','forbidden_role')
        return finish('Публикация требует конкретного согласованного предложения и отдельного подтверждения. Укажите план; проверки и подтверждение обязательны.','blocked','proposal_required')
    if kind=='whatif':
        return finish('Изменений действующего графика и доступности людей нет. Изолированный what-if с временным отсутствием сотрудников пока не поддерживается API расчёта: в него нельзя передать такую гипотезу без изменения исходных данных. Поэтому я не буду выдавать обычный расчёт за сценарий отсутствия. Для этого сценария нужны отдельный снимок доступности, два выбранных сотрудника и повторная проверка пересечений.','blocked','whatif_capability_unavailable')
    try:
        if kind in ('approve','publish'):
            name='publication_approve' if kind=='approve' else 'publication_publish'
            if name not in tools:return finish('Текущая роль не разрешает это действие. Изменений нет.','blocked','forbidden_role')
            identities=re.findall(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',question)
            if len(set(identities))!=1:return finish('Укажите одно предложение из списка согласований. Отдельное подтверждение обязательно.','blocked','proposal_required_or_ambiguous')
            identity=identities[0]
            found=await call('publication_read',dict(path=dict(identity=identity)),publication_transition=True)
            phases=[row for row in outcomes if row.get('tool_name')==name]
            matching=[]
            for phase in phases:
                result=phase.get('result')
                receipt=result.get('data') if isinstance(result,dict) else None
                if isinstance(receipt,dict) and str(receipt.get('proposal_id','')).casefold()==identity.casefold():
                    matching.append((phase,receipt))
            if matching:
                phase,receipt=matching[0]
                if phase.get('status')!='succeeded':
                    return finish('Исход этапа требует проверки. Повторное изменение не подготовлено.',
                                  'blocked','publication_phase_unverified')
                if not _publication_verified(kind,identity,receipt,found):
                    return finish('Завершение поручения не подтверждено: сохранённый исход этапа и актуальное предложение различаются. Повторная запись не запускается.',
                                  'blocked','publication_postcondition_unverified')
                return finish('Утверждение точного предложения подтверждено повторным чтением backend. Текущее состояние: '+
                              ('опубликовано.' if found['state']=='published' else 'утверждено.') if kind=='approve' else
                              'Предложение опубликовано; сохранённый выпуск и точный состав подтверждены повторным чтением backend.')
            if any(row.get('status')!='succeeded' or not isinstance(row.get('result'),dict) or
                   not isinstance(row['result'].get('data'),dict) for row in phases):
                return finish('Исход этапа не подтверждён проверяемым результатом. Повторная запись не запускается.',
                              'blocked','publication_phase_unverified')
            body=dict(expected_digest=found['proposal_digest'])
            if kind=='approve':body['reason']='Утверждение точного состава по поручению главного инженера'
            else:
                if found['state']!='approved' or not found.get('approval_token'):return finish('Предложение ещё не утверждено или подтверждение устарело. Публикация не подготовлена.','blocked','approval_required')
                body.update(approval_token=found['approval_token'],idempotency_key=str(uuid4()))
            return await proposal(name,dict(path=dict(identity=identity),body=body),'Утвердить выбранное предложение о выпуске.' if kind=='approve' else 'Опубликовать только выбранное утверждённое предложение. Это создаст действующие задания после вашего подтверждения.')
        if kind=='materials':
            equipment=[];offset=0
            while True:
                page=await call('equipment_find',dict(query=dict(offset=offset)));equipment.extend(page['items']);offset+=len(page['items'])
                if offset>=page['total'] or not page['items'] or offset>=500:break
            lines=['Ресурс установленных деталей текущего объекта (система не выполняет замену):']
            for eq in equipment:
                parts=await call('components_read',dict(path=dict(equipment_id=eq['equipment_id'])))
                for part in parts:
                    if part.get('removed_on'):continue
                    limit=part.get('resource_limit');remaining=part.get('remaining_usage');unit=part.get('usage_unit')
                    lines.append(f"- {eq['name']} / {part['name']}: наработка {part['current_usage']} {unit}; норматив {limit if limit is not None else 'не задан'}; остаток {remaining if remaining is not None else 'неизвестен'} {unit}.")
                    if limit is None:lines.append('  Не хватает норматива ресурса; срок замены не определён.')
                    elif remaining is not None and float(remaining)<=0:lines.append('  Ресурс исчерпан: требуется решение инженера о замене; автоматическая дата не назначается.')
                    else:lines.append('  Дата достижения ресурса за выбранный период не подтверждена: текущая наработка не задаёт будущую скорость использования.')
            if len(lines)==1:lines.append('Установленных деталей в прочитанном реестре не найдено.')
            if offset<page['total']:lines.append('Список частичный: предел чтения 500 единиц оборудования.')
            lines.append('Моточасы не преобразуются в календарные дни без подтверждённой модели использования. Календарный ресурс отдельно этим API деталей пока не моделируется.')
            return finish('\n'.join(lines),'partial','usage_forecast_unavailable')
        if not semantic:dates=period(question) or next((period(t['content']) for t in history[1:5] if period(t['content'])),None)
        lists=await call('drafts_find')
        if lists['total']>len(lists['items']):return finish('Доступно больше одной страницы черновиков. Нужно уточнить выбранный план или период; первую страницу не считаю полным списком.','partial','draft_list_incomplete')
        drafts={r['draft_id']:r for r in lists['items']}
        candidates=[r for r in drafts.values() if not dates or (str(r['starts_on']),str(r['ends_on']))==dates]
        if kind in ('compare','optimize','prepare_approval') and len(candidates)!=1:
            return finish('Для расчёта выберите один черновик: '+('; '.join(f"{r['title']} (ID: {r['draft_id']})" for r in candidates) or 'подходящий черновик не найден')+'. Изменений нет.','blocked','draft_required_or_ambiguous')
        record=candidates[0] if len(candidates)==1 else None
        if dates is None and record:dates=(str(record['starts_on']),str(record['ends_on']))
        if dates is None:return finish('Укажите месяц и год расчёта. Изменений нет.','blocked','period_required')
        context=await call('planning_context',dict(query=dict(starts_on=dates[0],ends_on=dates[1])))
        ledger=context['requirements'];site=context['site']['name'];catalogs=context['catalogs']
        if kind in ('calendar','readiness'):
            lines=[f"Период {dates[0]} — {dates[1]}, объект «{site}». Проверено по регламентам и решениям инженера."]
            matching_bindings=set()
            for eq in context['registry']['items']:
                for service in eq['services']:
                    p=service['pattern']
                    if p['frequency']=='month' and p.get('interval',1) in (1,6) or p['frequency']=='yearly_count' and p.get('count_per_year')==2:matching_bindings.add(service['binding_id'])
            catalog_frequencies={row:frequency for catalog in catalogs for row,frequency in catalog.get('frequencies',{}).items()}
            for item in ledger['items']:
                if kind=='calendar':
                    frequency=catalog_frequencies.get(str(item.get('source_row')),{});catalog_match=frequency.get('kind')=='month' and frequency.get('interval') in (1,6) or frequency.get('kind')=='yearly_count' and frequency.get('interval')==2
                    if item.get('binding_id') not in matching_bindings and not (item['source_kind']=='catalog' and catalog_match):continue
                states={'new':'новая обязанность','existing':'уже запланировано','fulfilled':'выполнено','review':'требует разбора'}
                lines.append(f"- {item['title']}: допустимо {item['earliest_date']} — {item['due_date']}; трудоёмкость {item['person_hours'] if item['person_hours'] is not None else 'не подтверждена'} чел·ч; {states.get(item['state'],item['state'])}.")
            if ledger['total']>len(ledger['items']):lines.append(f"Показана страница {len(ledger['items'])} из {ledger['total']} обязанностей; полный список требует продолжения чтения.")
            for issue in ledger['issues']:lines.append('- Ограничение: '+issue['message'])
            labels={'NEEDS_SEMANTICS':'не подтверждён смысл отметок','NEEDS_FREQUENCY':'не определена периодичность','NEEDS_ASSET_BINDING':'нет привязки оборудования','NEEDS_DURATION':'не подтверждена трудоёмкость/длительность','NEEDS_POLICY':'не определены правила выполнения'}
            for catalog in catalogs:
                blockers='; '.join(f"{labels.get(k,k)}: {v} строк" for k,v in catalog['blockers'].items()) or 'нет'
                lines.append(f"Каталог «{catalog['filename']}»: подготовлено строк {len(catalog['prepared_rows'])} из {catalog['total']}; неподготовленные строки не превращаются в работы. Ограничения: "+blockers)
            if context['catalogs_truncated']:lines.append('Прочитаны первые десять каталогов: список источников частичный.')
            for eq in context['registry']['items']:
                if not any(s['enabled'] for s in eq['services']):lines.append('Нет опубликованных регламентов: '+eq['name'])
            if kind=='calendar':lines.append('Одна ежемесячная обязанность с окном из десяти отметок остаётся одной работой. Отсутствие даты в этом периоде не означает отсутствия регламента на весь год.')
            else:
                policy=context['policy'];lines.append('Ёмкость: '+str(policy.get('capacity_status'))+'; доступ на объект: '+str(policy.get('access_status'))+'.')
                lines.append('Подтверждённая трудоёмкость выбранных обязанностей: '+str(ledger['summary']['known_person_hours'])+' чел·ч. Это не сумма всех неподготовленных строк.')
                people=await call('workforce_read')
                for person in people['staff']:
                    if person['role']!='executor' or not person['is_active']:continue
                    shifts=[s for s in person['shifts'] if s['is_active']]
                    slots=[s for s in person['exceptions'] if s['status']=='available']
                    periods='; '.join(str(s['start_at'])+' — '+str(s['end_at']) for s in slots[:3]) or 'не заданы'
                    lines.append(f"Исполнитель {person['full_name']}: активных правил смен {len(shifts)}, подтверждённых квалификаций {len(person['qualifications'])}; окна доступности: {periods}.")
                    if not shifts and not slots:lines.append('Не хватает подтверждённой доступности этого исполнителя.')
                lines.append('Это проверка исходных данных, а не рассчитанная штатная численность. До достоверного расписания дополнительно проверяются доступность, допуски, занятость, закрепления и результат валидатора. Длительность смены 24 часа сама по себе не доказывает 24 полезных часа.')
            return finish('\n'.join(lines))
        successful=[r for r in outcomes if r['status']=='succeeded' and isinstance(r.get('result'),dict)]
        applied=next((r for r in successful if r['tool_name']=='optimization_apply'),None)
        if applied and kind in ('create','optimize','prepare_approval'):
            data=applied['result'].get('data',{})
            start=next((r for r in successful if r['tool_name']=='optimization_start'),None)
            details=''
            if start:
                run=await call('optimization_read',dict(path=dict(run_id=start['result']['data']['run_id'])))
                if run.get('result'):
                    details='\n\n'+comparison(run['result'])
                    details+='\n'+await uncovered(run['run_id'],run['result'])
                    changes=await call('draft_changes',dict(query=dict(identity=run['draft_id'],before_revision=run['base_revision'],after_revision=data['revision'])))
                    details+='\n\nФактических изменений сегментов: '+str(changes['total'])+'.'
                    for change in changes['items']:
                        before=change.get('before') or {};after=change.get('after') or {}
                        names=', '.join(changes['worker_labels'].get(w,w) for w in after.get('worker_ids',[]))
                        details+=f"\n- {change['title']}: {before.get('start_at') or 'не размещено'} → {after.get('start_at') or 'не размещено'}; исполнители: {names or 'не назначены'}. Выбран допустимый вариант расчёта; закрепления не снимаются."
                    if changes['total']>len(changes['items']):details+='\nПоказана первая страница изменений.'
            if kind=='prepare_approval':
                active=await call('calendar_read',dict(query=dict(year=int(dates[0][:4]),month=int(dates[0][5:7]))))
                profiles=await call('publication_profiles',dict(path=dict(identity=data['draft_id']),query=dict(revision=data['revision'])))
                details+=f"\n\nВ действующем календаре текущего объекта за выбранный месяц: {len(active)} записей. Для {profiles['total']} исходных строк нужны подтверждённые инструкции, меры безопасности и чек-листы; сам список строк не является таким профилем. Предложение к утверждению пока не создано: эти сведения не предоставлены. Полное сравнение выпуска с действующим графиком доступно после его подготовки."
            return finish(f"Создана версия черновика {data.get('revision')}. Действующий график не опубликован. Закрепления проверены штатным валидатором. Для утверждения и публикации нужны отдельное предложение, утверждённые инструкции/чек-листы и подтверждение главного инженера."+details,
                          'partial' if kind=='prepare_approval' else 'completed','publication_profiles_required' if kind=='prepare_approval' else None)
        saved=next((r for r in successful if r['tool_name'] in ('portfolio_save','draft_save')),None)
        if kind=='create' and saved:record=saved['result'].get('data')
        if kind=='create' and not saved:
            policy=context['policy']
            if policy.get('capacity_status')!='confirmed' or policy.get('access_status')!='confirmed':return finish('Для нового плана нужны подтверждённые полезная ёмкость смены и условия доступа. Не принимаю 24-часовую смену за 24 полезных часа автоматически. Черновик не сохранён.','blocked','planning_policy_unconfirmed')
            request=context['portfolio_input'];preview=await call('portfolio_preview',dict(body=request))
            if not preview.get('can_save'):return finish('Предпросмотр не разрешает сохранить выбранный состав. Причины: '+str(preview.get('issues',[])),'blocked','portfolio_not_saveable')
            explanation=f"Сохранить черновик для объекта «{site}» за {dates[0]} — {dates[1]}. Состав: {preview['total_occurrences']} обязанностей; неизвестные исходные строки исключены и не считаются выполненными. После сохранения нужен отдельный расчёт размещения."
            return await proposal('portfolio_save',dict(body=dict(input=request,preview_sha256=preview['input_sha256'],idempotency_key=str(uuid4()),title='ТО/ППР '+dates[0][:7],reason='Поручение пользователя создать черновик')),explanation)
        if record is None:return finish('Не удалось однозначно выбрать черновик. Укажите его из списка.','blocked','draft_required_or_ambiguous')
        run_action=next((r for r in successful if r['tool_name']=='optimization_start'),None)
        if run_action:
            run_id=run_action['result']['data']['run_id'];run=await call('optimization_read',dict(path=dict(run_id=run_id)))
            if run['state'] not in ('succeeded','failed','cancelled'):return finish('Расчёт ещё выполняется. Действующий график не меняется; запросите результат после завершения.','running','optimizer_running')
            result=run.get('result')
            if not result:return finish('Расчёт завершился без подтверждённого результата: '+str(run.get('error_code') or run['state']),'blocked','optimizer_'+run['state'])
            if kind=='compare':
                comparable=all(isinstance(result.get(name),dict) and result[name].get('model_complete') is True
                    and result[name].get('validation',{}).get('status')=='valid' for name in ('baseline','optimized'))
                return finish('Фактическое сравнение расчёта:\n\n'+comparison(result)+'\n'+await uncovered(run_id,result)+'\n\nПроцент улучшения без расчёта не заявляется. Действующий график не изменён.',
                              'completed' if comparable else 'partial',None if comparable else 'comparison_not_fully_validated')
            variant=result.get('optimized')
            if variant and not variant.get('applicable') and variant['validation']['status']=='valid' and not result.get('diagnostic_counts'):
                return finish('Расчёт завершён: допустимый вариант совпадает с исходным. Перемещений нет, закрепления сохранены; новая идентичная версия не создаётся.\n\n'+comparison(result))
            if not variant or not variant.get('applicable'):return finish('Оптимизированный вариант нельзя применить: '+str(result.get('diagnostics')),'blocked','optimizer_result_not_applicable')
            current=await call('draft_read',dict(path=dict(identity=record['draft_id'])))
            return await proposal('optimization_apply',dict(path=dict(run_id=run_id),body=dict(expected_revision=current['record']['revision'],kind='optimized',reason='Новая оптимизированная версия по поручению пользователя')),'Применить проверенный вариант новой версией черновика. Закреплённые сегменты не снимаются; публикация не выполняется.')
        current=await call('draft_read',dict(path=dict(identity=record['draft_id'])))
        return await proposal('optimization_start',dict(path=dict(identity=record['draft_id']),body=dict(expected_revision=current['record']['revision'],idempotency_key=str(uuid4()),options=dict(replan_existing=kind in ('optimize','prepare_approval')))),'Рассчитать baseline и CP-SAT для выбранного черновика. Это сохраняет результат расчёта, но не меняет действующий график; применение потребует отдельного подтверждения.')
    except HTTPException as exc:
        return finish('Для текущей роли операция недоступна. Новое действие не выполнено.' if exc.status_code in (401,403) else 'Не удалось завершить проверку штатным backend: '+str(exc.detail)[:600]+'. Это не доказывает отсутствия данных. Изменений действующего графика нет.',
                      'blocked','forbidden_role' if exc.status_code in (401,403) else 'backend_error_'+str(exc.status_code))
