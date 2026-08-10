import { ArrowLeft, ShoppingCart } from "lucide-react";
import { productImage } from "../api/client";
import { useTranslation } from "../i18n";
import type { Product } from "../types";
import { formatCatalogPrice } from "../utils/formatters";
import { productDisplayCategory, productDisplayDescription, productDisplayName } from "../utils/productDisplay";

type Props = {
  product: Product;
  onClose: () => void;
  onAdd: (id: string, origin: DOMRect) => Promise<boolean>;
};

export function ProductDetail({ product, onClose, onAdd }: Props) {
  const { t } = useTranslation();
  const name = productDisplayName(product);
  const facts = [
    ["商品编号", product.sku || product.article_id],
    [t("category"), productDisplayCategory(product)],
    [t("color"), product.colour_group_name || t("unavailable")],
    [t("sizes"), product.available_sizes?.length ? product.available_sizes.join(" / ") : t("unavailable")]
  ];

  return (
    <main className="detail-page demo-detail-page">
      <button className="page-back" onClick={onClose} aria-label={t("close")}><ArrowLeft size={18} />返回商品列表</button>
      <div className="detail-layout">
        <figure className="detail-visual">
          <img src={productImage(product)} alt={name} />
        </figure>
        <div className="detail-narrative">
          <section className="detail-intro">
            <p className="section-kicker">{t("detail")}</p>
            <h1>{name}</h1>
            <p className="detail-taxonomy">{productDisplayCategory(product)} {product.colour_group_name ? `· ${product.colour_group_name}` : ""}</p>
            {product.price_info && <p className="detail-price">{formatCatalogPrice(product.price_info.amount, product.price_info.currency)}</p>}
            <button className="detail-add-button" onClick={(event) => onAdd(product.article_id, event.currentTarget.getBoundingClientRect())}><ShoppingCart size={18} />加入购物车</button>
          </section>

          <section className="detail-chapter">
            <h2>{t("productOverview")}</h2>
            <dl>{facts.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
          </section>
          <section className="detail-chapter detail-description-chapter">
            <h2>{t("productMaterial")}</h2>
            <p>{productDisplayDescription(product.detail_desc)}</p>
          </section>
        </div>
      </div>
    </main>
  );
}
