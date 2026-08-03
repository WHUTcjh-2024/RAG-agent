import { motion } from "motion/react";
import { ArrowRight, BriefcaseBusiness, Plus, Search } from "lucide-react";
import { productImage } from "../api/client";
import { useTranslation } from "../i18n";
import type { Product, User, WardrobeSnapshot } from "../types";

export function WardrobeScreen({ user, wardrobe, inspiration, onLogin, onDetail }: { user: User | null; wardrobe: WardrobeSnapshot | null; inspiration: Product[]; onLogin: () => void; onDetail: (id: string) => void }) {
  const { language } = useTranslation();
  const zh = language === "zh";
  const [featured, ...rest] = inspiration;
  return <div className="wardrobe-screen app-screen">
    {!user && <section className="wardrobe-login-card app-card"><span><BriefcaseBusiness size={18} /></span><div><h2>{zh ? "登录后建立专属衣橱" : "Sign in to build your wardrobe"}</h2><p>{zh ? "同步已有单品，让 Agent 避免重复购买。" : "Sync pieces so the Agent avoids duplicate purchases."}</p></div><button onClick={onLogin}>{zh ? "登录" : "Sign in"}<ArrowRight size={14} /></button></section>}
    <div className="app-search"><Search size={17} /><input aria-label={zh ? "搜索衣橱" : "Search wardrobe"} placeholder={zh ? "搜索衣橱与灵感" : "Search wardrobe and inspiration"} /><button aria-label={zh ? "添加" : "Add"} disabled={!user}><Plus size={17} /></button></div>
    <div className="app-segmented" role="tablist"><button className="is-active">{zh ? "全部" : "All"}</button><button>{zh ? "上衣" : "Tops"}</button><button>{zh ? "外套" : "Outerwear"}</button><button>{zh ? "裤装" : "Bottoms"}</button><button>{zh ? "配饰" : "Accessories"}</button></div>
    <section className="wardrobe-gallery">
      {featured && <motion.button className="wardrobe-featured" layoutId={`product-media-${featured.article_id}`} onClick={() => onDetail(featured.article_id)}><img src={productImage(featured)} alt={featured.prod_name} /><span><small>{zh ? "本周精选" : "WEEKLY PICK"}</small><strong>{featured.prod_name}</strong></span></motion.button>}
      <div>{rest.slice(0, 11).map((product) => <motion.button layout key={product.article_id} onClick={() => onDetail(product.article_id)}><img src={productImage(product)} alt={product.prod_name} /><span>{product.product_type_name}</span></motion.button>)}</div>
    </section>
    <section className="wardrobe-stats app-card"><header><span>{zh ? "衣橱洞察" : "WARDROBE INSIGHT"}</span><small>v{wardrobe?.version || 0}</small></header><div><p><strong>{wardrobe?.items.length || 0}</strong>{zh ? "真实衣橱单品" : "saved pieces"}</p><p><strong>{inspiration.length}</strong>{zh ? "目录灵感" : "catalog ideas"}</p><p><strong>{new Set(inspiration.map((item) => item.colour_group_name)).size}</strong>{zh ? "颜色" : "colors"}</p></div></section>
  </div>;
}
