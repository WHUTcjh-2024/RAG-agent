import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ArrowLeft, ArrowRight, Check, Circle, Database, GitCompareArrows, ImagePlus, Link2, LoaderCircle, RotateCcw, Search, ShieldCheck, Sparkles, Square, Wrench, X } from "lucide-react";
import { productImage } from "../api/client";
import { useTranslation } from "../i18n";
import { motionTokens } from "../motion/tokens";
import type { AgentNodeEvent, AgentPhase, DecisionCard, DecisionEvidence, Message, PendingCartAction, Product, Slots, ToolTrace, WardrobePlan, WardrobeSnapshot } from "../types";

type AgentState = "idle" | AgentPhase;

type Props = {
  messages: Message[];
  streaming: boolean;
  state: AgentState;
  events: AgentNodeEvent[];
  slots: Slots;
  traces: ToolTrace[];
  products: Product[];
  evidence: DecisionEvidence[];
  decision: DecisionCard | null;
  pendingAction: PendingCartAction | null;
  wardrobe: WardrobeSnapshot | null;
  wardrobePlan: WardrobePlan | null;
  error: string;
  onClose: () => void;
  onSubmit: (message: string, image: File | null, preview: string | null) => void;
  onCancel: () => void;
  onRetry: () => void;
  onConfirm: () => void;
  onPlanAccept: () => void;
  onPlanEdit: (operation: Record<string, unknown>) => void;
  onDetail: (id: string) => void;
};

const phaseOrder: AgentPhase[] = ["understanding", "constraints", "retrieval", "knowledge", "tool", "comparison", "verification", "generation"];

const icons: Record<string, React.ReactNode> = {
  understanding: <Sparkles size={14} />, constraints: <Circle size={14} />, retrieval: <Search size={14} />, knowledge: <Database size={14} />,
  tool: <Wrench size={14} />, comparison: <GitCompareArrows size={14} />, verification: <ShieldCheck size={14} />, generation: <LoaderCircle size={14} />
};

