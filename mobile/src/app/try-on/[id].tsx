import { useEffect, useState } from "react";
import { Image } from "expo-image";
import * as ImagePicker from "expo-image-picker";
import { useLocalSearchParams, useRouter } from "expo-router";
import { ArrowLeft, Camera, CheckCircle2, ImagePlus, LoaderCircle, RefreshCw, Sparkles, TriangleAlert } from "lucide-react-native";
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { createVirtualTryOn, fetchProduct, fetchVirtualTryOn } from "@/api/client";
import { assetUrl } from "@/config/environment";
import { useAppStore } from "@/store/use-app-store";
import { colors, radius, type } from "@/theme/tokens";
import type { PickedImage, Product, VirtualTryOnJob } from "@/types";

const MAX_IMAGE_BYTES = 12 * 1024 * 1024;

function toPickedImage(asset: ImagePicker.ImagePickerAsset): PickedImage {
  return {
    uri: asset.uri,
    name: asset.fileName || "try-on.jpg",
    mimeType: asset.mimeType === "image/jpg" ? "image/jpeg" : asset.mimeType || "image/jpeg",
  };
}

function statusCopy(job: VirtualTryOnJob | null): { title: string; detail: string } {
  if (job?.status === "QUEUED") return { title: "正在排队准备…", detail: "即将开始生成你的试穿效果。" };
  if (job?.status === "PROCESSING") return { title: "正在模拟服装细节…", detail: "正在处理面料垂坠、褶皱、遮挡与光影。" };
  if (job?.status === "FAILED") return { title: "本次生成未完成", detail: "请更换清晰、正面、全身入镜的照片后重试。" };
  return { title: "准备开始试穿", detail: "效果仅供视觉参考，不代表实际尺码或合身度。" };
}

