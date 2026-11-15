"""Read private XLSX as evidence, independently of domain-specific import formats."""
import json
import re
from fastapi import HTTPException
from app.catalog_excel import read_workbook
from .attachments import content,public,MAX_FILE

MIME='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
CONTEXT_BUDGET=60000


def load(app,identity):
    row,blob=content(app,identity)
    if row['mime_type']!=MIME:raise HTTPException(422,'Для чтения строк нужен файл XLSX')
    try:return row,read_workbook(blob,provenance=True,max_file=MAX_FILE)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None


def cells(values):
    # Include addresses via the row number + column, and cached formula results.
    # Never calculate formulas or follow hyperlinks/external workbook references.
    return {key:dict(value=cell['value'],formula=cell['formula_text']) if cell['formula'] else cell['value']
            for key,cell in values.items() if cell['value'] or cell['formula']}


def evidence_cells(values):
    """Losslessly fold repeated calendar marks; preserve individual formula cells."""
    result={};groups=[]
    def number(key):
        n=0
        for c in key:n=n*26+ord(c)-64
        return n
    for key,item in sorted(cells(values).items(),key=lambda pair:number(pair[0])):
        if groups and isinstance(item,str) and item==groups[-1][-1][1] and number(key)==number(groups[-1][-1][0])+1:
            groups[-1].append((key,item))
        else:groups.append([(key,item)])
    for group in groups:
        if len(group)>=3:result[group[0][0]+':'+group[-1][0]]=group[0][1]
        else:result.update(group)
    return result


def findings(sheets):
    notes=[]
    for name,rows in sheets.items():
        by_address={f'{key}{n}':cell for n,values in rows for key,cell in values.items()}
        for n,values in rows:
            for key,cell in values.items():
                if len(notes)>=30:return notes
                address=f'{key}{n}'
                if not cell['formula'] and re.search(r'[A-Z]{1,3}[0-9]+',cell['value']) and re.search(r'[+*/:=]',cell['value']):
                    notes.append(dict(sheet=name,cell=address,kind='expression_stored_as_text',value=cell['value']))
                if cell['formula'] and cell.get('formula_text'):
                    refs=re.findall(r'\b[A-Z]{1,3}[1-9][0-9]*\b',cell['formula_text'].replace('$',''))
                    empty=[ref for ref in refs if not by_address.get(ref,{}).get('value')]
                    if empty:notes.append(dict(sheet=name,cell=address,kind='formula_has_empty_referenced_cells',formula=cell['formula_text'],cached_value=cell['value'],empty_cells=empty))
                    elif re.fullmatch(r'\$?[A-Z]{1,3}\$?[0-9]+(?:[+*/-]\$?[A-Z]{1,3}\$?[0-9]+)+',cell['formula_text']):
                        notes.append(dict(sheet=name,cell=address,kind='formula_with_stored_inputs',formula=cell['formula_text'],cached_value=cell['value'],
                                          input_values={ref:by_address.get(ref,{}).get('value') for ref in refs}))
    return notes


def summary(sheets):
    return [dict(name=name,rows=len(rows),first_row=rows[0][0] if rows else None,last_row=rows[-1][0] if rows else None,
                 nonempty_rows=sum(bool(cells(values)) for _,values in rows),
                 formula_cells=sum(cell['formula'] for _,values in rows for cell in values.values()),
                 formulas_without_cached_value=sum(cell['formula'] and not cell['value'] for _,values in rows for cell in values.values()))
            for name,rows in sheets.items()]


def page(app,identity,sheet=None,offset=0,limit=25,q=''):
    row,sheets=load(app,identity)
    name=sheet or next(iter(sheets),'')
    if name not in sheets:raise HTTPException(422,'Лист не найден. Используйте точное имя из списка sheets')
    rows=[dict(row=number,cells=cells(values)) for number,values in sheets[name]]
    if q.strip():rows=[r for r in rows if q.casefold() in json.dumps(r['cells'],ensure_ascii=False).casefold()]
    selected=[];size=0
    for entry in rows[offset:offset+limit]:
        width=len(json.dumps(entry,ensure_ascii=False))
        if size+width>60000:
            if not selected:raise HTTPException(422,'Одна строка превышает 60 000 символов. Разделите её на несколько строк или файлов.')
            break
        selected.append(entry);size+=width
    return dict(attachment=public(row),sheets=summary(sheets),sheet=name,items=selected,total=len(rows),offset=offset,
                next_offset=offset+len(selected) if offset+len(selected)<len(rows) else None,
                truncated=len(selected)<min(limit,max(0,len(rows)-offset)),read_only=True,
                note='Строки исходного файла, не импорт. Формулы не вычислялись; value — сохранённое в Excel значение.')


def context(app,files,budget=CONTEXT_BUDGET):
    """Attach actual workbook evidence before routing. No domain writes or hidden truncation."""
    result=[];remaining=budget
    for index,file in enumerate(f for f in files if f['mime_type']==MIME):
        item=dict(attachment_id=str(file['attachment_id']),name=file['original_name'])
        if index>=4:
            item.update(status='deferred',note='Для остальных файлов используйте attachment_read по ID; они ещё не прочитаны.')
            result.append(item);continue
        try:
            _,sheets=load(app,file['attachment_id']);item.update(status='read',sheets=summary(sheets),findings=findings(sheets),
                notation='В data: [номер строки Excel, колонки]. Ключ H:AL означает одинаковое значение во всех колонках H..AL этой строки. Findings — наблюдения над исходными ячейками, не инженерный вердикт.')
            for meta,(name,rows) in zip(item['sheets'],sheets.items()):
                selected=[]
                for number,values in rows:
                    entry=[number,evidence_cells(values)]
                    width=len(json.dumps(entry,ensure_ascii=False,separators=(',',':')))
                    if width>remaining:break
                    selected.append(entry);remaining-=width
                meta.update(data=selected,rows_included=len(selected),truncated=len(selected)<len(rows))
            item['complete']=all(not sheet['truncated'] for sheet in item['sheets'])
        except HTTPException as exc:
            # A damaged workbook must not prevent analysing the other attachments.
            if exc.status_code in (403,404,409):raise
            item.update(status='unreadable',error=str(exc.detail))
        result.append(item)
    return result
