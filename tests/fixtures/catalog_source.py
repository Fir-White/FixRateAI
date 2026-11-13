"""Generated anonymous HVAC workbook; no customer operation text or source bytes."""
from app.catalog_excel import write_workbook

TYPE_COUNTS={'ТО1':38,'ТО2':46,'ТО2*':5,'ТО3':113,'ТОр':15}
FREQUENCY_COUNTS={'1/квар':61,'2/год':54,'1/год':46,'2/сутки':29,'1/мес':12,'1/день':5,'1/4года':4,'в составе \nТО2, ТО3':3,'1/нед':1,'1/5 лет':1,'по необходимости':1}

def catalog_book(count=217):
    kinds=[kind for kind,n in TYPE_COUNTS.items() for _ in range(n)]
    frequencies=[kind for kind,n in FREQUENCY_COUNTS.items() for _ in range(n)]
    rows=[['SYNTHETIC CATALOG'],['№','Наименование операции','Вид ТО','Периодичность','Время на опер. Ч','Деталь','Наработка часов','Январь'],
          ['', 'SYNTHETIC CATEGORY','','','','','',*range(1,32)]]
    for i in range(count):
        if i%14==0:
            group=i//14+1
            rows.append([str(group),'SYNTHETIC GROUP'])
            if group==10: rows.append(['10.1','SYNTHETIC NESTED GROUP'])
        code=f'{group}.{i%14+1}' if group!=10 else f'10.1.{i%14+1}'
        frequency=frequencies[i%217]
        marks=['']*31
        if frequency=='2/сутки':marks=['день\nночь']*31
        elif frequency=='1/мес':marks[:10]=['ТО2']*10
        elif frequency=='2/год':marks[4:25]=['ТО3']*21
        rows.append([code,f'SYNTHETIC OPERATION {i:04}',kinds[i%217],frequency,'','','',*marks])
    second=[[],['SYNTHETIC LOAD CHECK']]+[[] for _ in range(18)]
    second[5]=['']*8+['8+A6:S33']
    second[19]=['']*8+['20']
    return write_workbook({'Лист1':rows,'Лист2':second})
