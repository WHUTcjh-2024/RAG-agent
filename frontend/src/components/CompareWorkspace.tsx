import { motion } from "motion/react";
import { ArrowLeft, Check, Minus } from "lucide-react";
import { productImage } from "../api/client";
import { useTranslation } from "../i18n";
import { motionTokens } from "../motion/tokens";
import type { Product } from "../types";

export function CompareWorkspace({ products, onClose, onRemove, onDetail }: { products: Product[]; onClose: () => void; onRemove: (id: string) => void; onDetail: (id: string) => void }) {
  const { t } = useTranslation();
  const rows: [string, (product: Product) => string][] = [
    [t("category"), (product) => product.product_type_name || t("unavailable")],
    [t("color"), (product) => product.colour_group_name || t("unavailable")],
    [t("group"), (product) => product.garment_group_name || t("unavailable")],
    [t("inventory"), (product) => product.inventory_status === "unknown" || !product.inventory_status ? t("unavailable") : product.inventory_status],
    [t("sizes"), (product) => product.available_sizes?.length ? product.available_sizes.join(" / ") : t("unavailable")],
    [t("datasetPrice"), (product) => product.price_info ? `${product.price_info.amount.toFixed(4)} ${product.price_info.currency}` : t("unavailable")]
  ];

  return (
    <div className="compare-page">
      <header className="workspace-heading">
        <button onClick={onClose} aria-label={t("close")}><ArrowLeft size={17} />{t("discover")}</button>
        <div><p className="section-kicker">COMPARE WORKSPACE</p><h1>{t("compare")}</h1><p>{t("compareSubtitle")}</p></div>
      </header>
      {products.length < 2 ? <div className="empty-workspace"><Minus size={30} /><p>{t("selected", { count: products.length })}</p><button onClick={onClose}>{t("discover")}</button></div> : (
        <motion.div className="compare-grid" layout>
          <div className="compare-label-column"><div className="compare-media-spacer" />{rows.map(([label]) => <div key={label}>{label}</div>)}</div>
          {products.map((product, index) => (
            <motion.article key={product.article_id} layoutId={`product-card-${product.article_id}`} initial={{ opacity: 0, y: 40 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.08, ...motionTokens.spring.layout }}>
              <button className="compare-product-media" onClick={() => onDetail(product.article_id)}>
                <motion.img layoutId={`product-media-${product.article_id}`} src={productImage(product)} alt={product.prod_name} />
                <span>{product.prod_name}</span>
              </button>
              {rows.map(([label, read]) => {
                const value = read(product);
                const different = new Set(products.map(read)).size > 1;
                return <div key={label} className={different ? "compare-value is-different" : "compare-value"}>{different && <Check size={12} />}<span>{value}</span>{different && <small>{t("different")}</small>}</div>;
              })}
              <button className="compare-remove" onClick={() => onRemove(product.article_id)}>{t("remove")}</button>
            </motion.article>
          ))}
        </motion.div>
      )}
    </div>
  );
}
