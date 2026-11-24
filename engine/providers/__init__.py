"""Phase 03-B: Provider-agnostic AI Producer Context & Provider Adapter Registry."""

from .base import ProducerContext, ProviderInfo, build_producer_context
from .registry import (
    detect_providers,
    get_active_provider_id,
    get_provider_summary,
    invoke_llm_json,
    select_provider,
)

__all__ = [
    "ProducerContext",
    "ProviderInfo",
    "build_producer_context",
    "detect_providers",
    "get_active_provider_id",
    "get_provider_summary",
    "invoke_llm_json",
    "select_provider",
]
