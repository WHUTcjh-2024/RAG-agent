import { useRouter } from "expo-router";
import { BriefcaseBusiness, ChevronRight, CircleUserRound, GitCompareArrows, Languages, LogOut, ShieldCheck, ShoppingBag } from "lucide-react-native";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { AppHeader } from "@/components/ui/app-header";
import { Screen } from "@/components/ui/screen";
import { useAppStore } from "@/store/use-app-store";
import { colors, radius, type } from "@/theme/tokens";

export default function ProfileScreen() {
  const router = useRouter();
  const user = useAppStore((state) => state.user);
  const cart = useAppStore((state) => state.cart);
  const wardrobe = useAppStore((state) => state.wardrobe);
  const compareIds = useAppStore((state) => state.compareIds);
  const language = useAppStore((state) => state.language);
  const setLanguage = useAppStore((state) => state.setLanguage);
  const logout = useAppStore((state) => state.logout);

  return (
    <Screen header={<AppHeader eyebrow="PROFILE" title="我的 FitMe" />} contentStyle={styles.content}>
      <View style={styles.identity}><View style={styles.avatar}><CircleUserRound size={25} color={colors.primary} /></View><View style={styles.identityCopy}><Text style={styles.identityName}>{user?.displayName || "欢迎来到 FitMe"}</Text><Text style={styles.identityEmail} numberOfLines={1}>{user?.email || "登录以同步衣橱与购物袋"}</Text></View><Pressable onPress={() => user ? void logout() : router.push("/auth")} style={styles.authButton}>{user ? <LogOut size={14} color={colors.white} /> : null}<Text style={styles.authText}>{user ? "退出" : "登录"}</Text></Pressable></View>
      <View style={styles.metrics}>{[[<ShoppingBag key="cart" size={17} color={colors.primary} />, cart.length, "购物袋"], [<BriefcaseBusiness key="wardrobe" size={17} color={colors.primary} />, wardrobe?.items.length || 0, "衣橱"], [<GitCompareArrows key="compare" size={17} color={colors.primary} />, compareIds.length, "对比"]].map(([icon, value, label], index) => <View key={String(label)} style={[styles.metric, index > 0 && styles.metricBorder]}>{icon}<Text style={styles.metricValue}>{value}</Text><Text style={styles.metricLabel}>{label}</Text></View>)}</View>
      <View style={styles.list}><Text style={styles.listTitle}>APPLICATION</Text><Pressable style={styles.listRow} onPress={() => void setLanguage(language === "zh" ? "en" : "zh")}><View style={styles.listIdentity}><View style={styles.listIcon}><Languages size={18} color={colors.primary} /></View><Text style={styles.listLabel}>界面语言</Text></View><Text style={styles.listValue}>{language === "zh" ? "简体中文" : "English"}</Text><ChevronRight size={16} color={colors.muted} /></Pressable><Pressable style={[styles.listRow, styles.listRowBorder]}><View style={styles.listIdentity}><View style={styles.listIcon}><ShieldCheck size={18} color={colors.primary} /></View><Text style={styles.listLabel}>隐私与数据</Text></View><Text style={styles.listValue}>本地安全存储</Text><ChevronRight size={16} color={colors.muted} /></Pressable></View>
      <View style={styles.capabilities}><Text style={styles.capabilityEyebrow}>AGENT CAPABILITIES</Text><Text style={styles.capabilityTitle}>不是聊天机器人，而是可执行的穿搭工作区。</Text>{["理解需求与约束", "检索商品与知识库", "比较参数与验证依据", "规划衣橱并等待确认"].map((item, index) => <View key={item} style={styles.capabilityRow}><Text style={styles.capabilityIndex}>0{index + 1}</Text><Text style={styles.capabilityLabel}>{item}</Text></View>)}</View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: 13 }, identity: { padding: 17, flexDirection: "row", gap: 12, alignItems: "center", borderWidth: 1, borderColor: colors.line, borderRadius: radius.lg, backgroundColor: colors.surface }, avatar: { width: 48, height: 48, alignItems: "center", justifyContent: "center", borderRadius: 24, backgroundColor: colors.primaryPale }, identityCopy: { flex: 1 }, identityName: { color: colors.ink, fontSize: 15, fontWeight: "800" }, identityEmail: { marginTop: 4, color: colors.muted, fontSize: 10 }, authButton: { minHeight: 35, paddingHorizontal: 12, flexDirection: "row", gap: 5, alignItems: "center", borderRadius: 18, backgroundColor: colors.primary }, authText: { color: colors.white, fontSize: 10, fontWeight: "700" },
  metrics: { paddingVertical: 16, flexDirection: "row", borderWidth: 1, borderColor: colors.line, borderRadius: radius.lg, backgroundColor: colors.surface }, metric: { flex: 1, alignItems: "center", gap: 3 }, metricBorder: { borderLeftWidth: 1, borderLeftColor: colors.line }, metricValue: { marginTop: 3, color: colors.ink, fontSize: 18, fontWeight: "800" }, metricLabel: { color: colors.muted, fontSize: 9 }, list: { paddingHorizontal: 17, paddingTop: 15, borderWidth: 1, borderColor: colors.line, borderRadius: radius.lg, backgroundColor: colors.surface }, listTitle: { marginBottom: 7, color: colors.muted, fontFamily: type.mono, fontSize: 8, fontWeight: "800", letterSpacing: 1 }, listRow: { minHeight: 62, flexDirection: "row", alignItems: "center", gap: 8 }, listRowBorder: { borderTopWidth: 1, borderTopColor: colors.line }, listIdentity: { flex: 1, flexDirection: "row", alignItems: "center", gap: 10 }, listIcon: { width: 32, height: 32, alignItems: "center", justifyContent: "center", borderRadius: 16, backgroundColor: colors.primaryPale }, listLabel: { color: colors.ink, fontSize: 12, fontWeight: "700" }, listValue: { color: colors.muted, fontSize: 9 }, capabilities: { paddingTop: 9 }, capabilityEyebrow: { color: colors.primary, fontFamily: type.mono, fontSize: 8, fontWeight: "800", letterSpacing: 1 }, capabilityTitle: { marginTop: 9, marginBottom: 17, color: colors.ink, fontFamily: type.serif, fontSize: 24, lineHeight: 31 }, capabilityRow: { minHeight: 46, flexDirection: "row", alignItems: "center", borderTopWidth: 1, borderTopColor: colors.line }, capabilityIndex: { width: 42, color: colors.primary, fontFamily: type.mono, fontSize: 9 }, capabilityLabel: { color: colors.ink, fontSize: 12 },
});
