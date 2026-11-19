"""Database-backed conversation history helpers.

Unlike the former process-wide list, history is always scoped by both a
database session and a chat session ID.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from backend.memory.service import get_chat_messages, save_chat_message
from backend.models import ChatMessage, ChatSession


def add_message(
    db: Session,
    session: ChatSession,
    role: str,
    content: str,
) -> ChatMessage:
    return save_chat_message(db, session, role, content)


def get_history(db: Session, session_id: UUID) -> list[ChatMessage]:
    return get_chat_messages(db, session_id)
