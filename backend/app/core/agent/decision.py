from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from pydantic import BaseModel, Field

from app.core.agent.resilience import CircuitBreaker


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


class FactSourceKind(str, Enum):
    USER_DECLARED = "USER_DECLARED"
    USER_CONFIRMED = "USER_CONFIRMED"
    MERCHANT_FEED = "MERCHANT_FEED"
    PARTNER_API = "PARTNER_API"
    AFFILIATE_API = "AFFILIATE_API"
    OCR_CANDIDATE = "OCR_CANDIDATE"
    MODEL_INFERENCE = "MODEL_INFERENCE"
    UNKNOWN = "UNKNOWN"


class PassportStatus(str, Enum):
    VERIFIED = "VERIFIED"
    INCOMPLETE = "INCOMPLETE"


class VerificationStatus(str, Enum):
    PASSED = "PASSED"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"


class FactProvenance(BaseModel):
    source_kind: FactSourceKind = FactSourceKind.UNKNOWN
    source_id: str = Field(min_length=1, max_length=256)
    source_label: str = Field(min_length=1, max_length=120)
    observed_at: datetime
    confidence: float = Field(ge=0, le=1)
    verified: bool = False


class DecisionEvidence(BaseModel):
    source_type: EvidenceSourceType
    source_id: str = Field(min_length=1, max_length=256)
    field: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=500)
    observed_at: datetime
    source_kind: FactSourceKind = FactSourceKind.UNKNOWN
    source_label: str = "来源未验证"
    confidence: float = Field(default=0, ge=0, le=1)
    verified: bool = False


class ProductFactPassport(BaseModel):
    product_id: str = Field(min_length=1, max_length=128)
    sku_id: str | None = Field(default=None, max_length=128)
    version: str | None = Field(default=None, max_length=128)
    observed_at: datetime
    status: PassportStatus
    facts: list[DecisionEvidence] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)


class VerificationCheck(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=120)
    status: CheckStatus
    message: str = Field(min_length=1, max_length=500)
    evidence_refs: list[str] = Field(default_factory=list)


class DecisionVerification(BaseModel):
    status: VerificationStatus
    checks: list[VerificationCheck] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)


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
    fact_passport: ProductFactPassport
    verification: DecisionVerification
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
    provenance: dict[str, dict[str, Any]] = field(default_factory=dict)


class DecisionFactsProvider(Protocol):
    def get(self, *, user_id: str, product_id: str) -> DecisionFacts | None: ...


class JavaDecisionFactsProvider:
    """Read decision facts only from the Java business service.

    Local retrieval data deliberately cannot become a business fact: price, stock,
    size and a body profile must carry server-issued provenance before a purchase
    decision can rely on them.
    """

    def __init__(self, base_url: str | None = None, timeout_seconds: float = 2) -> None:
        self.base_url = (base_url or os.getenv("AGENT_FACTS_BASE_URL", "")).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._breaker = CircuitBreaker("load_business_facts")

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
            def load() -> dict[str, Any]:
                with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                    return json.loads(response.read().decode("utf-8"))

            payload = self._breaker.call(load)
        except Exception as error:
            if getattr(error, "code", None) is not None:
                raise

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
            provenance=dict(payload.get("provenance") or {}),
        )


