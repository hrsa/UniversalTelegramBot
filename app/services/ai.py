from langchain_core.language_models import BaseLanguageModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy.orm import Mapped

from app.config import settings


class AIModelProviderError(Exception):
    pass


def get_llm() -> BaseLanguageModel:
    provider = settings.AI_PROVIDER.lower()
    model = settings.AI_MODEL.lower()
    temperature = settings.AI_TEMPERATURE
    max_tokens = settings.AI_MAX_TOKENS

    if provider == "openai":
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required for OpenAI provider")

        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=settings.OPENAI_API_KEY,
        )

    elif provider == "anthropic":
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is required for Anthropic provider")

        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=settings.ANTHROPIC_API_KEY,
        )

    elif provider == "ollama":
        if not settings.OLLAMA_URL:
            raise ValueError("OLLAMA_URL is required for Ollama provider")

        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=model,
            temperature=temperature,
        )

    elif provider == "groq":
        if not settings.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is required for Groq provider")

        from langchain_groq import ChatGroq
        return ChatGroq(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=settings.GROQ_API_KEY,
        )

    else:
        raise AIModelProviderError(f"Unsupported AI_PROVIDER: {provider}")

class AIService:
    def __init__(self, llm: BaseLanguageModel | None = None):
        self.llm = llm or get_llm()

    async def rewrite_announcement(
            self,
            original_text: str | Mapped[str],
            language: str | None = None,
            tone: str | None = None,
            max_length: int | None = None) -> str:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "You are an assistant that rewrites Telegram group announcements so more users would sign up."
                        "Preserve the meaning and any important links and details, but improve clarity, correct mistakes."
                        "Keep formatting compatible with Telegram HTML parse_mode (<b>, <i>, <u>, <s>, <a>, <code>, <pre>, <tg-spoiler>, etc.), and never break HTML tags."
                    ),
                ),
                (
                    "human",
                    (
                        "Original announcement:\n"
                        "----------------------\n"
                        "{original}\n"
                        "----------------------\n\n"
                        "Requirements:\n"
                        "- Tone: {tone}\n"
                        "{language_instruction}"
                        "{length_instruction}"
                        "\nReturn only the rewritten announcement text."
                    ),
                ),
            ]
        )

        language_instruction = (
            f"- Language: rewrite in {language}.\n"
            if language
            else "- Language: keep the same language as the original.\n"
        )

        length_instruction = (
            f"- Length: keep it under ~{max_length} characters.\n"
            if max_length is not None
            else "- Length: similar length to the original (a bit shorter or longer is OK).\n"
        )

        chain = prompt | self.llm | StrOutputParser()

        result = await chain.ainvoke(
            {
                "original": original_text,
                "tone": tone or "respect the tone of original message, but make it more catchy and attractive",
                "language_instruction": language_instruction,
                "length_instruction": length_instruction
            }
        )

        return result.strip()