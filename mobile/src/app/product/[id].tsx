import { useEffect, useState } from "react";
import { Image } from "expo-image";
import { useLocalSearchParams, useRouter } from "expo-router";
import { ArrowLeft, Box, Database, MessageCircle, Plus, ShieldCheck } from "lucide-react-native";
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { addCart, fetchProduct, productImage } from "@/api/client";
import { useAppStore } from "@/store/use-app-store";
import { colors, radius, type } from "@/theme/tokens";
import type { Product } from "@/types";

export default function ProductDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [product, setProduct] = useState<Product | null>(null);
  const [adding, setAdding] = useState(false);
  const token = useAppStore((state) => state.accessToken);
  const refreshCart = useAppStore((state) => state.refreshCart);

  useEffect(() => { if (id) void fetchProduct(id).then(setProduct).catch((error) => Alert.alert("加载失败", error instanceof Error ? error.message : "请稍后重试")); }, [id]);
  const add = async () => {
    if (!product) return;
    if (!token) { router.push("/auth"); return; }
    setAdding(true);
    try { await addCart(token, product); await refreshCart(); Alert.alert("已加入购物袋", product.prod_name); }
    catch (error) { Alert.alert("加入失败", error instanceof Error ? error.message : "请稍后重试"); }
    finally { setAdding(false); }
  };
  if (!product) return <SafeAreaView style={styles.loading}><ActivityIndicator size="large" color={colors.primary} /></SafeAreaView>;

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <Pressable accessibilityLabel="关闭" onPress={() => router.back()} style={[styles.back, { top: insets.top + 10 }]}><ArrowLeft size={18} color={colors.ink} /><Text style={styles.backText}>返回</Text></Pressable>
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.content}>
        <View style={styles.visual}><Image source={{ uri: productImage(product) }} style={styles.image} contentFit="cover" transition={220} /><Text style={styles.id}>ID / {product.article_id}</Text></View>
        <View style={styles.card}><Text style={styles.eyebrow}>PRODUCT DETAIL</Text><Text style={styles.title}>{product.prod_name}</Text><Text style={styles.taxonomy}>{product.product_type_name || "—"} · {product.colour_group_name || "—"} · {product.garment_group_name || "—"}</Text><Text style={styles.price}>{typeof product.price === "number" ? product.price.toFixed(6) : "—"}<Text style={styles.currency}> {product.price_info?.currency || "数据价格"}</Text></Text><View style={styles.actions}><Pressable disabled={adding} onPress={() => void add()} style={styles.primary}><Plus size={17} color={colors.white} /><Text style={styles.primaryText}>{adding ? "加入中…" : "加入购物袋"}</Text></Pressable><Pressable onPress={() => router.push({ pathname: "/agent", params: { prompt: `请分析 ${product.prod_name} 是否适合我，并给出可验证依据。` } })} style={styles.secondary}><MessageCircle size={16} color={colors.primary} /><Text style={styles.secondaryText}>询问 Agent</Text></Pressable></View></View>
        <View style={styles.card}><Text style={styles.chapter}><Box size={15} color={colors.primary} /> 01 / VERIFIED FIELDS</Text><Text style={styles.chapterTitle}>真实商品参数</Text>{[["商品类型", product.product_type_name], ["商品组", product.product_group_name], ["颜色", product.colour_group_name], ["服装组", product.garment_group_name], ["库存", product.inventory_status || "unknown"], ["尺码", product.available_sizes?.join(" · ") || "数据源未提供"]].map(([label, value]) => <View key={label} style={styles.row}><Text>{label}</Text><Text>{value || "—"}</Text></View>)}</View>
        <View style={styles.card}><Text style={styles.chapter}><Database size={15} color={colors.primary} /> 02 / MATERIAL & SOURCE</Text><Text style={styles.chapterTitle}>材质与描述</Text><Text style={styles.description}>{product.detail_desc || "数据源未提供商品描述。"}</Text><View style={styles.source}><ShieldCheck size={17} color={colors.success} /><View><Text>数据来源可追溯</Text><Text>{product.price_info?.source || "商品目录"}</Text></View></View></View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background }, loading: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.background }, content: { paddingBottom: 35 }, back: { position: "absolute", zIndex: 10, left: 14, minHeight: 39, paddingHorizontal: 12, flexDirection: "row", gap: 7, alignItems: "center", borderWidth: 1, borderColor: colors.line, borderRadius: 20, backgroundColor: "rgba(255,253,251,.94)" }, backText: { color: colors.ink, fontSize: 10, fontWeight: "700" }, visual: { height: 500, overflow: "hidden", borderBottomLeftRadius: 30, borderBottomRightRadius: 30, backgroundColor: colors.surfaceSoft }, image: { width: "100%", height: "100%" }, id: { position: "absolute", right: 15, bottom: 14, padding: 7, overflow: "hidden", borderRadius: radius.sm, color: colors.muted, backgroundColor: "rgba(255,253,251,.85)", fontFamily: type.mono, fontSize: 8 },
  card: { marginHorizontal: 16, marginTop: 12, padding: 19, borderWidth: 1, borderColor: colors.line, borderRadius: radius.xl, backgroundColor: colors.surface }, eyebrow: { color: colors.primary, fontFamily: type.mono, fontSize: 8, fontWeight: "800", letterSpacing: 1 }, title: { marginTop: 12, color: colors.ink, fontFamily: type.serif, fontSize: 29, lineHeight: 34, letterSpacing: -1 }, taxonomy: { marginTop: 7, color: colors.muted, fontSize: 9 }, price: { marginTop: 16, color: colors.ink, fontSize: 19, fontWeight: "800" }, currency: { color: colors.muted, fontSize: 7, fontWeight: "400" }, actions: { marginTop: 17, flexDirection: "row", gap: 7 }, primary: { flex: 1, height: 46, flexDirection: "row", gap: 7, alignItems: "center", justifyContent: "center", borderRadius: radius.md, backgroundColor: colors.primary }, primaryText: { color: colors.white, fontSize: 11, fontWeight: "800" }, secondary: { flex: 1, height: 46, flexDirection: "row", gap: 7, alignItems: "center", justifyContent: "center", borderRadius: radius.md, backgroundColor: colors.primaryPale }, secondaryText: { color: colors.primary, fontSize: 11, fontWeight: "700" }, chapter: { color: colors.primary, fontFamily: type.mono, fontSize: 8, fontWeight: "800" }, chapterTitle: { marginTop: 9, marginBottom: 15, color: colors.ink, fontFamily: type.serif, fontSize: 22 }, row: { minHeight: 42, paddingVertical: 9, flexDirection: "row", justifyContent: "space-between", borderTopWidth: 1, borderTopColor: colors.line }, description: { color: colors.muted, fontSize: 12, lineHeight: 20 }, source: { marginTop: 14, padding: 12, flexDirection: "row", gap: 9, borderRadius: radius.md, backgroundColor: colors.successSoft },
});
