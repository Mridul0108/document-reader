import os
from functools import lru_cache

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()


@lru_cache(maxsize=1)
def get_llm():
    return ChatOpenAI(
        # Pin a general-purpose chat model. `openrouter/free` is a router
        # that can select classification/safety models for normal questions.
        model="liquid/lfm-2.5-2.6b:free",
        temperature=0,
        max_tokens=600,
        max_retries=2,
        timeout=60,
        reasoning_effort="low",
        extra_body={"provider": {"allow_fallbacks": True}},
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1",
    )
