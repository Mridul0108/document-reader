from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import SessionLocal, get_db
from backend.ingestion.service import ingest_pdf
from backend.generation.llm import get_llm
from backend.memory.service import (
    create_chat_session,
    delete_chat_session,
    get_chat_messages,
    get_chat_session,
    list_chat_sessions,
)
from backend.models import Document
from backend.rag import answer_question


PROJECT_DIR = Path(__file__).resolve().parents[2]
UPLOADS_DIR = PROJECT_DIR / "uploads"
TEMPLATES_DIR = PROJECT_DIR / "frontend" / "templates"

router = APIRouter()


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1)
    session_id: UUID


class AnswerResponse(BaseModel):
    answer: str


class CreateSessionRequest(BaseModel):
    title: str = Field(default="New Chat", max_length=200)


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    role: str
    content: str
    created_at: datetime


class ChatSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ChatSessionDetailResponse(ChatSessionResponse):
    messages: list[ChatMessageResponse]


@router.get("/api/health")
def health_check():
    return {"status": "ok", "model": get_llm().model_name}


@router.post("/api/sessions", response_model=ChatSessionResponse)
def create_session(
    request: CreateSessionRequest,
    db: Session = Depends(get_db),
):
    try:
        session = create_chat_session(db, request.title)
        db.commit()
        db.refresh(session)
        return session
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500, detail="The conversation could not be created."
        ) from exc


@router.get("/api/sessions", response_model=list[ChatSessionResponse])
def get_sessions(db: Session = Depends(get_db)):
    return list_chat_sessions(db)


@router.get(
    "/api/sessions/{session_id}", response_model=ChatSessionDetailResponse
)
def get_session(session_id: UUID, db: Session = Depends(get_db)):
    session = get_chat_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "messages": get_chat_messages(db, session_id),
    }


@router.delete("/api/sessions/{session_id}")
def remove_session(session_id: UUID, db: Session = Depends(get_db)):
    session = get_chat_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    try:
        delete_chat_session(db, session)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500, detail="The conversation could not be deleted."
        ) from exc
    return {"id": str(session_id), "deleted": True}



@router.get("/", include_in_schema=False)
def frontend_index():
    return FileResponse(TEMPLATES_DIR / "index.html")


@router.get("/api/documents")
def list_documents():
    db = SessionLocal()
    try:
        documents = db.scalars(
            select(Document).order_by(Document.uploaded_at.desc())
        ).all()
        print(documents)
        return [
            {
                "id": document.id,
                "file_name": document.file_name,
                "uploaded_at": document.uploaded_at.isoformat(),
            }
            for document in documents
        ]
    finally:
        db.close()


@router.delete("/api/documents/{document_id}")
def delete_document(document_id: int):
    db = SessionLocal()
    tombstone = None
    original_path = None
    try:
        document = db.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Source not found.")

        file_name = document.file_name
        original_path = UPLOADS_DIR / Path(file_name).name
        if original_path.exists():
            # Hide the PDF from startup indexing while the database delete is
            # committed. Restore it if the transaction fails.
            tombstone = UPLOADS_DIR / f".{uuid4().hex}.deleted"
            original_path.replace(tombstone)

        db.delete(document)
        db.commit()
    except Exception:
        db.rollback()
        if tombstone is not None and tombstone.exists() and original_path is not None:
            tombstone.replace(original_path)
        raise
    finally:
        db.close()

    if tombstone is not None:
        tombstone.unlink(missing_ok=True)
    return {"file_name": file_name, "deleted": True}




@router.post("/api/ask", response_model=AnswerResponse)
def ask_question(request: QuestionRequest, db: Session = Depends(get_db)):
    session = get_chat_session(db, request.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    try:
        answer = answer_question(request.question, request.session_id, db)
        db.commit()
        return AnswerResponse(answer=answer)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="The answer could not be generated or saved.",
        ) from exc




@router.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    file_name = Path(file.filename or "").name
    if not file_name or Path(file_name).suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    upload_path = PROJECT_DIR / "uploads" / file_name
    upload_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        upload_path.write_bytes(await file.read())
        chunk_count = ingest_pdf(upload_path, file_name)
    except ValueError as exc:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500,
            detail="The document could not be indexed.",
        ) from exc

    return {"file_name": file_name, "chunks": chunk_count}
