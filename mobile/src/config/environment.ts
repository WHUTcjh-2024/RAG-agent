import { Platform } from "react-native";

const emulatorHost = Platform.OS === "android" ? "10.0.2.2" : "127.0.0.1";

export const API_BASE_URL = (process.env.EXPO_PUBLIC_API_BASE_URL || `http://${emulatorHost}:8080`).replace(/\/$/, "");

export function apiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

export function assetUrl(path?: string | null): string {
  if (!path) return "";
  return apiUrl(path);
}
