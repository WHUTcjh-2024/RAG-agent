import { Platform } from "react-native";

export const colors = {
  background: "#F7F5F2",
  surface: "#FFFDFB",
  surfaceSoft: "#F0ECE8",
  ink: "#191716",
  muted: "#77716D",
  line: "rgba(36, 30, 27, 0.09)",
  primary: "#5F5365",
  primaryDark: "#443A48",
  primarySoft: "#E9E0EF",
  primaryPale: "#F4EEF7",
  accent: "#C48AA6",
  success: "#388260",
  successSoft: "#EAF4EE",
  error: "#A84B43",
  errorSoft: "#F7EAE8",
  white: "#FFFFFF",
  overlay: "rgba(24, 22, 21, 0.38)",
} as const;

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 22, xxl: 30 } as const;
export const radius = { sm: 10, md: 15, lg: 20, xl: 26, pill: 999 } as const;

export const type = {
  sans: Platform.select({ ios: "SF Pro Display", android: "sans-serif", default: "sans-serif" }),
  serif: Platform.select({ ios: "Songti SC", android: "serif", default: "serif" }),
  mono: Platform.select({ ios: "SF Mono", android: "monospace", default: "monospace" }),
} as const;

export const shadow = Platform.select({
  ios: { shadowColor: "#2C221E", shadowOffset: { width: 0, height: 12 }, shadowOpacity: 0.08, shadowRadius: 24 },
  android: { elevation: 4 },
  default: {},
});

export const motion = {
  micro: 150,
  state: 260,
  screen: 520,
  spring: { damping: 22, stiffness: 230, mass: 0.85 },
} as const;
