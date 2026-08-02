import { useEffect, useMemo, useState } from "react";
import { LinearGradient } from "expo-linear-gradient";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { ArrowRight, Check, ChevronRight, Circle, Sparkles } from "lucide-react-native";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { fetchProducts, productImage } from "@/api/client";
import { AppHeader } from "@/components/ui/app-header";
import { Screen } from "@/components/ui/screen";
import { SectionHeader } from "@/components/ui/section-header";
import { useAppStore } from "@/store/use-app-store";
import { colors, radius, shadow, type } from "@/theme/tokens";
import type { Product } from "@/types";

const phases = ["understanding", "constraints", "retrieval", "verification", "generation"] as const;

export default function HomeScreen() {
  const router = useRouter();
  const [products, setProducts] = useState<Product[]>([]);
  const user = useAppStore((state) => state.user);
  const wardrobe = useAppStore((state) => state.wardrobe);
  const agentState = useAppStore((state) => state.agentState);
  const events = useAppStore((state) => state.agentEvents);
  const language = useAppStore((state) => state.language);

  useEffect(() => { void fetchProducts({ page: 1, pageSize: 6, category: "Dress", sort: "popular" }).then((page) => setProducts(page.items)).catch(() => undefined); }, []);
  const completed = useMemo(() => new Set(events.filter((event) => event.state === "completed").map((event) => event.phase)), [events]);
  const labels = language === "zh" ? ["理解你的需求", "提取预算与场景", "检索真实商品", "验证推荐依据", "生成最终方案"] : ["Understand request", "Extract constraints", "Retrieve products", "Verify evidence", "Build final plan"];

  return (
    <Screen header={<AppHeader home />} contentStyle={styles.content}>
      <View style={styles.greeting}><Text style={styles.greetingName}>{language === "zh" ? `你好，${user?.displayName || "Kinoko"} 👋` : `Hello, ${user?.displayName || "Kinoko"} 👋`}</Text><Text style={styles.greetingQuestion}>{language === "zh" ? "今天想为什么穿搭？" : "What are you dressing for today?"}</Text></View>

      <LinearGradient colors={["#776B7B", "#4B424D"]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.agentCard}>
        <View style={styles.agentCopy}><Text style={styles.agentEyebrow}><Sparkles size={13} color="#E7DCEB" /> FITME AGENT</Text><Text style={styles.agentTitle}>{language === "zh" ? "把场景、预算和衣橱，交给真正会执行的穿搭 Agent。" : "A stylist Agent that understands context and takes action."}</Text><Text style={styles.agentBody}>{language === "zh" ? "实时检索、比较与验证，每一步都有真实事件和来源。" : "Live retrieval, comparison and evidence—grounded in real events."}</Text></View>
        <Pressable testID="open-agent" onPress={() => router.push("/agent")} style={({ pressed }) => [styles.agentButton, pressed && styles.pressed]}><Text>{language === "zh" ? "交给 FitMe Agent" : "Open FitMe Agent"}</Text><ArrowRight size={16} color={colors.primaryDark} /></Pressable>
        <View style={styles.orbOne} /><View style={styles.orbTwo} />
      </LinearGradient>

      <View style={styles.taskCard}>
        <View style={styles.taskHeader}><View><Text style={styles.cardEyebrow}>LIVE EXECUTION</Text><Text style={styles.cardTitle}>{agentState === "idle" ? (language === "zh" ? "Agent 等待你的任务" : "Agent is ready") : (language === "zh" ? "Agent 正在为你规划" : "Agent is working")}</Text></View><Pressable onPress={() => router.push("/agent")} style={styles.roundButton}><ChevronRight size={18} color={colors.ink} /></Pressable></View>
        <View style={styles.steps}>
          {phases.map((phase, index) => { const done = completed.has(phase); const active = agentState === phase; return <View key={phase} style={styles.step}><View style={[styles.stepIcon, done && styles.doneIcon, active && styles.activeIcon]}>{done ? <Check size={13} color={colors.white} /> : active ? <Sparkles size={12} color={colors.primary} /> : <Circle size={10} color="#AAA4A0" />}</View><Text style={[styles.stepLabel, (done || active) && styles.stepLabelActive]}>{labels[index]}</Text><Text style={styles.stepMeta}>{events.findLast((event) => event.phase === phase)?.summary || (done ? "DONE" : "—")}</Text></View>; })}
        </View>
        <Text style={styles.integrity}>{events.length ? `${events.length} ${language === "zh" ? "条真实工作流事件" : "verified workflow events"}` : (language === "zh" ? "状态由后端事件实时驱动" : "Driven by real backend events")}</Text>
      </View>

      <View style={styles.section}><SectionHeader index="01 / WARDROBE" title={language === "zh" ? "你的衣橱" : "Your wardrobe"} action={language === "zh" ? "查看全部" : "View all"} onAction={() => router.push("/wardrobe")} />
        <View style={styles.previewGrid}>{products.slice(0, 4).map((product) => <Pressable key={product.article_id} onPress={() => router.push(`/product/${product.article_id}`)} style={styles.preview}><Image source={{ uri: productImage(product) }} style={styles.previewImage} contentFit="cover" transition={180} /><Text style={styles.previewTitle} numberOfLines={1}>{product.prod_name}</Text></Pressable>)}</View>
        <View style={styles.metrics}>{[[wardrobe?.items.length || 0, language === "zh" ? "衣橱单品" : "ITEMS"], [wardrobe?.version || 0, language === "zh" ? "衣橱版本" : "VERSION"], [events.length, language === "zh" ? "规划步骤" : "STEPS"]].map(([value, label], index) => <View key={String(label)} style={[styles.metric, index > 0 && styles.metricBorder]}><Text style={styles.metricValue}>{value}</Text><Text style={styles.metricLabel}>{label}</Text></View>)}</View>
      </View>

      <View style={styles.section}><SectionHeader index="02 / DISCOVER" title={language === "zh" ? "为你推荐" : "Recommended"} action={language === "zh" ? "更多" : "More"} onAction={() => router.push("/discover")} />
        {products.slice(0, 3).map((product) => <Pressable key={product.article_id} onPress={() => router.push(`/product/${product.article_id}`)} style={styles.recommendation}><Image source={{ uri: productImage(product) }} style={styles.recommendationImage} contentFit="cover" /><View style={styles.recommendationCopy}><Text style={styles.recommendationTitle} numberOfLines={1}>{product.prod_name}</Text><Text style={styles.recommendationBody} numberOfLines={2}>{product.detail_desc || `${product.product_type_name} · ${product.colour_group_name}`}</Text></View><ChevronRight size={16} color={colors.muted} /></Pressable>)}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: 14 }, greeting: { paddingVertical: 3 }, greetingName: { color: colors.ink, fontSize: 15, fontWeight: "700" }, greetingQuestion: { marginTop: 4, color: colors.ink, fontFamily: type.serif, fontSize: 21 },
  agentCard: { position: "relative", minHeight: 220, padding: 21, overflow: "hidden", borderRadius: radius.xl, ...shadow }, agentCopy: { zIndex: 2, maxWidth: "88%" }, agentEyebrow: { color: "rgba(255,255,255,.72)", fontFamily: type.mono, fontSize: 9, fontWeight: "800", letterSpacing: 1 }, agentTitle: { marginTop: 14, color: colors.white, fontFamily: type.serif, fontSize: 25, lineHeight: 31, letterSpacing: -0.8 }, agentBody: { marginTop: 8, color: "rgba(255,255,255,.62)", fontSize: 11, lineHeight: 18 }, agentButton: { zIndex: 3, alignSelf: "flex-start", height: 44, marginTop: 17, paddingHorizontal: 15, flexDirection: "row", gap: 9, alignItems: "center", borderRadius: 22, backgroundColor: colors.white }, pressed: { transform: [{ scale: 0.96 }] }, orbOne: { position: "absolute", right: -60, bottom: -95, width: 220, height: 220, borderRadius: 110, backgroundColor: "rgba(255,255,255,.07)" }, orbTwo: { position: "absolute", right: 100, bottom: -100, width: 145, height: 145, borderRadius: 80, backgroundColor: "rgba(255,255,255,.05)" },
  taskCard: { padding: 18, borderWidth: 1, borderColor: colors.line, borderRadius: radius.xl, backgroundColor: colors.surface }, taskHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, cardEyebrow: { color: colors.muted, fontFamily: type.mono, fontSize: 8, fontWeight: "800", letterSpacing: 1 }, cardTitle: { marginTop: 6, color: colors.ink, fontSize: 16, fontWeight: "700" }, roundButton: { width: 34, height: 34, alignItems: "center", justifyContent: "center", borderRadius: 17, backgroundColor: colors.surfaceSoft }, steps: { marginTop: 14 }, step: { minHeight: 45, flexDirection: "row", gap: 9, alignItems: "center" }, stepIcon: { width: 29, height: 29, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.line, borderRadius: 15, backgroundColor: colors.surface }, doneIcon: { borderColor: colors.success, backgroundColor: colors.success }, activeIcon: { borderColor: "#BAAAC5", backgroundColor: colors.primaryPale }, stepLabel: { flex: 1, color: "#8A8480", fontSize: 11 }, stepLabelActive: { color: colors.ink, fontWeight: "600" }, stepMeta: { maxWidth: 108, color: "#AAA4A0", fontFamily: type.mono, fontSize: 7 }, integrity: { marginTop: 8, paddingTop: 12, borderTopWidth: 1, borderTopColor: colors.line, color: colors.success, fontSize: 9 },
  section: { paddingTop: 9 }, previewGrid: { flexDirection: "row", gap: 7 }, preview: { flex: 1 }, previewImage: { width: "100%", aspectRatio: 0.76, borderRadius: radius.md, backgroundColor: colors.surfaceSoft }, previewTitle: { marginTop: 5, color: colors.ink, fontSize: 8 }, metrics: { marginTop: 9, paddingVertical: 14, flexDirection: "row", borderWidth: 1, borderColor: colors.line, borderRadius: radius.lg, backgroundColor: colors.surface }, metric: { flex: 1, alignItems: "center" }, metricBorder: { borderLeftWidth: 1, borderLeftColor: colors.line }, metricValue: { color: colors.ink, fontSize: 17, fontWeight: "800" }, metricLabel: { marginTop: 3, color: colors.muted, fontSize: 8 }, recommendation: { marginBottom: 7, padding: 7, flexDirection: "row", gap: 11, alignItems: "center", borderWidth: 1, borderColor: colors.line, borderRadius: radius.md, backgroundColor: colors.surface }, recommendationImage: { width: 55, height: 62, borderRadius: radius.sm }, recommendationCopy: { flex: 1 }, recommendationTitle: { color: colors.ink, fontSize: 11, fontWeight: "800" }, recommendationBody: { marginTop: 4, color: colors.muted, fontSize: 9, lineHeight: 14 },
});
