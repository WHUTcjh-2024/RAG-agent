import { useEffect, useRef, useState } from "react";
import { GitCompareArrows } from "lucide-react";
import {
  addCart,
  cancelAgentTask,
  clearCart,
  compareProducts,
  confirmAgentCartAction,
  fetchCart,
  fetchCurrentUser,
  fetchFacets,
  fetchProduct,
  fetchProducts,
  fetchWardrobe,
  fetchSession,
  login,
  recordAgentActionCompletion,
  recordWardrobeFeedback,
  replanWardrobe,
  register,
  removeCart,
  streamChat
} from "./api/client";
import { CompareDrawer, CartDrawer, ProductDetailDrawer } from "./components/Drawers";
import { AuthDrawer } from "./components/AuthDrawer";
import { BrowseControls } from "./components/BrowseControls";
import { Header } from "./components/Header";
import { Hero } from "./components/Hero";
import { ProductGrid } from "./components/ProductGrid";
import { StylistDrawer } from "./components/StylistDrawer";
import { useAppStore } from "./store/useAppStore";
import type { Product, ProductFacets, ProductQuery } from "./types";
import { useTranslation } from "./i18n";

export default function App() {
  const { language, t } = useTranslation();
  const store = useAppStore();
  const [cartOpen, setCartOpen] = useState(false);
  const [authOpen, setAuthOpen] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);
  const [stylistOpen, setStylistOpen] = useState(false);
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState<ProductQuery>({ page: 1, pageSize: 12, sort: "popular" });
  const [facets, setFacets] = useState<ProductFacets | null>(null);
  const [total, setTotal] = useState(0);
  const [detail, setDetail] = useState<Product | null>(null);
  const [loading, setLoading] = useState(false);
  const abortController = useRef<AbortController | null>(null);
  const activeTaskId = useRef<string | null>(null);

  useEffect(() => {
    fetchFacets().then(setFacets).catch((error) => setNotice(error.message));
    fetchSession(store.sessionId).then((session) => {
      store.setSlots(session.slots);
      store.setMessages(session.history.map((item) => ({ ...item, id: crypto.randomUUID() })));
    }).catch((error) => setNotice(error.message));
    if (store.accessToken) {
      Promise.all([
        fetchCurrentUser(store.accessToken),
        fetchCart(store.accessToken)
      ]).then(([user, cart]) => {
        store.setAuth(store.accessToken, user);
        store.setCart(cart);
      }).catch(() => store.setAuth("", null));
      fetchWardrobe(store.accessToken).then(store.setWardrobe).catch(() => {
        // Wardrobe is additive; unavailable Java data must not invalidate login or cart state.
      });
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    const timer = window.setTimeout(() => {
      fetchProducts(query)
        .then((page) => { store.setProducts(page.items); setTotal(page.total); })
        .catch((error) => setNotice(error.message))
        .finally(() => setLoading(false));
    }, query.search ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [query]);

  const browse = (indexGroup?: string) => {
    setQuery((current) => ({ ...current, indexGroup: indexGroup || "", page: 1 }));
    window.setTimeout(() => document.getElementById("collection")?.scrollIntoView({ behavior: "smooth" }), 0);
  };

  const showDetail = async (id: string) => {
    try { setDetail(await fetchProduct(id)); }
    catch (error) { setNotice(error instanceof Error ? error.message : t("detailFailed")); }
  };

  const submit = async (message: string, image: File | null, preview: string | null) => {
    store.addMessage({ id: crypto.randomUUID(), role: "user", content: message || t("similarImage"), imagePreview: preview || undefined });
    store.setStreaming(true);
    setNotice("");
    activeTaskId.current = null;
    abortController.current = new AbortController();
    try {
      await streamChat(message, store.sessionId, image, language, {
        onMeta: ({ slots, task_id }) => { activeTaskId.current = task_id; store.setSlots(slots); },
        onTaskId: (taskId) => { activeTaskId.current = taskId; },
        onTool: store.addTrace,
        onProducts: store.setProducts,
        onComparison: store.setComparison,
        onDecision: store.setDecision,
        onConfirmRequired: store.setPendingAction,
        onWardrobePlan: store.setWardrobePlan,
        onMessage: store.appendAssistant,
        onError: () => undefined
      }, store.accessToken, abortController.current.signal);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      const text = error instanceof Error ? error.message : t("requestFailed");
      store.appendAssistant(`${t("unable")}${text}`);
      setNotice(text);
    } finally {
      abortController.current = null;
      activeTaskId.current = null;
      store.setStreaming(false);
    }
  };

  const cancelChat = () => {
    const taskId = activeTaskId.current;
    abortController.current?.abort();
    if (taskId) {
      cancelAgentTask(store.accessToken, taskId, store.sessionId).catch(() => {
        // Client cancellation is immediate; server cancellation is best effort after network loss.
      });
    }
  };

  const confirmPendingAction = async () => {
    if (!store.accessToken || !store.pendingAction) return;
    try {
      const item = await confirmAgentCartAction(store.accessToken, store.pendingAction);
      await recordAgentActionCompletion(store.accessToken, store.pendingAction.action_id, item.id);
      store.setCart(await fetchCart(store.accessToken));
      store.setPendingAction(null);
      setNotice(t("added"));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : t("addFailed"));
    }
  };

  const editWardrobePlan = async (operation: Record<string, unknown>) => {
    if (!store.accessToken || !store.wardrobePlan) return;
    try {
      store.setWardrobePlan(await replanWardrobe(store.accessToken, store.wardrobePlan.plan_id, store.wardrobePlan, operation));
      store.setWardrobe(await fetchWardrobe(store.accessToken));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : t("requestFailed"));
    }
  };

  const acceptWardrobePlan = async () => {
    if (!store.accessToken || !store.wardrobePlan) return;
    try {
      await recordWardrobeFeedback(store.accessToken, { planRef: store.wardrobePlan.plan_id, outcome: "ADOPTED" });
      setNotice("已记录本次穿搭采纳");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : t("requestFailed"));
    }
  };

  const add = async (id: string) => {
    if (!store.accessToken || !store.user) {
      setAuthOpen(true);
      setNotice(t("loginForCart"));
      return;
    }
    try {
      const product = store.products.find((item) => item.article_id === id)
        || (detail?.article_id === id ? detail : await fetchProduct(id));
      await addCart(store.accessToken, product);
      store.setCart(await fetchCart(store.accessToken));
      setNotice(t("added"));
    } catch (error) { setNotice(error instanceof Error ? error.message : t("addFailed")); }
  };

  const openCompare = async () => {
    if (store.compareIds.length < 2) return;
    try {
      const result = await compareProducts(store.compareIds);
      store.setComparison(result.products);
      setCompareOpen(true);
    } catch (error) { setNotice(error instanceof Error ? error.message : t("compareFailed")); }
  };

  const authenticate = async (
    mode: "login" | "register",
    credentials: { email: string; password: string; displayName?: string }
  ) => {
    const result = mode === "login"
      ? await login(credentials.email, credentials.password)
      : await register(credentials.email, credentials.password, credentials.displayName || "");
    store.setAuth(result.accessToken, result.user);
    store.setCart(await fetchCart(result.accessToken));
    setAuthOpen(false);
    setNotice(t("authSuccess"));
  };

  const logout = () => {
    store.setAuth("", null);
    setCartOpen(false);
    setNotice(t("loggedOut"));
  };

  const emptyCart = async () => {
    if (!store.accessToken) return;
    try {
      await clearCart(store.accessToken);
      store.setCart([]);
    } catch (error) { setNotice(error instanceof Error ? error.message : t("clearCartFailed")); }
  };

  return (
    <div className="min-h-screen bg-paper text-ink">
      <Header
        cartCount={store.cart.reduce((count, item) => count + item.quantity, 0)}
        user={store.user}
        onAuth={() => setAuthOpen(true)}
        onLogout={logout}
        onStylist={() => setStylistOpen(true)}
        onBrowse={browse}
        onCart={() => setCartOpen(true)}
      />
      <main>
        <Hero products={store.products} total={total} onStylist={() => setStylistOpen(true)} />
        <section className="mx-auto max-w-[1600px] px-4 py-16 sm:px-6 lg:px-10 lg:py-24">
          <BrowseControls facets={facets} query={query} onChange={(patch) => setQuery((current) => ({ ...current, ...patch }))} />
          {loading && <p className="mb-4 text-xs text-muted">{t("loading")}</p>}
          <ProductGrid products={store.products} total={total} compareIds={store.compareIds} onCompare={store.toggleCompare} onAdd={add} onDetail={showDetail} />
          {total > (query.pageSize || 12) && <div className="mt-12 flex items-center justify-center gap-4 text-xs">
            <button disabled={(query.page || 1) <= 1} onClick={() => setQuery((current) => ({ ...current, page: (current.page || 1) - 1 }))} className="border border-ink/15 px-4 py-2 disabled:opacity-30">{t("previous")}</button>
            <span>{t("page", { current: query.page || 1, total: Math.ceil(total / (query.pageSize || 12)) })}</span>
            <button disabled={(query.page || 1) >= Math.ceil(total / (query.pageSize || 12))} onClick={() => setQuery((current) => ({ ...current, page: (current.page || 1) + 1 }))} className="border border-ink/15 px-4 py-2 disabled:opacity-30">{t("next")}</button>
          </div>}
        </section>
      </main>

      {store.compareIds.length >= 2 && (
        <div className="fixed bottom-5 left-1/2 z-30 flex -translate-x-1/2 items-center gap-4 bg-ink px-5 py-3 text-white shadow-xl">
          <GitCompareArrows size={16} /><span className="text-xs">{t("selected", { count: store.compareIds.length })}</span>
          <button onClick={openCompare} className="border-l border-white/20 pl-4 text-[11px] uppercase tracking-wider text-[#f2d6d0]">{t("compareStart")}</button>
          <button onClick={store.clearCompare} className="text-[11px] text-white/55">{t("clear")}</button>
        </div>
      )}
      {notice && <button onClick={() => setNotice("")} className="fixed bottom-5 right-5 z-40 bg-paper px-4 py-3 text-xs shadow-xl ring-1 ring-ink/10">{notice}</button>}
      <CartDrawer
        open={cartOpen}
        cart={store.cart}
        authenticated={Boolean(store.user)}
        onClose={() => setCartOpen(false)}
        onLogin={() => { setCartOpen(false); setAuthOpen(true); }}
        onRemove={async (id) => {
          if (!store.accessToken) return;
          try {
            await removeCart(store.accessToken, id);
            store.setCart(await fetchCart(store.accessToken));
          } catch (error) {
            setNotice(error instanceof Error ? error.message : t("removeFailed"));
          }
        }}
        onClear={emptyCart}
      />
      <AuthDrawer open={authOpen} onClose={() => setAuthOpen(false)} onSubmit={authenticate} />
      <CompareDrawer open={compareOpen} products={store.comparison} onClose={() => setCompareOpen(false)} />
      <ProductDetailDrawer open={Boolean(detail)} product={detail} onClose={() => setDetail(null)} onAdd={add} />
      <StylistDrawer open={stylistOpen} onClose={() => setStylistOpen(false)} messages={store.messages} streaming={store.streaming} slots={store.slots} traces={store.traces} decision={store.decision} pendingAction={store.pendingAction} wardrobe={store.wardrobe} wardrobePlan={store.wardrobePlan} products={store.products} onPlanEdit={editWardrobePlan} onPlanAccept={acceptWardrobePlan} onConfirm={confirmPendingAction} onSubmit={submit} onCancel={cancelChat} />
    </div>
  );
}
