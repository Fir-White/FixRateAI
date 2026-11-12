"""Bounded XLSX interchange using inline strings; formulas are never evaluated."""
from io import BytesIO
from datetime import datetime, timedelta
from decimal import Decimal
import re
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED, BadZipFile

NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
ET.register_namespace('', NS)
MAX_FILE = 5 * 1024 * 1024


def xml(data):
    markup=data.replace(b'\x00',b'').upper()
    if b'<!DOCTYPE' in markup or b'<!ENTITY' in markup: raise ValueError('Недопустимый XML в Excel')
    return ET.fromstring(data)


def column(index):
    result = ''
    while index:
        index, digit = divmod(index-1, 26)
        result = chr(65+digit) + result
    return result


def read_workbook(data):
    if not data or len(data) > MAX_FILE: raise ValueError('Размер Excel должен быть от 1 байта до 5 МБ')
    try:
        with ZipFile(BytesIO(data)) as archive:
            files = archive.infolist()
            if len(files) > 200 or sum(f.file_size for f in files) > 20*1024*1024 or len({f.filename for f in files}) != len(files):
                raise ValueError('Слишком большой или неоднозначный архив Excel')
            if any('vbaProject' in f.filename or f.flag_bits & 1 for f in files): raise ValueError('Макросы и зашифрованные книги не поддерживаются')
            shared = []
            book=xml(archive.read('xl/workbook.xml'))
            properties=book.find(f'{{{NS}}}workbookPr')
            calendar1904=properties is not None and properties.attrib.get('date1904') in ('1','true')
            date_styles=set()
            if 'xl/styles.xml' in archive.namelist():
                styles=xml(archive.read('xl/styles.xml'))
                custom={int(e.attrib['numFmtId']):e.attrib['formatCode'] for e in styles.findall(f'{{{NS}}}numFmts/{{{NS}}}numFmt')}
                for index,style in enumerate(styles.findall(f'{{{NS}}}cellXfs/{{{NS}}}xf')):
                    number=int(style.attrib.get('numFmtId','0'))
                    code=re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"|\[[^]]*\]|\\.', '', custom.get(number,'')).lower()
                    if number in (14,15,16,17,22) or 'y' in code or 'd' in code:date_styles.add(index)
            if 'xl/sharedStrings.xml' in archive.namelist():
                shared = [''.join(si.itertext()) for si in xml(archive.read('xl/sharedStrings.xml')).findall(f'{{{NS}}}si')]
            links = {e.attrib['Id']: e.attrib['Target'] for e in xml(archive.read('xl/_rels/workbook.xml.rels')) if e.attrib.get('TargetMode') != 'External'}
            sheets = {}
            count = 0
            for sheet in book.findall(f'{{{NS}}}sheets/{{{NS}}}sheet'):
                if sheet.attrib['name'] in sheets:raise ValueError('Повтор названия листа')
                target = links[sheet.attrib[f'{{{REL}}}id']]
                target = target.lstrip('/') if target.startswith('/') else 'xl/' + target
                if '..' in PurePosixPath(target).parts: raise ValueError('Недопустимая ссылка на лист')
                rows = []
                for row in xml(archive.read(target)).findall(f'{{{NS}}}sheetData/{{{NS}}}row'):
                    count += 1
                    if count > 5000: raise ValueError('В книге допускается не более 5000 строк')
                    cells = {}
                    for cell in row.findall(f'{{{NS}}}c'):
                        key = ''.join(c for c in cell.attrib['r'] if c.isalpha())
                        value = cell.findtext(f'{{{NS}}}v', '')
                        if cell.attrib.get('t') == 's': value = shared[int(value)]
                        elif cell.attrib.get('t') == 'inlineStr': value = ''.join(cell.find(f'{{{NS}}}is').itertext())
                        elif value and cell.attrib.get('t','n')=='n' and int(cell.attrib.get('s','0')) in date_styles:
                            serial=Decimal(value)
                            if not serial.is_finite() or serial<0:raise ValueError('Некорректная дата Excel')
                            if not calendar1904 and int(serial)==60:raise ValueError('Excel содержит несуществующую дату 1900-02-29')
                            base=datetime(1904,1,1) if calendar1904 else datetime(1899,12,31) if serial<60 else datetime(1899,12,30)
                            value=(base+timedelta(days=float(serial))).date().isoformat()
                        if len(value) > 32767: raise ValueError('Слишком длинное значение в Excel')
                        cells[key] = dict(value=value.strip(), formula=cell.find(f'{{{NS}}}f') is not None)
                    rows.append((int(row.attrib['r']), cells))
                sheets[sheet.attrib['name']] = rows
            return sheets
    except (BadZipFile, KeyError, IndexError, ET.ParseError, TypeError, OSError, RuntimeError, OverflowError, ValueError) as error:
        if isinstance(error, ValueError): raise
        raise ValueError('Не удалось прочитать XLSX. Используйте шаблон реестра без пароля и макросов.') from None


