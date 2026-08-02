export function createClientId(): string {
  const randomUUID = globalThis.crypto?.randomUUID;
  if (typeof randomUUID === "function") return randomUUID.call(globalThis.crypto);

  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}
