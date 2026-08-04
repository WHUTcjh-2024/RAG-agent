import { ChevronRight } from "lucide-react-native";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { colors, type } from "@/theme/tokens";

export function SectionHeader({ index, title, action, onAction }: { index: string; title: string; action?: string; onAction?: () => void }) {
  return <View style={styles.root}><View><Text style={styles.index}>{index}</Text><Text style={styles.title}>{title}</Text></View>{action && <Pressable onPress={onAction} style={styles.action}><Text>{action}</Text><ChevronRight size={14} color={colors.muted} /></Pressable>}</View>;
}
const styles = StyleSheet.create({ root: { marginBottom: 12, flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between" }, index: { color: colors.primary, fontFamily: type.mono, fontSize: 8, fontWeight: "700", letterSpacing: 1.1 }, title: { marginTop: 5, color: colors.ink, fontSize: 17, fontWeight: "700" }, action: { flexDirection: "row", alignItems: "center", gap: 2 }, });