def table(rows):
    if not rows: return []
    headers = {key: cell['value'] for key, cell in rows[0][1].items() if cell['value']}
    if len(set(headers.values())) != len(headers): raise ValueError('Повторяющиеся заголовки колонок')
    result = []
    for number, cells in rows[1:]:
        if any(cell['formula'] for cell in cells.values()): raise ValueError(f'Строка {number}: замените формулы подтверждёнными значениями')
        values = {header: cells.get(key, {}).get('value', '') for key, header in headers.items()}
        if any(values.values()): result.append((number, values))
    return result


def write_workbook(sheets):
    buffer = BytesIO()
    with ZipFile(buffer, 'w', ZIP_DEFLATED) as archive:
        types = ET.Element('Types', xmlns='http://schemas.openxmlformats.org/package/2006/content-types')
        ET.SubElement(types, 'Default', Extension='rels', ContentType='application/vnd.openxmlformats-package.relationships+xml')
        ET.SubElement(types, 'Default', Extension='xml', ContentType='application/xml')
        ET.SubElement(types, 'Override', PartName='/xl/workbook.xml', ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml')
        workbook = ET.Element(f'{{{NS}}}workbook'); sheet_nodes = ET.SubElement(workbook, f'{{{NS}}}sheets')
        links = ET.Element('Relationships', xmlns='http://schemas.openxmlformats.org/package/2006/relationships')
        for index, (name, rows) in enumerate(sheets.items(), 1):
            ET.SubElement(types, 'Override', PartName=f'/xl/worksheets/sheet{index}.xml', ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml')
            ET.SubElement(sheet_nodes, f'{{{NS}}}sheet', name=name, sheetId=str(index), attrib={f'{{{REL}}}id': f'rId{index}'})
            ET.SubElement(links, 'Relationship', Id=f'rId{index}', Type=REL+'/worksheet', Target=f'worksheets/sheet{index}.xml')
            sheet = ET.Element(f'{{{NS}}}worksheet'); content = ET.SubElement(sheet, f'{{{NS}}}sheetData')
            for number, values in enumerate(rows, 1):
                row = ET.SubElement(content, f'{{{NS}}}row', r=str(number))
                for col, value in enumerate(values, 1):
                    cell = ET.SubElement(row, f'{{{NS}}}c', r=f'{column(col)}{number}', t='inlineStr')
                    text = ET.SubElement(ET.SubElement(cell, f'{{{NS}}}is'), f'{{{NS}}}t')
                    text.text = '' if value is None else str(value)
            archive.writestr(f'xl/worksheets/sheet{index}.xml', ET.tostring(sheet, encoding='utf-8', xml_declaration=True))
        archive.writestr('xl/workbook.xml', ET.tostring(workbook, encoding='utf-8', xml_declaration=True))
        archive.writestr('xl/_rels/workbook.xml.rels', ET.tostring(links, encoding='utf-8', xml_declaration=True))
        archive.writestr('[Content_Types].xml', ET.tostring(types, encoding='utf-8', xml_declaration=True))
        archive.writestr('_rels/.rels', f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{REL}/officeDocument" Target="xl/workbook.xml"/></Relationships>')
    return buffer.getvalue()
