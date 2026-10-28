from sqlalchemy import select
from sqlalchemy.orm import joinedload

from database import SessionLocal
from models import DocumentChunk
from ingestion.embeddings import get_embedding_model


def search_chunks(question: str, top_k: int = 5):
    db = SessionLocal()

    try:
        # Convert the question into a vector
        embedding_model = get_embedding_model()

        query_embedding = embedding_model.embed_query(question)

        statement = (
            select(DocumentChunk)
            .options(joinedload(DocumentChunk.document))
            .order_by(
                DocumentChunk.embedding.cosine_distance(query_embedding)
            )
            .limit(top_k)
        )

        results = db.execute(statement).scalars().all()

        return results

    finally:
        db.close()
