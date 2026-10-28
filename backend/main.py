from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Keep imports compatible with both `python backend/main.py` and Uvicorn.
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"
STATIC_DIR = FRONTEND_DIR / "static"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from rag import answer_question  # noqa: E402


class QuestionRequest(BaseModel):
    question: str


class AnswerResponse(BaseModel):
    answer: str


app = FastAPI(title="Document RAG")


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


@app.post("/api/ask", response_model=AnswerResponse)
def ask_question(request: QuestionRequest):
    return AnswerResponse(answer=answer_question(request.question))


@app.get("/", include_in_schema=False)
def frontend_index():
    return FileResponse(TEMPLATES_DIR / "index.html")


app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIR),
    name="static",
)


def cli():
    print("Ask questions about your documents.")
    print("Type 'exit' to quit.\n")

    while True:
        question = input("You: ")

        if question.lower() == "exit":
            break

        answer = answer_question(question=question)
        print("\nAI:", answer)
        print()


if __name__ == "__main__":
    cli()
