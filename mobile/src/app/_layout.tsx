import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { AppProvider } from "@/components/app-provider";
import { colors } from "@/theme/tokens";

export default function RootLayout() {
  return (
    <AppProvider>
      <StatusBar style="dark" />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.background }, animation: "fade_from_bottom", animationDuration: 260 }}>
        <Stack.Screen name="(tabs)" options={{ animation: "fade" }} />
        <Stack.Screen name="product/[id]" options={{ presentation: "card", animation: "slide_from_right" }} />
        <Stack.Screen name="compare" options={{ presentation: "card", animation: "slide_from_bottom" }} />
        <Stack.Screen name="cart" options={{ presentation: "modal", animation: "slide_from_bottom" }} />
        <Stack.Screen name="auth" options={{ presentation: "modal", animation: "slide_from_bottom" }} />
      </Stack>
    </AppProvider>
  );
}
