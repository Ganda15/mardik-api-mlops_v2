"""Factory for the production LLM client (Azure AI Inference, Kimi-K2.6)."""
from __future__ import annotations

import os
from typing import Any


def get_llm() -> Any:
    """Build the Azure-hosted chat model.

    Imported lazily so the rest of the package does not require the Azure SDK
    to be installed for offline runs.
    """
    from langchain_azure_ai.chat_models import AzureAIChatCompletionsModel

    return AzureAIChatCompletionsModel(
        endpoint=os.environ.get("AZURE_AI_ENDPOINT", ""),
        credential=os.environ.get("AZURE_AI_API_KEY", ""),
        model_name=os.environ.get("AZURE_AI_MODEL", "Kimi-K2.6"),
    )
