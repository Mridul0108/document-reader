import re

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from database import SessionLocal
from models import Document, DocumentChunk
from ingestion.embeddings import get_embedding_model


def search_chunks(
    question: str,
    top_k: int = 5,
    include_all_document_openings: bool = False,
    metadata_only: bool = False,
    prefer_document_name_match: bool = False,
):
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
        

        if prefer_document_name_match:
            question_terms = {
                term for term in re.findall(r"[a-z0-9]+", question.lower())
                if len(term) >= 4
                and term not in {"summarize", "summary", "overview", "about"}
            }
            if question_terms:
                documents = db.scalars(select(Document)).all()
                matching_document_ids = {
                    document.id
                    for document in documents
                    if len(
                        question_terms
                        & set(re.findall(r"[a-z0-9]+", document.file_name.lower()))
                    ) >= 1
                }
                matching_results = [
                    chunk
                    for chunk in results
                    if chunk.document_id in matching_document_ids
                ]
                if matching_results:
                    # Once a filename/title match identifies the document,
                    # use its early chunks as summary material instead of
                    # mixing a few coincidental matches from other PDFs.
                    results = db.execute(
                        select(DocumentChunk)
                        .options(joinedload(DocumentChunk.document))
                        .where(
                            DocumentChunk.document_id.in_(matching_document_ids)
                        )
                        .order_by(DocumentChunk.document_id, DocumentChunk.id)
                        .limit(top_k)
                    ).scalars().all()

        # The opening chunk commonly contains the title, author, and other
        # document metadata. Keep it available even when semantic similarity
        # ranks later content above it.
        document_ids = {chunk.document_id for chunk in results}
        if include_all_document_openings:
            document_ids = set(
                db.scalars(select(DocumentChunk.document_id)).all()
            )
        if document_ids:
            opening_chunks = db.execute(
                select(DocumentChunk)
                .options(joinedload(DocumentChunk.document))
                .where(DocumentChunk.document_id.in_(document_ids))
                .order_by(DocumentChunk.document_id, DocumentChunk.id)
            ).scalars().all()
            first_chunk_by_document = {}
            for chunk in opening_chunks:
                first_chunk_by_document.setdefault(chunk.document_id, chunk)

            existing_ids = {chunk.id for chunk in results}
            results.extend(
                chunk
                for document_id, chunk in first_chunk_by_document.items()
                if chunk.id not in existing_ids
            )

            if metadata_only:
                return list(first_chunk_by_document.values())
       
        return results

    finally:
        db.close()
