from __future__ import annotations


# Catalog fields are English while the primary UX is Chinese. These terms are
# deterministic aliases, not generated product facts, and can be audited/versioned.
_ALIASES = {
    "白色": "white",
    "黑色": "black",
    "蓝色": "blue",
    "红色": "red",
    "绿色": "green",
    "灰色": "grey",
    "米色": "beige",
    "粉色": "pink",
    "黄色": "yellow",
    "棕色": "brown",
    "银色": "silver",
    "橙色": "orange",
    "浅黄色": "light yellow",
    "衬衫": "shirt",
    "连衣裙": "dress",
    "半身裙": "skirt",
    "短裙": "skirt",
    "夹克": "jacket",
    "外套": "jacket",
    "领带": "tie",
    "雨伞": "umbrella",
    "平底鞋": "ballerina flat",
    "芭蕾鞋": "ballerina flat",
    "背心": "top",
    "帽": "beanie hat",
    "针织帽": "beanie hat",
    "眼罩": "sleep mask",
    "套装": "garment set",
    "仿皮": "imitation leather",
    "机车": "biker",
    "翻领": "turn-down collar",
    "棉质": "cotton",
    "有机棉": "organic cotton",
    "高腰": "high-waisted",
    "百褶": "pleated",
    "可折叠": "telescopic",
    "通勤": "office",
}


def expand_catalog_query(query: str) -> str:
    """Append catalog-language aliases for deterministic Chinese retrieval recall."""
    additions = [
        alias
        for term, alias in _ALIASES.items()
        if term in query and alias.casefold() not in query.casefold()
    ]
    return " ".join([query.strip(), *dict.fromkeys(additions)]).strip()
