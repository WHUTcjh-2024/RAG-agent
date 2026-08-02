import * as Crypto from "expo-crypto";
import * as SecureStore from "expo-secure-store";
import { create } from "zustand";
import { fetchCart, fetchCurrentUser, fetchSession, fetchWardrobe } from "@/api/client";
import type { AgentNodeEvent, AgentPhase, CartItem, DecisionCard, DecisionEvidence, Message, PendingCartAction, Product, Slots, ToolTrace, User, WardrobePlan, WardrobeSnapshot } from "@/types";

const TOKEN_KEY = "fitme.accessToken";
const SESSION_KEY = "fitme.sessionId";
const LANGUAGE_KEY = "fitme.language";

type Language = "zh" | "en";

type Store = {
  hydrated: boolean;
  accessToken: string;
  user: User | null;
  cart: CartItem[];
  wardrobe: WardrobeSnapshot | null;
  compareIds: string[];
  language: Language;
  sessionId: string;
  messages: Message[];
  agentState: AgentPhase | "idle";
  agentEvents: AgentNodeEvent[];
  agentProducts: Product[];
  evidence: DecisionEvidence[];
  traces: ToolTrace[];
  decision: DecisionCard | null;
  pendingAction: PendingCartAction | null;
  wardrobePlan: WardrobePlan | null;
  initialize: () => Promise<void>;
  setLanguage: (language: Language) => Promise<void>;
  setAuth: (token: string, user: User | null) => Promise<void>;
  logout: () => Promise<void>;
  setCart: (items: CartItem[]) => void;
  refreshCart: () => Promise<void>;
  setWardrobe: (snapshot: WardrobeSnapshot | null) => void;
  toggleCompare: (id: string) => void;
  clearCompare: () => void;
  addMessage: (message: Message) => void;
  appendAssistant: (delta: string) => void;
  setAgentState: (state: AgentPhase | "idle") => void;
  addAgentEvent: (event: AgentNodeEvent) => void;
  setAgentProducts: (items: Product[]) => void;
  addEvidence: (item: DecisionEvidence) => void;
  addTrace: (trace: ToolTrace) => void;
  setSlots: (slots: Slots) => void;
  slots: Slots;
  setDecision: (card: DecisionCard | null) => void;
  setPendingAction: (action: PendingCartAction | null) => void;
  setWardrobePlan: (plan: WardrobePlan | null) => void;
  resetExecution: () => void;
};

export const useAppStore = create<Store>((set, get) => ({
  hydrated: false,
  accessToken: "",
  user: null,
  cart: [],
  wardrobe: null,
  compareIds: [],
  language: "zh",
  sessionId: Crypto.randomUUID(),
  messages: [],
  agentState: "idle",
  agentEvents: [],
  agentProducts: [],
  evidence: [],
  traces: [],
  slots: {},
  decision: null,
  pendingAction: null,
  wardrobePlan: null,

  initialize: async () => {
    const [token, savedSession, savedLanguage] = await Promise.all([
      SecureStore.getItemAsync(TOKEN_KEY),
      SecureStore.getItemAsync(SESSION_KEY),
      SecureStore.getItemAsync(LANGUAGE_KEY),
    ]);
    const sessionId = savedSession || get().sessionId;
    if (!savedSession) await SecureStore.setItemAsync(SESSION_KEY, sessionId);
    set({ accessToken: token || "", sessionId, language: savedLanguage === "en" ? "en" : "zh" });

    const sessionResult = await fetchSession(sessionId).catch(() => null);
    if (sessionResult) set({ slots: sessionResult.slots, messages: sessionResult.history.map((message) => ({ ...message, id: Crypto.randomUUID() })) });

    if (token) {
      const [userResult, cartResult, wardrobeResult] = await Promise.allSettled([
        fetchCurrentUser(token), fetchCart(token), fetchWardrobe(token),
      ]);
      if (userResult.status === "fulfilled") {
        set({ user: userResult.value, cart: cartResult.status === "fulfilled" ? cartResult.value : [], wardrobe: wardrobeResult.status === "fulfilled" ? wardrobeResult.value : null });
      } else {
        await SecureStore.deleteItemAsync(TOKEN_KEY);
        set({ accessToken: "" });
      }
    }
    set({ hydrated: true });
  },
  setLanguage: async (language) => { await SecureStore.setItemAsync(LANGUAGE_KEY, language); set({ language }); },
  setAuth: async (accessToken, user) => { if (accessToken) await SecureStore.setItemAsync(TOKEN_KEY, accessToken); else await SecureStore.deleteItemAsync(TOKEN_KEY); set({ accessToken, user }); },
  logout: async () => { await SecureStore.deleteItemAsync(TOKEN_KEY); set({ accessToken: "", user: null, cart: [], wardrobe: null }); },
  setCart: (cart) => set({ cart }),
  refreshCart: async () => { const token = get().accessToken; if (token) set({ cart: await fetchCart(token) }); },
  setWardrobe: (wardrobe) => set({ wardrobe }),
  toggleCompare: (id) => set((state) => ({ compareIds: state.compareIds.includes(id) ? state.compareIds.filter((item) => item !== id) : state.compareIds.length < 3 ? [...state.compareIds, id] : state.compareIds })),
  clearCompare: () => set({ compareIds: [] }),
  addMessage: (message) => set((state) => ({ messages: [...state.messages, message] })),
  appendAssistant: (delta) => set((state) => {
    const messages = [...state.messages];
    const last = messages.at(-1);
    if (last?.role === "assistant") messages[messages.length - 1] = { ...last, content: last.content + delta };
    else messages.push({ id: Crypto.randomUUID(), role: "assistant", content: delta });
    return { messages };
  }),
  setAgentState: (agentState) => set({ agentState }),
  addAgentEvent: (event) => set((state) => ({ agentEvents: [...state.agentEvents, event].slice(-40), agentState: event.state === "failed" ? "failure" : event.phase })),
  setAgentProducts: (agentProducts) => set({ agentProducts }),
  addEvidence: (item) => set((state) => ({ evidence: [...state.evidence, item], agentState: "verification" })),
  addTrace: (trace) => set((state) => ({ traces: [...state.traces, trace], agentState: "tool" })),
  setSlots: (slots) => set({ slots }),
  setDecision: (decision) => set({ decision }),
  setPendingAction: (pendingAction) => set({ pendingAction }),
  setWardrobePlan: (wardrobePlan) => set({ wardrobePlan }),
  resetExecution: () => set({ agentEvents: [], agentProducts: [], evidence: [], traces: [], decision: null, pendingAction: null, wardrobePlan: null }),
}));
