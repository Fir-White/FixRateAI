"""Unit-тесты извлечения текста из документов."""
import pytest
from app.ocr.document_parser import DocumentParser


def test_document_parser_single_page():
    parser = DocumentParser()
    content = "Акт осмотра здания № 42.\nОбнаружена трещина фасада длиной 4 метра."
    res = parser.parse_document(content.encode("utf-8"), document_id="doc-100", file_name="act.txt")

    assert res.document_id == "doc-100"
    assert res.file_name == "act.txt"
    assert res.total_pages == 1
    assert "трещина фасада" in res.pages[0].text
    assert res.pages[0].page_number == 1


def test_document_parser_multipage():
    parser = DocumentParser()
    # Две страницы, разделённые form-feed \f
    content = "Страница 1: паспорт объекта.\fСтраница 2: дефектная ведомость."
    res = parser.parse_document(content, document_id="doc-101", file_name="report.pdf")

    assert res.total_pages == 2
    assert res.pages[0].page_number == 1
    assert "паспорт объекта" in res.pages[0].text
    assert res.pages[1].page_number == 2
    assert "дефектная ведомость" in res.pages[1].text
