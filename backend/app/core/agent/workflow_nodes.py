from __future__ import annotations

from typing import Any

from app.core.agent.contracts import AgentResponse, Intent, NodeTrace, ToolTrace
from app.core.agent.errors import invalid_input
from app.core.agent.memory import validate_session_id
from app.core.agent.orchestrator import ShoppingAgentOrchestrator
from app.core.agent.workflow_state import AgentState, validate_task_id
from app.core.request_id import normalize_request_id


class ShoppingAgentWorkflowNodes:
    """Single-purpose business nodes; persistence and retries live in the graph."""

    def __init__(self, orchestrator: ShoppingAgentOrchestrator) -> None:
        self.orchestrator = orchestrator

    @property
    def mapping(self) -> dict[str, Any]:
        return {
            "validate_input": self.validate_input,
            "understand_request": self.understand_request,
            "load_context": self.load_context,
            "plan_tools": self.plan_tools,
            "retrieve_candidates": self.retrieve_candidates,
            "verify_constraints": self.verify_constraints,
            "build_evidence": self.build_evidence,
            "generate_answer": self.generate_answer,
            "wait_for_confirmation": self.wait_for_confirmation,
            "complete": self.complete,
        }

    @staticmethod
    def summary(node: str, updates: AgentState) -> str:
        if node == "validate_input":
            return "input accepted"
        if node == "understand_request":
            return f"captured {len(updates.get('slots', {}))} request slots"
        if node == "load_context":
            return f"loaded {len(updates.get('slots', {}))} merged slots"
        if node == "plan_tools":
            return f"planned {updates.get('planned_tool') or 'no external tool'}"
        if node == "retrieve_candidates":
            count = len(
                updates.get("candidate_products", []) or updates.get("comparison", [])
            )
            return f"retrieved {count} catalog products"
        if node == "verify_constraints":
            return f"verified {len(updates.get('candidate_products', []))} candidates"
        if node == "build_evidence":
            return f"built {len(updates.get('evidence', []))} evidence records"
        if node == "generate_answer":
            return "generated grounded answer"
        if node == "wait_for_confirmation":
            return "prepared Java commerce handoff"
        if node == "complete":
            return "task completed"
        return "completed"

    def validate_input(self, state: AgentState) -> AgentState:
        session_id = validate_session_id(state["session_id"])
        task_id = validate_task_id(state["task_id"])
        message = state.get("message", "").strip()
        if not message and not state.get("image_path"):
            raise invalid_input("Message or image is required.")
        return {
            "session_id": session_id,
            "trusted_user_id": session_id,
            "task_id": task_id,
            "request_id": normalize_request_id(state.get("request_id")),
            "message": message,
            "language": state.get("language", "zh"),
            "status": "validated",
            "error": None,
        }

    def understand_request(self, state: AgentState) -> AgentState:
        extracted = self.orchestrator.slot_extractor.extract(state["message"])
        hard_keys = {"color", "category", "budget", "avoid"}
        return {
            "goal": state["message"] or "find visually similar products",
            "slots": extracted,
            "hard_constraints": {
                key: value for key, value in extracted.items() if key in hard_keys
            },
            "soft_preferences": {
                key: value for key, value in extracted.items() if key not in hard_keys
            },
            "missing_fields": [],
            "fit_risks": [],
            "confidence": 0.5,
            "status": "understood",
        }

    @staticmethod
    def _merge_slots(
        existing: dict[str, Any], updates: dict[str, Any]
    ) -> dict[str, Any]:
        merged = dict(existing)
        for key, value in updates.items():
            if value in (None, "", []):
                continue
            if key == "avoid":
                merged[key] = list(dict.fromkeys([*merged.get(key, []), *value]))
            else:
                merged[key] = value
        return merged

    def load_context(self, state: AgentState) -> AgentState:
        session = self.orchestrator.memory.get(state["session_id"])
        slots = self._merge_slots(session.slots, state.get("slots", {}))
        return {
            "slots": slots,
            "context_refs": {
                "history_count": len(session.history.messages),
                "last_result_ids": list(session.last_results),
            },
            "status": "context_loaded",
        }

    def plan_tools(self, state: AgentState) -> AgentState:
        message = state["message"]
        image_path = state.get("image_path")
        intent = self.orchestrator.planner.choose(
            message,
            bool(image_path),
            lambda: self.orchestrator.classify_intent(message, bool(image_path)),
        )
        slots = state.get("slots", {})
        filters = self.orchestrator.slot_extractor.to_filters(slots)
        query = self.orchestrator.slot_extractor.enrich_query(message, slots)
        tool: str | None = None
        arguments: dict[str, Any] = {}
        missing_fields: list[str] = []

        if intent == Intent.HYBRID_SEARCH:
            tool = "hybrid_search"
            arguments = {
                "query": query,
                "image_path": str(image_path),
                "filters": filters,
                "top_k": 5,
            }
        elif intent == Intent.IMAGE_SEARCH:
            tool = "search_products_by_image"
            arguments = {
                "image_path": str(image_path),
                "filters": filters,
                "top_k": 5,
            }
        elif intent == Intent.TEXT_RECOMMENDATION:
            tool = "search_products_by_text"
            arguments = {"query": query, "filters": filters, "top_k": 5}
        elif intent == Intent.COMPARE:
            product_ids = self.orchestrator._resolve_product_ids(
                state["session_id"],
                message,
            )
            if len(product_ids) >= 2:
                tool = "compare_products"
                arguments = {"product_ids": product_ids[:3]}
            else:
                missing_fields = ["comparison_product_ids"]

        return {
            "intent": intent.value,
            "planned_tool": tool,
            "planned_arguments": arguments,
            "missing_fields": missing_fields,
            "status": "planned",
        }

    def retrieve_candidates(self, state: AgentState) -> AgentState:
        tool = state.get("planned_tool")
        if not tool:
            return {
                "candidate_products": [],
                "comparison": [],
                "tool_results": {},
                "tool_trace": [],
                "status": "retrieved",
            }

        traces: list[ToolTrace] = []
        result = self.orchestrator._invoke(
            traces,
            tool,
            state.get("planned_arguments", {}),
        )
        if tool == "compare_products":
            comparison = result["products"]
            products: list[dict[str, Any]] = []
            count = len(comparison)
        else:
            comparison = []
            products = result["results"]
            count = len(products)
        return {
            "candidate_products": products,
            "comparison": comparison,
            "tool_results": {
                tool: {
                    "count": count,
                    "total_candidates": result.get("total_candidates", count),
                }
            },
            "tool_trace": [trace.model_dump(mode="json") for trace in traces],
            "status": "retrieved",
        }

    def verify_constraints(self, state: AgentState) -> AgentState:
        catalog = self.orchestrator.toolset.catalog
        candidates = [
            product
            for product in state.get("candidate_products", [])
            if str(product.get("article_id", "")) in catalog
        ]
        comparison = [
            product
            for product in state.get("comparison", [])
            if str(product.get("article_id", "")) in catalog
        ]
        fit_risks = list(state.get("fit_risks", []))
        if (
            state.get("intent")
            in {
                Intent.TEXT_RECOMMENDATION.value,
                Intent.IMAGE_SEARCH.value,
                Intent.HYBRID_SEARCH.value,
            }
            and not candidates
        ):
            fit_risks.append("no_catalog_candidate")
        return {
            "candidate_products": candidates,
            "comparison": comparison,
            "fit_risks": fit_risks,
            "confidence": 0.9 if candidates or comparison else 0.4,
            "status": "verified",
        }

    def build_evidence(self, state: AgentState) -> AgentState:
        products = state.get("candidate_products") or state.get("comparison", [])
        evidence = [
            {
                "source": "catalog",
                "article_id": str(product["article_id"]),
                "fields": {
                    key: product.get(key)
                    for key in (
                        "prod_name",
                        "product_type_name",
                        "colour_group_name",
                        "price",
                        "score",
                    )
                    if product.get(key) is not None
                },
            }
            for product in products
        ]
        context_refs = dict(state.get("context_refs", {}))
        context_refs["candidate_article_ids"] = [
            item["article_id"] for item in evidence
        ]
        return {
            "evidence": evidence,
            "context_refs": context_refs,
            "status": "evidence_ready",
        }

    def generate_answer(self, state: AgentState) -> AgentState:
        intent = Intent(state["intent"])
        language = state.get("language", "zh")
        candidates = [dict(product) for product in state.get("candidate_products", [])]
        pending_action = None

        if intent in {
            Intent.TEXT_RECOMMENDATION,
            Intent.IMAGE_SEARCH,
            Intent.HYBRID_SEARCH,
        }:
            answer = self.orchestrator._recommendation_answer(
                state["session_id"],
                state["message"],
                candidates,
                state.get("slots", {}),
                language,
            )
        elif intent == Intent.COMPARE:
            answer = (
                "Please specify two or three products, for example: compare item 1 and item 3."
                if language == "en"
                else "请说明要对比的两到三件商品，例如“对比第1件和第3件”。"
            )
            if state.get("comparison"):
                answer = (
                    "The comparison uses verified catalog fields."
                    if language == "en"
                    else "已按真实商品字段整理对比结果。"
                )
        else:
            answer = (
                "The shopping bag is managed by the Java account service. "
                "Please use the product card or shopping bag."
                if language == "en"
                else "购物车由 Java 账户服务统一管理，请使用商品卡片或购物袋操作。"
            )
            pending_action = {"type": "java_cart_handoff"}

        return {
            "candidate_products": candidates,
            "answer": answer,
            "pending_action": pending_action,
            "status": "answer_ready",
        }

    @staticmethod
    def wait_for_confirmation(state: AgentState) -> AgentState:
        return {
            "pending_action": state.get("pending_action"),
            "status": "handoff_ready",
        }

    def complete(self, state: AgentState) -> AgentState:
        products = state.get("candidate_products", [])
        last_results = [
            str(product["article_id"])
            for product in products
            if product.get("article_id")
        ]
        self.orchestrator.memory.commit_turn(
            task_id=state["task_id"],
            session_id=state["session_id"],
            user_content=state["message"] or "[上传图片]",
            assistant_content=state["answer"],
            slots=state.get("slots", {}),
            last_results=last_results,
        )
        response = AgentResponse(
            task_id=state["task_id"],
            request_id=state["request_id"],
            session_id=state["session_id"],
            intent=Intent(state["intent"]),
            answer=state["answer"],
            products=products,
            comparison=state.get("comparison", []),
            slots=state.get("slots", {}),
            tool_trace=[
                ToolTrace.model_validate(trace) for trace in state.get("tool_trace", [])
            ],
            node_trace=[
                NodeTrace.model_validate(trace) for trace in state.get("node_trace", [])
            ],
        ).to_dict()
        return {
            "response": response,
            "status": "completed",
            "pending_action": None,
        }
