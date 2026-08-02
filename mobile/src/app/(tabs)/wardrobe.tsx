import { useEffect, useMemo, useState } from "react";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { ArrowRight, Plus, Search, Shirt } from "lucide-react-native";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { fetchProducts, productImage } from "@/api/client";
import { AppHeader } from "@/components/ui/app-header";
import { Screen } from "@/components/ui/screen";
import { useAppStore } from "@/store/use-app-store";
import { colors, radius } from "@/theme/tokens";
import type { Product } from "@/types";

export default function WardrobeScreen() {
  const router = useRouter();
  const [products, setProducts] = useState<Product[]>([]);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("全部");
  const user = useAppStore((state) => state.user);
  const wardrobe = useAppStore((state) => state.wardrobe);

  useEffect(() => { void fetchProducts({ page: 1, pageSize: 18, sort: "popular" }).then((page) => setProducts(page.items)).catch(() => undefined); }, []);
  const categories = ["全部", "上衣", "外套", "裤子", "裙子", "鞋子"];
  const items = useMemo(() => products.filter((product) => !search || `${product.prod_name} ${product.product_type_name}`.toLowerCase().includes(search.toLowerCase())), [products, search]);

  return (
    <Screen header={<AppHeader eyebrow="WARDROBE" title="我的衣橱" />} contentStyle={styles.content}>
      {!user && <View style={styles.loginCard}><View style={styles.loginIcon}><Shirt size={21} color={colors.primary} /></View><View style={styles.loginCopy}><Text style={styles.loginTitle}>登录后同步你的衣橱</Text><Text style={styles.loginBody}>让 Agent 基于已有单品规划，减少重复购买。</Text></View><Pressable style={styles.loginAction} onPress={() => router.push("/auth")}><Text style={styles.loginActionText}>登录</Text><ArrowRight size={14} color={colors.primary} /></Pressable></View>}
      <View style={styles.search}><Search size={17} color={colors.muted} /><TextInput accessibilityLabel="搜索衣物" value={search} onChangeText={setSearch} placeholder="搜索衣物" placeholderTextColor="#A39C97" style={styles.input} /><Pressable accessibilityLabel="添加衣物" disabled={!user} style={styles.add}><Plus size={17} color={colors.white} /></Pressable></View>
      <View style={styles.segments}>{categories.map((item) => <Pressable key={item} onPress={() => setCategory(item)} style={[styles.segment, category === item && styles.segmentActive]}><Text style={[styles.segmentText, category === item && styles.segmentTextActive]}>{item}</Text></Pressable>)}</View>
      {items[0] && <Pressable onPress={() => router.push(`/product/${items[0].article_id}`)} style={styles.featured}><Image source={{ uri: productImage(items[0]) }} style={styles.featuredImage} contentFit="cover" transition={180} /><View style={styles.featuredOverlay}><Text style={styles.featuredEyebrow}>FEATURED ITEM</Text><Text style={styles.featuredTitle} numberOfLines={1}>{items[0].prod_name}</Text></View></Pressable>}
      <View style={styles.gallery}>{items.slice(1, 13).map((product) => <Pressable key={product.article_id} onPress={() => router.push(`/product/${product.article_id}`)} style={styles.item}><Image source={{ uri: productImage(product) }} style={styles.image} contentFit="cover" transition={180} /><Text style={styles.itemTitle} numberOfLines={1}>{product.prod_name}</Text></Pressable>)}</View>
      <View style={styles.stats}><View style={styles.statsHeader}><Text style={styles.statsTitle}>衣橱洞察</Text><Text style={styles.statsVersion}>VERSION {wardrobe?.version || 0}</Text></View><View style={styles.statRow}>{[[wardrobe?.items.length || 0, "真实单品"], [new Set(wardrobe?.items.map((item) => item.category)).size || 0, "品类"], [items.length, "灵感款"]].map(([value, label], index) => <View key={String(label)} style={[styles.stat, index > 0 && styles.statBorder]}><Text style={styles.statValue}>{value}</Text><Text style={styles.statLabel}>{label}</Text></View>)}</View></View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: 12 }, loginCard: { padding: 15, flexDirection: "row", gap: 11, alignItems: "center", borderWidth: 1, borderColor: colors.line, borderRadius: radius.lg, backgroundColor: colors.surface }, loginIcon: { width: 42, height: 42, alignItems: "center", justifyContent: "center", borderRadius: 21, backgroundColor: colors.primaryPale }, loginCopy: { flex: 1 }, loginTitle: { color: colors.ink, fontSize: 12, fontWeight: "800" }, loginBody: { marginTop: 3, color: colors.muted, fontSize: 9, lineHeight: 14 }, loginAction: { alignItems: "center", gap: 3 }, loginActionText: { color: colors.primary, fontSize: 10, fontWeight: "700" },
  search: { height: 48, paddingHorizontal: 12, flexDirection: "row", gap: 9, alignItems: "center", borderWidth: 1, borderColor: colors.line, borderRadius: radius.md, backgroundColor: colors.surface }, input: { flex: 1, color: colors.ink, fontSize: 12 }, add: { width: 32, height: 32, alignItems: "center", justifyContent: "center", borderRadius: 16, backgroundColor: colors.primary },
  segments: { flexDirection: "row", gap: 5 }, segment: { flex: 1, height: 33, alignItems: "center", justifyContent: "center", borderRadius: 17, backgroundColor: colors.surfaceSoft }, segmentActive: { backgroundColor: colors.ink }, segmentText: { color: colors.muted, fontSize: 9 }, segmentTextActive: { color: colors.white },
  featured: { position: "relative", height: 250, overflow: "hidden", borderRadius: radius.xl, backgroundColor: colors.surfaceSoft }, featuredImage: { width: "100%", height: "100%" }, featuredOverlay: { position: "absolute", right: 0, bottom: 0, left: 0, padding: 17, backgroundColor: "rgba(25,22,25,.62)" }, featuredEyebrow: { color: "rgba(255,255,255,.68)", fontSize: 7, fontWeight: "800", letterSpacing: 1 }, featuredTitle: { marginTop: 5, color: colors.white, fontSize: 15, fontWeight: "800" }, gallery: { flexDirection: "row", flexWrap: "wrap", gap: 7 }, item: { width: "31.9%" }, image: { width: "100%", aspectRatio: 0.8, borderRadius: radius.md, backgroundColor: colors.surfaceSoft }, itemTitle: { marginTop: 5, color: colors.ink, fontSize: 9 },
  stats: { padding: 16, borderWidth: 1, borderColor: colors.line, borderRadius: radius.lg, backgroundColor: colors.surface }, statsHeader: { flexDirection: "row", justifyContent: "space-between" }, statsTitle: { color: colors.ink, fontSize: 12, fontWeight: "800" }, statsVersion: { color: colors.muted, fontSize: 7 }, statRow: { marginTop: 14, flexDirection: "row" }, stat: { flex: 1, alignItems: "center" }, statBorder: { borderLeftWidth: 1, borderLeftColor: colors.line }, statValue: { color: colors.ink, fontSize: 18, fontWeight: "800" }, statLabel: { marginTop: 3, color: colors.muted, fontSize: 8 },
});
