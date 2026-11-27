"""PostgreSQL checkpoints with the same lifetime as the private conversation."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from sqlalchemy import text


SCHEMA = 'assistant_checkpoints'
TABLES = ('checkpoints', 'checkpoint_blobs', 'checkpoint_writes')


def connection_info(engine):
    url = engine.url.set(drivername='postgresql')
    options = url.query.get('options', '')
    return make_conninfo(url.render_as_string(hide_password=False),
                         options=f'{options} -csearch_path={SCHEMA}'.strip())


def migrate(engine):
    """Run vendor DDL explicitly under the application migration lock."""
    with PostgresSaver.from_conn_string(connection_info(engine)) as saver:
        saver.setup()
        with saver.conn.transaction():
            for table in TABLES:
                constraint = f'{table}_assistant_thread_fk'
                existing = saver.conn.execute(
                    'SELECT 1 FROM pg_constraint WHERE conname=%s AND conrelid=%s::regclass',
                    (constraint, f'{SCHEMA}.{table}'),
                ).fetchone()
                if not existing:
                    saver.conn.execute(
                        f'ALTER TABLE {SCHEMA}.{table} ADD CONSTRAINT {constraint} '
                        'FOREIGN KEY (thread_id) REFERENCES public.assistant_graph_threads(thread_id) ON DELETE CASCADE'
                    )


class GraphSaver(PostgresSaver):
    """Expose the official sync saver to async graphs, including Windows Proactor."""

    async def aget_tuple(self, config):
        return await asyncio.to_thread(self.get_tuple, config)

    async def aput(self, config, checkpoint, metadata, new_versions):
        return await asyncio.to_thread(self.put, config, checkpoint, metadata, new_versions)

    async def aput_writes(self, config, writes, task_id, task_path=''):
        await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id):
        await asyncio.to_thread(self.delete_thread, thread_id)


@contextmanager
def open_saver(engine):
    with ConnectionPool(connection_info(engine), min_size=0, max_size=4, timeout=5,
                        kwargs=dict(autocommit=True, prepare_threshold=0, row_factory=dict_row)) as pool:
        yield GraphSaver(pool, serde=JsonPlusSerializer(allowed_msgpack_modules=None))


def thread_config(principal, conversation_id, kind, identity):
    scope = (principal.user_id, principal.site_id, principal.role, conversation_id)
    return {'configurable': {'thread_id': ':'.join(map(str, ('v3.1', *scope, kind, identity)))},
            'recursion_limit': 128}


def register_thread(session, config, conversation_id):
    session.execute(text('''
        INSERT INTO assistant_graph_threads(thread_id, conversation_id) VALUES (:thread, :chat)
        ON CONFLICT (thread_id) DO NOTHING
    '''), dict(thread=config['configurable']['thread_id'], chat=conversation_id))
