from generation.llm import get_llm


llm = get_llm()

response = llm.invoke(
    "Explain RAG in one simple sentence."
)

print(response.content)