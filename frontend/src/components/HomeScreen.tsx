import { ArrowRight, Camera, ShoppingBag } from "lucide-react";
import { productImage } from "../api/client";
import type { Product } from "../types";
import { formatCatalogPrice } from "../utils/formatters";
import { productDisplayCategory, productDisplayName } from "../utils/productDisplay";

type Props = {
  products: Product[];
  onAgent: () => void;
  onDiscover: () => void;
  onDetail: (id: string) => void;
};

export function HomeScreen({ products, onAgent, onDiscover, onDetail }: Props) {
  return (
    <main className="home-demo app-screen">
      <section className="demo-hero">
        <span>FitMe 精选</span>
        <h1>发现适合你的时尚单品</h1>
        <p>从丰富的服装目录中，为你挑选值得浏览的时尚单品。</p>
        <div>
          <button className="demo-primary-button" onClick={onDiscover}><ShoppingBag size={18} />浏览商品<ArrowRight size={17} /></button>
          <button className="demo-secondary-button" data-testid="open-stylist" onClick={onAgent}><Camera size={18} />图片找同款</button>
        </div>
      </section>

      <section className="demo-feature-row" aria-label="商城服务">
        <div><strong>精选商品</strong><span>发现更多日常穿搭灵感</span></div>
        <div><strong>快速筛选</strong><span>按分类、颜色和价格浏览</span></div>
        <div><strong>购物流程</strong><span>支持购物车与订单演示</span></div>
      </section>

      <section className="home-product-section">
        <header>
          <div><p>热门推荐</p><h2>大家都在看</h2></div>
          <button onClick={onDiscover}>查看全部<ArrowRight size={15} /></button>
        </header>
        <div className="home-product-grid">
          {products.slice(0, 6).map((product) => (
            <button className="home-product" key={product.article_id} onClick={() => onDetail(product.article_id)}>
              <img src={productImage(product)} alt={productDisplayName(product)} />
              <span>{productDisplayCategory(product)}</span>
              <strong>{productDisplayName(product)}</strong>
              {product.price_info && <em>{formatCatalogPrice(product.price_info.amount, product.price_info.currency)}</em>}
            </button>
          ))}
        </div>
      </section>
    </main>
  );
}
