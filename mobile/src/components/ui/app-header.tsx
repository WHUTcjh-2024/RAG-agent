import { Bell, Languages, ShoppingBag } from "lucide-react-native";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { colors, radius, type } from "@/theme/tokens";
import { useAppStore } from "@/store/use-app-store";

export function AppHeader({ eyebrow, title, home = false }: { eyebrow?: string; title?: string; home?: boolean }) {
  const router = useRouter();
  const cartCount = useAppStore((state) => state.cart.reduce((total, item) => total + item.quantity, 0));
  const language = useAppStore((state) => state.language);
  const setLanguage = useAppStore((state) => state.setLanguage);
  return (
    <View style={styles.header}>
      <View style={styles.copy}>
        {home ? <Text style={styles.logo}>FitMe<Text style={styles.sparkle}> ✦</Text></Text> : <><Text style={styles.eyebrow}>{eyebrow}</Text><Text style={styles.title}>{title}</Text></>}
        {home && <Text style={styles.subtitle}>{language === "zh" ? "智能穿搭与衣橱助手" : "YOUR INTELLIGENT WARDROBE"}</Text>}
      </View>
      <View style={styles.actions}>
        <Pressable accessibilityLabel="Language" onPress={() => void setLanguage(language === "zh" ? "en" : "zh")} style={({ pressed }) => [styles.action, pressed && styles.pressed]}><Languages size={18} color={colors.ink} /></Pressable>
        <Pressable accessibilityLabel={language === "zh" ? "通知" : "Notifications"} style={({ pressed }) => [styles.action, pressed && styles.pressed]}><Bell size={18} color={colors.ink} /></Pressable>
        <Pressable accessibilityLabel={language === "zh" ? "购物袋" : "Shopping bag"} onPress={() => router.push("/cart")} style={({ pressed }) => [styles.action, pressed && styles.pressed]}>
          <ShoppingBag size={18} color={colors.ink} />{cartCount > 0 && <Text style={styles.badge}>{cartCount}</Text>}
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { minHeight: 78, paddingHorizontal: 16, paddingVertical: 12, flexDirection: "row", alignItems: "center", justifyContent: "space-between", backgroundColor: colors.background },
  copy: { flex: 1 }, logo: { color: colors.ink, fontSize: 28, fontFamily: type.sans, fontWeight: "800", letterSpacing: -1.5 }, sparkle: { color: colors.accent, fontSize: 15 },
  subtitle: { marginTop: 7, color: colors.muted, fontFamily: type.mono, fontSize: 9, letterSpacing: 0.8 },
  eyebrow: { color: colors.muted, fontFamily: type.mono, fontSize: 9, letterSpacing: 1.1 }, title: { marginTop: 5, color: colors.ink, fontSize: 23, fontWeight: "700", letterSpacing: -0.7 },
  actions: { flexDirection: "row", gap: 6 }, action: { width: 38, height: 38, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.line, borderRadius: radius.pill, backgroundColor: colors.surface }, pressed: { transform: [{ scale: 0.91 }], backgroundColor: colors.surfaceSoft },
  badge: { position: "absolute", top: -3, right: -2, minWidth: 16, height: 16, paddingHorizontal: 4, overflow: "hidden", borderRadius: 8, color: colors.white, backgroundColor: colors.primary, fontSize: 9, fontWeight: "800", lineHeight: 16, textAlign: "center" },
});