class DecisionVerifier:
    """Deterministically vetoes decisions that lack a complete trusted evidence set."""

    _TRUSTED_SOURCES = {
        FactSourceKind.USER_DECLARED,
        FactSourceKind.USER_CONFIRMED,
        FactSourceKind.MERCHANT_FEED,
        FactSourceKind.PARTNER_API,
        FactSourceKind.AFFILIATE_API,
    }

    def verify(
        self,
        *,
        facts: DecisionFacts | None,
        provenance: dict[str, FactProvenance],
        budget: Any = None,
    ) -> DecisionVerification:
        if facts is None:
            missing = [
                "trustedBodyProfile",
                "skuMeasurement",
                "price",
                "inventory",
                "returnPolicy",
            ]
            return DecisionVerification(
                status=VerificationStatus.BLOCKED,
                missing_fields=missing,
                checks=[
                    VerificationCheck(
                        code="trusted_facts",
                        label="可信业务事实",
                        status=CheckStatus.FAIL,
                        message="未获得经过网关授权的身体档案与 SKU 事实。",
                    )
                ],
            )

        checks: list[VerificationCheck] = []
        missing: list[str] = []

        self._require(
            checks, missing, "bodyProfile.chestCm", "身体胸围", facts.profile.get("chest_cm"),
            provenance.get("bodyProfile.chestCm"), "BODY_PROFILE:chestCm",
        )
        self._require(
            checks, missing, "skuMeasurement.chestCm", "SKU 胸围实测", facts.sku_measurements.get("chest_cm"),
            provenance.get("skuMeasurement.chestCm"), "SKU_MEASUREMENT:chestCm",
        )
        self._require(
            checks, missing, "skuMeasurement.size", "SKU 尺码", facts.sku_measurements.get("size"),
            provenance.get("skuMeasurement.size"), "SKU_MEASUREMENT:size",
        )
        self._require(
            checks, missing, "price.amount", "商品价格", facts.price.get("amount"),
            provenance.get("price.amount"), "PRICE:amount",
        )
        self._require(
            checks, missing, "inventory.inStock", "商品库存", facts.inventory.get("in_stock"),
            provenance.get("inventory.inStock"), "INVENTORY:inStock",
            allow_false=True,
        )
        self._require(
            checks, missing, "returnPolicy.summary", "退换规则", facts.return_policy.get("summary"),
            provenance.get("returnPolicy.summary"), "RETURN_POLICY:summary",
        )

        price = self._number(facts.price.get("amount"))
        budget_amount = self._number(budget)
        if budget is None or budget_amount is None:
            checks.append(
                VerificationCheck(
                    code="budget", label="预算约束", status=CheckStatus.SKIPPED,
                    message="用户未提供可校验预算。",
                    evidence_refs=["PRICE:amount"] if price is not None else [],
                )
            )
        elif price is None:
            checks.append(
                VerificationCheck(
                    code="budget", label="预算约束", status=CheckStatus.SKIPPED,
                    message="价格事实缺失，无法校验预算。",
                )
            )
        elif price <= budget_amount:
            checks.append(
                VerificationCheck(
                    code="budget", label="预算约束", status=CheckStatus.PASS,
                    message="商品价格符合当前预算。", evidence_refs=["PRICE:amount"],
                )
            )
        else:
            checks.append(
                VerificationCheck(
                    code="budget", label="预算约束", status=CheckStatus.FAIL,
                    message="商品价格超过当前预算。", evidence_refs=["PRICE:amount"],
                )
            )

        in_stock = facts.inventory.get("in_stock")
        if in_stock is False:
            checks.append(
                VerificationCheck(
                    code="inventory_available", label="可售状态", status=CheckStatus.FAIL,
                    message="该 SKU 当前无库存。", evidence_refs=["INVENTORY:inStock"],
                )
            )
        elif in_stock is True:
            checks.append(
                VerificationCheck(
                    code="inventory_available", label="可售状态", status=CheckStatus.PASS,
                    message="该 SKU 当前可售。", evidence_refs=["INVENTORY:inStock"],
                )
            )

        if missing:
            status = VerificationStatus.BLOCKED
        elif any(check.status == CheckStatus.FAIL for check in checks):
            status = VerificationStatus.REJECTED
        else:
            status = VerificationStatus.PASSED
        return DecisionVerification(status=status, checks=checks, missing_fields=list(dict.fromkeys(missing)))

    def _require(
        self,
        checks: list[VerificationCheck],
        missing: list[str],
        code: str,
        label: str,
        value: Any,
        provenance: FactProvenance | None,
        evidence_ref: str,
        *,
        allow_false: bool = False,
    ) -> None:
        present = value is not None and value != "" and (allow_false or value is not False)
        if not present:
            missing.append(code)
            checks.append(VerificationCheck(
                code=code, label=label, status=CheckStatus.FAIL,
                message=f"缺少{label}，不能作为购买依据。",
            ))
            return
        if not self._trusted(provenance):
            missing.append(f"{code}.provenance")
            checks.append(VerificationCheck(
                code=code, label=label, status=CheckStatus.FAIL,
                message=f"{label}来源未核验，不能作为购买依据。",
                evidence_refs=[evidence_ref],
            ))
            return
        checks.append(VerificationCheck(
            code=code, label=label, status=CheckStatus.PASS,
            message=f"{label}已由{provenance.source_label}核验。",
            evidence_refs=[evidence_ref],
        ))

    def _trusted(self, provenance: FactProvenance | None) -> bool:
        return bool(
            provenance
            and provenance.verified
            and provenance.source_kind in self._TRUSTED_SOURCES
            and provenance.confidence > 0
        )

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None


