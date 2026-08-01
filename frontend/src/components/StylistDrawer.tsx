import { X } from "lucide-react";
import type { DecisionCard, Message, PendingCartAction, Slots, ToolTrace } from "../types";
import { ChatPanel } from "./ChatPanel";
import { InsightPanel } from "./InsightPanel";
import { useTranslation } from "../i18n";

type Props = { open: boolean; onClose: () => void; messages: Message[]; streaming: boolean; slots: Slots; traces: ToolTrace[]; decision: DecisionCard | null; pendingAction: PendingCartAction | null; onConfirm: () => void; onSubmit: (message: string, image: File | null, preview: string | null) => void };

export function StylistDrawer({ open, onClose, messages, streaming, slots, traces, decision, pendingAction, onConfirm, onSubmit }: Props) {
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
          <InsightPanel slots={slots} traces={traces} /></div>
      </aside>
    </div>
  );
}
