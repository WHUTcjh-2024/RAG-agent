import { motion } from "motion/react";
import { ArrowRight, Bot, Check, ChevronRight, CloudSun, Database, ScanSearch, Sparkles } from "lucide-react";
import { productImage } from "../api/client";
import { useTranslation } from "../i18n";
import type { AgentNodeEvent, AgentPhase, Product, WardrobeSnapshot } from "../types";

type Props = {
  products: Product[];
  agentState: "idle" | AgentPhase;
  events: AgentNodeEvent[];
  wardrobe: WardrobeSnapshot | null;
  onAgent: () => void;
  onWardrobe: () => void;
  onDiscover: () => void;
  onDetail: (id: string) => void;
};

const capabilities = [
  { node: "understand_request", icon: ScanSearch, zh: "理解你的场景与约束", en: "Understand context and constraints" },
  { node: "load_context", icon: CloudSun, zh: "结合衣橱与使用场景", en: "Use wardrobe and context" },
  { node: "retrieve_candidates", icon: Database, zh: "检索真实商品知识库", en: "Retrieve grounded products" },
  { node: "generate_answer", icon: Sparkles, zh: "生成可验证穿搭建议", en: "Build a grounded recommendation" }
];

export function HomeScreen({ products, agentState, events, wardrobe, onAgent, onWardrobe, onDiscover, onDetail }: Props) {
  const { language } = useTranslation();
  const zh = language === "zh";
  const completed = new Set(events.filter((event) => event.state === "completed").map((event) => event.node));
  const visibleProducts = products.slice(0, 4);
  return (
    <div className="home-screen app-screen">
      <section className="agent-entry-card">
        <div><span><Bot size={15} />AI AGENT</span><h2>{zh ? "今天想解决什么穿搭问题？" : "What are you dressing for today?"}</h2><p>{zh ? "告诉我场景、天气、预算或上传参考图。" : "Share a setting, weather, budget, or reference image."}</p></div>
        <motion.button whileTap={{ scale: .96 }} onClick={onAgent}>{zh ? "交给 FitMe Agent" : "Ask FitMe Agent"}<ArrowRight size={16} /></motion.button>
        <i className="agent-orb orb-one" /><i className="agent-orb orb-two" />
      </section>

      <section className="app-card task-card">
        <header><div><span>{zh ? "智能任务" : "SMART TASK"}</span><h3>{agentState === "idle" ? (zh ? "Agent 已准备好" : "Agent is ready") : (zh ? "Agent 正在处理你的需求" : "Agent is working")}</h3></div><button onClick={onAgent}><ChevronRight size={18} /></button></header>
        <div className="task-steps">
          {capabilities.map(({ node, icon: Icon, zh: zhLabel, en }, index) => {
            const done = completed.has(node);
            const active = events.at(-1)?.node === node && agentState !== "success";
            return <div key={node} className={`${done ? "is-done" : ""}${active ? " is-active" : ""}`}><span>{done ? <Check size={13} /> : <Icon size={14} />}</span><p>{zh ? zhLabel : en}</p><small>{done ? (zh ? "已完成" : "Done") : active ? (zh ? "处理中" : "Working") : `0${index + 1}`}</small></div>;
          })}
        </div>
        {events.length > 0 && <p className="task-integrity">{events.length} {zh ? "条真实工作流事件" : "real workflow events"}</p>}
      </section>

      <section className="home-section">
        <header><div><span>{zh ? "衣橱速览" : "WARDROBE"}</span><h3>{zh ? "你的日常单品" : "Your daily pieces"}</h3></div><button onClick={onWardrobe}>{zh ? "查看全部" : "View all"}<ChevronRight size={15} /></button></header>
        <div className="wardrobe-preview-grid">
          {visibleProducts.map((product) => <motion.button layoutId={`product-media-${product.article_id}`} key={product.article_id} onClick={() => onDetail(product.article_id)}><img src={productImage(product)} alt={product.prod_name} /><span>{product.product_type_name}</span></motion.button>)}
        </div>
        <div className="wardrobe-summary app-card"><div><strong>{wardrobe?.items.length || 0}</strong><span>{zh ? "衣橱单品" : "Pieces"}</span></div><div><strong>{visibleProducts.length}</strong><span>{zh ? "今日灵感" : "Ideas"}</span></div><div><strong>{completed.size}</strong><span>{zh ? "任务节点" : "Task nodes"}</span></div></div>
      </section>

      <section className="home-section recommendation-strip">
        <header><div><span>{zh ? "为你推荐" : "FOR YOU"}</span><h3>{zh ? "从真实目录发现" : "Grounded catalog picks"}</h3></div><button onClick={onDiscover}>{zh ? "更多" : "More"}<ChevronRight size={15} /></button></header>
        <div>{products.slice(0, 3).map((product) => <button key={product.article_id} onClick={() => onDetail(product.article_id)}><img src={productImage(product)} alt="" /><span><strong>{product.prod_name}</strong><small>{product.colour_group_name} · {product.product_type_name}</small></span></button>)}</div>
      </section>
    </div>
  );
}
