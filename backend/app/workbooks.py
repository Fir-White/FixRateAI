from io import BytesIO
from pathlib import PureWindowsPath
from xml.etree.ElementTree import ParseError
from xml.etree.ElementTree import tostring
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from app.catalog_excel import MAX_FILE, REL, read_workbook, xml


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CONNECTIONS = "xl/connections.xml"


def workbook_filename(filename: str) -> str:
    name = "".join(char for char in PureWindowsPath(filename).name if ord(char) >= 32 and ord(char) != 127)
    stem, extension = PureWindowsPath(name).stem, PureWindowsPath(name).suffix
    if extension.lower() != ".xlsx" or not stem:
        raise ValueError("Загрузите книгу в формате .xlsx.")
    return stem[:251] + ".xlsx"


def validate_xlsx(content: bytes) -> None:
    if not content or len(content) > MAX_FILE:
        raise ValueError("Размер книги должен быть от 1 байта до 5 МиБ.")
    # Use the bounded reader for validation only. Persist the original package bytes.
    if not read_workbook(content):
        raise ValueError("В книге Excel нет листов.")
    try:
        with ZipFile(BytesIO(content)) as package:
            names = set(package.namelist())
            if CONNECTIONS in names:
                xml(package.read("[Content_Types].xml"))
            for member in package.namelist():
                lowered = member.lower()
                if (lowered.startswith(("xl/externallinks/", "xl/querytables/", "xl/embeddings/", "xl/model/"))
                        or lowered == CONNECTIONS and member != CONNECTIONS):
                    raise ValueError("Внешние подключения и встроенные объекты в Excel не поддерживаются.")
                if CONNECTIONS in names and lowered.startswith("xl/pivotcache/"):
                    raise ValueError("Книга содержит сводные таблицы с потенциальной зависимостью от внешних данных.")
                if lowered.endswith(".rels"):
                    for element in xml(package.read(member)):
                        if element.get("TargetMode", "").lower() == "external":
                            raise ValueError("Внешние ссылки в книге Excel не поддерживаются.")
                        if element.get("Type") == f"{REL}/connections" and (
                                member != "xl/_rels/workbook.xml.rels"
                                or element.get("Target") not in {"connections.xml", "/"+CONNECTIONS}
                                or CONNECTIONS not in names):
                            raise ValueError("Не удалось безопасно отключить подключения к данным.")
    except (BadZipFile, ParseError, KeyError, OSError, RuntimeError) as error:
        raise ValueError("Не удалось проверить структуру книги Excel.") from error


def has_connections(content: bytes) -> bool:
    with ZipFile(BytesIO(content)) as package:
        return CONNECTIONS in package.namelist()


def editor_workbook(content: bytes) -> bytes:
    """Remove standalone workbook data connections from the editor copy only."""
    with ZipFile(BytesIO(content)) as source:
        if CONNECTIONS not in source.namelist():
            return content
        result = BytesIO()
        with ZipFile(result, "w", ZIP_DEFLATED) as target:
            for name in source.namelist():
                if name == CONNECTIONS:
                    continue
                data = source.read(name)
                if name in ("[Content_Types].xml", "xl/_rels/workbook.xml.rels"):
                    tree = xml(data)
                    for node in list(tree):
                        if node.get("PartName") == "/" + CONNECTIONS or node.get("Type") == f"{REL}/connections":
                            tree.remove(node)
                    data = tostring(tree, encoding="utf-8", xml_declaration=True)
                target.writestr(name, data)
    return result.getvalue()
