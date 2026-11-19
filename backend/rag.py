import logging
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from openai import APIError
from sqlalchemy.orm import Session

from backend.generation.llm import get_llm
from backend.memory.buffer import add_message, get_history
from backend.memory.service import get_chat_session
from backend.memory.vector import retrieve_memories, store_memory
from backend.retrieval.search import search_chunks

logger = logging.getLogger(__name__)


def _source_line(source_names: list[str]) -> str:
    if len(source_names) == 1:
        return f"This information is from {source_names[0]}."
    if source_names:
        return "This information is from these documents: " + ", ".join(source_names) + "."
    return "This information is from the provided documents."


def answer_question(
    question: str,
    session_id: UUID,
    db: Session,
    recent_message_limit: int = 12,
    memory_top_k: int = 3,
) -> str:
    """Answer a question using document evidence and this session's context.

    Successful messages and their vector memory are flushed in the caller's
    transaction. The route commits only after this function returns.
    """
    session = get_chat_session(db, session_id)
    if session is None:
        raise ValueError("Chat session does not exist")

    history = get_history(db, session_id)[-recent_message_limit:]
    memories = retrieve_memories(db, question, session_id, top_k=memory_top_k)

    normalized_question = question.lower()
    summary_question = any(
        phrase in normalized_question
        for phrase in (
            "summarize",
            "summary",
            "essence",
            "core message",
            "central message",
            "overview",
            "main idea",
            "key idea",
            "key takeaway",
            "what is this book about",
            "what is this document about",
        )
    )
    chunks = search_chunks(
        question=question,
        top_k=8 if summary_question else 5,
        prefer_document_name_match=summary_question,
    )
    source_names = list(
        dict.fromkeys(chunk.document.file_name for chunk in chunks)
    )
    document_context = "\n\n".join(
        f"Document: {chunk.document.file_name}\n{chunk.chunk_text}"
        for chunk in chunks
    ) or "No relevant document excerpts were retrieved."
    memory_context = "\n\n".join(
        memory.content for memory in memories
    ) or "No relevant prior conversation memories were retrieved."

    system_prompt = f"""
You are a thoughtful document assistant. Answer the user's question using
provided document excerpts as the factual source. Use recent conversation and
retrieved memories to understand references and maintain continuity. Memories
are records of prior conversation, not unquestionable facts; do not treat them
as verified evidence. If a memory conflicts with the documents, prefer the
documents and say so when relevant.

Give a natural, polished answer that directly addresses the user's question.
Synthesize related points across excerpts instead of looking for one sentence
that exactly matches the question. You may explain implications or connect
ideas when that follows clearly from the excerpts, but do not invent facts,
examples, dates, or opinions not supported by them. If the excerpts are
insufficient for a factual answer, say what is supported and briefly explain
what is missing. You may refer to prior conversation when the user asks about
it or uses a reference that depends on it.

For a summary or overview, describe the document's central subject, main ideas,
and useful takeaways concisely. Do not refuse merely because the exact wording
of the question is absent from the excerpts.

Use at most 2 short paragraphs or 5 bullet points unless the user asks for
more detail. Do not add a source or document-attribution line; the application
adds that separately. Do not mention amounts unless the user asks about them.

If there is genuinely no relevant evidence in the excerpts and no useful prior
conversation context, say: "I don't know based on the provided documents."

Document context:
{document_context}

Retrieved vector memories (conversation context, not verified facts):
{memory_context}
"""
    chat_history = [
        HumanMessage(content=message.content)
        if message.role == "user"
        else AIMessage(content=message.content)
        for message in history
        if message.role in {"user", "assistant"}
    ]

    response = None
    llm = get_llm()
    for _ in range(2):
        try:
            response = llm.invoke(
                [SystemMessage(content=system_prompt), *chat_history,
                 HumanMessage(content=question)]
            )
        except APIError:
            logger.exception("LLM provider request failed")
            response = None
            break
        except Exception:
            logger.exception("Unexpected error while generating an answer")
            response = None
            break
        if response.content and str(response.content).strip():
            break

    if response is None or not response.content or not str(response.content).strip():
        return (
            f"{_source_line(source_names)}\n\n"
            "I found relevant text in your document, but couldn't generate an "
            "answer right now. Please try again in a moment."
        )

    answer = str(response.content).strip()
    attributed_answer = f"{_source_line(source_names)}\n\n{answer}"
    add_message(db, session, "user", question)
    add_message(db, session, "assistant", attributed_answer)
    store_memory(
        db,
        session_id,
        f"User question: {question}\n\nAssistant answer: {attributed_answer}",
    )
    return attributed_answer
