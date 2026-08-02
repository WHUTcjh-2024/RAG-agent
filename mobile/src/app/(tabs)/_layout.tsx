import type { ReactNode } from "react";
import { Tabs } from "expo-router";
import { BriefcaseBusiness, Compass, Home, Sparkles, UserRound } from "lucide-react-native";
import { Pressable, StyleSheet, View, type AccessibilityState, type GestureResponderEvent } from "react-native";
import { colors } from "@/theme/tokens";

type AgentButtonProps = { children?: ReactNode; onPress?: ((event: GestureResponderEvent) => void) | null; accessibilityState?: AccessibilityState };

function AgentButton({ children, onPress, accessibilityState }: AgentButtonProps) {
  const selected = accessibilityState?.selected;
  return <Pressable accessibilityRole="button" accessibilityState={accessibilityState} onPress={onPress} style={styles.agentButtonSlot}><View style={[styles.agentButton, selected && styles.agentButtonActive]}>{children}</View></Pressable>;
}

export default function TabLayout() {
  return (
    <Tabs screenOptions={{
      headerShown: false,
      tabBarActiveTintColor: colors.ink,
      tabBarInactiveTintColor: "#938D89",
      tabBarHideOnKeyboard: true,
      tabBarStyle: styles.tabBar,
      tabBarLabelStyle: styles.label,
      sceneStyle: { backgroundColor: colors.background },
    }}>
      <Tabs.Screen name="index" options={{ title: "首页", tabBarIcon: ({ color }) => <Home size={21} color={color} strokeWidth={1.8} /> }} />
      <Tabs.Screen name="wardrobe" options={{ title: "衣橱", tabBarIcon: ({ color }) => <BriefcaseBusiness size={21} color={color} strokeWidth={1.8} /> }} />
      <Tabs.Screen name="agent" options={{ title: "Agent", tabBarButton: AgentButton, tabBarIcon: () => <Sparkles size={20} color={colors.white} strokeWidth={2} /> }} />
      <Tabs.Screen name="discover" options={{ title: "发现", tabBarIcon: ({ color }) => <Compass size={21} color={color} strokeWidth={1.8} /> }} />
      <Tabs.Screen name="profile" options={{ title: "我的", tabBarIcon: ({ color }) => <UserRound size={21} color={color} strokeWidth={1.8} /> }} />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  tabBar: { height: 76, paddingTop: 7, paddingBottom: 9, borderTopColor: colors.line, backgroundColor: "rgba(255,253,251,.98)", elevation: 12 },
  label: { fontSize: 9, fontWeight: "600" },
  agentButtonSlot: { flex: 1, alignItems: "center", justifyContent: "center" },
  agentButton: { width: 48, height: 48, marginTop: -28, alignItems: "center", justifyContent: "center", borderWidth: 5, borderColor: colors.background, borderRadius: 24, backgroundColor: colors.primary, elevation: 8 },
  agentButtonActive: { backgroundColor: colors.primaryDark, transform: [{ scale: 1.04 }] },
});