export function AgentWorkspace(props: Props) {
  const { language, t } = useTranslation();
  const [value, setValue] = useState("");
  const [image, setImage] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [mobilePane, setMobilePane] = useState<"execution" | "dialogue" | "evidence">("dialogue");
  const messageEnd = useRef<HTMLDivElement>(null);
  const prompts = [t("prompt1"), t("prompt2"), t("prompt3")];
  const labels: Record<AgentPhase, string> = language === "zh" ? {
    understanding: "正在理解需求", constraints: "正在提取约束", retrieval: "正在检索商品", knowledge: "正在查询知识库", tool: "正在调用工具",
    comparison: "正在比较参数", verification: "正在验证推荐依据", generation: "正在生成最终建议", waiting: "等待用户补充", success: "执行成功",
    failure: "执行失败", cancelled: "已取消", retrying: "正在重试"
  } : {
    understanding: "Understanding request", constraints: "Extracting constraints", retrieval: "Retrieving products", knowledge: "Querying knowledge base", tool: "Calling tools",
    comparison: "Comparing parameters", verification: "Verifying evidence", generation: "Generating recommendation", waiting: "Waiting for input", success: "Complete",
    failure: "Failed", cancelled: "Cancelled", retrying: "Retrying"
  };

  useEffect(() => { messageEnd.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [props.messages]);

  const completedPhases = useMemo(() => new Set(props.events.filter((event) => event.state === "completed").map((event) => event.phase)), [props.events]);
  const startedNodes = useMemo(() => props.events.filter((event) => event.state === "started"), [props.events]);
  const latestAssistantMessage = useMemo(
    () => [...props.messages].reverse().find((message) => message.role === "assistant" && message.content.trim()),
    [props.messages]
  );

  const selectImage = (file?: File) => {
    if (!file) return;
    if (preview) URL.revokeObjectURL(preview);
    setImage(file); setPreview(URL.createObjectURL(file));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if ((!value.trim() && !image) || props.streaming) return;
    props.onSubmit(value.trim(), image, preview);
    setValue(""); setImage(null); setPreview(null);
  };

  return (
    <div className="agent-page">
      <header className="agent-header">
        <button onClick={props.onClose} aria-label={t("close")}><ArrowLeft size={18} /></button>
        <div><span className="agent-avatar"><Sparkles size={14} /></span><span>{language === "zh" ? "在线" : "ONLINE"}</span><h1>FitMe Agent</h1></div>
        <div className={`agent-live-state state-${props.state}`}><i />{props.state === "idle" ? t("waiting") : labels[props.state]}</div>
      </header>

      <nav className="agent-mobile-tabs" aria-label={language === "zh" ? "Agent 工作区面板" : "Agent workspace panels"}>
        {([
          ["execution", <Wrench size={13} />, language === "zh" ? "执行" : "Execution"],
          ["dialogue", <Sparkles size={13} />, language === "zh" ? "对话" : "Dialogue"],
          ["evidence", <Link2 size={13} />, language === "zh" ? "依据" : "Evidence"]
        ] as const).map(([pane, icon, label]) => (
          <button key={pane} aria-current={mobilePane === pane ? "page" : undefined} onClick={() => setMobilePane(pane)}>
            {icon}{label}
          </button>
        ))}
      </nav>

      <div className={`agent-layout mobile-pane-${mobilePane}`}>
        <aside className="agent-execution-panel">
          <div className="panel-heading"><span>01</span><h2>{t("execution")}</h2></div>
          <p className="agent-principle">{t("agentIntro")}</p>
          <div className="phase-rail">
            {phaseOrder.map((phase) => {
              const active = props.state === phase;
              const complete = completedPhases.has(phase);
              const event = [...props.events].reverse().find((item) => item.phase === phase);
              return (
                <motion.div layout key={phase} className={active ? "phase-step is-active" : complete ? "phase-step is-complete" : "phase-step"}>
                  <span>{complete ? <Check size={13} /> : icons[phase]}</span>
                  <div><strong>{labels[phase]}</strong>{event?.summary && <small>{event.summary}</small>}{event?.durationMs !== undefined && <small>{event.durationMs.toFixed(1)}ms</small>}</div>
                  {active && <motion.i layoutId="active-phase" />}
                </motion.div>
              );
            })}
          </div>
          {props.events.length === 0 && <p className="empty-trace">{t("noExecution")}</p>}
          <AnimatePresence>
            {props.state === "retrying" && <motion.div className="special-agent-state" initial={{ opacity: 0 }} animate={{ opacity: 1 }}><RotateCcw size={14} />{labels.retrying}</motion.div>}
            {props.state === "cancelled" && <motion.div className="special-agent-state" initial={{ opacity: 0 }} animate={{ opacity: 1 }}><Square size={13} />{labels.cancelled}</motion.div>}
          </AnimatePresence>
          {props.traces.length > 0 && <div className="tool-traces"><span>{t("execution")} / Tools</span>{props.traces.map((trace, index) => <motion.div key={`${trace.tool}-${index}`} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }}><Wrench size={12} /><p><strong>{trace.tool}</strong>{trace.summary}</p></motion.div>)}</div>}
        </aside>

        <section className="agent-conversation">
          <div className="conversation-heading"><div><span>02 / DIALOGUE</span><h2>{t("dressingFor")}</h2></div>{props.streaming && <button onClick={props.onCancel}><Square size={12} />{t("stop")}</button>}</div>
          <div className="message-stream">
            {props.messages.length === 0 ? <div className="prompt-intro"><p>{t("chatHelp")}</p>{prompts.map((prompt, index) => <button key={prompt} onClick={() => setValue(prompt)}><span>0{index + 1}</span>{prompt}<ArrowRight size={14} /></button>)}</div> : (
              <AnimatePresence initial={false}>
                {props.messages.map((message) => (
                  <motion.article key={message.id} className={`agent-message ${message.role}`} initial={{ opacity: 0, y: 16, filter: "blur(5px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}>
                    <span>{message.role === "user" ? "YOU" : "ATELIER"}</span>
                    <div data-testid={message.role === "assistant" ? "assistant-message" : undefined}>
                      {message.imagePreview && <img src={message.imagePreview} alt={t("uploadAlt")} />}
                      <p>{message.content}</p>
                      {props.streaming && message.role === "assistant" && message === props.messages.at(-1) && <i className="semantic-caret" />}
                    </div>
                  </motion.article>
                ))}
              </AnimatePresence>
            )}
            <div ref={messageEnd} />
          </div>
          <form className="agent-composer" onSubmit={submit}>
            <AnimatePresence>{preview && <motion.div className="composer-preview" initial={{ height: 0, opacity: 0 }} animate={{ height: 70, opacity: 1 }} exit={{ height: 0, opacity: 0 }}><img src={preview} alt={t("preview")} /><div><strong>{image?.name}</strong><span>{t("visualSearch")}</span></div><button type="button" aria-label={t("close")} onClick={() => { URL.revokeObjectURL(preview); setImage(null); setPreview(null); }}><X size={14} /></button></motion.div>}</AnimatePresence>
            <div>
              <label aria-label={t("upload")}><ImagePlus size={18} /><input type="file" accept="image/*" onChange={(event) => selectImage(event.target.files?.[0])} /></label>
              <textarea data-testid="agent-message" aria-label={t("request")} value={value} onChange={(event) => setValue(event.target.value)} placeholder={t("chatPlaceholder")} rows={3} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} />
              <motion.button data-testid="agent-send" aria-label={t("send")} type="submit" disabled={props.streaming || (!value.trim() && !image)} whileTap={{ scale: motionTokens.scale.press }}><ArrowRight size={17} /></motion.button>
            </div>
          </form>
          {props.error && <motion.div className="agent-error" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}><X size={14} /><span>{props.error}</span><button onClick={props.onRetry}>{t("retry")}</button></motion.div>}
        </section>

        <aside className="agent-evidence-panel">
          <div className="panel-heading"><span>03</span><h2>{t("constraints")}</h2></div>
          <div className="slot-cloud"><AnimatePresence mode="popLayout">{Object.entries(props.slots).map(([key, value]) => <motion.span layout key={key} initial={{ scale: 0.7, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}><small>{key}</small>{Array.isArray(value) ? value.join(" · ") : value}</motion.span>)}</AnimatePresence>{Object.keys(props.slots).length === 0 && <p>—</p>}</div>

          {props.products.length > 0 && <div className="agent-candidates"><h3>{t("candidates")} <span>{props.products.length}</span></h3><div>{props.products.slice(0, 4).map((product, index) => <motion.button key={product.article_id} onClick={() => props.onDetail(product.article_id)} initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: index * 0.06 }}><img src={productImage(product)} alt="" /><span>{product.prod_name}<small>{product.reason || `${product.product_type_name} · ${product.colour_group_name}`}</small></span></motion.button>)}</div></div>}

          {(props.evidence.length > 0 || props.decision) && <div className="evidence-map"><h3><Link2 size={13} />{t("evidence")}</h3>{latestAssistantMessage && <div className="grounded-conclusion"><span>{language === "zh" ? "关联结论" : "Linked conclusion"}</span><p>{latestAssistantMessage.content}</p></div>}{props.evidence.map((item) => <details key={`${item.source_id}-${item.field}`}><summary>{item.field}<span>{item.source_type}</span></summary><p>{item.value}</p><small>{item.source_id}</small></details>)}{props.decision && <motion.div className="decision-card" initial={{ clipPath: "inset(0 0 100% 0)" }} animate={{ clipPath: "inset(0 0 0% 0)" }}><span>{props.decision.verdict.replaceAll("_", " ")}</span><strong>{Math.round(props.decision.confidence * 100)}%</strong>{props.decision.reasons.map((reason) => <p key={reason}>{reason}</p>)}</motion.div>}</div>}

          {props.pendingAction && <motion.div className="confirm-card" initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}><span>{t("waiting")}</span><p>{props.pendingAction.summary}</p><button onClick={props.onConfirm}>{t("confirmAdd")}</button></motion.div>}

          {props.wardrobePlan && <div className="wardrobe-plan"><h3>{t("wardrobe")} <small>v{props.wardrobePlan.wardrobe_version}</small></h3><p>{props.wardrobe?.items.length || 0} existing · {props.wardrobePlan.new_item_total} new</p>{props.wardrobePlan.outfits.map((outfit) => <div key={outfit.outfit_id}><strong>{outfit.name}</strong>{outfit.items.map((item) => <span key={item.item_id}>{item.name}<button disabled={item.locked} onClick={() => props.onPlanEdit({ action: "LOCK", outfit_id: outfit.outfit_id, item_id: item.item_id })}>{item.locked ? "✓" : "○"}</button></span>)}</div>)}<button onClick={props.onPlanAccept}>{t("adoptPlan")}</button></div>}

          {startedNodes.length > 0 && <p className="event-integrity"><ShieldCheck size={12} /> {startedNodes.length} verified workflow events</p>}
        </aside>
      </div>
    </div>
  );
}
