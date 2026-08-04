import { motion, useScroll, useTransform } from "motion/react";
import { ArrowLeft, Box, Database, MessageCircle, Plus, ShieldCheck } from "lucide-react";
import { productImage } from "../api/client";
import { useTranslation } from "../i18n";
import { useMotionSystem } from "../motion/MotionSystem";
import { motionTokens } from "../motion/tokens";
import type { Product } from "../types";

type Props = {
  product: Product;
  onClose: () => void;
  onAdd: (id: string, origin: DOMRect) => Promise<boolean>;
  onAskAgent: (query: string) => void;
};

export function ProductDetail({ product, onClose, onAdd, onAskAgent }: Props) {
  const { t } = useTranslation();
  const { capability } = useMotionSystem();
  const { scrollYProgress } = useScroll();
  const visualScale = useTransform(scrollYProgress, [0, 0.7], [1, capability === "full" ? 0.88 : 1]);
  const visualRotate = useTransform(scrollYProgress, [0, 0.7], [0, capability === "full" ? -1.8 : 0]);

  const add = (event: React.MouseEvent<HTMLButtonElement>) => onAdd(product.article_id, event.currentTarget.getBoundingClientRect());
  const facts = [
    ["SKU", product.sku || product.article_id],
    [t("category"), product.product_type_name || product.product_group_name || t("unavailable")],
    [t("color"), product.colour_group_name || t("unavailable")],
    [t("group"), product.garment_group_name || t("unavailable")],
    [t("inventory"), product.inventory_status === "unknown" || !product.inventory_status ? t("unavailable") : product.inventory_status],
    [t("sizes"), product.available_sizes?.length ? product.available_sizes.join(" / ") : t("unavailable")]
  ];

  return (
    <div className="detail-page" style={{ "--detail-ambient": product.colour_group_name?.toLowerCase().includes("red") ? "#a77970" : "#8d9188" } as React.CSSProperties}>
      <div className="detail-ambient" aria-hidden="true" />
      <button className="page-back" onClick={onClose} aria-label={t("close")}><ArrowLeft size={17} />{t("discover")}</button>
      <div className="detail-layout">
        <div className="detail-visual-column">
          <motion.figure className="detail-visual" style={{ scale: visualScale, rotate: visualRotate }}>
            <motion.img layoutId={`product-media-${product.article_id}`} src={productImage(product)} alt={product.prod_name} />
            <span className="detail-id">{product.article_id}</span>
            <div className="material-lens" aria-hidden="true" />
          </motion.figure>
        </div>
        <div className="detail-narrative">
          <section className="detail-intro">
            <p className="section-kicker">{t("productStory")}</p>
            <span className="detail-page-label">{t("detail")}</span>
            <h1>{product.prod_name}</h1>
            <p className="detail-taxonomy">{product.product_type_name} · {product.colour_group_name} · {product.garment_group_name}</p>
            {product.price_info && <p className="detail-price">{product.price_info.amount.toFixed(6)} <small>{product.price_info.currency}</small></p>}
            <div className="detail-primary-actions">
              <motion.button whileTap={{ scale: motionTokens.scale.press }} onClick={add}><Plus size={16} />{t("addCart")}</motion.button>
              <button onClick={() => onAskAgent(`请结合真实信息分析 ${product.prod_name} 是否适合我`)}><MessageCircle size={16} />{t("consult")}</button>
            </div>
          </section>

          <section className="detail-chapter">
            <span><Database size={16} />01</span><h2>{t("productOverview")}</h2>
            <dl>{facts.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
          </section>
          <section className="detail-chapter detail-description-chapter">
            <span><Box size={16} />02</span><h2>{t("productMaterial")}</h2>
            <p>{product.detail_desc || t("noDescription")}</p>
            <div className="source-note"><ShieldCheck size={18} /><div><strong>{t("sourceTruth")}</strong><p>{t("sourceTruthCopy")}</p></div></div>
          </section>
          <section className="detail-chapter detail-decision-chapter">
            <span>03</span><h2>{t("productDecision")}</h2>
            <p>{t("reviewsUnavailable")}</p>
            <button onClick={() => onAskAgent(`对比 ${product.prod_name} 的适配风险、价格和替代商品`)}>{t("consult")}</button>
          </section>
        </div>
      </div>
    </div>
  );
}
