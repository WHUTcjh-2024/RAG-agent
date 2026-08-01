import { create } from "zustand";
import type { CartItem, DecisionCard, Message, PendingCartAction, Product, Slots, ToolTrace, User } from "../types";

const sessionId =
  localStorage.getItem("atelier-session") || `web-${crypto.randomUUID()}`;
localStorage.setItem("atelier-session", sessionId);
const accessToken = localStorage.getItem("atelier-access-token") || "";

type AppState = {
  sessionId: string;
  accessToken: string;
  user: User | null;
  messages: Message[];
  products: Product[];
  traces: ToolTrace[];
  slots: Slots;
  cart: CartItem[];
  compareIds: string[];
  comparison: Product[];
  streaming: boolean;
  decision: DecisionCard | null;
  pendingAction: PendingCartAction | null;
  addMessage: (message: Message) => void;
  setMessages: (messages: Message[]) => void;
  appendAssistant: (delta: string) => void;
  setProducts: (products: Product[]) => void;
  addTrace: (trace: ToolTrace) => void;
  setSlots: (slots: Slots) => void;
  setAuth: (accessToken: string, user: User | null) => void;
  setCart: (cart: CartItem[]) => void;
  toggleCompare: (id: string) => void;
  setComparison: (products: Product[]) => void;
  clearCompare: () => void;
  setStreaming: (streaming: boolean) => void;
  setDecision: (decision: DecisionCard | null) => void;
  setPendingAction: (action: PendingCartAction | null) => void;
};

export const useAppStore = create<AppState>((set) => ({
  sessionId,
  accessToken,
  user: null,
  messages: [],
  products: [],
  traces: [],
  slots: {},
  cart: [],
  compareIds: [],
  comparison: [],
  streaming: false,
  decision: null,
  pendingAction: null,
  addMessage: (message) => set((state) => ({ messages: [...state.messages, message] })),
  setMessages: (messages) => set({ messages }),
  appendAssistant: (delta) =>
    set((state) => {
      const messages = [...state.messages];
      const last = messages.at(-1);
      if (last?.role === "assistant") last.content += delta;
      else messages.push({ id: crypto.randomUUID(), role: "assistant", content: delta });
      return { messages };
    }),
  setProducts: (products) => set({ products }),
  addTrace: (trace) => set((state) => ({ traces: [...state.traces, trace].slice(-8) })),
  setSlots: (slots) => set({ slots }),
  setAuth: (token, user) => {
    if (token) localStorage.setItem("atelier-access-token", token);
    else localStorage.removeItem("atelier-access-token");
    set((state) => ({
      accessToken: token,
      user,
      cart: token ? state.cart : []
    }));
  },
  setCart: (cart) => set({ cart }),
  toggleCompare: (id) =>
    set((state) => ({
      compareIds: state.compareIds.includes(id)
        ? state.compareIds.filter((item) => item !== id)
        : state.compareIds.length < 3
          ? [...state.compareIds, id]
          : state.compareIds
    })),
  setComparison: (comparison) => set({ comparison }),
  clearCompare: () => set({ compareIds: [], comparison: [] }),
  setStreaming: (streaming) => set({ streaming }),
  setDecision: (decision) => set({ decision }),
  setPendingAction: (pendingAction) => set({ pendingAction })
}));
