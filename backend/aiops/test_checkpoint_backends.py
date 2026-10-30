import os
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.db import connection
from django.test import SimpleTestCase, TransactionTestCase, override_settings

from . import langgraph_pilot as pilot


class CheckpointBackendTests(SimpleTestCase):
    def test_default_checkpoint_backend_tracks_database_and_keeps_sqlite_local(self):
        with patch.dict(os.environ, {'AIOPS_LANGGRAPH_CHECKPOINT_BACKEND': ''}):
            for engine, expected in [('postgresql', 'postgresql'), ('mysql', 'mysql'), ('sqlite3', 'sqlite')]:
                with override_settings(DATABASES={'default': {'ENGINE': f'django.db.backends.{engine}'}}):
                    self.assertEqual(pilot._checkpoint_backend(), expected)

    def test_explicit_checkpoint_backend_is_preserved(self):
        with patch.dict(os.environ, {'AIOPS_LANGGRAPH_CHECKPOINT_BACKEND': 'sqlite'}):
            self.assertEqual(pilot._checkpoint_backend(), 'sqlite')


@skipUnless(connection.vendor == 'postgresql', 'Requires an isolated PostgreSQL test database')
class PostgreSQLCheckpointTests(TransactionTestCase):
    def test_graph_checkpoint_is_shared_between_independent_savers(self):
        from langgraph.checkpoint.postgres import PostgresSaver
        from langgraph.graph import START, END, StateGraph
        from typing_extensions import TypedDict

        class State(TypedDict):
            value: str

        with patch.dict(os.environ, {'AIOPS_LANGGRAPH_CHECKPOINT_BACKEND': 'postgresql'}), \
                patch.object(pilot, '_CHECKPOINTER', None), patch.object(pilot, '_CHECKPOINTER_CONNECTION', None):
            saver = pilot._get_checkpointer()
            pool = pilot._CHECKPOINTER_CONNECTION
            config = {'configurable': {'thread_id': f'postgres-test-{uuid4()}'}}
            try:
                graph = StateGraph(State)
                graph.add_node('persist', lambda state: {'value': state['value'] + '-saved'})
                graph.add_edge(START, 'persist')
                graph.add_edge('persist', END)
                compiled = graph.compile(checkpointer=saver)
                self.assertEqual(compiled.invoke({'value': '中文状态'}, config)['value'], '中文状态-saved')
                second = PostgresSaver(pool)
                stored = second.get_tuple(config)
                self.assertEqual(stored.checkpoint['channel_values']['value'], '中文状态-saved')
            finally:
                saver.delete_thread(config['configurable']['thread_id'])
                pool.close()
