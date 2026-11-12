from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select

from database import SessionLocal
from ingestion.service import ingest_pdf
from generation.llm import get_llm
from models import Document
from rag import answer_question


PROJECT_DIR = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = PROJECT_DIR / "frontend" / "templates"

router = APIRouter()


class QuestionRequest(BaseModel):
    question: str


class AnswerResponse(BaseModel):
    answer: str


@router.get("/api/documents")
def list_documents():
    db = SessionLocal()
    try:
        documents = db.scalars(
            select(Document).order_by(Document.uploaded_at.desc())
        ).all()
        return [
            {
                "file_name": document.file_name,
                "uploaded_at": document.uploaded_at.isoformat(),
            }
            for document in documents
        ]
    finally:
        db.close()


@router.get("/api/health")
def health_check():
    return {"status": "ok", "model": get_llm().model_name}


@router.post("/api/ask", response_model=AnswerResponse)
def ask_question(request: QuestionRequest):
    return AnswerResponse(answer=answer_question(request.question))


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


@router.get("/", include_in_schema=False)
def frontend_index():
    return FileResponse(TEMPLATES_DIR / "index.html")
