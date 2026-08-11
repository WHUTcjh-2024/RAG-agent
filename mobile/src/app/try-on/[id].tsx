import { useCallback, useEffect, useMemo, useState } from "react";
import { Image } from "expo-image";
import { useLocalSearchParams, useRouter } from "expo-router";
import { ArrowLeft, CheckCircle2, Heart, LoaderCircle, RefreshCw, Share2, Sparkles, ThumbsDown, ThumbsUp, Trash2, UserRound } from "lucide-react-native";
import { ActivityIndicator, Pressable, ScrollView, Share, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import {
  createVirtualTryOn,
  deleteVirtualTryOn,
  feedbackVirtualTryOn,
  fetchProduct,
  fetchVirtualTryOn,
  listVirtualTryOns,
  saveVirtualTryOn,
  shareVirtualTryOn
} from "@/api/client";
import { assetUrl } from "@/config/environment";
import { useAppStore } from "@/store/use-app-store";
import { colors, radius, type } from "@/theme/tokens";
import type { Product } from "@/types";
import type { SyntheticBodyProfile, VirtualTryOnJob } from "@/types/try-on";

const DEFAULT_PROFILE: SyntheticBodyProfile = {
  height_cm: 168, weight_kg: 58, chest_cm: 88, waist_cm: 70, hip_cm: 94,
  shoulder_cm: 40, inseam_cm: 76, presentation: "NEUTRAL", body_shape: "BALANCED",
  skin_tone: "MEDIUM", fit_preference: "REGULAR",
};

const OPTIONS = {
  presentation: [["FEMININE", "偏女性化"], ["MASCULINE", "偏男性化"], ["NEUTRAL", "中性"]],
  body_shape: [["BALANCED", "均衡"], ["TRIANGLE", "梨形"], ["INVERTED_TRIANGLE", "倒三角"], ["RECTANGLE", "直筒"], ["OVAL", "椭圆"]],
  skin_tone: [["LIGHT", "浅"], ["MEDIUM", "中等"], ["TAN", "小麦"], ["DEEP", "深"]],
  fit_preference: [["CLOSE", "合身"], ["REGULAR", "标准"], ["RELAXED", "宽松"]],
} as const;

function statusCopy(job: VirtualTryOnJob | null): { title: string; detail: string } {
  if (job?.status === "QUEUED") return { title: "虚拟模特正在排队", detail: "即将生成匿名成年模特。" };
  if (job?.status === "PROCESSING") return { title: "正在生成试穿效果", detail: "正在处理身体比例、服装细节、垂坠与光影。" };
  if (job?.status === "FAILED") return { title: "本次生成未完成", detail: "请确认参数后重新生成。" };
  return { title: "参数准备完成", detail: "无需真人照片，效果仅供视觉参考。" };
}

function MetricField({ label, value, unit, onChange }: { label: string; value: number | undefined; unit: string; onChange: (value: number) => void }) {
  return <View style={styles.metric}><Text style={styles.metricLabel}>{label}</Text><View style={styles.metricInput}><TextInput value={value === undefined ? "" : String(value)} keyboardType="decimal-pad" onChangeText={(text) => onChange(Number(text.replace(",", ".")) || 0)} style={styles.input} /><Text style={styles.unit}>{unit}</Text></View></View>;
}

function ChoiceRow<K extends keyof typeof OPTIONS>({ label, kind, value, onChange }: { label: string; kind: K; value: string; onChange: (value: string) => void }) {
  return <View style={styles.choiceBlock}><Text style={styles.choiceLabel}>{label}</Text><ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.choices}>{OPTIONS[kind].map(([option, copy]) => <Pressable key={option} onPress={() => onChange(option)} style={[styles.choice, value === option && styles.choiceActive]}><Text style={[styles.choiceText, value === option && styles.choiceTextActive]}>{copy}</Text></Pressable>)}</ScrollView></View>;
}

function ModelPreview({ profile }: { profile: SyntheticBodyProfile }) {
  const scale = (value: number) => 44 + Math.min(Math.max(value - 60, 0), 100) * 0.35;
  const skin = { LIGHT: "#ead3c3", MEDIUM: "#c99772", TAN: "#9b6947", DEEP: "#65412f" }[profile.skin_tone];
  return <View style={styles.preview}><View style={[styles.head, { backgroundColor: skin }]} /><View style={[styles.chest, { width: scale(profile.chest_cm) }]} /><View style={[styles.waist, { width: scale(profile.waist_cm) }]} /><View style={[styles.hip, { width: scale(profile.hip_cm) }]} /><View style={styles.legs}><View style={styles.leg} /><View style={styles.leg} /></View><View style={styles.previewCaption}><UserRound size={12} color={colors.primary} /><Text style={styles.previewCaptionText}>匿名合成模特 · 不使用真人照片</Text></View></View>;
}

