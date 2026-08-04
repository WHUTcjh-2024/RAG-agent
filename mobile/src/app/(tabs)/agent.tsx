import { useEffect, useMemo, useRef, useState } from "react";
import * as Crypto from "expo-crypto";
import * as Haptics from "expo-haptics";
import * as ImagePicker from "expo-image-picker";
import { Image } from "expo-image";
import { useLocalSearchParams, useRouter } from "expo-router";
import { ArrowLeft, ArrowRight, Check, Circle, Database, ImagePlus, Link2, LoaderCircle, Search, ShieldCheck, Sparkles, Square, Wrench } from "lucide-react-native";
import { Alert, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { cancelAgentTask, confirmAgentCartAction, productImage, streamChat } from "@/api/client";
import { useAppStore } from "@/store/use-app-store";
import { colors, radius, type } from "@/theme/tokens";
import type { AgentPhase, PickedImage } from "@/types";

const phaseOrder: AgentPhase[] = ["understanding", "constraints", "retrieval", "knowledge", "tool", "comparison", "verification", "generation"];
const phaseIcons: Record<string, React.ReactNode> = { understanding: <Sparkles size={14} />, constraints: <Circle size={13} />, retrieval: <Search size={14} />, knowledge: <Database size={14} />, tool: <Wrench size={14} />, comparison: <Circle size={13} />, verification: <ShieldCheck size={14} />, generation: <LoaderCircle size={14} /> };

export default function AgentScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ prompt?: string }>();
  const [pane, setPane] = useState<"dialogue" | "execution" | "evidence">("dialogue");
  const [value, setValue] = useState(params.prompt || "");
  const [pickedImage, setPickedImage] = useState<PickedImage | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const taskIdRef = useRef("");
  const scrollRef = useRef<ScrollView>(null);

  const store = useAppStore();
  const completed = useMemo(() => new Set(store.agentEvents.filter((event) => event.state === "completed").map((event) => event.phase)), [store.agentEvents]);
  const latestAnswer = [...store.messages].reverse().find((message) => message.role === "assistant" && message.content);
  const labels: Record<string, string> = store.language === "zh" ? { understanding: "理解需求", constraints: "提取约束", retrieval: "检索商品", knowledge: "查询知识库", tool: "调用工具", comparison: "比较参数", verification: "验证依据", generation: "生成建议", waiting: "等待确认", success: "执行成功", failure: "执行失败", cancelled: "已取消", retrying: "正在重试", idle: "等待任务" } : { understanding: "Understanding", constraints: "Constraints", retrieval: "Retrieval", knowledge: "Knowledge", tool: "Tools", comparison: "Comparing", verification: "Evidence", generation: "Generating", waiting: "Waiting", success: "Complete", failure: "Failed", cancelled: "Cancelled", retrying: "Retrying", idle: "Ready" };

  useEffect(() => { setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 40); }, [store.messages]);

  const chooseImage = async () => {
    const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.82, allowsEditing: false });
    if (result.canceled) return;
    const asset = result.assets[0];
    setPickedImage({ uri: asset.uri, name: asset.fileName || `fitme-${Date.now()}.jpg`, mimeType: asset.mimeType || "image/jpeg" });
  };

  const submit = async () => {
    const text = value.trim();
    if ((!text && !pickedImage) || streaming) return;
    await Haptics.selectionAsync();
    const request = text || "请推荐与图片相似的商品";
    store.addMessage({ id: Crypto.randomUUID(), role: "user", content: request, imagePreview: pickedImage?.uri });
    store.resetExecution();
    store.setAgentState("understanding");
    setValue(""); setError(""); setStreaming(true);
    const image = pickedImage; setPickedImage(null);
    abortRef.current = new AbortController();
    let semanticBuffer = "";
    let timer: ReturnType<typeof setTimeout> | undefined;
    const flush = () => { if (semanticBuffer) { store.appendAssistant(semanticBuffer); semanticBuffer = ""; } if (timer) clearTimeout(timer); timer = undefined; };
    const enqueue = (delta: string) => { semanticBuffer += delta; if (semanticBuffer.length >= 36 || /[。！？.!?]\s*$/.test(semanticBuffer)) flush(); else if (!timer) timer = setTimeout(flush, 70); };

    try {
      await streamChat(request, store.sessionId, image, store.language, {
        onTaskId: (id) => { taskIdRef.current = id; },
        onNode: store.addAgentEvent,
        onMeta: store.setSlots,
        onTool: store.addTrace,
        onProducts: (items) => { store.setAgentProducts(items); store.setAgentState("retrieval"); },
        onComparison: () => store.setAgentState("comparison"),
        onEvidence: store.addEvidence,
        onDecision: store.setDecision,
        onConfirm: (action) => { store.setPendingAction(action); store.setAgentState("waiting"); },
        onWardrobePlan: store.setWardrobePlan,
        onMessage: (delta) => { store.setAgentState("generation"); enqueue(delta); },
        onDone: () => { flush(); store.setAgentState("success"); },
        onError: setError,
      }, store.accessToken, abortRef.current.signal);
      flush();
    } catch (reason) {
      flush();
      if (reason instanceof Error && reason.name === "AbortError") store.setAgentState("cancelled");
      else { setError(reason instanceof Error ? reason.message : "Agent 执行失败"); store.setAgentState("failure"); }
    } finally {
      if (timer) clearTimeout(timer);
      flush(); setStreaming(false); abortRef.current = null; taskIdRef.current = "";
    }
  };

  const cancel = () => {
    abortRef.current?.abort();
    store.setAgentState("cancelled");
    if (taskIdRef.current) void cancelAgentTask(store.accessToken, taskIdRef.current, store.sessionId).catch(() => undefined);
  };

  const confirm = async () => {
    if (!store.pendingAction || !store.accessToken) { router.push("/auth"); return; }
    try { await confirmAgentCartAction(store.accessToken, store.pendingAction); await store.refreshCart(); store.setPendingAction(null); store.setAgentState("success"); Alert.alert("任务完成", "商品已加入购物袋"); }
    catch (reason) { Alert.alert("执行失败", reason instanceof Error ? reason.message : "请稍后重试"); }
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <View style={styles.header}><Pressable accessibilityLabel="返回首页" onPress={() => router.push("/")} style={styles.back}><ArrowLeft size={19} color={colors.ink} /></Pressable><View style={styles.agentIdentity}><View style={styles.avatar}><Sparkles size={15} color={colors.primary} /></View><View><Text style={styles.online}>● 在线</Text><Text style={styles.agentName}>FitMe Agent</Text></View></View><View style={styles.liveState}><View style={[styles.liveDot, store.agentState === "success" && styles.successDot, store.agentState === "failure" && styles.errorDot]} /><Text numberOfLines={1}>{labels[store.agentState]}</Text></View></View>
      <View style={styles.tabs}>{(["execution", "dialogue", "evidence"] as const).map((item) => <Pressable key={item} onPress={() => setPane(item)} style={[styles.tab, pane === item && styles.tabActive]}>{item === "execution" ? <Wrench size={13} color={pane === item ? colors.primary : colors.muted} /> : item === "dialogue" ? <Sparkles size={13} color={pane === item ? colors.primary : colors.muted} /> : <Link2 size={13} color={pane === item ? colors.primary : colors.muted} />}<Text style={[styles.tabText, pane === item && styles.tabTextActive]}>{item === "execution" ? "执行" : item === "dialogue" ? "对话" : "依据"}</Text></Pressable>)}</View>

      {pane === "dialogue" && <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === "ios" ? "padding" : "height"} keyboardVerticalOffset={Platform.OS === "android" ? 8 : 0}>
        <ScrollView ref={scrollRef} style={styles.flex} contentContainerStyle={styles.messages} keyboardShouldPersistTaps="handled">
          {!store.messages.length && <View style={styles.intro}><Text style={styles.introEyebrow}>AI STYLIST WORKSPACE</Text><Text style={styles.introTitle}>今天为什么穿搭？</Text><Text style={styles.introBody}>描述场景、天气、预算或偏好，Agent 会逐步检索与验证。</Text>{["适合夏天通勤的白色衬衫", "预算 500 元的周末约会穿搭", "分析图片并寻找相似款"].map((prompt, index) => <Pressable key={prompt} onPress={() => setValue(prompt)} style={styles.prompt}><Text>0{index + 1}</Text><Text>{prompt}</Text><ArrowRight size={14} color={colors.muted} /></Pressable>)}</View>}
          {store.messages.map((message) => <View key={message.id} style={[styles.message, message.role === "user" && styles.userMessage]}><Text style={styles.messageRole}>{message.role === "user" ? "YOU" : "FITME AGENT"}</Text><View style={[styles.bubble, message.role === "user" && styles.userBubble]}>{message.imagePreview && <Image source={{ uri: message.imagePreview }} style={styles.messageImage} contentFit="cover" />}<Text style={[styles.messageText, message.role === "user" && styles.userText]}>{message.content}</Text>{streaming && message.role === "assistant" && message === store.messages.at(-1) && <Text style={styles.caret}>▋</Text>}</View></View>)}
        </ScrollView>
        {error && <View style={styles.error}><Text>{error}</Text></View>}
        {pickedImage && <View style={styles.preview}><Image source={{ uri: pickedImage.uri }} style={styles.previewImage} /><Text numberOfLines={1}>{pickedImage.name}</Text><Pressable onPress={() => setPickedImage(null)}><Text>移除</Text></Pressable></View>}
        <View style={styles.composer}><Pressable accessibilityLabel="选择图片" onPress={() => void chooseImage()} style={styles.imageButton}><ImagePlus size={20} color={colors.primary} /></Pressable><TextInput accessibilityLabel="导购需求" value={value} onChangeText={setValue} placeholder="描述你的穿搭问题…" placeholderTextColor="#9D9691" multiline style={styles.composerInput} onSubmitEditing={() => void submit()} /><Pressable accessibilityLabel={streaming ? "停止生成" : "发送"} onPress={streaming ? cancel : () => void submit()} disabled={!streaming && !value.trim() && !pickedImage} style={[styles.send, !streaming && !value.trim() && !pickedImage && styles.disabled]}>{streaming ? <Square size={15} color={colors.white} fill={colors.white} /> : <ArrowRight size={18} color={colors.white} />}</Pressable></View>
      </KeyboardAvoidingView>}

      {pane === "execution" && <ScrollView contentContainerStyle={styles.panel}><Text style={styles.panelIndex}>01 / EXECUTION</Text><Text style={styles.panelTitle}>真实执行轨迹</Text><Text style={styles.panelIntro}>只展示后端真实事件，不使用虚假进度。</Text><View style={styles.phaseRail}>{phaseOrder.map((phase) => { const event = [...store.agentEvents].reverse().find((item) => item.phase === phase); const active = store.agentState === phase; const done = completed.has(phase); return <View key={phase} style={[styles.phase, active && styles.phaseActive]}><View style={[styles.phaseIcon, done && styles.phaseDone]}>{done ? <Check size={13} color={colors.white} /> : phaseIcons[phase]}</View><View style={styles.phaseCopy}><Text style={styles.phaseTitle}>{labels[phase]}</Text>{event?.summary && <Text style={styles.phaseSummary} numberOfLines={2}>{event.summary}</Text>}</View><Text style={styles.duration}>{event?.durationMs !== undefined ? `${event.durationMs.toFixed(1)}ms` : "—"}</Text></View>; })}</View>{store.traces.map((trace, index) => <View key={`${trace.tool}-${index}`} style={styles.trace}><Wrench size={14} color={colors.primary} /><View style={styles.traceCopy}><Text style={styles.traceTitle}>{trace.tool}</Text><Text style={styles.traceSummary}>{trace.summary}</Text></View></View>)}</ScrollView>}

      {pane === "evidence" && <ScrollView contentContainerStyle={styles.panel}><Text style={styles.panelIndex}>03 / EVIDENCE</Text><Text style={styles.panelTitle}>约束与推荐依据</Text><View style={styles.slotCloud}>{Object.entries(store.slots).map(([key, item]) => <View key={key} style={styles.slot}><Text style={styles.slotKey}>{key.toUpperCase()}</Text><Text style={styles.slotValue}>{Array.isArray(item) ? item.join(" · ") : String(item)}</Text></View>)}</View>{store.agentProducts.length > 0 && <View style={styles.candidates}><Text style={styles.blockTitle}>候选商品 {store.agentProducts.length}</Text>{store.agentProducts.slice(0, 4).map((product) => <Pressable key={product.article_id} onPress={() => router.push(`/product/${product.article_id}`)} style={styles.candidate}><Image source={{ uri: productImage(product) }} style={styles.candidateImage} /><View style={styles.candidateCopy}><Text style={styles.candidateTitle} numberOfLines={1}>{product.prod_name}</Text><Text style={styles.candidateBody} numberOfLines={2}>{product.reason || `${product.product_type_name} · ${product.colour_group_name}`}</Text></View><ArrowRight size={14} color={colors.muted} /></Pressable>)}</View>}{(latestAnswer || store.evidence.length > 0) && <View style={styles.evidenceBlock}><Text style={styles.blockTitle}>推荐依据</Text>{latestAnswer && <View style={styles.linkedConclusion}><Text style={styles.conclusionLabel}>关联结论</Text><Text style={styles.conclusionText}>{latestAnswer.content}</Text></View>}{store.evidence.map((item, index) => <View key={`${item.source_id}-${item.field}-${index}`} style={styles.evidenceItem}><View style={styles.evidenceMeta}><Text style={styles.evidenceField}>{item.field}</Text><Text style={styles.evidenceType}>{item.source_type}</Text></View><Text style={styles.evidenceValue}>{item.value}</Text><Text style={styles.evidenceSource}>{item.source_id}</Text></View>)}</View>}{store.decision && <View style={styles.decision}><Text>{store.decision.verdict.replaceAll("_", " ")}</Text><Text>{Math.round(store.decision.confidence * 100)}%</Text>{store.decision.reasons.map((reason) => <Text key={reason}>{reason}</Text>)}</View>}{store.pendingAction && <View style={styles.confirm}><Text>等待你的确认</Text><Text>{store.pendingAction.summary}</Text><Pressable onPress={() => void confirm()}><Text>确认执行</Text></Pressable></View>}</ScrollView>}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background }, flex: { flex: 1 }, header: { minHeight: 72, paddingHorizontal: 14, flexDirection: "row", gap: 9, alignItems: "center", borderBottomWidth: 1, borderBottomColor: colors.line, backgroundColor: colors.surface }, back: { width: 38, height: 38, alignItems: "center", justifyContent: "center", borderRadius: 19, backgroundColor: colors.surfaceSoft }, agentIdentity: { flex: 1, flexDirection: "row", gap: 9, alignItems: "center" }, avatar: { width: 36, height: 36, alignItems: "center", justifyContent: "center", borderRadius: 18, backgroundColor: colors.primarySoft }, online: { color: colors.success, fontFamily: type.mono, fontSize: 7 }, agentName: { marginTop: 3, color: colors.ink, fontSize: 13, fontWeight: "800" }, liveState: { maxWidth: 122, flexDirection: "row", gap: 5, alignItems: "center" }, liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.primary }, successDot: { backgroundColor: colors.success }, errorDot: { backgroundColor: colors.error },
  tabs: { height: 44, padding: 5, flexDirection: "row", gap: 5, borderBottomWidth: 1, borderBottomColor: colors.line, backgroundColor: colors.surface }, tab: { flex: 1, flexDirection: "row", gap: 6, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "transparent", borderRadius: radius.md }, tabActive: { borderColor: "#D9CCDF", backgroundColor: colors.primaryPale }, tabText: { color: colors.muted, fontSize: 10 }, tabTextActive: { color: colors.primary, fontWeight: "700" },
  messages: { padding: 16, paddingBottom: 22 }, intro: { paddingTop: 10 }, introEyebrow: { color: colors.primary, fontFamily: type.mono, fontSize: 8, fontWeight: "800", letterSpacing: 1 }, introTitle: { marginTop: 9, color: colors.ink, fontFamily: type.serif, fontSize: 28 }, introBody: { marginTop: 8, marginBottom: 17, color: colors.muted, fontSize: 11, lineHeight: 18 }, prompt: { minHeight: 50, paddingVertical: 8, flexDirection: "row", gap: 10, alignItems: "center", borderTopWidth: 1, borderTopColor: colors.line },
  message: { marginBottom: 16, alignItems: "flex-start" }, userMessage: { alignItems: "flex-end" }, messageRole: { marginBottom: 5, color: colors.muted, fontFamily: type.mono, fontSize: 7, fontWeight: "700" }, bubble: { maxWidth: "88%", padding: 12, borderRadius: 5, borderTopRightRadius: radius.lg, borderBottomRightRadius: radius.lg, borderBottomLeftRadius: radius.lg, backgroundColor: colors.surface }, userBubble: { borderTopRightRadius: 5, borderTopLeftRadius: radius.lg, backgroundColor: colors.primary }, messageText: { color: colors.ink, fontSize: 13, lineHeight: 20 }, userText: { color: colors.white }, messageImage: { width: 180, height: 150, marginBottom: 9, borderRadius: radius.md }, caret: { color: colors.primary }, error: { marginHorizontal: 16, padding: 9, borderRadius: radius.sm, backgroundColor: colors.errorSoft }, preview: { marginHorizontal: 12, padding: 8, flexDirection: "row", gap: 9, alignItems: "center", borderRadius: radius.md, backgroundColor: colors.surface }, previewImage: { width: 45, height: 45, borderRadius: radius.sm }, composer: { minHeight: 66, paddingHorizontal: 12, paddingVertical: 9, flexDirection: "row", gap: 7, alignItems: "flex-end", borderTopWidth: 1, borderTopColor: colors.line, backgroundColor: colors.surface }, imageButton: { width: 42, height: 42, alignItems: "center", justifyContent: "center", borderRadius: 21, backgroundColor: colors.primaryPale }, composerInput: { flex: 1, maxHeight: 96, minHeight: 42, paddingHorizontal: 12, paddingVertical: 10, borderRadius: radius.md, color: colors.ink, backgroundColor: colors.surfaceSoft, fontSize: 12 }, send: { width: 42, height: 42, alignItems: "center", justifyContent: "center", borderRadius: 21, backgroundColor: colors.primary }, disabled: { opacity: 0.38 },
  panel: { padding: 17, paddingBottom: 110 }, panelIndex: { color: colors.primary, fontFamily: type.mono, fontSize: 8, fontWeight: "800", letterSpacing: 1 }, panelTitle: { marginTop: 7, color: colors.ink, fontFamily: type.serif, fontSize: 25 }, panelIntro: { marginTop: 8, marginBottom: 17, color: colors.muted, fontSize: 10 }, phaseRail: { padding: 7, borderWidth: 1, borderColor: colors.line, borderRadius: radius.lg, backgroundColor: colors.surface }, phase: { minHeight: 56, padding: 7, flexDirection: "row", gap: 10, alignItems: "center", borderRadius: radius.md }, phaseActive: { backgroundColor: colors.primaryPale }, phaseIcon: { width: 31, height: 31, alignItems: "center", justifyContent: "center", borderRadius: 16, color: colors.muted, backgroundColor: colors.surfaceSoft }, phaseDone: { backgroundColor: colors.success }, phaseCopy: { flex: 1 }, phaseTitle: { color: colors.ink, fontSize: 12, fontWeight: "700" }, phaseSummary: { marginTop: 2, color: colors.muted, fontSize: 9 }, duration: { color: colors.muted, fontFamily: type.mono, fontSize: 8 }, trace: { marginTop: 7, padding: 11, flexDirection: "row", gap: 9, alignItems: "center", borderRadius: radius.md, backgroundColor: colors.surface }, traceCopy: { flex: 1 }, traceTitle: { color: colors.ink, fontSize: 11, fontWeight: "700" }, traceSummary: { marginTop: 2, color: colors.muted, fontSize: 9 },
  slotCloud: { marginTop: 15, flexDirection: "row", flexWrap: "wrap", gap: 6 }, slot: { minWidth: 76, paddingHorizontal: 10, paddingVertical: 8, borderWidth: 1, borderColor: colors.line, borderRadius: radius.md, backgroundColor: colors.surface }, slotKey: { color: colors.muted, fontFamily: type.mono, fontSize: 6, fontWeight: "800", letterSpacing: 0.7 }, slotValue: { marginTop: 3, color: colors.ink, fontSize: 10, fontWeight: "700" }, candidates: { marginTop: 20 }, blockTitle: { marginBottom: 10, color: colors.ink, fontSize: 13, fontWeight: "800" }, candidate: { marginBottom: 6, padding: 6, flexDirection: "row", gap: 10, alignItems: "center", borderRadius: radius.md, backgroundColor: colors.surface }, candidateImage: { width: 54, height: 61, borderRadius: radius.sm }, candidateCopy: { flex: 1 }, candidateTitle: { color: colors.ink, fontSize: 11, fontWeight: "800" }, candidateBody: { marginTop: 3, color: colors.muted, fontSize: 9, lineHeight: 13 }, evidenceBlock: { marginTop: 20 }, linkedConclusion: { marginBottom: 8, padding: 12, borderWidth: 1, borderColor: "#DED3E4", borderRadius: radius.md, backgroundColor: colors.primaryPale }, conclusionLabel: { color: colors.primary, fontFamily: type.mono, fontSize: 7, fontWeight: "800", letterSpacing: 0.8 }, conclusionText: { marginTop: 7, color: colors.ink, fontSize: 11, lineHeight: 18 }, evidenceItem: { paddingVertical: 10, borderTopWidth: 1, borderTopColor: colors.line }, evidenceMeta: { flexDirection: "row", justifyContent: "space-between" }, evidenceField: { color: colors.ink, fontSize: 10, fontWeight: "800" }, evidenceType: { color: colors.primary, fontFamily: type.mono, fontSize: 7 }, evidenceValue: { marginTop: 5, color: colors.ink, fontSize: 10, lineHeight: 15 }, evidenceSource: { marginTop: 3, color: colors.muted, fontFamily: type.mono, fontSize: 7 }, decision: { marginTop: 13, padding: 13, borderRadius: radius.md, backgroundColor: colors.successSoft }, confirm: { marginTop: 13, padding: 14, borderRadius: radius.lg, backgroundColor: colors.surface },
});
