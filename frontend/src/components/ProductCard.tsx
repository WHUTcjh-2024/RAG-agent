import { useState } from "react";
import { motion, useMotionValue, useSpring, useTransform } from "motion/react";
import { Check, GitCompareArrows, Heart, Plus } from "lucide-react";
import { productImage } from "../api/client";
import { useTranslation } from "../i18n";
import { useMotionSystem } from "../motion/MotionSystem";
import { motionTokens } from "../motion/tokens";
import type { Product } from "../types";

type Props = {
  product: Product;
  index: number;
  featured?: boolean;
  selected: boolean;
  onCompare: (id: string) => void;
  onAdd: (id: string, origin: DOMRect) => Promise<boolean>;
  onDetail: (id: string) => void;
};

export function ProductCard({ product, index, featured, selected, onCompare, onAdd, onDetail }: Props) {
  const { t } = useTranslation();
  const { capability } = useMotionSystem();
  const [favorite, setFavorite] = useState(false);
  const [added, setAdded] = useState(false);
  const pointerX = useMotionValue(0);
  const pointerY = useMotionValue(0);
  const smoothX = useSpring(pointerX, { stiffness: 180, damping: 26 });
  const smoothY = useSpring(pointerY, { stiffness: 180, damping: 26 });
  const imageX = useTransform(smoothX, [-0.5, 0.5], ["-2.5%", "2.5%"]);
  const imageY = useTransform(smoothY, [-0.5, 0.5], ["-2%", "2%"]);
  const score = typeof product.score === "number" ? Math.round(product.score * 100) : null;

  const move = (event: React.PointerEvent<HTMLDivElement>) => {
    if (capability !== "full") return;
    const rect = event.currentTarget.getBoundingClientRect();
    pointerX.set((event.clientX - rect.left) / rect.width - 0.5);
    pointerY.set((event.clientY - rect.top) / rect.height - 0.5);
  };

  const add = async (event: React.MouseEvent<HTMLButtonElement>) => {
    const success = await onAdd(product.article_id, event.currentTarget.getBoundingClientRect());
    if (!success) return;
    setAdded(true);
    window.setTimeout(() => setAdded(false), 1600);
  };

  return (
    <motion.article
      data-testid="product-card"
      layout
      layoutId={`product-card-${product.article_id}`}
      className={featured ? "product-card product-card-featured" : "product-card"}
      initial={{ opacity: 0, y: index % 2 ? 28 : 44, clipPath: "inset(0 0 12% 0)" }}
      animate={{ opacity: 1, y: 0, clipPath: "inset(0 0 0% 0)" }}
      exit={{ opacity: 0, scale: 0.96, filter: "blur(7px)" }}
      transition={{ layout: motionTokens.spring.layout, delay: Math.min(index, 8) * motionTokens.stagger.tight }}
    >
      <div
        className="product-media"
        onPointerMove={move}
        onPointerLeave={() => { pointerX.set(0); pointerY.set(0); }}
      >
        <motion.button
          className="product-image-button"
          onClick={() => onDetail(product.article_id)}
          aria-label={t("viewDetails", { name: product.prod_name })}
          whileTap={{ scale: motionTokens.scale.press }}
        >
          <motion.img
            layoutId={`product-media-${product.article_id}`}
            src={productImage(product)}
            alt={product.prod_name}
            loading="lazy"
            style={{ x: imageX, y: imageY }}
          />
          <span className="image-focus" aria-hidden="true" />
        </motion.button>
        <span className="product-index">{String(index + 1).padStart(2, "0")}</span>
        <button
          className={favorite ? "favorite-button is-active" : "favorite-button"}
          onClick={() => setFavorite((value) => !value)}
          aria-label={favorite ? t("unfavorite") : t("favorite")}
        >
          <motion.span animate={{ scale: favorite ? [1, 0.78, 1.08, 1] : 1 }}><Heart size={16} fill={favorite ? "currentColor" : "none"} /></motion.span>
        </button>
        <div className="product-card-actions">
          <button
            className={selected ? "card-action is-active" : "card-action"}
            onClick={() => onCompare(product.article_id)}
            aria-label={t("addCompare")}
            aria-pressed={selected}
          >
            {selected ? <Check size={15} /> : <GitCompareArrows size={15} />}
          </button>
          <button className={added ? "card-action add-action is-success" : "card-action add-action"} onClick={add} aria-label={t("addCart")}>
            <motion.span key={added ? "done" : "add"} initial={{ scale: 0.5, rotate: -20 }} animate={{ scale: 1, rotate: 0 }}>
              {added ? <Check size={16} /> : <Plus size={16} />}
            </motion.span>
          </button>
        </div>
        {score !== null && (
          <div className="match-orbit" aria-label={`${t("match")} ${score}%`}>
            <svg viewBox="0 0 40 40"><circle cx="20" cy="20" r="17" /><motion.circle cx="20" cy="20" r="17" initial={{ pathLength: 0 }} animate={{ pathLength: score / 100 }} transition={{ duration: 0.8, ease: motionTokens.easing.enter }} /></svg>
            <span>{score}</span>
          </div>
        )}
      </div>
      <div className="product-information">
        <div>
          <p className="product-taxonomy">{product.product_type_name || product.product_group_name} · {product.colour_group_name}</p>
          <button className="product-name" onClick={() => onDetail(product.article_id)}>{product.prod_name}</button>
        </div>
        {product.price_info && <p className="product-price">{product.price_info.amount.toFixed(4)}<small>{product.price_info.currency}</small></p>}
        {product.reason && <motion.div className="product-reason" initial={{ opacity: 0 }} animate={{ opacity: 1 }}><span>{t("recommendationReason")}</span><p>{product.reason}</p></motion.div>}
      </div>
    </motion.article>
  );
}
