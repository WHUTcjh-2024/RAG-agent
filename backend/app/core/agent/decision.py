from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from pydantic import BaseModel, Field



class DecisionVerdict(str, Enum):
    RECOMMEND_BUY = "RECOMMEND_BUY"
    BUY_WITH_CAUTION = "BUY_WITH_CAUTION"
    NOT_RECOMMENDED = "NOT_RECOMMENDED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class FitRiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class EvidenceSourceType(str, Enum):
    BODY_PROFILE = "BODY_PROFILE"
    SKU_MEASUREMENT = "SKU_MEASUREMENT"
    PRICE = "PRICE"
    INVENTORY = "INVENTORY"
    RETURN_POLICY = "RETURN_POLICY"


class DecisionEvidence(BaseModel):
    source_type: EvidenceSourceType
    source_id: str = Field(min_length=1, max_length=128)
    field: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=500)
    observed_at: datetime


class FitRisk(BaseModel):
    area: str = Field(min_length=1, max_length=100)
    level: FitRiskLevel
    message: str = Field(min_length=1, max_length=500)
    evidence_refs: list[str] = Field(min_length=1)


class DecisionCard(BaseModel):
    decision_id: str
    verdict: DecisionVerdict
    confidence: float = Field(ge=0, le=1)
    recommended_size: str | None = None
    fit_risks: list[FitRisk] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    evidence: list[DecisionEvidence] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    alternatives: list[dict[str, Any]] = Field(default_factory=list)
    confidence_components: dict[str, float] = Field(default_factory=dict)


@dataclass(frozen=True)
class DecisionFacts:
    user_id: str
    product_id: str
    sku_id: str | None
    profile: dict[str, Any]
    sku_measurements: dict[str, Any]
    price: dict[str, Any]
    inventory: dict[str, Any]
    return_policy: dict[str, Any]
    version: str | None
    observed_at: datetime


class DecisionFactsProvider(Protocol):
    def get(self, *, user_id: str, product_id: str) -> DecisionFacts | None: ...


