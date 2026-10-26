#!/usr/bin/env python3
"""CLI-утилита для индексации строительных нормативов в PostgreSQL (pgvector).

Пример запуска:
    # Сухой прогон (проверка парсинга и генерации эмбеддингов):
    python -m scripts.ingest_normatives --dir data/normatives

    # Боевая индексация в локальный PostgreSQL:
    python -m scripts.ingest_normatives --dir data/normatives --apply

    # Экспорт в автономный SQL-файл:
    python -m scripts.ingest_normatives --dir data/normatives --export-sql data/seed_normative_chunks.sql
"""
import argparse
import sys
from pathlib import Path

# Добавляем ml_service в PYTHONPATH при прямом запуске скрипта
sys_path = Path(__file__).resolve().parent.parent
if str(sys_path) not in sys.path:
    sys.path.insert(0, str(sys_path))

from app.core.config import get_settings
from app.rag.chunker import NormativeChunker
from app.rag.embeddings import GigaChatEmbeddingsProvider, MockEmbeddingsProvider
from app.rag.ingestion import NormativeIngestionPipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Индексация строительных нормативов FixRate AI")
    parser.add_argument(
        "--dir",
        default=str(sys_path / "data" / "normatives"),
        help="Путь к каталогу с файлами нормативов (.md, .txt)",
    )
    parser.add_argument(
        "--provider",
        choices=["mock", "gigachat"],
        default="mock",
        help="Провайдер эмбеддингов (по умолчанию mock для автономности)",
    )
    parser.add_argument(
        "--db-url",
        default="",
        help="URL подключения к PostgreSQL (по умолчанию из настроек ML_DATABASE_URL)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Записать чанки в базу данных (по умолчанию dry-run)",
    )
    parser.add_argument(
        "--export-sql",
        default="",
        help="Экспортировать готовые INSERT-запросы в SQL-файл",
    )

    args = parser.parse_args()
    settings = get_settings()

    db_url = args.db_url or settings.database_url or "postgresql://fixrate:ChangeMe-local-only@localhost:5432/fixrate"

    if args.provider == "gigachat":
        print(f"Используется боевой провайдер GigaChat Embeddings (модель: Embeddings 1024d)...")
        embeddings = GigaChatEmbeddingsProvider(fallback_to_mock=True)
    else:
        print(f"Используется детерминированный MockEmbeddingsProvider (1024d)...")
        embeddings = MockEmbeddingsProvider(dimension=1024)

    pipeline = NormativeIngestionPipeline(
        chunker=NormativeChunker(),
        embeddings_provider=embeddings,
        db_url=db_url,
    )

    normatives_dir = Path(args.dir)
    if not normatives_dir.is_dir():
        print(f"Ошибка: каталог {normatives_dir} не найден!", file=sys.stderr)
        return 1

    print(f"Каталог нормативов: {normatives_dir}")
    print(f"Режим: {'БОЕВОЙ (запись в БД)' if args.apply else 'ТЕСТОВЫЙ DRY-RUN'}")

    try:
        report = pipeline.ingest_directory(normatives_dir, dry_run=not args.apply)

        print("\n" + "=" * 60)
        print("РЕЗУЛЬТАТЫ ИНДЕКСАЦИИ:")
        print("=" * 60)
        for doc_stats in report.documents:
            print(
                f"- {doc_stats.document_title}: {doc_stats.total_chunks} чанков "
                f"(вставлено: {doc_stats.inserted_chunks}, обновлено: {doc_stats.updated_chunks}, пропущено: {doc_stats.skipped_chunks})"
            )
        print("-" * 60)
        print(f"Всего документов: {report.total_documents}")
        print(f"Всего чанков:     {report.total_chunks}")
        print(f"Новых записей:    {report.inserted_chunks}")
        print(f"Обновленных:      {report.updated_chunks}")
        print(f"Пропущенных:      {report.skipped_chunks}")
        print("=" * 60)

        if args.export_sql:
            sql_out = Path(args.export_sql)
            count = pipeline.export_sql_seed(normatives_dir, sql_out)
            print(f"\nЭкспортировано {count} чанков в SQL: {sql_out}")

        return 0
    except Exception as e:
        print(f"\nКритическая ошибка индексации: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
