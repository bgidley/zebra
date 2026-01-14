"""LLM provider implementations."""

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from zebra_tasks.llm.providers.registry import get_provider, register_provider

__all__ = ["get_provider", "register_provider"]
