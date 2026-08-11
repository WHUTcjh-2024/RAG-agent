import { useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircle2, Heart, LoaderCircle, RefreshCw, Share2, Sparkles, ThumbsDown, ThumbsUp, Trash2, UserRound } from "lucide-react";
import {
  createVirtualTryOn,
  deleteVirtualTryOn,
  feedbackVirtualTryOn,
  fetchVirtualTryOn,
  listVirtualTryOns,
  saveVirtualTryOn,
  shareVirtualTryOn
} from "../api/client";
import type { Product } from "../types";
import type { SyntheticBodyProfile, VirtualTryOnJob } from "../try-on-types";
import "../try-on.css";

type Props = {
  product: Product;
  accessToken: string;
  onRequireLogin: () => void;
};

const DEFAULT_PROFILE: SyntheticBodyProfile = {
  height_cm: 168,
  weight_kg: 58,
  chest_cm: 88,
  waist_cm: 70,
  hip_cm: 94,
  shoulder_cm: 40,
  inseam_cm: 76,
  presentation: "NEUTRAL",
  body_shape: "BALANCED",
  skin_tone: "MEDIUM",
  fit_preference: "REGULAR"
};

const LABELS = {
  presentation: { FEMININE: "偏女性化", MASCULINE: "偏男性化", NEUTRAL: "中性" },
  body_shape: { BALANCED: "均衡", TRIANGLE: "梨形", INVERTED_TRIANGLE: "倒三角", RECTANGLE: "直筒", OVAL: "椭圆" },
  skin_tone: { LIGHT: "浅", MEDIUM: "中等", TAN: "小麦", DEEP: "深" },
  fit_preference: { CLOSE: "合身", REGULAR: "标准", RELAXED: "宽松" }
} as const;

function statusCopy(job: VirtualTryOnJob): string {
  if (job.status === "QUEUED") return "虚拟模特正在排队";
  if (job.status === "PROCESSING") return "正在生成模特并模拟面料细节";
  if (job.status === "SUCCEEDED") return "虚拟试穿已生成";
  return "本次生成未完成，请重试";
}

function MetricInput({ label, value, unit, onChange }: { label: string; value: number | undefined; unit: string; onChange: (value: number) => void }) {
  return (
    <label className="body-tryon-metric">
      <span>{label}</span>
      <div><input type="number" inputMode="decimal" value={value ?? ""} onChange={(event) => onChange(Number(event.target.value))} /><small>{unit}</small></div>
    </label>
  );
}

function ModelPreview({ profile }: { profile: SyntheticBodyProfile }) {
  const chest = Math.min(Math.max(profile.chest_cm, 60), 170);
  const waist = Math.min(Math.max(profile.waist_cm, 45), 180);
  const hip = Math.min(Math.max(profile.hip_cm, 60), 180);
  const scale = (value: number) => 28 + ((value - 45) / 135) * 40;
  const chestWidth = scale(chest);
  const waistWidth = scale(waist);
  const hipWidth = scale(hip);
  const skin = { LIGHT: "#ead3c3", MEDIUM: "#c99772", TAN: "#9b6947", DEEP: "#65412f" }[profile.skin_tone];
  const silhouette = `M ${90 - chestWidth} 82 Q 90 66 ${90 + chestWidth} 82 L ${90 + waistWidth} 153 Q ${90 + hipWidth} 170 ${90 + hipWidth - 3} 196 L ${105} 277 L 90 277 L 75 277 L ${90 - hipWidth + 3} 196 Q ${90 - hipWidth} 170 ${90 - waistWidth} 153 Z`;
  return (
    <figure className="body-model-preview" aria-label="根据身体参数生成的匿名模特比例预览">
      <svg viewBox="0 0 180 300" role="img">
        <circle cx="90" cy="43" r="25" fill={skin} />
        <path d={silhouette} fill="url(#model-fill)" />
        <defs><linearGradient id="model-fill" x1="0" y1="0" x2="1" y2="1"><stop stopColor="#73627a" /><stop offset="1" stopColor="#a58cab" /></linearGradient></defs>
      </svg>
      <figcaption><UserRound size={13} /> 匿名合成模特 · 不使用真人照片</figcaption>
    </figure>
  );
}