class JavaDecisionFactsProvider:
    """Read decision facts only from the Java business service.

    The client intentionally has no catalog fallback: local retrieval data is not a
    trusted source for price, stock, SKU measurements, or a body profile.
    """

    def __init__(self, base_url: str | None = None, timeout_seconds: float = 2) -> None:
        self.base_url = (base_url or os.getenv("AGENT_FACTS_BASE_URL", "")).rstrip("/")
        self.timeout_seconds = timeout_seconds

    def get(self, *, user_id: str, product_id: str) -> DecisionFacts | None:
        if not self.base_url:
            return None
        query = urlencode({"trusted_user_id": user_id, "product_id": product_id})
        token = os.getenv("AGENT_FACTS_INTERNAL_TOKEN", "")
        request = Request(
            f"{self.base_url}/internal/agent/decision-facts?{query}",
            headers={"X-Agent-Internal-Token": token},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as error:
            from app.core.agent.contracts import ErrorCode
            from app.core.agent.errors import AgentException

            raise AgentException(
                ErrorCode.BUSINESS_FACT_UNAVAILABLE,
                "Java business facts are temporarily unavailable.",
                status_code=503,
                retryable=True,
                stage="load_business_facts",
            ) from error
        observed_at = payload.get("observed_at") or datetime.now(timezone.utc).isoformat()
        return DecisionFacts(
            user_id=str(payload["user_id"]),
            product_id=str(payload["product_id"]),
            sku_id=payload.get("sku_id"),
            profile=dict(payload.get("profile") or {}),
            sku_measurements=dict(payload.get("sku_measurements") or {}),
            price=dict(payload.get("price") or {}),
            inventory=dict(payload.get("inventory") or {}),
            return_policy=dict(payload.get("return_policy") or {}),
            version=payload.get("version"),
            observed_at=datetime.fromisoformat(observed_at.replace("Z", "+00:00")),
        )


class DecisionCardBuilder:
    REQUIRED_PROFILE_FIELDS = ("chest_cm",)
    REQUIRED_MEASUREMENT_FIELDS = ("chest_cm", "size")

    @staticmethod
    def _evidence(
        source_type: EvidenceSourceType,
        source_id: str,
        field: str,
        value: Any,
        observed_at: datetime,
    ) -> DecisionEvidence:
        return DecisionEvidence(
            source_type=source_type,
            source_id=source_id,
            field=field,
            value=str(value),
            observed_at=observed_at,
        )

    @staticmethod
    def _number(data: dict[str, Any], key: str) -> float | None:
        value = data.get(key)
        try:
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    def build(
        self,
        *,
        facts: DecisionFacts | None,
        alternatives: list[dict[str, Any]],
    ) -> DecisionCard:
        if facts is None:
            return self._insufficient(["trustedBodyProfile", "skuMeasurement", "price", "inventory"], alternatives)

        missing: list[str] = []
        profile_chest = self._number(facts.profile, "chest_cm")
        if profile_chest is None:
            missing.append("bodyProfile.chestCm")
        measurement_chest = self._number(facts.sku_measurements, "chest_cm")
        size = str(facts.sku_measurements.get("size") or "").strip()
        if measurement_chest is None or not size:
            missing.append("skuMeasurement")
        if self._number(facts.price, "amount") is None:
            missing.append("price")
        if "in_stock" not in facts.inventory:
            missing.append("inventory")
        if missing:
            return self._insufficient(missing, alternatives)

        sku_id = facts.sku_id or facts.product_id
        evidence = [
            self._evidence(EvidenceSourceType.BODY_PROFILE, facts.user_id, "chestCm", profile_chest, facts.observed_at),
            self._evidence(EvidenceSourceType.SKU_MEASUREMENT, sku_id, "chestCm", measurement_chest, facts.observed_at),
            self._evidence(EvidenceSourceType.SKU_MEASUREMENT, sku_id, "size", size, facts.observed_at),
            self._evidence(EvidenceSourceType.PRICE, facts.product_id, "amount", facts.price["amount"], facts.observed_at),
            self._evidence(EvidenceSourceType.INVENTORY, sku_id, "inStock", facts.inventory["in_stock"], facts.observed_at),
        ]
        evidence_refs = ["BODY_PROFILE:chestCm", "SKU_MEASUREMENT:chestCm"]
        difference = measurement_chest - profile_chest
        risks: list[FitRisk] = []
        if not bool(facts.inventory["in_stock"]):
            return DecisionCard(
                decision_id=f"decision-{uuid4()}",
                verdict=DecisionVerdict.NOT_RECOMMENDED,
                confidence=0.95,
                reasons=["该 SKU 当前无库存。"],
                evidence=evidence,
                alternatives=alternatives,
                confidence_components={"rule": 1.0, "model": 0.8},
            )
        if difference < 0:
            risks.append(FitRisk(area="chest", level=FitRiskLevel.HIGH, message="商品胸围小于身体胸围，存在明显偏紧风险。", evidence_refs=evidence_refs))
            verdict = DecisionVerdict.NOT_RECOMMENDED
            confidence = 0.93
            reasons = ["实测胸围无法满足基础穿着余量。"]
        elif difference < 6:
            risks.append(FitRisk(area="chest", level=FitRiskLevel.MEDIUM, message="胸围余量较小，叠穿时可能偏紧。", evidence_refs=evidence_refs))
            verdict = DecisionVerdict.BUY_WITH_CAUTION
            confidence = 0.78
            reasons = ["尺码可穿，但建议结合版型与个人偏好确认。"]
        else:
            verdict = DecisionVerdict.RECOMMEND_BUY
            confidence = 0.86
            reasons = ["商品实测胸围与身体数据保留了合理余量。"]
        return DecisionCard(
            decision_id=f"decision-{uuid4()}",
            verdict=verdict,
            confidence=confidence,
            recommended_size=size,
            fit_risks=risks,
            reasons=reasons,
            evidence=evidence,
            alternatives=alternatives,
            confidence_components={"rule": 0.8, "model": 0.7},
        )

    @staticmethod
    def _insufficient(missing: list[str], alternatives: list[dict[str, Any]]) -> DecisionCard:
        return DecisionCard(
            decision_id=f"decision-{uuid4()}",
            verdict=DecisionVerdict.INSUFFICIENT_DATA,
            confidence=0,
            reasons=["可信业务事实不足，无法给出精确尺码或购买结论。"],
            missing_fields=list(dict.fromkeys(missing)),
            alternatives=alternatives,
            confidence_components={"rule": 0.0, "model": 0.0},
        )
