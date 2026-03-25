"""
Gemini client for AI-powered trading decisions.
Uses Google's free Gemini API directly — no OpenRouter, no billing.
Free tier: 15 requests/min, 1M tokens/day.
"""

import asyncio
import json
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from json_repair import repair_json
from openai import AsyncOpenAI

from src.clients.xai_client import TradingDecision
from src.config.settings import settings
from src.utils.logging_setup import TradingLoggerMixin


class GeminiClient(TradingLoggerMixin):
    """
    Gemini client using Google's OpenAI-compatible endpoint.
    Free tier — no cost tracking needed.
    """

    def __init__(self, api_key: Optional[str] = None, db_manager: Any = None):
        self.api_key = api_key or settings.api.gemini_api_key
        self.db_manager = db_manager
        self.total_cost = 0.0
        self.request_count = 0

        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            timeout=60.0,
            max_retries=0,
        )

        self.primary_model = "gemini-1.5-flash"
        self.fallback_model = "gemini-1.5-flash-8b"
        self.temperature = settings.trading.ai_temperature
        self.max_tokens = settings.trading.ai_max_tokens

        self.logger.info(
            "Gemini client initialized",
            primary_model=self.primary_model,
            free_tier=True,
        )

    async def get_completion(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        strategy: str = "unknown",
        query_type: str = "completion",
        market_id: Optional[str] = None,
    ) -> Optional[str]:
        """Get a completion from Gemini."""
        for model in [self.primary_model, self.fallback_model]:
            try:
                response = await self.client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature if temperature is not None else self.temperature,
                    max_tokens=max_tokens or self.max_tokens,
                )

                if response.choices and response.choices[0].message.content:
                    self.request_count += 1
                    content = response.choices[0].message.content
                    self.logger.debug(
                        "Gemini completion succeeded",
                        model=model,
                        strategy=strategy,
                        market_id=market_id,
                    )
                    return content

            except Exception as e:
                self.logger.warning(f"Gemini model {model} failed: {e}")
                if model == self.fallback_model:
                    self.logger.error(f"All Gemini models failed: {e}")
                await asyncio.sleep(1)
                continue

        return None

    async def get_trading_decision(
        self,
        market_data: Dict[str, Any],
        portfolio_data: Dict[str, Any],
        news_summary: str = "",
    ) -> Optional[TradingDecision]:
        """Get a trading decision from Gemini."""
        prompt = self._build_trading_prompt(market_data, portfolio_data, news_summary)
        response = await self.get_compl
