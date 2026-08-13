from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field


class AgentSkill(BaseModel):
    """Versioned, auditable capability exposed by the shopping Agent Harness."""

    id: str = Field(pattern="^[a-z][a-z0-9_]{2,63}$")
    version: str = Field(pattern=r"^v\d+$")
    description: str = Field(min_length=1, max_length=240)
    risk_level: str = Field(pattern="^(read_only|confirm_required)$")
    allowed_tools: list[str] = Field(default_factory=list)
    supported_intents: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class _SkillDefinition:
    skill: AgentSkill


class ShoppingSkillRegistry:
    """Maps one business task to a small, versioned and tool-bounded skill.

    This is deliberately a domain registry, rather than a second planner. The
    workflow still decides *when* to use a tool; the skill contract decides
    which tools are allowed and whether a write must wait for confirmation.
    """

    _definitions = {
        "catalog_retrieval": _SkillDefinition(
            AgentSkill(
                id="catalog_retrieval",
                version="v1",
                description="Searches and inspects verified catalog products with text, image, or hybrid retrieval.",
                risk_level="read_only",
                allowed_tools=[
                    "search_products_by_text",
                    "search_products_by_image",
                    "hybrid_search",
                    "get_product_detail",
                    "compare_products",
                    "update_user_preference",
                ],
                supported_intents=[
                    "text_recommendation",
                    "image_search",
                    "hybrid_search",
                ],
            )
        ),
        "product_comparison": _SkillDefinition(
            AgentSkill(
                id="product_comparison",
                version="v1",
                description="Compares two or three catalog products using verified fields only.",
                risk_level="read_only",
                allowed_tools=["compare_products", "update_user_preference"],
                supported_intents=["compare"],
            )
        ),
        "purchase_decision": _SkillDefinition(
            AgentSkill(
                id="purchase_decision",
                version="v1",
                description="Builds a purchase decision card from Java-owned fit and SKU facts.",
                risk_level="read_only",
                allowed_tools=[
                    "search_products_by_text",
                    "get_product_detail",
                    "update_user_preference",
                ],
                supported_intents=["text_recommendation"],
            )
        ),
        "wardrobe_planning": _SkillDefinition(
            AgentSkill(
                id="wardrobe_planning",
                version="v1",
                description="Builds outfit plans from a versioned wardrobe and missing-category retrieval.",
                risk_level="read_only",
                allowed_tools=["search_products_by_text", "update_user_preference"],
                supported_intents=["wardrobe_plan"],
            )
        ),
        "purchase_handoff": _SkillDefinition(
            AgentSkill(
                id="purchase_handoff",
                version="v1",
                description="Prepares a signed cart confirmation without directly writing commerce data.",
                risk_level="confirm_required",
                allowed_tools=["get_product_detail", "update_user_preference"],
                supported_intents=["cart_handoff"],
            )
        ),
    }

    @classmethod
    def all(cls) -> list[AgentSkill]:
        return [definition.skill.model_copy(deep=True) for definition in cls._definitions.values()]

    @classmethod
    def resolve(cls, *, intent: str, decision_product_id: str | None) -> AgentSkill:
        if decision_product_id:
            key = "purchase_decision"
        elif intent in {"text_recommendation", "image_search", "hybrid_search"}:
            key = "catalog_retrieval"
        elif intent == "compare":
            key = "product_comparison"
        elif intent == "wardrobe_plan":
            key = "wardrobe_planning"
        else:
            key = "purchase_handoff"
        return cls._definitions[key].skill.model_copy(deep=True)

    @staticmethod
    def permits(skill: AgentSkill, tool: str | None) -> bool:
        return tool is None or tool in skill.allowed_tools
