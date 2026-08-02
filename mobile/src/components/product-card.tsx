import { Check, GitCompareArrows, Heart, Plus } from "lucide-react-native";
import { Image } from "expo-image";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { productImage } from "@/api/client";
import { colors, radius } from "@/theme/tokens";
import type { Product } from "@/types";

export function ProductCard({ product, selected, onPress, onCompare, onAdd }: { product: Product; selected?: boolean; onPress: () => void; onCompare: () => void; onAdd: () => void }) {
  return (
    <View style={styles.card}>
      <Pressable onPress={onPress} style={({ pressed }) => [styles.media, pressed && styles.mediaPressed]}>
        <Image source={{ uri: productImage(product) }} style={styles.image} contentFit="cover" transition={180} />
        <Pressable accessibilityLabel="收藏" hitSlop={8} style={styles.favorite}><Heart size={15} color={colors.ink} /></Pressable>
        <View style={styles.actions}>
          <Pressable accessibilityLabel="加入对比" onPress={onCompare} style={[styles.action, selected && styles.selected]}>{selected ? <Check size={15} color={colors.white} /> : <GitCompareArrows size={15} color={colors.ink} />}</Pressable>
          <Pressable accessibilityLabel="加入购物袋" onPress={onAdd} style={[styles.action, styles.add]}><Plus size={16} color={colors.white} /></Pressable>
        </View>
      </Pressable>
      <Pressable onPress={onPress}>
        <Text style={styles.taxonomy} numberOfLines={1}>{product.product_type_name || "ITEM"} · {product.colour_group_name || "—"}</Text>
        <Text style={styles.name} numberOfLines={1}>{product.prod_name}</Text>
        <Text style={styles.price}>{typeof product.price === "number" ? product.price.toFixed(4) : "—"}<Text style={styles.currency}> {product.price_info?.currency || "数据价"}</Text></Text>
      </Pressable>
      {product.reason && <View style={styles.reason}><Text>MATCH REASON</Text><Text>{product.reason}</Text></View>}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { flex: 1, minWidth: 0 }, media: { aspectRatio: 0.76, overflow: "hidden", borderRadius: radius.lg, backgroundColor: colors.surfaceSoft }, mediaPressed: { transform: [{ scale: 0.985 }] }, image: { width: "100%", height: "100%" },
  favorite: { position: "absolute", top: 8, right: 8, width: 30, height: 30, alignItems: "center", justifyContent: "center", borderRadius: 15, backgroundColor: "rgba(255,253,251,.88)" },
  actions: { position: "absolute", right: 8, bottom: 8, flexDirection: "row", gap: 5 }, action: { width: 34, height: 34, alignItems: "center", justifyContent: "center", borderRadius: 17, backgroundColor: "rgba(255,253,251,.94)" }, add: { backgroundColor: colors.ink }, selected: { backgroundColor: colors.primary },
  taxonomy: { marginTop: 9, color: colors.muted, fontSize: 9 }, name: { marginTop: 4, color: colors.ink, fontSize: 12, fontWeight: "600" }, price: { marginTop: 6, color: colors.ink, fontSize: 11, fontWeight: "800" }, currency: { color: colors.muted, fontSize: 6, fontWeight: "400" },
  reason: { marginTop: 7, padding: 8, borderRadius: radius.sm, backgroundColor: colors.primaryPale },
});
