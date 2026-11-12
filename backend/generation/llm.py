import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()
load_dotenv(Path(__file__).resolve().parents[2] / ".env.groq", override=True)


@lru_cache(maxsize=1)
def get_llm():
    return ChatOpenAI(
        model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        temperature=0,
        max_tokens=800,
        max_retries=3,
        timeout=60,
        api_key=os.getenv("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
    )
