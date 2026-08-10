import { useState } from "react";
import { Check, GitCompareArrows, Heart, ShoppingCart } from "lucide-react";
import { motion } from "motion/react";
import { productImage } from "../api/client";
import { useTranslation } from "../i18n";
import type { Product } from "../types";
import { formatCatalogPrice } from "../utils/formatters";
import { productDisplayCategory, productDisplayName } from "../utils/productDisplay";

type Props = {
  product: Product;
  index: number;
  selected: boolean;
  onCompare: (id: string) => void;
  onAdd: (id: string, origin: DOMRect) => Promise<boolean>;
  onDetail: (id: string) => void;
};

export function ProductCard({ product, index, selected, onCompare, onAdd, onDetail }: Props) {
  const { t } = useTranslation();
  const [favorite, setFavorite] = useState(false);
  const [added, setAdded] = useState(false);
  const name = productDisplayName(product);

  const add = async (event: React.MouseEvent<HTMLButtonElement>) => {
    if (!await onAdd(product.article_id, event.currentTarget.getBoundingClientRect())) return;
    setAdded(true);
    window.setTimeout(() => setAdded(false), 1300);
  };

  return (
    <motion.article
      data-testid="product-card"
      className="product-card demo-product-card"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index, 8) * 0.035 }}
    >
      <div className="product-media">
        <button className="product-image-button" onClick={() => onDetail(product.article_id)} aria-label={t("viewDetails", { name })}>
          <img src={productImage(product)} alt={name} loading="lazy" />
        </button>
        <button className={favorite ? "favorite-button is-active" : "favorite-button"} onClick={() => setFavorite((value) => !value)} aria-label={favorite ? t("unfavorite") : t("favorite")}>
          <Heart size={17} fill={favorite ? "currentColor" : "none"} />
        </button>
      </div>
      <div className="product-information">
        <p className="product-taxonomy">{productDisplayCategory(product)}</p>
        <button className="product-name" onClick={() => onDetail(product.article_id)}>{name}</button>
        {product.price_info && <p className="product-price">{formatCatalogPrice(product.price_info.amount, product.price_info.currency)}</p>}
        <div className="demo-card-actions">
          <button className={selected ? "compare-button is-active" : "compare-button"} onClick={() => onCompare(product.article_id)} aria-label={t("addCompare")} aria-pressed={selected}>
            {selected ? <Check size={15} /> : <GitCompareArrows size={15} />}<span>{selected ? "已选择" : "对比"}</span>
          </button>
          <button className={added ? "add-button is-success" : "add-button"} onClick={add} aria-label={t("addCart")}>
            {added ? <Check size={16} /> : <ShoppingCart size={16} />}<span>{added ? "已加入" : "加入购物车"}</span>
          </button>
        </div>
      </div>
    </motion.article>
  );
}
