import { useEffect, useState } from "react";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { ArrowLeft, X } from "lucide-react-native";
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { compareProducts, productImage } from "@/api/client";
import { useAppStore } from "@/store/use-app-store";
import { colors, radius, type } from "@/theme/tokens";
import type { Product } from "@/types";

const fields: { label: string; value: (product: Product) => string }[] = [
  { label: "类型", value: (item) => item.product_type_name || "—" }, { label: "颜色", value: (item) => item.colour_group_name || "—" },
  { label: "服装组", value: (item) => item.garment_group_name || "—" }, { label: "价格", value: (item) => typeof item.price === "number" ? item.price.toFixed(5) : "—" },
  { label: "尺码", value: (item) => item.available_sizes?.join(" · ") || "未提供" }, { label: "库存", value: (item) => item.inventory_status || "unknown" },
];

export default function CompareScreen() {
  const router = useRouter();
  const ids = useAppStore((state) => state.compareIds);
  const toggle = useAppStore((state) => state.toggleCompare);
  const [products, setProducts] = useState<Product[]>([]);
  useEffect(() => { if (ids.length >= 2) void compareProducts(ids).then((result) => setProducts(result.products)).catch((error) => Alert.alert("对比失败", error instanceof Error ? error.message : "请稍后重试")); }, [ids]);
  return <SafeAreaView style={styles.safe} edges={["top"]}><View style={styles.header}><Pressable onPress={() => router.back()} style={styles.back}><ArrowLeft size={18} color={colors.ink} /></Pressable><View><Text style={styles.eyebrow}>COMPARE WORKSPACE</Text><Text style={styles.title}>单品对比</Text><Text style={styles.subtitle}>只突出真实差异，缺失字段不会被推测。</Text></View></View>{!products.length ? <ActivityIndicator style={styles.loader} size="large" color={colors.primary} /> : <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.table}><View style={styles.labels}><View style={styles.mediaSpacer} />{fields.map((field) => <View key={field.label} style={styles.labelCell}><Text>{field.label}</Text></View>)}</View>{products.map((product) => <View key={product.article_id} style={styles.column}><Pressable onPress={() => router.push(`/product/${product.article_id}`)} style={styles.media}><Image source={{ uri: productImage(product) }} style={styles.image} contentFit="cover" /><Text numberOfLines={1}>{product.prod_name}</Text></Pressable>{fields.map((field) => <View key={field.label} style={styles.valueCell}><Text>{field.value(product)}</Text></View>)}<Pressable accessibilityLabel={`移除 ${product.prod_name}`} onPress={() => toggle(product.article_id)} style={styles.remove}><X size={14} color={colors.error} /><Text>移出对比</Text></Pressable></View>)}</ScrollView>}</SafeAreaView>;
}

const styles = StyleSheet.create({ safe: { flex: 1, backgroundColor: colors.background }, header: { padding: 16, flexDirection: "row", gap: 14 }, back: { width: 39, height: 39, alignItems: "center", justifyContent: "center", borderRadius: 20, backgroundColor: colors.surface }, eyebrow: { color: colors.primary, fontFamily: type.mono, fontSize: 8, fontWeight: "800" }, title: { marginTop: 6, color: colors.ink, fontFamily: type.serif, fontSize: 26 }, subtitle: { marginTop: 5, color: colors.muted, fontSize: 9 }, loader: { flex: 1 }, table: { margin: 16, overflow: "hidden", borderWidth: 1, borderColor: colors.line, borderRadius: radius.lg, backgroundColor: colors.surface }, labels: { width: 82 }, mediaSpacer: { height: 190 }, labelCell: { height: 62, padding: 8, justifyContent: "center", borderTopWidth: 1, borderTopColor: colors.line }, column: { width: 160, borderLeftWidth: 1, borderLeftColor: colors.line }, media: { height: 190, padding: 8 }, image: { width: "100%", height: 145, borderRadius: radius.md }, valueCell: { height: 62, padding: 8, justifyContent: "center", borderTopWidth: 1, borderTopColor: colors.line }, remove: { height: 44, margin: 7, flexDirection: "row", gap: 5, alignItems: "center", justifyContent: "center", borderRadius: radius.sm, backgroundColor: colors.errorSoft } });
