"""
Gemini client for AI-powered trading decisions.
Uses Google's free Gemini API directly — no OpenRouter, no billing.
Free tier: 15 requests/min, 1M tokens/day.
"""

import asyncio
import json
import re
from typing import Any, Dict, Optional

from json_repair import repair_json
from openai import AsyncOpenAI

from src.clients.xai_client import TradingDecision
from src.config.settings import settings
from src.utils.logging_setup import TradingLoggerMixin


class GeminiClient(TradingLoggerMixin):

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

        self.logger.info("Gemini client initialized", primary_model=self.primary_model, free_tier=True)

    async def get_completion(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        strategy: str = "unknown",
        query_type: str = "completion",
        market_id: Optional[str] = None,
    ) -> Optional[str]:
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
                    return response.choices[0].message.content
            except Exception as e:
                self.logger.warning(f"Gemini model {model} failed: {e}")
                await asyncio.sleep(1)
                continue
        return None

    async def get_trading_decision(
        self,
        market_data: Dict[str, Any],
        portfolio_data: Dict[str, Any],
        news_summary: str = "",
    ) -> Optional[TradingDecision]:
        prompt = self._build_trading_prompt(market_data, portfolio_data, news_summary)
        response = await self.get_completion(
            prompt=prompt,
            temperature=0.1,
            max_tokens=1000,
            strategy="gemini",
            query_type="trading_decision",
        )
        if response:
            return self._parse_trading_decision(response)
        return None

    def _build_trading_prompt(
        self,
        market_data: Dict[str, Any],
        portfolio_data: Dict[str, Any],
        news_summary: str,
    ) -> str:
        title = market_data.get("title", "Unknown Market")
        yes_price = (market_data.get("yes_bid", 0) + market_data.get("yes_ask", 100)) / 2
        no_price = (market_data.get("no_bid", 0) + market_data.get("no_ask", 100)) / 2
        volume = int(float(market_data.get("volume_fp", 0) or market_data.get("volume", 0) or 0))
        days_to_expiry = market_data.get("days_to_expiry", "Unknown")
        cash = portfolio_data.get("cash", portfolio_data.get("balance", 1000))
        truncated_news = news_summary[:600] + "..." if len(news_summary) > 600 else news_summary

        return f"""Analyze this prediction market and provide a trading decision.

Market: {title}
YES: {yes_price}c | NO: {no_price}c | Volume: ${volume:,.0f} | Days left: {days_to_expiry}
Cash: ${cash:,.2f}

Context: {truncated_news}

Rules:
- Only trade if your estimated edge (|your_prob - market_price/100|) > 5%
- Confidence must be >55% to trade
- Return ONLY JSON, no extra text

Format:
{{"action": "BUY", "side": "YES", "limit_price": 55, "confidence": 0.72, "reasoning": "brief"}}
or
{{"action": "SKIP", "side": "YES", "limit_price": 0, "confidence": 0.40, "reasoning": "no edge"}}"""

    def _parse_trading_decision(self, response_text: str) -> Optional[TradingDecision]:
        try:
            json_match = re.search(r"```(?:json)?\s*(.*?)\s*```", response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
                if not json_match:
                    return None
                json_str = json_match.group(0)

            try:
                data = json.loads(json_str)
            except json.JSONDecodeError:
                repaired = repair_json(json_str)
                data = json.loads(repaired) if repaired else None
                if not data:
                    return None

            action = data.get("action", "SKIP").upper()
            action = "BUY" if action in ("BUY_YES", "BUY_NO", "BUY") else "SKIP"
            side = data.get("side", "YES").upper()
            confidence = float(data.get("confidence", 0.5))
            limit_price = int(data.get("limit_price", 50)) if data.get("limit_price") else None

            return TradingDecision(action=action, side=side, confidence=confidence, limit_price=limit_price)

        except Exception as e:
            self.logger.error(f"Error parsing Gemini decision: {e}")
            return None

    async def close(self) -> None:
        try:
            await self.client.close()
        except Exception:
            pass
        self.logger.info("Gemini client closed", total_requests=self.request_count)
