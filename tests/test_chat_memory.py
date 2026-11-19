import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.memory.service import (
    create_chat_session,
    delete_chat_session,
    get_chat_messages,
    get_chat_session,
    list_chat_sessions,
    save_chat_message,
)
from backend.memory.vector import retrieve_memories, store_memory
from backend.models import ChatMessage, ChatSession
from backend.router import routes as route_handlers


class ChatMemoryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(connection, _record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(
            self.engine,
            tables=[ChatSession.__table__, ChatMessage.__table__],
        )
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.session_factory()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_sessions_keep_ordered_persistent_isolated_histories(self):
        first = create_chat_session(self.db)
        second = create_chat_session(self.db)
        save_chat_message(self.db, first, "user", "alpha private question")
        save_chat_message(self.db, first, "assistant", "alpha private answer")
        save_chat_message(self.db, second, "user", "beta private question")
        self.db.commit()
        first_id, second_id = first.id, second.id

        self.db.close()
        self.db = self.session_factory()
        first_messages = get_chat_messages(self.db, first_id)
        second_messages = get_chat_messages(self.db, second_id)

        self.assertEqual([m.role for m in first_messages], ["user", "assistant"])
        self.assertIn("alpha private question", first_messages[0].content)
        self.assertEqual(len(second_messages), 1)
        self.assertNotIn(
            "alpha", " ".join(message.content for message in second_messages)
        )
        self.assertEqual(get_chat_session(self.db, first_id).title, "alpha private question")
        self.assertEqual(list_chat_sessions(self.db)[0].id, second_id)

    def test_deleting_session_cascades_to_messages(self):
        session = create_chat_session(self.db)
        session_id = session.id
        save_chat_message(self.db, session, "user", "to be removed")
        self.db.commit()

        delete_chat_session(self.db, session)
        self.db.commit()

        self.assertIsNone(get_chat_session(self.db, session_id))
        self.assertEqual(get_chat_messages(self.db, session_id), [])

    def test_session_route_handlers_create_list_load_and_delete(self):
        from backend.router.routes import (
            ChatSessionDetailResponse,
            ChatSessionResponse,
            CreateSessionRequest,
        )

        created = route_handlers.create_session(
            CreateSessionRequest(title="Route level"), self.db
        )
        session = ChatSessionResponse.model_validate(created)
        save_chat_message(
            self.db, get_chat_session(self.db, session.id), "user", "route history"
        )
        self.db.commit()

        listed = route_handlers.get_sessions(self.db)
        detail = route_handlers.get_session(session.id, self.db)
        self.assertEqual(ChatSessionResponse.model_validate(listed[0]).id, session.id)
        self.assertEqual(
            ChatSessionDetailResponse.model_validate(detail).messages[0].content,
            "route history",
        )

        route_handlers.remove_session(session.id, self.db)
        with self.assertRaises(HTTPException) as missing:
            route_handlers.get_session(session.id, self.db)
        self.assertEqual(missing.exception.status_code, 404)

    def test_vector_memory_storage_and_search_are_session_scoped(self):
        expected_embedding = [0.25] * 384
        fake_model = SimpleNamespace(embed_query=lambda _content: expected_embedding)

        class FakeScalars:
            def all(self):
                return []

        class FakeDB:
            def __init__(self):
                self.added = []
                self.statement = None

            def add(self, value):
                self.added.append(value)

            def flush(self):
                pass

            def scalars(self, statement):
                self.statement = statement
                return FakeScalars()

        fake_db = FakeDB()
        session_id = uuid4()
        with patch("backend.memory.vector.get_embedding_model", return_value=fake_model):
            memory = store_memory(fake_db, session_id, "question and answer")
            results = retrieve_memories(fake_db, "follow up", session_id, top_k=4)

        self.assertEqual(memory.session_id, session_id)
        self.assertEqual(memory.embedding, expected_embedding)
        self.assertEqual(fake_db.added, [memory])
        self.assertEqual(results, [])
        criteria = fake_db.statement._where_criteria
        self.assertEqual(len(criteria), 1)
        self.assertEqual(criteria[0].left.key, "session_id")
        self.assertEqual(criteria[0].right.value, session_id)
        self.assertEqual(fake_db.statement._limit_clause.value, 4)

    def test_rag_persists_only_the_selected_sessions_messages(self):
        from backend import rag

        first = create_chat_session(self.db)
        second = create_chat_session(self.db)
        save_chat_message(self.db, first, "user", "first session secret")
        self.db.commit()
        captured = []

        class FakeLLM:
            def invoke(self, messages):
                captured.append(messages)
                return SimpleNamespace(content="A grounded answer.")

        with (
            patch.object(rag, "get_llm", return_value=FakeLLM()),
            patch.object(rag, "search_chunks", return_value=[]),
            patch.object(rag, "retrieve_memories", return_value=[]),
            patch.object(rag, "store_memory") as store,
        ):
            result = rag.answer_question("second session question", second.id, self.db)
            self.db.commit()

        self.assertIn("A grounded answer.", result)
        self.assertEqual(len(captured), 1)
        prompt_text = " ".join(str(message.content) for message in captured[0])
        self.assertNotIn("first session secret", prompt_text)
        second_history = get_chat_messages(self.db, second.id)
        self.assertEqual([message.role for message in second_history], ["user", "assistant"])
        self.assertIn("second session question", second_history[0].content)
        self.assertEqual(store.call_count, 1)

    def test_failed_generation_does_not_save_messages_or_memory(self):
        from backend import rag

        session = create_chat_session(self.db)

        class EmptyLLM:
            def invoke(self, _messages):
                return SimpleNamespace(content="")

        with (
            patch.object(rag, "get_llm", return_value=EmptyLLM()),
            patch.object(rag, "search_chunks", return_value=[]),
            patch.object(rag, "retrieve_memories", return_value=[]),
            patch.object(rag, "store_memory") as store,
        ):
            rag.answer_question("question without answer", session.id, self.db)

        self.assertEqual(get_chat_messages(self.db, session.id), [])
        store.assert_not_called()


if __name__ == "__main__":
    unittest.main()
