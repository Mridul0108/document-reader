from openai import APIError

from retrieval.search import search_chunks
from generation.llm import get_llm


def _source_line(source_names: list[str]) -> str:
    if len(source_names) == 1:
        return f"This information is from {source_names[0]}."
    if source_names:
        return "This information is from these documents: " + ", ".join(source_names) + "."
    return "This information is from the provided documents."


def answer_question(question: str):
    # Retrieve the most relevant chunks across all documents
    normalized_question = question.lower()
    summary_question = any(
        phrase in normalized_question
        for phrase in (
            "summarize",
            "summary",
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
        # A summary needs enough passages to synthesize the document, while
        # ordinary questions should stay focused on the closest evidence.
        top_k=8 if summary_question else 5,
        prefer_document_name_match=summary_question,
    )
    source_names = list(
        dict.fromkeys(chunk.document.file_name for chunk in chunks)
    )

    context = "\n\n".join(
        f"Document: {chunk.document.file_name}\n{chunk.chunk_text}"
        for chunk in chunks
    )

    prompt = f"""
You are a thoughtful document assistant. Answer the user's question using the
provided document excerpts as your factual source.

Give a natural, polished answer that directly addresses what the user asked.
Synthesize related points across excerpts instead of looking for one sentence
that exactly matches the question. You may explain implications or connect
ideas when that follows clearly from the excerpts, but do not invent facts,
examples, dates, or opinions that are not supported by them. If the excerpts
are insufficient, say what is supported and briefly explain what is missing.

For a summary or overview, describe the document's central subject, main ideas,
and useful takeaways in a concise form. Do not refuse merely because the exact
wording of the question is absent from the excerpts.

Use at most 2 short paragraphs or 5 bullet points unless the user asks for
more detail. Do not add a source or document-attribution line; the application
adds that line separately. Do not mention amounts unless the user asks about
an amount.

If there is genuinely no relevant evidence in the excerpts, say:
"I don't know based on the provided documents."

Document excerpts:
{context}

User question:
{question}
"""

    llm = get_llm()

    response = None
    llm_error = None
    for _ in range(2):
        try:
            response = llm.invoke(prompt)
        except APIError as exc:
            llm_error = str(exc)
            response = None
            break
        except Exception as exc:
            llm_error = str(exc)
            response = None
            break
        if response.content and str(response.content).strip():
            break

    if response is not None and response.content:
        return f"{_source_line(source_names)}\n\n{response.content}"

    if llm_error and "free-models-per-day" in llm_error:
        fallback_notice = (
            "The OpenRouter free-model quota has been exhausted. "
            "Add credits/use your own provider key or set OPENROUTER_MODEL "
            "to a funded model. Relevant passages:\n"
        )
    else:
        fallback_notice = (
            "The answer service is temporarily unavailable. Relevant passages:\n"
        )

    return (
        f"{_source_line(source_names)}\n\n"
        + fallback_notice
        + context[:1000]
    )
