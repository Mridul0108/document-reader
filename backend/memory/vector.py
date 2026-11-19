"""Session-scoped semantic memory storage and retrieval."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.ingestion.embeddings import get_embedding_model
from backend.models import VectorMemory


def store_memory(db: Session, session_id: UUID, content: str) -> VectorMemory:
    """Store one completed conversation exchange in the current transaction."""
    embedding = get_embedding_model().embed_query(content)
    memory = VectorMemory(
        session_id=session_id,
        content=content,
        embedding=embedding,
    )
    db.add(memory)
    db.flush()
    return memory


def retrieve_memories(
    db: Session,
    question: str,
    session_id: UUID,
    top_k: int = 3,
) -> list[VectorMemory]:
    """Return the closest memories from this session only."""
    if top_k <= 0:
        return []

    question_embedding = get_embedding_model().embed_query(question)
    statement = (
        select(VectorMemory)
        .where(VectorMemory.session_id == session_id)
        .order_by(VectorMemory.embedding.cosine_distance(question_embedding))
        .limit(top_k)
    )
    return list(db.scalars(statement).all())