export function VirtualTryOn({ product, accessToken, onRequireLogin }: Props) {
  const [profile, setProfile] = useState<SyntheticBodyProfile>(DEFAULT_PROFILE);
  const [job, setJob] = useState<VirtualTryOnJob | null>(null);
  const [recent, setRecent] = useState<VirtualTryOnJob[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refreshRecent = useCallback(async () => {
    if (!accessToken) return;
    try { setRecent(await listVirtualTryOns(accessToken, 8)); } catch { /* History is non-blocking. */ }
  }, [accessToken]);

  useEffect(() => { void refreshRecent(); }, [refreshRecent]);

  useEffect(() => {
    if (!accessToken || !job || !["QUEUED", "PROCESSING"].includes(job.status)) return;
    let cancelled = false;
    let timer: number | undefined;
    let failures = 0;
    const poll = async () => {
      try {
        const next = await fetchVirtualTryOn(accessToken, job.id);
        if (cancelled) return;
        failures = 0;
        setJob(next);
        if (next.status === "SUCCEEDED") void refreshRecent();
        if (["QUEUED", "PROCESSING"].includes(next.status)) {
          timer = window.setTimeout(poll, Math.max(next.retry_after_seconds || 2, 1) * 1000);
        }
      } catch (cause) {
        if (cancelled) return;
        failures += 1;
        setError(cause instanceof Error ? cause.message : "试穿状态暂时无法获取。");
        timer = window.setTimeout(poll, Math.min(1000 * 2 ** failures, 15_000));
      }
    };
    timer = window.setTimeout(poll, 700);
    return () => { cancelled = true; if (timer) window.clearTimeout(timer); };
  }, [accessToken, job?.id, job?.status, refreshRecent]);

  const updateMetric = (key: keyof SyntheticBodyProfile, value: number) => {
    setProfile((current) => ({ ...current, [key]: Number.isFinite(value) ? value : 0 }));
    setError("");
  };
  const profileValid = useMemo(() => [profile.height_cm, profile.weight_kg, profile.chest_cm, profile.waist_cm, profile.hip_cm].every((value) => value > 0), [profile]);
  const busy = job?.status === "QUEUED" || job?.status === "PROCESSING";

  const generate = async () => {
    if (!accessToken) { onRequireLogin(); return; }
    if (!profileValid) { setError("请完整填写身高、体重和三围。"); return; }
    try {
      setError(""); setNotice("");
      setJob(await createVirtualTryOn(accessToken, product.article_id, profile));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "试穿服务暂时不可用，请稍后重试。");
    }
  };

  const toggleSave = async () => {
    if (!accessToken || !job) return;
    try { const next = await saveVirtualTryOn(accessToken, job.id, !job.saved); setJob(next); setNotice(next.saved ? "已保存 7 天" : "已取消保存"); void refreshRecent(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "保存失败"); }
  };

  const share = async () => {
    if (!accessToken || !job) return;
    try {
      const path = await shareVirtualTryOn(accessToken, job.id);
      const url = new URL(path, window.location.origin).toString();
      const shareApi = (navigator as unknown as { share?: (data: ShareData) => Promise<void> }).share;
      if (shareApi) await shareApi.call(navigator, { title: `${product.prod_name} 虚拟试穿`, url });
      else await navigator.clipboard.writeText(url);
      setNotice(shareApi ? "已打开分享面板" : "分享链接已复制");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "分享失败"); }
  };

  const remove = async () => {
    if (!accessToken || !job) return;
    try { await deleteVirtualTryOn(accessToken, job.id); setJob(null); setNotice("试穿结果已删除"); void refreshRecent(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "删除失败"); }
  };

  const feedback = async (positive: boolean) => {
    if (!accessToken || !job) return;
    try {
      const next = await feedbackVirtualTryOn(accessToken, job.id, { rating: positive ? 5 : 2, issues: positive ? [] : ["BODY_PROPORTION"] });
      setJob(next); setNotice("感谢反馈");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "反馈提交失败"); }
  };

  return (
    <section className="body-tryon" aria-labelledby="body-tryon-title">
      <header className="body-tryon-heading">
        <span><Sparkles size={16} /> AI 虚拟模特试穿</span>
        <p id="body-tryon-title">输入身体参数生成匿名成年模特，无需上传真人照片。</p>
      </header>

      <div className="body-tryon-layout">
        <ModelPreview profile={profile} />
        <div className="body-tryon-form">
          <div className="body-tryon-metrics">
            <MetricInput label="身高" value={profile.height_cm} unit="cm" onChange={(value) => updateMetric("height_cm", value)} />
            <MetricInput label="体重" value={profile.weight_kg} unit="kg" onChange={(value) => updateMetric("weight_kg", value)} />
            <MetricInput label="胸围" value={profile.chest_cm} unit="cm" onChange={(value) => updateMetric("chest_cm", value)} />
            <MetricInput label="腰围" value={profile.waist_cm} unit="cm" onChange={(value) => updateMetric("waist_cm", value)} />
            <MetricInput label="臀围" value={profile.hip_cm} unit="cm" onChange={(value) => updateMetric("hip_cm", value)} />
            <MetricInput label="肩宽" value={profile.shoulder_cm} unit="cm" onChange={(value) => updateMetric("shoulder_cm", value)} />
          </div>
          <div className="body-tryon-selects">
            <label>模特呈现<select value={profile.presentation} onChange={(event) => setProfile({ ...profile, presentation: event.target.value as SyntheticBodyProfile["presentation"] })}>{Object.entries(LABELS.presentation).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label>体型<select value={profile.body_shape} onChange={(event) => setProfile({ ...profile, body_shape: event.target.value as SyntheticBodyProfile["body_shape"] })}>{Object.entries(LABELS.body_shape).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label>肤色<select value={profile.skin_tone} onChange={(event) => setProfile({ ...profile, skin_tone: event.target.value as SyntheticBodyProfile["skin_tone"] })}>{Object.entries(LABELS.skin_tone).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label>穿着偏好<select value={profile.fit_preference} onChange={(event) => setProfile({ ...profile, fit_preference: event.target.value as SyntheticBodyProfile["fit_preference"] })}>{Object.entries(LABELS.fit_preference).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          </div>
        </div>
      </div>

      <div className={`body-tryon-stage ${job ? "is-active" : ""}`} aria-live="polite">
        {job?.status === "SUCCEEDED" && job.result?.url ? (
          <figure className="body-tryon-result"><img src={job.result.url} alt={`${product.prod_name} 的匿名虚拟模特试穿效果`} /><figcaption><CheckCircle2 size={14} /> AI 合成模特 · 不代表真实尺码</figcaption></figure>
        ) : <><span className="body-tryon-stage-icon">{busy ? <LoaderCircle className="body-tryon-spin" /> : <UserRound />}</span><strong>{job ? statusCopy(job) : "参数准备完成"}</strong><small>生成结果默认保留 24 小时，主动保存后保留 7 天。</small></>}
      </div>

      {job?.status === "SUCCEEDED" && <div className="body-tryon-actions">
        <button type="button" onClick={() => void toggleSave()}><Heart size={15} fill={job.saved ? "currentColor" : "none"} />{job.saved ? "已保存" : "保存"}</button>
        <button type="button" onClick={() => void share()}><Share2 size={15} />分享</button>
        <button type="button" onClick={() => void feedback(true)}><ThumbsUp size={15} />准确</button>
        <button type="button" onClick={() => void feedback(false)}><ThumbsDown size={15} />需改进</button>
        <button type="button" onClick={() => void remove()}><Trash2 size={15} />删除</button>
      </div>}
      <p className="body-tryon-privacy">仅处理身体参数并生成匿名成年模特，不上传或存储真人照片。</p>
      {error && <p className="body-tryon-error" role="alert">{error}</p>}
      {notice && <p className="body-tryon-notice" role="status">{notice}</p>}
      <button type="button" className="body-tryon-generate" onClick={() => void generate()} disabled={!profileValid || busy}>
        {busy ? <><LoaderCircle className="body-tryon-spin" size={16} />生成中</> : job?.status === "FAILED" ? <><RefreshCw size={16} />重新生成</> : <><Sparkles size={16} />生成虚拟模特并试穿</>}
      </button>

      {recent.some((item) => item.status === "SUCCEEDED" && item.result?.url) && <section className="body-tryon-recent" aria-label="最近试穿">
        <h3>最近试穿</h3><div>{recent.filter((item) => item.status === "SUCCEEDED" && item.result?.url).slice(0, 4).map((item) => <button type="button" key={item.id} onClick={() => setJob(item)} aria-label={`查看 ${item.product_id} 的试穿结果`}><img src={item.result!.url} alt="" /><span>{item.saved ? "已保存" : "24 小时"}</span></button>)}</div>
      </section>}
    </section>
  );
}