export default function TryOnScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const token = useAppStore((state) => state.accessToken);
  const [product, setProduct] = useState<Product | null>(null);
  const [photo, setPhoto] = useState<PickedImage | null>(null);
  const [consented, setConsented] = useState(false);
  const [job, setJob] = useState<VirtualTryOnJob | null>(null);
  const [error, setError] = useState("");

  useEffect(() => { if (id) void fetchProduct(id).then(setProduct).catch((cause) => setError(cause instanceof Error ? cause.message : "商品暂时无法加载")); }, [id]);
  useEffect(() => {
    let active = true;
    void ImagePicker.getPendingResultAsync().then((result) => {
      if (!active || !result || !("canceled" in result) || result.canceled || !result.assets?.[0]) return;
      setPhoto(toPickedImage(result.assets[0]));
    }).catch(() => undefined);
    return () => { active = false; };
  }, []);
  useEffect(() => {
    const jobId = job?.id;
    const jobStatus = job?.status;
    const pollAfterSeconds = job?.retry_after_seconds;
    if (!token || !jobId || !jobStatus || !["QUEUED", "PROCESSING"].includes(jobStatus)) return;
    let active = true;
    const timer = setTimeout(async () => {
      try {
        const next = await fetchVirtualTryOn(token, jobId);
        if (active) setJob(next);
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : "试穿状态暂时无法获取");
      }
    }, Math.max(pollAfterSeconds || 2, 1) * 1000);
    return () => { active = false; clearTimeout(timer); };
  }, [token, job?.id, job?.status, job?.retry_after_seconds]);

  const selectPhoto = async () => {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) { Alert.alert("需要照片权限", "请允许访问照片，以选择全身照进行虚拟试穿。"); return; }
    const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], allowsEditing: true, aspect: [3, 4], quality: 0.92, exif: false });
    if (result.canceled || !result.assets[0]) return;
    const asset = result.assets[0];
    const selected = toPickedImage(asset);
    if (asset.fileSize && asset.fileSize > MAX_IMAGE_BYTES) { setError("照片不能超过 12 MB"); return; }
    if (!["image/jpeg", "image/png", "image/webp"].includes(selected.mimeType)) { setError("请选择 JPG、PNG 或 WebP 格式的照片"); return; }
    setPhoto(selected); setJob(null); setError("");
  };

  const generate = async () => {
    if (!product) return;
    if (!token) { router.push("/auth"); return; }
    if (!photo || !consented) { setError("请选择照片并确认照片处理说明"); return; }
    try { setError(""); setJob(await createVirtualTryOn(token, product.article_id, photo)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "试穿服务暂时不可用，请稍后重试"); }
  };

  if (!product) return <SafeAreaView style={styles.loading}><ActivityIndicator size="large" color={colors.primary} /><Text style={styles.loadingText}>{error || "正在加载试穿服务"}</Text></SafeAreaView>;
  const busy = job?.status === "QUEUED" || job?.status === "PROCESSING";
  const status = statusCopy(job);
  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <View style={styles.header}><Pressable accessibilityLabel="返回商品" onPress={() => router.back()} style={styles.back}><ArrowLeft size={18} color={colors.ink} /></Pressable><View><Text style={styles.eyebrow}>FITME / VIRTUAL TRY-ON</Text><Text style={styles.headerTitle}>AI 虚拟试穿</Text></View></View>
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.intro}><Sparkles size={18} color={colors.primary} /><View><Text style={styles.introTitle}>{product.prod_name}</Text><Text style={styles.introText}>上传清晰全身照，预览服装在你身上的视觉效果。</Text></View></View>
        <View style={styles.guide}><Camera size={16} color={colors.primary} /><Text style={styles.guideText}>建议在自然光下正面站立，头到脚完整入镜；避免镜面、强遮挡和多人照片。</Text></View>
        <View style={styles.stage}>
          <Pressable accessibilityLabel="选择全身照" onPress={() => void selectPhoto()} disabled={busy} style={styles.photoSlot}>
            {photo ? <Image source={{ uri: photo.uri }} style={styles.stageImage} contentFit="cover" /> : <><ImagePlus size={27} color={colors.primary} /><Text style={styles.slotTitle}>选择全身照</Text><Text style={styles.slotText}>JPG · PNG · WebP</Text></>}
          </Pressable>
          {job?.status === "SUCCEEDED" && job.result?.url ? <View style={styles.resultSlot}><Image source={{ uri: assetUrl(job.result.url) }} style={styles.stageImage} contentFit="cover" /><View style={styles.successBadge}><CheckCircle2 size={12} color={colors.white} /><Text style={styles.successText}>已生成</Text></View></View> : <View style={styles.statusSlot}>{busy ? <LoaderCircle size={27} color={colors.primary} /> : job?.status === "FAILED" ? <TriangleAlert size={27} color={colors.error} /> : <Sparkles size={27} color={colors.primary} />}<Text style={styles.statusTitle}>{status.title}</Text><Text style={styles.statusText}>{status.detail}</Text></View>}
        </View>
        {job?.photo_quality.warnings.map((warning) => <Text key={warning} style={styles.warning}>• {warning}</Text>)}
        <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: consented }} onPress={() => setConsented((value) => !value)} style={styles.consent}><View style={[styles.checkbox, consented && styles.checkboxChecked]}>{consented && <CheckCircle2 size={12} color={colors.white} />}</View><Text style={styles.consentText}>我确认已获得照片中人物授权；原始上传照片仅用于本次生成，完成后自动删除，结果将在 24 小时后删除。</Text></Pressable>
        {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
        <Pressable onPress={() => void generate()} disabled={!photo || !consented || busy} style={[styles.generate, (!photo || !consented || busy) && styles.generateDisabled]}>{busy ? <LoaderCircle size={17} color={colors.white} /> : job?.status === "FAILED" ? <RefreshCw size={17} color={colors.white} /> : <Sparkles size={17} color={colors.white} />}<Text style={styles.generateText}>{busy ? "正在生成" : job?.status === "FAILED" ? "重新生成" : "开始试穿"}</Text></Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background }, loading: { flex: 1, alignItems: "center", justifyContent: "center", gap: 12, backgroundColor: colors.background }, loadingText: { color: colors.muted, fontSize: 12 }, header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, paddingVertical: 13, borderBottomWidth: 1, borderBottomColor: colors.line, backgroundColor: colors.surface }, back: { width: 38, height: 38, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.line, borderRadius: radius.pill }, eyebrow: { color: colors.primary, fontFamily: type.mono, fontSize: 8, fontWeight: "800", letterSpacing: 1 }, headerTitle: { marginTop: 3, color: colors.ink, fontFamily: type.serif, fontSize: 22 }, content: { padding: 16, paddingBottom: 38 }, intro: { flexDirection: "row", gap: 10, alignItems: "flex-start", padding: 15, borderWidth: 1, borderColor: colors.line, borderRadius: radius.lg, backgroundColor: colors.surface }, introTitle: { color: colors.ink, fontSize: 14, fontWeight: "800" }, introText: { marginTop: 5, color: colors.muted, fontSize: 11, lineHeight: 16 }, guide: { flexDirection: "row", gap: 8, alignItems: "flex-start", marginTop: 12, padding: 13, borderRadius: radius.md, backgroundColor: colors.primaryPale }, guideText: { flex: 1, color: colors.primaryDark, fontSize: 11, lineHeight: 16 }, stage: { flexDirection: "row", gap: 10, minHeight: 250, marginTop: 14 }, photoSlot: { flex: 1, alignItems: "center", justifyContent: "center", overflow: "hidden", borderWidth: 1, borderStyle: "dashed", borderColor: "#BBAEC0", borderRadius: radius.lg, backgroundColor: colors.surface }, resultSlot: { flex: 1, overflow: "hidden", borderRadius: radius.lg, backgroundColor: colors.surfaceSoft }, stageImage: { width: "100%", height: "100%" }, slotTitle: { marginTop: 9, color: colors.primary, fontSize: 11, fontWeight: "800" }, slotText: { marginTop: 4, color: colors.muted, fontSize: 8 }, statusSlot: { flex: 1, alignItems: "flex-start", justifyContent: "center", gap: 9, padding: 16, borderRadius: radius.lg, backgroundColor: "#F1EDF3" }, statusTitle: { color: colors.ink, fontSize: 13, fontWeight: "800" }, statusText: { color: colors.muted, fontSize: 10, lineHeight: 15 }, successBadge: { position: "absolute", right: 8, bottom: 8, flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 8, paddingVertical: 5, borderRadius: radius.sm, backgroundColor: "rgba(25,23,22,.72)" }, successText: { color: colors.white, fontSize: 9, fontWeight: "700" }, warning: { marginTop: 8, color: "#806343", fontSize: 10, lineHeight: 14 }, consent: { flexDirection: "row", alignItems: "flex-start", gap: 8, marginTop: 17 }, checkbox: { width: 17, height: 17, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "#AAA1AF", borderRadius: 4, backgroundColor: colors.white }, checkboxChecked: { borderColor: colors.primary, backgroundColor: colors.primary }, consentText: { flex: 1, color: colors.muted, fontSize: 10, lineHeight: 15 }, error: { marginTop: 10, color: colors.error, fontSize: 11 }, generate: { height: 47, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, marginTop: 18, borderRadius: radius.md, backgroundColor: colors.primary }, generateDisabled: { opacity: 0.48 }, generateText: { color: colors.white, fontSize: 13, fontWeight: "800" },
});
