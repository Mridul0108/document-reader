from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# Keep imports compatible with both `python backend/main.py` and Uvicorn.
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"
STATIC_DIR = FRONTEND_DIR / "static"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from backend.ingestion.service import sync_uploads  # noqa: E402
from backend.database import SessionLocal  # noqa: E402
from backend.memory.service import create_chat_session  # noqa: E402
from backend.rag import answer_question  # noqa: E402
from backend.router import router  # noqa: E402


app = FastAPI(title="Document RAG")
app.include_router(router)


@app.on_event("startup")
def index_existing_uploads():
    sync_uploads(PROJECT_DIR / "uploads")


app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIR),
    name="static",
)


def cli():
    print("Ask questions about your documents.")
    print("Type 'exit' to quit.\n")

    db = SessionLocal()
    try:
        session = create_chat_session(db)
        db.commit()
    except Exception:
        db.rollback()
        db.close()
        raise

    try:
        while True:
            question = input("You: ")

            if question.lower() == "exit":
                break

            try:
                answer = answer_question(question, session.id, db)
                db.commit()
            except Exception:
                db.rollback()
                raise
            print("\nAI:", answer)
            print()
    finally:
        db.close()


if __name__ == "__main__":
    # Direct CLI execution does not trigger FastAPI startup events.
    sync_uploads(PROJECT_DIR / "uploads")
    cli()