export default function TryOnScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const token = useAppStore((state) => state.accessToken);
  const [product, setProduct] = useState<Product | null>(null);
  const [profile, setProfile] = useState<SyntheticBodyProfile>(DEFAULT_PROFILE);
  const [job, setJob] = useState<VirtualTryOnJob | null>(null);
  const [recent, setRecent] = useState<VirtualTryOnJob[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => { if (id) void fetchProduct(id).then(setProduct).catch((cause) => setError(cause instanceof Error ? cause.message : "商品暂时无法加载")); }, [id]);
  const refreshRecent = useCallback(async () => { if (token) try { setRecent(await listVirtualTryOns(token, 8)); } catch { /* Non-blocking. */ } }, [token]);
  useEffect(() => {
    let active = true;
    if (token) void listVirtualTryOns(token, 8).then((items) => { if (active) setRecent(items); }).catch(() => undefined);
    return () => { active = false; };
  }, [token]);
  useEffect(() => {
    if (!token || !job || !["QUEUED", "PROCESSING"].includes(job.status)) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;
    const poll = async () => {
      try {
        const next = await fetchVirtualTryOn(token, job.id);
        if (!active) return;
        failures = 0; setJob(next); setError("");
        if (next.status === "SUCCEEDED") void refreshRecent();
        if (["QUEUED", "PROCESSING"].includes(next.status)) timer = setTimeout(poll, Math.max(next.retry_after_seconds || 2, 1) * 1000);
      } catch (cause) {
        if (!active) return;
        failures += 1; setError(cause instanceof Error ? cause.message : "试穿状态暂时无法获取");
        timer = setTimeout(poll, Math.min(1000 * 2 ** failures, 15_000));
      }
    };
    timer = setTimeout(poll, 700);
    return () => { active = false; if (timer) clearTimeout(timer); };
  }, [token, job, refreshRecent]);

  const updateMetric = (key: keyof SyntheticBodyProfile, value: number) => { setProfile((current) => ({ ...current, [key]: value })); setError(""); };
  const valid = useMemo(() => [profile.height_cm, profile.weight_kg, profile.chest_cm, profile.waist_cm, profile.hip_cm].every((value) => value > 0), [profile]);
  const busy = job?.status === "QUEUED" || job?.status === "PROCESSING";
  const copy = statusCopy(job);

  const generate = async () => {
    if (!product) return;
    if (!token) { router.push("/auth"); return; }
    if (!valid) { setError("请完整填写身高、体重和三围"); return; }
    try { setError(""); setNotice(""); setJob(await createVirtualTryOn(token, product.article_id, profile)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "试穿服务暂时不可用，请稍后重试"); }
  };
  const toggleSave = async () => { if (token && job) try { const next = await saveVirtualTryOn(token, job.id, !job.saved); setJob(next); setNotice(next.saved ? "已保存 7 天" : "已取消保存"); void refreshRecent(); } catch (cause) { setError(cause instanceof Error ? cause.message : "保存失败"); } };
  const share = async () => { if (token && job) try { const url = await shareVirtualTryOn(token, job.id); await Share.share({ message: `${product?.prod_name || "商品"} 虚拟试穿：${url}`, url }); } catch (cause) { setError(cause instanceof Error ? cause.message : "分享失败"); } };
  const remove = async () => { if (token && job) try { await deleteVirtualTryOn(token, job.id); setJob(null); setNotice("试穿结果已删除"); void refreshRecent(); } catch (cause) { setError(cause instanceof Error ? cause.message : "删除失败"); } };
  const feedback = async (positive: boolean) => { if (token && job) try { setJob(await feedbackVirtualTryOn(token, job.id, { rating: positive ? 5 : 2, issues: positive ? [] : ["BODY_PROPORTION"] })); setNotice("感谢反馈"); } catch (cause) { setError(cause instanceof Error ? cause.message : "反馈失败"); } };

  if (!product) return <SafeAreaView style={styles.loading}><ActivityIndicator size="large" color={colors.primary} /><Text style={styles.error}>{error}</Text></SafeAreaView>;
  return <SafeAreaView style={styles.safe} edges={["top", "bottom"]}>
    <View style={styles.header}><Pressable accessibilityLabel="返回商品" onPress={() => router.back()} style={styles.back}><ArrowLeft size={18} color={colors.ink} /></Pressable><View><Text style={styles.eyebrow}>SYNTHETIC MODEL / TRY-ON</Text><Text style={styles.headerTitle}>AI 虚拟模特试穿</Text></View></View>
    <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.content}>
      <Text style={styles.intro}>输入身体参数生成匿名成年模特，无需上传真人照片。</Text>
      <ModelPreview profile={profile} />
      <View style={styles.metrics}><MetricField label="身高" value={profile.height_cm} unit="cm" onChange={(value) => updateMetric("height_cm", value)} /><MetricField label="体重" value={profile.weight_kg} unit="kg" onChange={(value) => updateMetric("weight_kg", value)} /><MetricField label="胸围" value={profile.chest_cm} unit="cm" onChange={(value) => updateMetric("chest_cm", value)} /><MetricField label="腰围" value={profile.waist_cm} unit="cm" onChange={(value) => updateMetric("waist_cm", value)} /><MetricField label="臀围" value={profile.hip_cm} unit="cm" onChange={(value) => updateMetric("hip_cm", value)} /><MetricField label="肩宽" value={profile.shoulder_cm} unit="cm" onChange={(value) => updateMetric("shoulder_cm", value)} /></View>
      <ChoiceRow label="模特呈现" kind="presentation" value={profile.presentation} onChange={(value) => setProfile({ ...profile, presentation: value as SyntheticBodyProfile["presentation"] })} />
      <ChoiceRow label="体型" kind="body_shape" value={profile.body_shape} onChange={(value) => setProfile({ ...profile, body_shape: value as SyntheticBodyProfile["body_shape"] })} />
      <ChoiceRow label="肤色" kind="skin_tone" value={profile.skin_tone} onChange={(value) => setProfile({ ...profile, skin_tone: value as SyntheticBodyProfile["skin_tone"] })} />
      <ChoiceRow label="穿着偏好" kind="fit_preference" value={profile.fit_preference} onChange={(value) => setProfile({ ...profile, fit_preference: value as SyntheticBodyProfile["fit_preference"] })} />
      {job?.status === "SUCCEEDED" && job.result?.url ? <View style={styles.result}><Image source={{ uri: assetUrl(job.result.url) }} style={styles.resultImage} contentFit="contain" transition={220} /><View style={styles.resultBadge}><CheckCircle2 size={13} color={colors.white} /><Text>AI 合成模特 · 不代表真实尺码</Text></View></View> : <View style={styles.status}>{busy ? <LoaderCircle size={24} color={colors.primary} /> : <Sparkles size={24} color={colors.primary} />}<Text style={styles.statusTitle}>{copy.title}</Text><Text style={styles.statusDetail}>{copy.detail}</Text></View>}
      {job?.status === "SUCCEEDED" && <View style={styles.actions}><Pressable onPress={() => void toggleSave()} style={styles.action}><Heart size={17} color={colors.primary} fill={job.saved ? colors.primary : "transparent"} /><Text style={styles.actionText}>{job.saved ? "已保存" : "保存"}</Text></Pressable><Pressable onPress={() => void share()} style={styles.action}><Share2 size={17} color={colors.primary} /><Text style={styles.actionText}>分享</Text></Pressable><Pressable onPress={() => void feedback(true)} style={styles.action}><ThumbsUp size={17} color={colors.primary} /><Text style={styles.actionText}>准确</Text></Pressable><Pressable onPress={() => void feedback(false)} style={styles.action}><ThumbsDown size={17} color={colors.primary} /><Text style={styles.actionText}>需改进</Text></Pressable><Pressable onPress={() => void remove()} style={styles.action}><Trash2 size={17} color={colors.error} /><Text style={styles.actionText}>删除</Text></Pressable></View>}
      <Text style={styles.privacy}>仅处理身体参数并生成匿名成年模特；未保存结果 24 小时后删除。</Text>
      {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}{!!notice && <Text style={styles.notice}>{notice}</Text>}
      <Pressable disabled={!valid || busy} onPress={() => void generate()} style={[styles.generate, (!valid || busy) && styles.disabled]}>{busy ? <LoaderCircle size={17} color={colors.white} /> : job?.status === "FAILED" ? <RefreshCw size={17} color={colors.white} /> : <Sparkles size={17} color={colors.white} />}<Text style={styles.generateText}>{busy ? "生成中" : job?.status === "FAILED" ? "重新生成" : "生成虚拟模特并试穿"}</Text></Pressable>
      {recent.some((item) => item.status === "SUCCEEDED" && item.result?.url) && <View style={styles.recent}><Text style={styles.recentTitle}>最近试穿</Text><ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.recentRow}>{recent.filter((item) => item.status === "SUCCEEDED" && item.result?.url).map((item) => <Pressable key={item.id} onPress={() => setJob(item)} style={styles.recentItem}><Image source={{ uri: assetUrl(item.result!.url) }} style={styles.recentImage} contentFit="cover" /><Text>{item.saved ? "已保存" : "24 小时"}</Text></Pressable>)}</ScrollView></View>}
    </ScrollView>
  </SafeAreaView>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background }, loading: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.background }, header: { height: 66, paddingHorizontal: 16, flexDirection: "row", gap: 12, alignItems: "center", borderBottomWidth: 1, borderBottomColor: colors.line, backgroundColor: colors.surface }, back: { width: 38, height: 38, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.line, borderRadius: 19 }, eyebrow: { color: colors.primary, fontFamily: type.mono, fontSize: 8, fontWeight: "800" }, headerTitle: { marginTop: 3, color: colors.ink, fontSize: 18, fontWeight: "800" }, content: { padding: 16, paddingBottom: 40 }, intro: { color: colors.muted, fontSize: 12, lineHeight: 19 },
  preview: { height: 290, marginTop: 14, alignItems: "center", justifyContent: "center", overflow: "hidden", borderWidth: 1, borderColor: colors.line, borderRadius: radius.xl, backgroundColor: colors.surfaceSoft }, head: { width: 50, height: 50, borderRadius: 25 }, chest: { height: 62, marginTop: 5, borderTopLeftRadius: 24, borderTopRightRadius: 24, backgroundColor: "#73627a" }, waist: { height: 48, backgroundColor: "#87738e" }, hip: { height: 50, borderBottomLeftRadius: 20, borderBottomRightRadius: 20, backgroundColor: "#9f88a6" }, legs: { height: 57, flexDirection: "row", gap: 9 }, leg: { width: 15, height: 55, borderBottomLeftRadius: 7, borderBottomRightRadius: 7, backgroundColor: "#78677f" }, previewCaption: { position: "absolute", bottom: 10, flexDirection: "row", gap: 5, alignItems: "center" }, previewCaptionText: { color: colors.primary, fontSize: 9 },
  metrics: { marginTop: 14, flexDirection: "row", flexWrap: "wrap", gap: 8 }, metric: { width: "48%", gap: 5 }, metricLabel: { color: colors.muted, fontSize: 10 }, metricInput: { height: 42, paddingHorizontal: 10, flexDirection: "row", alignItems: "center", borderWidth: 1, borderColor: colors.line, borderRadius: radius.md, backgroundColor: colors.surface }, input: { flex: 1, color: colors.ink, fontSize: 14, fontWeight: "700" }, unit: { color: colors.muted, fontSize: 9 }, choiceBlock: { marginTop: 13 }, choiceLabel: { marginBottom: 6, color: colors.muted, fontSize: 10 }, choices: { gap: 6 }, choice: { minHeight: 34, paddingHorizontal: 12, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.line, borderRadius: 17, backgroundColor: colors.surface }, choiceActive: { borderColor: colors.primary, backgroundColor: colors.primaryPale }, choiceText: { color: colors.muted, fontSize: 10 }, choiceTextActive: { color: colors.primary, fontWeight: "800" },
  status: { minHeight: 130, marginTop: 15, padding: 18, alignItems: "center", justifyContent: "center", borderRadius: radius.xl, backgroundColor: colors.surfaceSoft }, statusTitle: { marginTop: 9, color: colors.ink, fontSize: 14, fontWeight: "800" }, statusDetail: { marginTop: 5, color: colors.muted, fontSize: 10, textAlign: "center" }, result: { minHeight: 360, marginTop: 15, overflow: "hidden", borderRadius: radius.xl, backgroundColor: colors.surfaceSoft }, resultImage: { width: "100%", height: 420 }, resultBadge: { position: "absolute", right: 9, bottom: 9, padding: 7, flexDirection: "row", gap: 5, alignItems: "center", borderRadius: radius.sm, backgroundColor: "rgba(20,18,22,.72)" },
  actions: { marginTop: 9, flexDirection: "row", justifyContent: "space-between", gap: 5 }, action: { minWidth: 52, minHeight: 48, paddingHorizontal: 5, alignItems: "center", justifyContent: "center", gap: 3, borderWidth: 1, borderColor: colors.line, borderRadius: radius.sm, backgroundColor: colors.surface }, actionText: { color: colors.muted, fontSize: 8 }, privacy: { marginTop: 12, color: colors.muted, fontSize: 9, lineHeight: 15 }, error: { marginTop: 9, color: colors.error, fontSize: 10 }, notice: { marginTop: 9, color: colors.success, fontSize: 10 }, generate: { height: 48, marginTop: 12, flexDirection: "row", gap: 7, alignItems: "center", justifyContent: "center", borderRadius: radius.md, backgroundColor: colors.primary }, generateText: { color: colors.white, fontSize: 12, fontWeight: "800" }, disabled: { opacity: 0.48 }, recent: { marginTop: 20 }, recentTitle: { color: colors.ink, fontSize: 13, fontWeight: "800" }, recentRow: { gap: 8, paddingTop: 9 }, recentItem: { width: 88, overflow: "hidden", borderRadius: radius.md, backgroundColor: colors.surface }, recentImage: { width: 88, height: 104 },
});