class DecisionCardBuilder:
    def __init__(self, verifier: DecisionVerifier | None = None) -> None:
        self.verifier = verifier or DecisionVerifier()

    def build(
        self,
        *,
        facts: DecisionFacts | None,
        alternatives: list[dict[str, Any]],
        budget: Any = None,
        product_id: str | None = None,
    ) -> DecisionCard:
        passport = self._passport(facts, product_id)
        provenance = self._provenance_map(facts)
        verification = self.verifier.verify(facts=facts, provenance=provenance, budget=budget)
        if facts is None or verification.status == VerificationStatus.BLOCKED:
            return self._insufficient(alternatives, passport, verification)

        profile_chest = self._number(facts.profile, "chest_cm")
        measurement_chest = self._number(facts.sku_measurements, "chest_cm")
        size = str(facts.sku_measurements["size"]).strip()
        evidence = passport.facts
        if verification.status == VerificationStatus.REJECTED:
            reasons = [
                check.message for check in verification.checks if check.status == CheckStatus.FAIL
            ]
            return DecisionCard(
                decision_id=f"decision-{uuid4()}",
                verdict=DecisionVerdict.NOT_RECOMMENDED,
                confidence=self._confidence(passport, 0.9),
                reasons=reasons,
                evidence=evidence,
                fact_passport=passport,
                verification=verification,
                alternatives=alternatives,
                confidence_components={"rule": 1.0, "model": 0.0, "fact_quality": self._fact_quality(passport)},
            )

        assert profile_chest is not None and measurement_chest is not None
        difference = measurement_chest - profile_chest
        risks: list[FitRisk] = []
        if difference < 0:
            risks.append(FitRisk(
                area="chest", level=FitRiskLevel.HIGH,
                message="商品胸围小于身体胸围，存在明显偏紧风险。",
                evidence_refs=["BODY_PROFILE:chestCm", "SKU_MEASUREMENT:chestCm"],
            ))
            verdict = DecisionVerdict.NOT_RECOMMENDED
            confidence = 0.93
            reasons = ["实测胸围无法满足基础穿着余量。"]
        elif difference < 6:
            risks.append(FitRisk(
                area="chest", level=FitRiskLevel.MEDIUM,
                message="胸围余量较小，叠穿时可能偏紧。",
                evidence_refs=["BODY_PROFILE:chestCm", "SKU_MEASUREMENT:chestCm"],
            ))
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
            confidence=self._confidence(passport, confidence),
            recommended_size=size,
            fit_risks=risks,
            reasons=reasons,
            evidence=evidence,
            fact_passport=passport,
            verification=verification,
            alternatives=alternatives,
            confidence_components={"rule": 0.8, "model": 0.0, "fact_quality": self._fact_quality(passport)},
        )

    def _passport(
        self, facts: DecisionFacts | None, product_id: str | None
    ) -> ProductFactPassport:
        observed_at = facts.observed_at if facts else datetime.now(timezone.utc)
        if facts is None:
            return ProductFactPassport(
                product_id=product_id or "unknown-product",
                observed_at=observed_at,
                status=PassportStatus.INCOMPLETE,
                missing_fields=["trustedBodyProfile", "skuMeasurement", "price", "inventory", "returnPolicy"],
            )
        provenance = self._provenance_map(facts)
        source_values = (
            (EvidenceSourceType.BODY_PROFILE, "bodyProfile.chestCm", "chestCm", facts.profile.get("chest_cm")),
            (EvidenceSourceType.SKU_MEASUREMENT, "skuMeasurement.chestCm", "chestCm", facts.sku_measurements.get("chest_cm")),
            (EvidenceSourceType.SKU_MEASUREMENT, "skuMeasurement.size", "size", facts.sku_measurements.get("size")),
            (EvidenceSourceType.PRICE, "price.amount", "amount", facts.price.get("amount")),
            (EvidenceSourceType.INVENTORY, "inventory.inStock", "inStock", facts.inventory.get("in_stock")),
            (EvidenceSourceType.RETURN_POLICY, "returnPolicy.summary", "summary", facts.return_policy.get("summary")),
        )
        evidence = [
            self._evidence(source_type, key, field_name, value, provenance[key])
            for source_type, key, field_name, value in source_values
            if value not in (None, "") and key in provenance
        ]
        required = {"bodyProfile.chestCm", "skuMeasurement.chestCm", "skuMeasurement.size", "price.amount", "inventory.inStock", "returnPolicy.summary"}
        available = {
            key for _source_type, key, _field_name, value in source_values
            if value not in (None, "") and key in provenance and self.verifier._trusted(provenance[key])
        }
        missing = sorted(required - available)
        return ProductFactPassport(
            product_id=facts.product_id,
            sku_id=facts.sku_id,
            version=facts.version,
            observed_at=facts.observed_at,
            status=PassportStatus.VERIFIED if not missing else PassportStatus.INCOMPLETE,
            facts=evidence,
            missing_fields=missing,
        )

    def _provenance_map(self, facts: DecisionFacts | None) -> dict[str, FactProvenance]:
        if facts is None:
            return {}
        result: dict[str, FactProvenance] = {}
        for key, value in facts.provenance.items():
            try:
                result[key] = FactProvenance.model_validate(value)
            except (TypeError, ValueError):
                continue
        return result

    @staticmethod
    def _evidence(
        source_type: EvidenceSourceType,
        _key: str,
        field_name: str,
        value: Any,
        provenance: FactProvenance,
    ) -> DecisionEvidence:
        return DecisionEvidence(
            source_type=source_type,
            source_id=provenance.source_id,
            field=field_name,
            value=str(value),
            observed_at=provenance.observed_at,
            source_kind=provenance.source_kind,
            source_label=provenance.source_label,
            confidence=provenance.confidence,
            verified=provenance.verified,
        )

    @staticmethod
    def _number(data: dict[str, Any], key: str) -> float | None:
        try:
            value = data.get(key)
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _fact_quality(passport: ProductFactPassport) -> float:
        if not passport.facts:
            return 0.0
        return round(sum(item.confidence for item in passport.facts if item.verified) / 6, 2)

    def _confidence(self, passport: ProductFactPassport, base: float) -> float:
        return round(min(base, base * self._fact_quality(passport)), 2)

    @staticmethod
    def _insufficient(
        alternatives: list[dict[str, Any]],
        passport: ProductFactPassport,
        verification: DecisionVerification,
    ) -> DecisionCard:
        return DecisionCard(
            decision_id=f"decision-{uuid4()}",
            verdict=DecisionVerdict.INSUFFICIENT_DATA,
            confidence=0,
            reasons=["可信业务事实或来源证明不足，无法给出精确尺码或购买结论。"],
            evidence=passport.facts,
            fact_passport=passport,
            verification=verification,
            missing_fields=list(dict.fromkeys([*passport.missing_fields, *verification.missing_fields])),
            alternatives=alternatives,
            confidence_components={"rule": 0.0, "model": 0.0, "fact_quality": 0.0},
        )
