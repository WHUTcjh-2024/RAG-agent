from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
from langchain_core.tools import BaseTool, StructuredTool
from PIL import Image

from app.core.agent.memory import AgentMemoryStore
from app.core.catalog_fields import enrich_commerce_fields


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, name: str, description: str, function: Callable[..., Any]) -> None:
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        self._tools[name] = StructuredTool.from_function(
            func=function,
            name=name,
            description=description,
        )

    def invoke(self, name: str, arguments: dict[str, Any]) -> Any:
        try:
            tool = self._tools[name]
        except KeyError as error:
            raise KeyError(f"Unknown tool: {name}") from error
        return tool.invoke(arguments)

    @property
    def tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    @property
    def names(self) -> list[str]:
        return list(self._tools)


class CommerceToolset:
    def __init__(
        self,
        text_retriever,
        image_retriever,
        hybrid_retriever,
        memory: AgentMemoryStore,
    ) -> None:
        self.text_retriever = text_retriever
        self.image_retriever = image_retriever
        self.hybrid_retriever = hybrid_retriever
        self.memory = memory
        products = list(text_retriever.products) + list(image_retriever.products)
        self.catalog = {
            str(product["article_id"]): enrich_commerce_fields(product)
            for product in products
            if product.get("article_id")
        }

    def build_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(
            "search_products_by_text",
            "Search real catalog products using text and structured filters.",
            self.search_products_by_text,
        )
        registry.register(
            "search_products_by_image",
            "Search visually similar real products from an uploaded local image.",
            self.search_products_by_image,
        )
        registry.register(
            "hybrid_search",
            "Fuse text, uploaded image, structured filters, and popularity.",
            self.hybrid_search,
        )
        registry.register(
            "get_product_detail",
            "Return one real catalog product by article_id.",
            self.get_product_detail,
        )
        registry.register(
            "compare_products",
            "Compare two or three real products using catalog fields only.",
            self.compare_products,
        )
        registry.register(
            "update_user_preference",
            "Update structured preference slots for the current session.",
            self.update_user_preference,
        )
        return registry

    def search_products_by_text(
        self, query: str, filters: dict[str, str], top_k: int = 5
    ) -> dict[str, Any]:
        results, total = self.text_retriever.search(query, top_k, filters)
        return {"results": results, "total_candidates": total}

    def search_products_by_image(
        self, image_path: str, filters: dict[str, str], top_k: int = 5
    ) -> dict[str, Any]:
        with Image.open(image_path) as source:
            source.load()
            results, total = self.image_retriever.search(
                source.convert("RGB"), top_k, filters
            )
        return {"results": results, "total_candidates": total}

    def hybrid_search(
        self,
        query: str,
        image_path: str,
        filters: dict[str, str],
        top_k: int = 5,
    ) -> dict[str, Any]:
        with Image.open(image_path) as source:
            source.load()
            results, total = self.hybrid_retriever.search(
                query, source.convert("RGB"), top_k, filters
            )
        return {"results": results, "total_candidates": total}

    def get_product_detail(self, product_id: str) -> dict[str, Any]:
        product = self.catalog.get(product_id)
        if product is None:
            raise ValueError(f"Unknown product_id: {product_id}")
        return dict(product)

    def compare_products(self, product_ids: list[str]) -> dict[str, Any]:
        unique_ids = list(dict.fromkeys(product_ids))
        if not 2 <= len(unique_ids) <= 3:
            raise ValueError("compare_products requires two or three product IDs.")
        fields = (
            "article_id",
            "prod_name",
            "product_type_name",
            "product_group_name",
            "colour_group_name",
            "garment_group_name",
            "detail_desc",
            "image_path",
            "sku",
            "price",
            "price_info",
            "available_sizes",
            "inventory_status",
        )
        products = []
        for product_id in unique_ids:
            product = self.get_product_detail(product_id)
            products.append({field: product.get(field, "") for field in fields})
        return {"products": products}

    def update_user_preference(
        self, session_id: str, slots: dict[str, Any]
    ) -> dict[str, Any]:
        return {"slots": self.memory.update_slots(session_id, slots)}
