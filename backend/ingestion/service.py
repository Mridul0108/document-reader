from pathlib import Path
import logging

from sqlalchemy import select

from database import SessionLocal
from ingestion.chunker import split_documents
from ingestion.embeddings import get_embedding_model
from models import Document, DocumentChunk
from ingestion.loader import load_pdf

logger = logging.getLogger(__name__)


def ingest_pdf(file_path: Path, file_name: str) -> int:
    """Extract, chunk, embed, and persist one PDF. Returns chunk count."""

    pages = load_pdf(str(file_path))
    chunks = split_documents(pages)
    if not chunks:
        raise ValueError("The PDF does not contain extractable text.")

    texts = [chunk.page_content.strip() for chunk in chunks]
    texts = [text for text in texts if text]
    if not texts:
        raise ValueError("The PDF does not contain extractable text.")

    embeddings = get_embedding_model().embed_documents(texts)
    db = SessionLocal()

    try:
        existing = db.scalar(
            select(Document).where(Document.file_name == file_name)
        )
        if existing is not None:
            db.delete(existing)
            db.flush()

        document = Document(file_name=file_name)
        db.add(document)
        db.flush()

        db.add_all(
            DocumentChunk(
                document_id=document.id,
                chunk_text=text,
                embedding=embedding,
            )
            for text, embedding in zip(texts, embeddings)
        )
        db.commit()
        return len(texts)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def sync_uploads(upload_dir: Path) -> None:
    """Index PDFs that exist on disk but are missing from the database."""
    db = SessionLocal()
    try:
        indexed_names = set(db.scalars(select(Document.file_name)).all())
    finally:
        db.close()

    for file_path in sorted(upload_dir.glob("*.pdf")):
        if file_path.name in indexed_names:
            continue
        try:
            count = ingest_pdf(file_path, file_path.name)
            logger.info("Indexed %s (%s chunks)", file_path.name, count)
        except Exception:
            logger.exception("Could not index %s", file_path.name)
