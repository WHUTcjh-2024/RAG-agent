import { X } from "lucide-react";
import type { DecisionCard, Message, PendingCartAction, Product, Slots, ToolTrace, WardrobePlan, WardrobeSnapshot } from "../types";
import { ChatPanel } from "./ChatPanel";
import { InsightPanel } from "./InsightPanel";
import { useTranslation } from "../i18n";

type Props = { open: boolean; onClose: () => void; messages: Message[]; streaming: boolean; slots: Slots; traces: ToolTrace[]; decision: DecisionCard | null; pendingAction: PendingCartAction | null; wardrobe: WardrobeSnapshot | null; wardrobePlan: WardrobePlan | null; products: Product[]; onPlanEdit: (operation: Record<string, unknown>) => void; onPlanAccept: () => void; onConfirm: () => void; onSubmit: (message: string, image: File | null, preview: string | null) => void };

const productCategory = (product: Product) => {
  const value = `${product.product_type_name || ""} ${product.product_group_name || ""}`.toLowerCase();
  if (/shirt|top|sweater|t-shirt/.test(value)) return "TOP";
  if (/trouser|pants|skirt|shorts/.test(value)) return "BOTTOM";
  return "OTHER";
};

export function StylistDrawer({ open, onClose, messages, streaming, slots, traces, decision, pendingAction, wardrobe, wardrobePlan, products, onPlanEdit, onPlanAccept, onConfirm, onSubmit }: Props) {
  const { t } = useTranslation();
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50">
      <button onClick={onClose} className="absolute inset-0 bg-ink/30 backdrop-blur-[2px]" aria-label={t("close")} />
      <aside className="absolute right-0 top-0 h-full w-full max-w-[500px] overflow-y-auto bg-canvas shadow-2xl animate-slide-in">
        <div className="sticky top-0 z-10 flex h-16 items-center justify-between border-b border-ink/10 bg-canvas/95 px-5 backdrop-blur-md">
          <div><span className="eyebrow">{t("appointment")}</span><h2 className="mt-1 font-display text-xl">{t("stylist")}</h2></div>
          <button onClick={onClose} className="icon-button" aria-label={t("close")}><X size={18} /></button>
        </div>
        <div className="p-4"><ChatPanel messages={messages} streaming={streaming} onSubmit={onSubmit} />
          {decision && <section className="mt-4 border border-ink/10 bg-paper p-4 text-sm">
            <p className="eyebrow">购买决策</p><p className="mt-1 font-display text-lg">{decision.verdict.replaceAll("_", " ")}</p>
            <p className="mt-2 text-xs text-muted">置信度 {Math.round(decision.confidence * 100)}%{decision.recommended_size ? ` · 建议尺码 ${decision.recommended_size}` : ""}</p>
            {decision.reasons.map((reason) => <p key={reason} className="mt-2 text-sm">{reason}</p>)}
            {decision.fit_risks.map((risk) => <p key={`${risk.area}-${risk.message}`} className="mt-2 text-xs text-[#9b4b42]">{risk.message}</p>)}
            {decision.missing_fields.length > 0 && <p className="mt-2 text-xs text-muted">待补充：{decision.missing_fields.join("、")}</p>}
          </section>}
          {pendingAction && <section className="mt-4 border border-ink/10 bg-paper p-4 text-sm">
            <p className="eyebrow">需要确认</p>
            <p className="mt-2">{pendingAction.summary}</p>
            <p className="mt-1 text-xs text-muted">当前价格：{pendingAction.product.price ?? "-"} · 有效至 {new Date(pendingAction.expires_at).toLocaleTimeString()}</p>
            <button className="mt-3 rounded bg-ink px-3 py-2 text-xs text-white" onClick={onConfirm}>确认加入购物车</button>
          </section>}
          {wardrobePlan && <section className="mt-4 border border-ink/10 bg-paper p-4 text-sm">
            <div className="flex items-center justify-between"><p className="eyebrow">数字衣橱方案</p><span className="text-[11px] text-muted">衣橱 v{wardrobePlan.wardrobe_version}</span></div>
            <p className="mt-2 text-xs text-muted">复用 {wardrobe?.items.length || 0} 件已有单品 · 新购合计 {wardrobePlan.new_item_total}</p>
            {wardrobePlan.outfits.map((outfit) => <div key={outfit.outfit_id} className="mt-3 border-t border-ink/10 pt-3">
              <p className="font-medium">{outfit.name}{outfit.complete ? "" : " · 需要补充"}</p>
              {outfit.items.map((item) => {
                const replacement = products.find((product) => product.article_id !== item.item_id && productCategory(product) === item.category);
                return <div key={item.item_id} className="mt-2 flex items-center justify-between gap-2 text-xs">
                  <span>{item.name} <span className="text-muted">{item.source === "WARDROBE" ? "衣橱" : "候选"}{item.locked ? " · 已锁定" : ""}</span></span>
                  <span className="flex gap-2 whitespace-nowrap"><button onClick={() => onPlanEdit({ action: "LOCK", outfit_id: outfit.outfit_id, item_id: item.item_id })}>锁定</button><button disabled={item.locked} onClick={() => onPlanEdit({ action: "REMOVE", outfit_id: outfit.outfit_id, item_id: item.item_id })}>删除</button>{replacement && <button disabled={item.locked} onClick={() => onPlanEdit({ action: "REPLACE", outfit_id: outfit.outfit_id, item_id: item.item_id, replacement: { item_id: replacement.article_id, source: "CATALOG", name: replacement.prod_name, category: replacement.product_type_name || replacement.product_group_name || "", image_url: replacement.image_url, price: replacement.price } })}>替换</button>}</span>
                </div>;
              })}
            </div>)}
            {wardrobePlan.missing_categories.length > 0 && <p className="mt-3 text-xs text-[#9b4b42]">缺失品类：{wardrobePlan.missing_categories.join("、")}</p>}
            {wardrobePlan.fallback && <p className="mt-2 text-xs text-muted">降级方案：{wardrobePlan.fallback}</p>}
            <button className="mt-3 rounded bg-ink px-3 py-2 text-xs text-white" onClick={onPlanAccept}>采纳此方案</button>
          </section>}
          <InsightPanel slots={slots} traces={traces} /></div>
      </aside>
    </div>
  );
}
