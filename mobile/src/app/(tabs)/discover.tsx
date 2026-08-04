import { useEffect, useRef, useState } from "react";
import { useRouter } from "expo-router";
import { GitCompareArrows, Search, SlidersHorizontal, X } from "lucide-react-native";
import { ActivityIndicator, Alert, FlatList, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { addCart, fetchFacets, fetchProducts } from "@/api/client";
import { ProductCard } from "@/components/product-card";
import { AppHeader } from "@/components/ui/app-header";
import { Screen } from "@/components/ui/screen";
import { useAppStore } from "@/store/use-app-store";
import { colors, radius, shadow, type } from "@/theme/tokens";
import type { Product, ProductFacets } from "@/types";

export default function DiscoverScreen() {
  const router = useRouter();
  const [products, setProducts] = useState<Product[]>([]);
  const [facets, setFacets] = useState<ProductFacets | null>(null);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const request = useRef(0);
  const token = useAppStore((state) => state.accessToken);
  const compareIds = useAppStore((state) => state.compareIds);
  const toggleCompare = useAppStore((state) => state.toggleCompare);
  const clearCompare = useAppStore((state) => state.clearCompare);
  const refreshCart = useAppStore((state) => state.refreshCart);

  useEffect(() => { void fetchFacets().then(setFacets).catch(() => undefined); }, []);
  useEffect(() => {
    const id = ++request.current;
    const timer = setTimeout(() => {
      setLoading(true);
      void fetchProducts({ page: 1, pageSize: 24, search: search.trim() || undefined, category: category || undefined, sort: "popular" })
        .then((page) => { if (id === request.current) { setProducts(page.items); setTotal(page.total); } })
        .catch((error) => Alert.alert("检索失败", error instanceof Error ? error.message : "请稍后重试"))
        .finally(() => { if (id === request.current) setLoading(false); });
    }, search ? 260 : 0);
    return () => clearTimeout(timer);
  }, [search, category]);

  const add = async (product: Product) => {
    if (!token) { router.push("/auth"); return; }
    try { await addCart(token, product); await refreshCart(); Alert.alert("已加入购物袋", product.prod_name); }
    catch (error) { Alert.alert("加入失败", error instanceof Error ? error.message : "请稍后重试"); }
  };

  return (
    <Screen scroll={false} header={<AppHeader eyebrow="LIVE CATALOG" title="发现单品" />}>
      <View style={styles.heading}><View><Text style={styles.eyebrow}>REAL PRODUCT DATA</Text><Text style={styles.title}>为当前需求重新编排</Text></View><Text style={styles.count}>{total} 件商品</Text></View>
      <View style={styles.searchBar}><Search size={18} color={colors.muted} /><TextInput accessibilityLabel="搜索商品" value={search} onChangeText={setSearch} placeholder="搜索商品名称或描述" placeholderTextColor="#A39C97" style={styles.input} returnKeyType="search" />{search ? <Pressable onPress={() => setSearch("")}><X size={16} color={colors.muted} /></Pressable> : <SlidersHorizontal size={17} color={colors.primary} />}</View>
      <FlatList style={styles.filterList} horizontal data={["", ...(facets?.categories || []).slice(0, 8)]} keyExtractor={(item) => item || "all"} showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filters} renderItem={({ item }) => <Pressable onPress={() => setCategory(item)} style={[styles.filter, category === item && styles.filterActive]}><Text style={[styles.filterText, category === item && styles.filterTextActive]}>{item || "全部"}</Text></Pressable>} />
      {loading && !products.length ? <ActivityIndicator style={styles.loader} color={colors.primary} /> : <FlatList data={products} numColumns={2} keyExtractor={(item) => item.article_id} columnWrapperStyle={styles.row} contentContainerStyle={styles.grid} showsVerticalScrollIndicator={false} renderItem={({ item }) => <View style={styles.cell}><ProductCard product={item} selected={compareIds.includes(item.article_id)} onPress={() => router.push(`/product/${item.article_id}`)} onCompare={() => toggleCompare(item.article_id)} onAdd={() => void add(item)} /></View>} ListEmptyComponent={<View style={styles.empty}><Text>没有匹配商品</Text><Text>放宽搜索或分类条件后再试。</Text></View>} />}
      {compareIds.length >= 2 && <View style={styles.compareTray}><GitCompareArrows size={17} color={colors.white} /><Text>已选择 {compareIds.length} 件</Text><Pressable onPress={() => router.push("/compare")}><Text>开始对比</Text></Pressable><Pressable onPress={clearCompare}><X size={16} color="rgba(255,255,255,.65)" /></Pressable></View>}
    </Screen>
  );
}

const styles = StyleSheet.create({
  heading: { paddingHorizontal: 16, paddingTop: 6, flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between" }, eyebrow: { color: colors.primary, fontFamily: type.mono, fontSize: 8, fontWeight: "800", letterSpacing: 1 }, title: { marginTop: 6, color: colors.ink, fontFamily: type.serif, fontSize: 25, letterSpacing: -0.8 }, count: { color: colors.muted, fontSize: 9 },
  searchBar: { height: 48, marginHorizontal: 16, marginTop: 15, paddingHorizontal: 13, flexDirection: "row", gap: 9, alignItems: "center", borderWidth: 1, borderColor: colors.line, borderRadius: radius.md, backgroundColor: colors.surface }, input: { flex: 1, color: colors.ink, fontSize: 12 },
  filterList: { flexGrow: 0, height: 53 }, filters: { paddingHorizontal: 16, paddingVertical: 10, gap: 5 }, filter: { height: 33, paddingHorizontal: 13, justifyContent: "center", borderRadius: 17, backgroundColor: colors.surfaceSoft }, filterActive: { backgroundColor: colors.ink }, filterText: { color: colors.muted, fontSize: 10 }, filterTextActive: { color: colors.white },
  loader: { flex: 1 }, grid: { paddingHorizontal: 16, paddingBottom: 120 }, row: { gap: 9, marginBottom: 20 }, cell: { flex: 1, minWidth: 0 }, empty: { height: 360, alignItems: "center", justifyContent: "center" },
  compareTray: { position: "absolute", right: 12, bottom: 86, left: 12, minHeight: 54, paddingHorizontal: 12, flexDirection: "row", gap: 9, alignItems: "center", borderRadius: radius.lg, backgroundColor: "rgba(43,39,44,.97)", ...shadow },
});
