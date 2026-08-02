import type { PropsWithChildren, ReactNode } from "react";
import { ScrollView, StyleSheet, View, type ScrollViewProps, type ViewStyle } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { colors } from "@/theme/tokens";

type Props = PropsWithChildren<{ scroll?: boolean; header?: ReactNode; contentStyle?: ViewStyle; scrollProps?: ScrollViewProps }>;

export function Screen({ children, scroll = true, header, contentStyle, scrollProps }: Props) {
  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      {header}
      {scroll ? (
        <ScrollView contentContainerStyle={[styles.content, contentStyle]} showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled" {...scrollProps}>{children}</ScrollView>
      ) : <View style={[styles.flex, contentStyle]}>{children}</View>}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({ safe: { flex: 1, backgroundColor: colors.background }, flex: { flex: 1 }, content: { paddingHorizontal: 16, paddingBottom: 120 } });
