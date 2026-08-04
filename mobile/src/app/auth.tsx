import { useState } from "react";
import { useRouter } from "expo-router";
import { ArrowLeft, Eye, EyeOff, Sparkles } from "lucide-react-native";
import { ActivityIndicator, Alert, KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { fetchCart, fetchWardrobe, login, register } from "@/api/client";
import { useAppStore } from "@/store/use-app-store";
import { colors, radius, type } from "@/theme/tokens";

export default function AuthScreen() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [visible, setVisible] = useState(false);
  const [loading, setLoading] = useState(false);
  const setAuth = useAppStore((state) => state.setAuth);
  const setCart = useAppStore((state) => state.setCart);
  const setWardrobe = useAppStore((state) => state.setWardrobe);

  const submit = async () => {
    if (!email.trim() || password.length < 8 || (mode === "register" && !displayName.trim())) { Alert.alert("请检查输入", "请填写有效邮箱，密码至少 8 位。"); return; }
    setLoading(true);
    try {
      const result = mode === "login" ? await login(email.trim(), password) : await register(email.trim(), password, displayName.trim());
      await setAuth(result.accessToken, result.user);
      const [cart, wardrobe] = await Promise.all([fetchCart(result.accessToken).catch(() => []), fetchWardrobe(result.accessToken).catch(() => null)]);
      setCart(cart); setWardrobe(wardrobe); router.back();
    } catch (error) { Alert.alert(mode === "login" ? "登录失败" : "注册失败", error instanceof Error ? error.message : "请稍后重试"); }
    finally { setLoading(false); }
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]}><KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === "ios" ? "padding" : "height"}>
      <Pressable accessibilityLabel="关闭" onPress={() => router.back()} style={styles.close}><ArrowLeft size={19} color={colors.ink} /></Pressable>
      <View style={styles.content}><View style={styles.mark}><Sparkles size={22} color={colors.primary} /></View><Text style={styles.eyebrow}>FITME ACCOUNT</Text><Text style={styles.title}>{mode === "login" ? "欢迎回来" : "创建你的 FitMe"}</Text><Text style={styles.subtitle}>安全同步衣橱、购物袋与 Agent 偏好。</Text>
        <View style={styles.switch}>{(["login", "register"] as const).map((item) => <Pressable key={item} onPress={() => setMode(item)} style={[styles.switchButton, mode === item && styles.switchActive]}><Text style={[styles.switchText, mode === item && styles.switchTextActive]}>{item === "login" ? "登录" : "注册"}</Text></Pressable>)}</View>
        {mode === "register" && <View style={styles.field}><Text>昵称</Text><TextInput accessibilityLabel="昵称" value={displayName} onChangeText={setDisplayName} placeholder="你的名字" placeholderTextColor="#A39C97" style={styles.input} /></View>}
        <View style={styles.field}><Text>邮箱</Text><TextInput accessibilityLabel="邮箱" value={email} onChangeText={setEmail} placeholder="name@example.com" placeholderTextColor="#A39C97" autoCapitalize="none" keyboardType="email-address" autoComplete="email" style={styles.input} /></View>
        <View style={styles.field}><Text>密码</Text><View style={styles.passwordRow}><TextInput accessibilityLabel="密码" value={password} onChangeText={setPassword} placeholder="至少 8 位" placeholderTextColor="#A39C97" secureTextEntry={!visible} autoComplete={mode === "login" ? "current-password" : "new-password"} style={styles.passwordInput} /><Pressable accessibilityLabel={visible ? "隐藏密码" : "显示密码"} onPress={() => setVisible(!visible)}>{visible ? <EyeOff size={18} color={colors.muted} /> : <Eye size={18} color={colors.muted} />}</Pressable></View></View>
        <Pressable disabled={loading} onPress={() => void submit()} style={({ pressed }) => [styles.submit, pressed && styles.pressed]}>{loading ? <ActivityIndicator color={colors.white} /> : <Text style={styles.submitText}>{mode === "login" ? "登录" : "创建账户"}</Text>}</Pressable>
        <Text style={styles.security}>登录凭据不会写入普通存储；访问令牌使用系统 SecureStore 保存。</Text>
      </View>
    </KeyboardAvoidingView></SafeAreaView>
  );
}

const styles = StyleSheet.create({ safe: { flex: 1, backgroundColor: colors.background }, flex: { flex: 1 }, close: { width: 40, height: 40, margin: 15, alignItems: "center", justifyContent: "center", borderRadius: 20, backgroundColor: colors.surface }, content: { flex: 1, paddingHorizontal: 22, justifyContent: "center" }, mark: { width: 52, height: 52, marginBottom: 18, alignItems: "center", justifyContent: "center", borderRadius: 26, backgroundColor: colors.primarySoft }, eyebrow: { color: colors.primary, fontFamily: type.mono, fontSize: 9, fontWeight: "800", letterSpacing: 1.2 }, title: { marginTop: 9, color: colors.ink, fontFamily: type.serif, fontSize: 33 }, subtitle: { marginTop: 8, marginBottom: 22, color: colors.muted, fontSize: 11 }, switch: { height: 42, padding: 4, flexDirection: "row", borderRadius: radius.md, backgroundColor: colors.surfaceSoft }, switchButton: { flex: 1, alignItems: "center", justifyContent: "center", borderRadius: radius.sm }, switchActive: { backgroundColor: colors.surface }, switchText: { color: colors.muted }, switchTextActive: { color: colors.ink, fontWeight: "700" }, field: { marginTop: 15 }, input: { height: 50, marginTop: 7, paddingHorizontal: 13, borderWidth: 1, borderColor: colors.line, borderRadius: radius.md, color: colors.ink, backgroundColor: colors.surface }, passwordRow: { height: 50, marginTop: 7, paddingHorizontal: 13, flexDirection: "row", alignItems: "center", borderWidth: 1, borderColor: colors.line, borderRadius: radius.md, backgroundColor: colors.surface }, passwordInput: { flex: 1, color: colors.ink }, submit: { height: 50, marginTop: 22, alignItems: "center", justifyContent: "center", borderRadius: radius.md, backgroundColor: colors.primary }, submitText: { color: colors.white, fontSize: 11, fontWeight: "800" }, pressed: { transform: [{ scale: 0.98 }] }, security: { marginTop: 14, color: colors.muted, fontSize: 9, lineHeight: 15, textAlign: "center" } });
