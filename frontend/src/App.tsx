import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, LayoutGroup, motion } from "motion/react";
import { GitCompareArrows, X } from "lucide-react";
import { createClientId } from "./utils/clientId";
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
  fetchSession,
  fetchWardrobe,
  login,
  productImage,
  recordAgentActionCompletion,
  recordWardrobeFeedback,
  register,
  removeCart,
  replanWardrobe,
  streamChat
} from "./api/client";
import { CartDrawer, AuthOverlay, CartFlight, NetworkNotice, type Flight } from "./components/CommerceOverlays";
import { HomeScreen } from "./components/HomeScreen";
import { AppTopBar, BottomNavigation } from "./components/MobileShell";
import { ProductCollection } from "./components/ProductCollection";
import { ProfileScreen } from "./components/ProfileScreen";
import { WardrobeScreen } from "./components/WardrobeScreen";
import { useTranslation } from "./i18n";
import { useMotionSystem } from "./motion/MotionSystem";
import { PageTransition } from "./motion/PageTransition";
import { motionTokens } from "./motion/tokens";
import { useAppStore } from "./store/useAppStore";
import type { AgentNodeEvent, AgentPhase, DecisionEvidence, Product, ProductFacets, ProductQuery } from "./types";

type ViewTransitionDocument = Document & { startViewTransition?: (update: () => void) => { finished: Promise<void> } };
type AgentViewState = "idle" | AgentPhase;

const AgentWorkspace = lazy(() => import("./components/AgentWorkspace").then((module) => ({ default: module.AgentWorkspace })));
const CompareWorkspace = lazy(() => import("./components/CompareWorkspace").then((module) => ({ default: module.CompareWorkspace })));
const ProductDetail = lazy(() => import("./components/ProductDetail").then((module) => ({ default: module.ProductDetail })));

