from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.memory.memory_model import ConversationMemory
from backend.ingestion.embeddings import get_embedding_model
from backend.models import ChatMessage, ChatSession, utcnow


def create_chat_session(db: Session, title: str = "New Chat") -> ChatSession:
    """Add a conversation session to the current transaction."""
    session = ChatSession(title=title.strip() or "New Chat")
    db.add(session)
    db.flush()
    return session


def get_chat_session(db: Session, session_id: UUID) -> ChatSession | None:
    return db.get(ChatSession, session_id)


def list_chat_sessions(db: Session) -> list[ChatSession]:
    statement = select(ChatSession).order_by(
        ChatSession.updated_at.desc(), ChatSession.created_at.desc()
    )
    return list(db.scalars(statement).all())


def get_chat_messages(db: Session, session_id: UUID) -> list[ChatMessage]:
    statement = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at, ChatMessage.id)
    )
    return list(db.scalars(statement).all())


def save_chat_message(
    db: Session,
    session: ChatSession,
    role: str,
    content: str,
) -> ChatMessage:
    """Add a message and mark its session as recently updated.

    The caller owns the transaction and should commit or roll it back after
    completing the operation (or the full assistant exchange).
    """
    if role not in {"user", "assistant"}:
        raise ValueError("role must be 'user' or 'assistant'")

    message = ChatMessage(
        session_id=session.id,
        role=role,
        content=content,
    )
    if role == "user" and session.title == "New Chat":
        session.title = " ".join(content.split())[:80] or "New Chat"
    session.updated_at = utcnow()
    db.add(message)
    db.flush()
    return message


def delete_chat_session(db: Session, session: ChatSession) -> None:
    """Delete a session; related messages and memories cascade with it."""
    db.delete(session)
    db.flush()


def store_memory(db: Session, content: str):
    embedding_model = get_embedding_model()

    embedding = embedding_model.embed_query(content)

    memory = ConversationMemory(
        content=content,
        embedding=embedding
    )

    db.add(memory)
    db.commit()
    db.refresh(memory)

    return memory
