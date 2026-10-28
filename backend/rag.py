from retrieval.search import search_chunks
from generation.llm import get_llm


def answer_question(question: str):
    # Retrieve the most relevant chunks across all documents
    chunks = search_chunks(question=question,top_k=5)
    context = "\n\n".join(
        f"Document: {chunk.document.file_name}\n{chunk.chunk_text}"
        for chunk in chunks
    )

    prompt = f"""
You are answering questions using the most relevant documents.

Keep the answer concise: use at most 2 short paragraphs or 5 bullet points.

Use ONLY the information provided in the context below.

If the exact amount or situation is not covered, still provide the closest
relevant information from the context and clearly state that the exact amount
is not addressed. Do not answer only with "I don't know" when related
information is available.

If the answer cannot be found in the context, say:
"I don't know based on the provided documents."

Context:
{context}

Question:
{question}
"""

    llm = get_llm()

    response = llm.invoke(prompt)

    if response.content:
        return response.content

    return (
        "The documents do not address that exact amount. Relevant information "
        "from the documents:\n\n"
        f"{context[:1200]}"
    )