export default function App() {
  const { language, t } = useTranslation();
  const { reduced } = useMotionSystem();
  const store = useAppStore();
  const [pathname, setPathname] = useState(() => window.location.pathname);
  const [cartOpen, setCartOpen] = useState(false);
  const [authOpen, setAuthOpen] = useState(false);
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState<ProductQuery>({ page: 1, pageSize: 12, sort: "popular" });
  const [facets, setFacets] = useState<ProductFacets | null>(null);
  const [catalogProducts, setCatalogProducts] = useState<Product[]>([]);
  const [editorialProducts, setEditorialProducts] = useState<Product[]>([]);
  const [agentProducts, setAgentProducts] = useState<Product[]>([]);
  const [total, setTotal] = useState(0);
  const [detail, setDetail] = useState<Product | null>(null);
  const [loading, setLoading] = useState(true);
  const [flight, setFlight] = useState<Flight | null>(null);
  const [agentState, setAgentState] = useState<AgentViewState>("idle");
  const [agentEvents, setAgentEvents] = useState<AgentNodeEvent[]>([]);
  const [agentEvidence, setAgentEvidence] = useState<DecisionEvidence[]>([]);
  const [agentError, setAgentError] = useState("");
  const abortController = useRef<AbortController | null>(null);
  const activeTaskId = useRef<string | null>(null);
  const catalogRequest = useRef(0);
  const lastAgentRequest = useRef<{ message: string; image: File | null; preview: string | null } | null>(null);

  const transitionNavigate = useCallback((to: string | number) => {
    const update = () => {
      if (typeof to === "number") history.go(to);
      else {
        if (window.location.pathname !== to) history.pushState({}, "", to);
        setPathname(to);
        window.scrollTo({ top: 0, behavior: reduced ? "auto" : "smooth" });
      }
    };
    const documentWithTransition = document as ViewTransitionDocument;
    if (!reduced && documentWithTransition.startViewTransition) documentWithTransition.startViewTransition(update);
    else update();
  }, [reduced]);

  useEffect(() => {
    const update = () => setPathname(window.location.pathname);
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  }, []);

  useEffect(() => {
    fetchFacets().then(setFacets).catch((error) => setNotice(error.message));
    fetchProducts({ page: 1, pageSize: 6, category: "Dress", sort: "popular" })
      .then((page) => setEditorialProducts(page.items))
      .catch(() => undefined);
    fetchSession(store.sessionId).then((session) => {
      const currentState = useAppStore.getState();
      if (currentState.messages.length === 0) {
        currentState.setSlots(session.slots);
        currentState.setMessages(session.history.map((item) => ({ ...item, id: createClientId() })));
      }
    }).catch(() => undefined);
    if (store.accessToken) {
      Promise.all([fetchCurrentUser(store.accessToken), fetchCart(store.accessToken)])
        .then(([user, cart]) => { store.setAuth(store.accessToken, user); store.setCart(cart); })
        .catch(() => store.setAuth("", null));
      fetchWardrobe(store.accessToken).then(store.setWardrobe).catch(() => undefined);
    }
  }, []);

  useEffect(() => {
    const request = ++catalogRequest.current;
    setLoading(true);
    const timer = window.setTimeout(() => {
      fetchProducts(query).then((page) => {
        if (request !== catalogRequest.current) return;
        setCatalogProducts(page.items); store.setProducts(page.items); setTotal(page.total);
      }).catch((error) => setNotice(error.message)).finally(() => {
        if (request === catalogRequest.current) setLoading(false);
      });
    }, query.search ? 240 : 0);
    return () => window.clearTimeout(timer);
  }, [query]);

  const productId = pathname.startsWith("/product/") ? decodeURIComponent(pathname.slice("/product/".length)) : "";
  useEffect(() => {
    const id = productId;
    if (!id || detail?.article_id === id) return;
    const existing = [...catalogProducts, ...agentProducts].find((product) => product.article_id === id);
    if (existing) setDetail(existing);
    fetchProduct(id).then(setDetail).catch((error) => setNotice(error.message));
  }, [productId]);

  const changeQuery = (patch: Partial<ProductQuery>) => setQuery((current) => ({ ...current, ...patch }));
  const clearQuery = () => setQuery({ page: 1, pageSize: query.pageSize || 12, sort: query.sort || "popular" });

  const showDetail = async (id: string) => {
    const existing = [...catalogProducts, ...agentProducts].find((product) => product.article_id === id);
    if (existing) setDetail(existing);
    transitionNavigate(`/product/${encodeURIComponent(id)}`);
    try { setDetail(await fetchProduct(id)); }
    catch (error) { setNotice(error instanceof Error ? error.message : t("detailFailed")); }
  };

  const add = async (id: string, origin: DOMRect): Promise<boolean> => {
    if (!store.accessToken || !store.user) {
      setAuthOpen(true); setNotice(t("loginForCart")); return false;
    }
    try {
      const product = [...catalogProducts, ...agentProducts].find((item) => item.article_id === id)
        || (detail?.article_id === id ? detail : await fetchProduct(id));
      await addCart(store.accessToken, product);
      store.setCart(await fetchCart(store.accessToken));
      const target = document.querySelector("[data-cart-target]")?.getBoundingClientRect();
      if (target && !reduced) {
        setFlight({ key: Date.now(), image: productImage(product), origin, target });
        window.setTimeout(() => setFlight(null), 650);
      }
      setNotice(t("added")); return true;
    } catch (error) {
      setNotice(error instanceof Error ? error.message : t("addFailed")); return false;
    }
  };

  const openCompare = async () => {
    if (store.compareIds.length < 2) return;
    try {
      const result = await compareProducts(store.compareIds);
      store.setComparison(result.products);
      transitionNavigate("/compare");
    } catch (error) { setNotice(error instanceof Error ? error.message : t("compareFailed")); }
  };

  const submitAgent = async (message: string, image: File | null, preview: string | null) => {
    const requestMessage = message || t("similarImage");
    lastAgentRequest.current = { message, image, preview };
    store.addMessage({ id: createClientId(), role: "user", content: requestMessage, imagePreview: preview || undefined });
    store.resetExecution();
    store.setStreaming(true); setAgentState("understanding"); setAgentEvents([]); setAgentEvidence([]); setAgentProducts([]); setAgentError("");
    activeTaskId.current = null;
    abortController.current = new AbortController();
    let semanticBuffer = "";
    let semanticTimer: number | undefined;
    const flush = () => {
      if (!semanticBuffer) return;
      store.appendAssistant(semanticBuffer); semanticBuffer = "";
      if (semanticTimer) window.clearTimeout(semanticTimer);
      semanticTimer = undefined;
    };
    const enqueue = (delta: string) => {
      semanticBuffer += delta;
      if (semanticBuffer.length >= 42 || /[。！？.!?]\s*$/.test(semanticBuffer)) flush();
      else if (!semanticTimer) semanticTimer = window.setTimeout(flush, 64);
    };

    try {
      await streamChat(message, store.sessionId, image, language, {
        onStatus: ({ taskId }) => { if (taskId) activeTaskId.current = taskId; },
        onTaskId: (taskId) => { activeTaskId.current = taskId; },
        onNode: (event) => {
          setAgentEvents((events) => {
            const repeated = event.state === "started" && events.some((item) => item.node === event.node && item.state === "started");
            setAgentState(repeated ? "retrying" : event.state === "failed" ? "failure" : event.phase);
            return [...events, event].slice(-40);
          });
        },
        onMeta: ({ slots, task_id }) => { activeTaskId.current = task_id; store.setSlots(slots); },
        onTool: (trace) => { store.addTrace(trace); setAgentState("tool"); },
        onProducts: (products) => { setAgentProducts(products); setAgentState("retrieval"); },
        onComparison: (products) => { store.setComparison(products); setAgentState("comparison"); },
        onEvidence: (evidence) => { setAgentEvidence((items) => [...items, evidence]); setAgentState("verification"); },
        onDecision: store.setDecision,
        onConfirmRequired: (action) => { store.setPendingAction(action); setAgentState("waiting"); },
        onWardrobePlan: store.setWardrobePlan,
        onMessage: (delta) => { setAgentState("generation"); enqueue(delta); },
        onDone: () => { flush(); setAgentState("success"); },
        onError: (error) => { setAgentError(error); setAgentState("failure"); }
      }, store.accessToken, abortController.current.signal);
      flush();
    } catch (error) {
      flush();
      if (error instanceof DOMException && error.name === "AbortError") { setAgentState("cancelled"); return; }
      const text = error instanceof Error ? error.message : t("requestFailed");
      setAgentError(text); setAgentState("failure");
    } finally {
      if (semanticTimer) window.clearTimeout(semanticTimer);
      flush(); abortController.current = null; activeTaskId.current = null; store.setStreaming(false);
    }
  };

  const cancelAgent = () => {
    const taskId = activeTaskId.current;
    abortController.current?.abort(); setAgentState("cancelled");
    if (taskId) cancelAgentTask(store.accessToken, taskId, store.sessionId).catch(() => undefined);
  };

  const retryAgent = () => {
    if (!lastAgentRequest.current || store.streaming) return;
    setAgentState("retrying");
    const request = lastAgentRequest.current;
    window.setTimeout(() => submitAgent(request.message, request.image, request.preview), 180);
  };

  const confirmPendingAction = async () => {
    if (!store.accessToken || !store.pendingAction) return;
    try {
      const item = await confirmAgentCartAction(store.accessToken, store.pendingAction);
      await recordAgentActionCompletion(store.accessToken, store.pendingAction.action_id, item.id);
      store.setCart(await fetchCart(store.accessToken)); store.setPendingAction(null); setAgentState("success"); setNotice(t("added"));
    } catch (error) { setAgentError(error instanceof Error ? error.message : t("addFailed")); setAgentState("failure"); }
  };

  const editWardrobePlan = async (operation: Record<string, unknown>) => {
    if (!store.accessToken || !store.wardrobePlan) return;
    try {
      store.setWardrobePlan(await replanWardrobe(store.accessToken, store.wardrobePlan.plan_id, store.wardrobePlan, operation));
      store.setWardrobe(await fetchWardrobe(store.accessToken));
    } catch (error) { setAgentError(error instanceof Error ? error.message : t("requestFailed")); }
  };

  const acceptWardrobePlan = async () => {
    if (!store.accessToken || !store.wardrobePlan) return;
    try { await recordWardrobeFeedback(store.accessToken, { planRef: store.wardrobePlan.plan_id, outcome: "ADOPTED" }); setNotice(t("adoptPlan")); }
    catch (error) { setAgentError(error instanceof Error ? error.message : t("requestFailed")); }
  };

  const authenticate = async (mode: "login" | "register", credentials: { email: string; password: string; displayName?: string }) => {
    const result = mode === "login" ? await login(credentials.email, credentials.password) : await register(credentials.email, credentials.password, credentials.displayName || "");
    store.setAuth(result.accessToken, result.user); store.setCart(await fetchCart(result.accessToken)); setAuthOpen(false); setNotice(t("authSuccess"));
  };

  const logout = () => { store.setAuth("", null); setCartOpen(false); setNotice(t("loggedOut")); };
  const emptyCart = async () => {
    if (!store.accessToken) return;
    try { await clearCart(store.accessToken); store.setCart([]); }
    catch (error) { setNotice(error instanceof Error ? error.message : t("clearCartFailed")); }
  };

  const collection = (
    <ProductCollection
      products={catalogProducts} total={total} loading={loading} facets={facets} query={query} compareIds={store.compareIds}
      onChange={changeQuery} onClear={clearQuery} onCompare={store.toggleCompare} onAdd={add} onDetail={showDetail}
    />
  );

  const loadingPage = <div className="page-loading"><span />{t("loading")}</div>;
  const appProducts = editorialProducts.length ? editorialProducts : catalogProducts;
  const pageContent = pathname === "/" ? (
    <HomeScreen products={appProducts} agentState={agentState} events={agentEvents} wardrobe={store.wardrobe} onAgent={() => transitionNavigate("/agent")} onWardrobe={() => transitionNavigate("/wardrobe")} onDiscover={() => transitionNavigate("/discover")} onDetail={showDetail} />
  ) : pathname === "/wardrobe" ? (
    <WardrobeScreen user={store.user} wardrobe={store.wardrobe} inspiration={[...appProducts, ...catalogProducts]} onLogin={() => setAuthOpen(true)} onDetail={showDetail} />
  ) : pathname === "/discover" ? (
    collection
  ) : pathname === "/profile" ? (
    <ProfileScreen user={store.user} cartCount={store.cart.reduce((count, item) => count + item.quantity, 0)} wardrobeCount={store.wardrobe?.items.length || 0} compareCount={store.compareIds.length} onAuth={() => setAuthOpen(true)} onLogout={logout} />
  ) : pathname.startsWith("/product/") ? (
    <Suspense fallback={loadingPage}>{detail ? <ProductDetail product={detail} onClose={() => transitionNavigate(-1)} onAdd={add} onAskAgent={(message) => { lastAgentRequest.current = { message, image: null, preview: null }; transitionNavigate("/agent"); window.setTimeout(() => submitAgent(message, null, null), 420); }} /> : loadingPage}</Suspense>
  ) : pathname === "/compare" ? (
    <Suspense fallback={loadingPage}><CompareWorkspace products={store.comparison.length ? store.comparison : catalogProducts.filter((product) => store.compareIds.includes(product.article_id))} onClose={() => transitionNavigate("/discover")} onRemove={store.toggleCompare} onDetail={showDetail} /></Suspense>
  ) : pathname === "/agent" ? (
    <Suspense fallback={loadingPage}><AgentWorkspace messages={store.messages} streaming={store.streaming} state={agentState} events={agentEvents} slots={store.slots} traces={store.traces} products={agentProducts} evidence={agentEvidence} decision={store.decision} pendingAction={store.pendingAction} wardrobe={store.wardrobe} wardrobePlan={store.wardrobePlan} error={agentError} onClose={() => transitionNavigate("/")} onSubmit={submitAgent} onCancel={cancelAgent} onRetry={retryAgent} onConfirm={confirmPendingAction} onPlanAccept={acceptWardrobePlan} onPlanEdit={editWardrobePlan} onDetail={showDetail} /></Suspense>
  ) : (
    <HomeScreen products={appProducts} agentState={agentState} events={agentEvents} wardrobe={store.wardrobe} onAgent={() => transitionNavigate("/agent")} onWardrobe={() => transitionNavigate("/wardrobe")} onDiscover={() => transitionNavigate("/discover")} onDetail={showDetail} />
  );

  const rootScreen = ["/", "/wardrobe", "/agent", "/discover", "/profile"].includes(pathname);
  const cartCount = store.cart.reduce((count, item) => count + item.quantity, 0);

  return (
    <LayoutGroup>
      <div className={`app-shell route-${pathname.split("/")[1] || "home"}`}>
        {rootScreen && pathname !== "/agent" && <AppTopBar pathname={pathname} user={store.user} cartCount={cartCount} onCart={() => setCartOpen(true)} onProfile={() => transitionNavigate("/profile")} />}
        <AnimatePresence mode="wait" initial={false}>
          <PageTransition key={pathname}>{pageContent}</PageTransition>
        </AnimatePresence>

        {rootScreen && <BottomNavigation pathname={pathname} onNavigate={transitionNavigate} />}

        <AnimatePresence>
          {store.compareIds.length >= 2 && !pathname.startsWith("/compare") && (
            <motion.div className="compare-tray" initial={{ y: 90, x: "-50%", opacity: 0 }} animate={{ y: 0, x: "-50%", opacity: 1 }} exit={{ y: 80, x: "-50%", opacity: 0 }} transition={motionTokens.spring.drawer}>
              <GitCompareArrows size={15} />
              <div>{catalogProducts.filter((product) => store.compareIds.includes(product.article_id)).map((product) => <motion.img layoutId={`compare-thumb-${product.article_id}`} key={product.article_id} src={productImage(product)} alt="" />)}</div>
              <span>{t("selected", { count: store.compareIds.length })}</span><button onClick={openCompare}>{t("compareStart")}</button><button onClick={store.clearCompare} aria-label={t("clear")}><X size={14} /></button>
            </motion.div>
          )}
        </AnimatePresence>

        <CartDrawer open={cartOpen} authenticated={Boolean(store.user)} cart={store.cart} onClose={() => setCartOpen(false)} onLogin={() => { setCartOpen(false); setAuthOpen(true); }} onRemove={async (id) => { if (!store.accessToken) return; try { await removeCart(store.accessToken, id); store.setCart(await fetchCart(store.accessToken)); } catch (error) { setNotice(error instanceof Error ? error.message : t("removeFailed")); } }} onClear={emptyCart} />
        <AuthOverlay open={authOpen} onClose={() => setAuthOpen(false)} onSubmit={authenticate} />
        <CartFlight flight={flight} />
        <NetworkNotice />
        <AnimatePresence>{notice && <motion.button className="toast" onClick={() => setNotice("")} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 12 }}>{notice}<span>×</span></motion.button>}</AnimatePresence>
      </div>
    </LayoutGroup>
  );
}
