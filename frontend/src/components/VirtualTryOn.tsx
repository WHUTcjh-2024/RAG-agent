import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { Camera, CheckCircle2, ImagePlus, LoaderCircle, RefreshCw, Sparkles, TriangleAlert } from "lucide-react";
import { createVirtualTryOn, fetchVirtualTryOn } from "../api/client";
import type { Product, VirtualTryOnJob } from "../types";

type Props = {
  product: Product;
  accessToken: string;
  onRequireLogin: () => void;
};

const MAX_IMAGE_BYTES = 12 * 1024 * 1024;

function messageFor(job: VirtualTryOnJob): string {
  if (job.status === "QUEUED") return "正在排队准备试穿…";
  if (job.status === "PROCESSING") return "正在模拟面料垂坠、遮挡与光影…";
  if (job.status === "SUCCEEDED") return "试穿效果已生成";
  return "这次试穿未能生成，请更换清晰全身照后重试。";
}

export function VirtualTryOn({ product, accessToken, onRequireLogin }: Props) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [consented, setConsented] = useState(false);
  const [job, setJob] = useState<VirtualTryOnJob | null>(null);
  const [error, setError] = useState("");

  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl); }, [previewUrl]);

  useEffect(() => {
    if (!accessToken || !job || !["QUEUED", "PROCESSING"].includes(job.status)) return;
    let cancelled = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const next = await fetchVirtualTryOn(accessToken, job.id);
        if (cancelled) return;
        setJob(next);
        if (["QUEUED", "PROCESSING"].includes(next.status)) {
          timer = window.setTimeout(poll, Math.max(next.retry_after_seconds || 2, 1) * 1000);
        }
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "试穿状态暂时无法获取。");
      }
    };
    timer = window.setTimeout(poll, 700);
    return () => { cancelled = true; if (timer) window.clearTimeout(timer); };
  }, [accessToken, job?.id, job?.status]);

  const selectFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
      setError("请选择 JPG、PNG 或 WebP 格式的照片。");
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setError("照片不能超过 12 MB。");
      return;
    }
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setError(""); setJob(null); setSelectedFile(file); setPreviewUrl(URL.createObjectURL(file));
  };

  const generate = async () => {
    if (!accessToken) { onRequireLogin(); return; }
    if (!selectedFile || !consented) {
      setError("请选择照片并确认照片处理说明。");
      return;
    }
    try {
      setError("");
      setJob(await createVirtualTryOn(accessToken, product.article_id, selectedFile));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "试穿服务暂时不可用，请稍后重试。");
    }
  };

  const busy = job?.status === "QUEUED" || job?.status === "PROCESSING";
  const canGenerate = Boolean(selectedFile && consented && !busy);
  return (
    <section className="virtual-tryon" aria-labelledby="tryon-title">
      <div className="tryon-heading">
        <span><Sparkles size={15} /> AI 虚拟试穿</span>
        <p id="tryon-title">上传清晰全身照，预览这件商品在你身上的视觉效果。</p>
      </div>
      <div className="tryon-guidance">
        <Camera size={16} /><span>自然光、正面站立、全身入镜，效果更稳定。</span>
      </div>
      <input ref={fileInput} className="sr-only" type="file" accept="image/jpeg,image/png,image/webp" onChange={selectFile} />
      <div className="tryon-workspace">
        <button type="button" className="tryon-picker" onClick={() => fileInput.current?.click()} disabled={busy}>
          {previewUrl ? <img src={previewUrl} alt="待试穿的人像预览" /> : <><ImagePlus size={22} /><span>选择全身照片</span></>}
        </button>
        {job?.status === "SUCCEEDED" && job.result?.url ? (
          <figure className="tryon-result"><img src={job.result.url} alt={`${product.prod_name} 的虚拟试穿效果`} /><figcaption><CheckCircle2 size={14} /> 已生成 · 结果将在 24 小时后删除</figcaption></figure>
        ) : (
          <div className={`tryon-status ${job ? "is-active" : ""}`} aria-live="polite">
            {busy ? <LoaderCircle className="tryon-spin" size={22} /> : job?.status === "FAILED" ? <TriangleAlert size={22} /> : <Sparkles size={22} />}
            <strong>{job ? messageFor(job) : "准备开始试穿"}</strong>
            <span>{job ? "将保留你的姿态与商品细节；不代表实际尺码或合身度。" : "我们会在生成后删除原始上传照片。"}</span>
          </div>
        )}
      </div>
      {job?.photo_quality.warnings.length ? <ul className="tryon-warnings">{job.photo_quality.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : null}
      <label className="tryon-consent"><input type="checkbox" checked={consented} onChange={(event) => setConsented(event.target.checked)} disabled={busy} /><span>我确认已获照片中人物授权；上传照仅用于本次试穿，生成后删除。</span></label>
      {error ? <p className="tryon-error" role="alert">{error}</p> : null}
      <button type="button" className="tryon-generate" onClick={() => void generate()} disabled={!canGenerate}>
        {busy ? <><LoaderCircle className="tryon-spin" size={16} /> 生成中</> : job?.status === "FAILED" ? <><RefreshCw size={16} /> 重新生成</> : <><Sparkles size={16} /> 开始试穿</>}
      </button>
    </section>
  );
}
