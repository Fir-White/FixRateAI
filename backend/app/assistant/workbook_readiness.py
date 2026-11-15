"""Read-only source diagnostics; raw Excel never certifies a real staffing calculation."""
from decimal import Decimal,InvalidOperation
import re

NORM_HEADERS={'person_hours','man_hours','norm_hours','norm_value','duration_hours','duration_minutes','labor_hours','трудоемкость','трудоёмкость','человеко_часы','чел_ч','время_на_опер_ч','время_на_операцию_ч'}
QUANTITY_HEADERS={'quantity','qty','количество','кол_во'}

def header(value):return re.sub(r'[^\w]+','_',str(value).casefold()).strip('_')

def quantity_cell(column,row,cells):
    raw=str(cells.get(column,{}).get('value',''))
    return dict(cell=column+str(row),value=raw if len(raw)<=64 else None,value_truncated=len(raw)>64)

def quality(sheets):
    tables=[]
    for name,rows in sheets.items():
        for index,(number,values) in enumerate(rows[:100]):
            norms={column:cell['value'] for column,cell in values.items() if header(cell['value']) in NORM_HEADERS}
            if not norms:continue
            quantities={column:cell['value'] for column,cell in values.items() if header(cell['value']) in QUANTITY_HEADERS}
            if len(norms)>16 or len(quantities)>16:
                tables.append(dict(sheet=name,header_row=number,norm_fields_checked=0,raw_numeric_norm_fields=0,
                    unknown_norm_fields=None,issues=[],issues_truncated=True,norms_confirmed=False,layout_too_wide=True))
                break
            issues=[];known=0;issue_count=0;checked=0
            for row,cells in rows[index+1:]:
                if not any(cell.get('value') or cell.get('formula') for cell in cells.values()):continue
                for column,field in norms.items():
                    checked+=1;cell=cells.get(column,{})
                    value=cell.get('value','');status=None
                    if cell.get('formula'):status='formula_unverified'
                    elif not str(value).strip():status='missing'
                    else:
                        try:
                            numeric=Decimal(str(value).replace(',','.'))
                            if not numeric.is_finite() or numeric<=0:status='invalid'
                        except (InvalidOperation,ValueError):status='invalid'
                    if status:
                        issue_count+=1
                        if len(issues)<25:
                            issues.append(dict(sheet=name,cell=column+str(row),field=field,status=status,
                                quantity_cells=[quantity_cell(c,row,cells) for c in list(quantities)[:4]]))
                    else:known+=1
            tables.append(dict(sheet=name,header_row=number,norm_columns=list(norms),norm_fields_checked=checked,raw_numeric_norm_fields=known,
                unknown_norm_fields=issue_count,issues=issues,issues_truncated=issue_count>len(issues),norms_confirmed=False))
            break
    return dict(source='raw_workbook',tables=tables,can_calculate_real_staffing=False,
        note='Raw values and cached formulas are not an approved norm, asset binding or capacity policy.')

def preserve_missing_norms(row,values,diagnostics,sheet):
    result=dict(values)
    if not result:return result
    for table in diagnostics['tables']:
        if table['sheet']==sheet and row>table['header_row']:
            for column in table.get('norm_columns',[]):result.setdefault(column,None)
    return result

def requested(question):
    if re.search(r'импорт|загрузи|добавь.{0,30}(?:оборудован|норматив)',question,re.I):return False
    people=re.search(r'сколько.{0,50}(?:человек|сотрудник|работник|исполнител)|(?:рассчитай|определи).{0,40}(?:численност|потребност)',question,re.I|re.S)
    demand=re.search(r'нуж|надо|треб|потреб|для выполн|на обслужив|на (?:ТО|ППР)\b',question,re.I)
    plan=re.search(r'(?:составь|сформируй|распредели|спланируй).{0,40}(?:план\w*\s+(?:ТО|ППР|обслужив)|работ|график)',question,re.I|re.S)
    effort=re.search(r'(?:сколько.{0,25}|рассчитай.{0,40}|посчитай.{0,40})(?:человеко[ -]?час|чел[. ·]?ч|трудозатрат|трудо[её]мк)',question,re.I)
    return bool(people and demand or plan or effort)

def fact(workbooks):
    tables=[table for book in workbooks for table in book.get('quality',{}).get('tables',[])]
    known=bool(tables) and all(isinstance(table['unknown_norm_fields'],int) for table in tables)
    return dict(source='raw_workbook',can_calculate_real_staffing=False,
        unknown_norm_fields=sum(table['unknown_norm_fields'] for table in tables) if known else None,
        raw_numeric_norm_fields=sum(table['raw_numeric_norm_fields'] for table in tables),
        norms_confirmed=False,source_files=len(workbooks))

def prior_sources(question,files):
    """Use only sent metadata; never search another chat or invent an attachment."""
    books=[f for f in files if f['mime_type']=='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']
    named=[f for f in books if re.search(r'(?<![\w.-])'+re.escape(f['original_name'])+r'(?=$|[\s»"\',;:?!)\]])',question,re.I)]
    if named:return named
    if '.xlsx' in question.casefold():return []
    if len(books)<=1:return books
    if re.search(r'этой|этому|этого|последн|прикрепл',question,re.I):return books[:1]
    if re.search(r'все.{0,20}(?:файл|таблиц)|по (?:файлам|таблицам|книгам)',question,re.I):return books
    return None

def report(workbooks):
    from app.assistant.inventory_report import label
    lines=['### Для расчёта численности нужны подтверждённые исходные данные',
        'Численность не рассчитана. Прикреплённый Excel — исходный файл: он сам по себе не подтверждает нормативы, привязку к оборудованию, состав бригады и полезную ёмкость смены. Количество единиц нельзя считать человеко-часами.']
    for book in workbooks:
        title=label(book.get('name','Excel'))
        if book.get('status')!='read' or not book.get('complete'):
            lines.append(f'Файл «{title}» прочитан не полностью либо недоступен. Это не означает, что на объекте нет оборудования или регламентов.')
            continue
        tables=book.get('quality',{}).get('tables',[])
        if not tables:lines.append(f'Для файла «{title}» требуется подтвердить, какие поля содержат норматив и в каких единицах.')
        for table in tables:
            for issue in table['issues'][:8]:
                reason={'missing':'пусто','invalid':'нет положительного числового норматива','formula_unverified':'формула и её сохранённый результат требуют проверки'}[issue['status']]
                lines.append(f"- «{title}», {label(issue['sheet'])}!{label(issue['cell'])}, поле «{label(issue['field'])}»: {reason}.")
                for item in issue['quantity_cells']:
                    if item.get('value_truncated'):
                        lines.append(f"  Значение количества в {label(item['cell'])} слишком длинное для краткой диагностики; оно не использовано как норматив.")
                        continue
                    try:value=Decimal(str(item['value']).replace(',','.'));valid=value.is_finite()
                    except InvalidOperation:valid=False
                    if valid:lines.append(f"  Количество из {label(item['cell'])} = {value}; это количество, не норматив трудоёмкости.")
            if table['issues_truncated'] or len(table['issues'])>8:lines.append('Показана часть проблемных ячеек; неполный перечень не выдаётся за полный.')
    lines.append('Следующий шаг — подтвердить нормативы и единицы, реальные активы, период и полезную ёмкость смен, затем выполнить серверный расчёт по подготовленным данным. Если нужен импорт файла, его можно подготовить отдельным предложением для вашего подтверждения. График и назначения не изменялись.')
    return '\n\n'.join(lines)
