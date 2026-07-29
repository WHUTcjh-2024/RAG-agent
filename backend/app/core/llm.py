from __future__ import annotations

import json
import logging
import os
from typing import Any

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.core.agent.contracts import ErrorCode
from app.core.agent.prompts import (
    GROUNDED_RECOMMENDATION_HUMAN,
    GROUNDED_RECOMMENDATION_SYSTEM,
)
from app.core.request_id import current_request_id

logger = logging.getLogger(__name__)


class ProductReason(BaseModel):
    article_id: str
    reason: str = Field(min_length=1, max_length=180)


class GroundedRecommendation(BaseModel):
    intro: str = Field(min_length=1, max_length=240)
    recommendations: list[ProductReason] = Field(max_length=3)


class GroundedRecommendationGenerator:
    def __init__(self, chain=None) -> None:
        self.parser = PydanticOutputParser(pydantic_object=GroundedRecommendation)
        self.chain = chain if chain is not None else self._create_chain_from_env()

    def _create_chain_from_env(self):
        if os.getenv("LLM_ENABLED", "true").strip().casefold() not in {"1", "true", "yes"}:
            return None
        api_key = os.getenv("LLM_API_KEY", "").strip()
        model = os.getenv("LLM_MODEL", "").strip()
        if not api_key or not model:
            return None
        base_url = os.getenv("LLM_BASE_URL", "").strip() or None
        llm = ChatOpenAI(
            api_key=api_key,
            model=model,
            base_url=base_url,
            temperature=0,
            max_retries=2,
            request_timeout=30,
            extra_body={
                "thinking": {"type": os.getenv("LLM_THINKING", "disabled")}
            },
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", GROUNDED_RECOMMENDATION_SYSTEM),
                ("human", GROUNDED_RECOMMENDATION_HUMAN),
            ]
        ).partial(format_instructions=self.parser.get_format_instructions())
        return prompt | llm | self.parser

    @staticmethod
    def _fallback(products: list[dict[str, Any]], language: str = "zh") -> tuple[str, dict[str, str]]:
        if not products:
            return ("No matching products were found. Try relaxing the color or category filters." if language == "en" else "暂时没有找到符合条件的商品，可以放宽颜色或品类限制。"), {}
        reasons: dict[str, str] = {}
        for product in products[:3]:
            article_id = str(product["article_id"])
            name = product.get("prod_name") or "这件商品"
            category = product.get("product_type_name") or "服装"
            color = product.get("colour_group_name") or "未标注颜色"
            reasons[article_id] = (f"{name} is a {category} in {color}, matching the current search criteria." if language == "en" else f"{name} 属于 {category}，颜色为 {color}，与当前检索条件匹配。")
        return ("I selected these candidates from the real product catalog." if language == "en" else "根据你的需求，我从真实商品库中筛出了这些候选。"), reasons

    def generate(
        self,
        user_query: str,
        products: list[dict[str, Any]],
        slots: dict[str, Any],
        history: list[dict[str, str]],
        language: str = "zh",
    ) -> tuple[str, dict[str, str]]:
        if not products or self.chain is None:
            return self._fallback(products, language)

        allowed = {str(product["article_id"]) for product in products}
        safe_products = [
            {
                key: product.get(key)
                for key in (
                    "article_id",
                    "prod_name",
                    "product_type_name",
                    "product_group_name",
                    "colour_group_name",
                    "garment_group_name",
                    "detail_desc",
                    "score",
                    "text_score",
                    "image_score",
                )
            }
            for product in products
        ]
        try:
            output = self.chain.invoke(
                {
                    "user_query": user_query,
                    "response_language": "English" if language == "en" else "中文",
                    "slots": json.dumps(slots, ensure_ascii=False),
                    "history": json.dumps(history[-6:], ensure_ascii=False),
                    "products": json.dumps(safe_products, ensure_ascii=False),
                }
            )
            if isinstance(output, dict):
                output = GroundedRecommendation.model_validate(output)
            reasons: dict[str, str] = {}
            for item in output.recommendations:
                if item.article_id in allowed and item.article_id not in reasons:
                    reasons[item.article_id] = item.reason
            if not reasons:
                return self._fallback(products, language)
            return output.intro, reasons
        except Exception as error:
            logger.warning(
                "agent_model_fallback request_id=%s code=%s stage=generate_answer error_type=%s",
                current_request_id(),
                ErrorCode.MODEL_UNAVAILABLE.value,
                type(error).__name__,
            )
            return self._fallback(products, language)
