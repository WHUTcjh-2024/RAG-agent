import { FormEvent, useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, Check, Minus, ShoppingBag, UserRound, Wifi, WifiOff, X } from "lucide-react";
import { useTranslation } from "../i18n";
import { motionTokens } from "../motion/tokens";
import type { CartItem } from "../types";

function SpatialShell({ open, title, onClose, children }: { open: boolean; title: string; onClose: () => void; children: React.ReactNode }) {
  const { t } = useTranslation();
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="overlay-root" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <motion.button className="overlay-scrim" onClick={onClose} aria-label={t("close")} initial={{ backdropFilter: "blur(0px)" }} animate={{ backdropFilter: "blur(8px)" }} />
          <motion.aside className="spatial-drawer" initial={{ x: "104%", rotateY: -3 }} animate={{ x: 0, rotateY: 0 }} exit={{ x: "104%", rotateY: -3 }} transition={motionTokens.spring.drawer}>
            <header><div><span>PRIVATE SERVICE</span><h2>{title}</h2></div><button onClick={onClose} aria-label={t("close")}><X size={18} /></button></header>
            <div className="drawer-content">{children}</div>
          </motion.aside>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

type CartProps = {
  open: boolean;
  authenticated: boolean;
  cart: CartItem[];
  onClose: () => void;
  onLogin: () => void;
  onRemove: (id: string) => void;
  onClear: () => void;
};

export function CartDrawer({ open, authenticated, cart, onClose, onLogin, onRemove, onClear }: CartProps) {
  const { t } = useTranslation();
  const total = cart.reduce((sum, item) => sum + item.unitPrice * item.quantity, 0);
  return (
    <SpatialShell open={open} title={t("cart")} onClose={onClose}>
      {!authenticated ? (
        <div className="drawer-empty"><UserRound size={34} /><p>{t("loginForCart")}</p><button onClick={onLogin}>{t("login")}<ArrowRight size={15} /></button></div>
      ) : cart.length === 0 ? (
        <motion.div className="drawer-empty" initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }}><ShoppingBag size={34} /><p>{t("emptyCart")}</p></motion.div>
      ) : (
        <div className="cart-layout">
          <div className="cart-items">
            <AnimatePresence mode="popLayout">
              {cart.map((item) => (
                <motion.article layout key={item.id} initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 40, height: 0 }}>
                  <img src={item.productImageUrl || ""} alt={item.productName} />
                  <div><h3>{item.productName}</h3><p>{item.unitPrice.toFixed(4)} · × {item.quantity}</p><button onClick={() => onRemove(item.id)}><Minus size={12} />{t("remove")}</button></div>
                </motion.article>
              ))}
            </AnimatePresence>
          </div>
          <footer className="cart-footer"><div><span>Total</span><strong>{total.toFixed(4)}</strong></div><button onClick={onClear}>{t("clearCart")}</button></footer>
        </div>
      )}
    </SpatialShell>
  );
}

type AuthProps = {
  open: boolean;
  onClose: () => void;
  onSubmit: (mode: "login" | "register", credentials: { email: string; password: string; displayName?: string }) => Promise<void>;
};

export function AuthOverlay({ open, onClose, onSubmit }: AuthProps) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true); setError("");
    try {
      await onSubmit(mode, { email: String(data.get("email")), password: String(data.get("password")), displayName: String(data.get("displayName") || "") });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t("authFailed"));
    } finally { setBusy(false); }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div className="auth-root" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <button className="overlay-scrim" onClick={onClose} aria-label={t("close")} />
          <motion.section className="auth-card" initial={{ opacity: 0, scale: 0.94, y: 28 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.96, y: 18 }} transition={motionTokens.spring.drawer}>
            <button className="auth-close" onClick={onClose} aria-label={t("close")}><X size={18} /></button>
            <span>FITME ACCOUNT</span><h2>{mode === "login" ? t("login") : t("register")}</h2>
            <AnimatePresence mode="wait">
              <motion.form key={mode} onSubmit={submit} initial={{ opacity: 0, x: mode === "login" ? -14 : 14 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: mode === "login" ? 14 : -14 }}>
                {mode === "register" && <label><span>{t("displayName")}</span><input name="displayName" aria-label={t("displayName")} required minLength={2} /></label>}
                <label><span>{t("email")}</span><input name="email" aria-label={t("email")} type="email" required autoComplete="email" /></label>
                <label><span>{t("password")}</span><input name="password" aria-label={t("password")} type="password" required minLength={8} autoComplete={mode === "login" ? "current-password" : "new-password"} /></label>
                {error && <motion.p className="form-error" initial={{ x: -8 }} animate={{ x: [0, 5, -4, 0] }}>{error}</motion.p>}
                <motion.button whileTap={{ scale: motionTokens.scale.press }} disabled={busy}>{busy ? <span className="button-loader" /> : mode === "login" ? t("login") : t("register")}</motion.button>
              </motion.form>
            </AnimatePresence>
            <button className="auth-mode" onClick={() => setMode((value) => value === "login" ? "register" : "login")}>{mode === "login" ? t("needAccount") : t("haveAccount")}</button>
          </motion.section>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export type Flight = { key: number; image: string; origin: DOMRect; target: DOMRect };

export function CartFlight({ flight }: { flight: Flight | null }) {
  return <AnimatePresence>{flight && <motion.img key={flight.key} className="cart-flight" src={flight.image} alt="" initial={{ left: flight.origin.left, top: flight.origin.top, width: flight.origin.width, height: flight.origin.height, opacity: 0.9, scale: 1 }} animate={{ left: flight.target.left, top: flight.target.top, width: flight.target.width, height: flight.target.height, opacity: 0.1, scale: 0.25, rotate: 5 }} exit={{ opacity: 0 }} transition={{ duration: 0.58, ease: motionTokens.easing.enter }} />}</AnimatePresence>;
}

export function NetworkNotice() {
  const { t } = useTranslation();
  const [online, setOnline] = useState(navigator.onLine);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const update = () => { setOnline(navigator.onLine); setVisible(true); window.setTimeout(() => setVisible(false), 3200); };
    window.addEventListener("online", update); window.addEventListener("offline", update);
    return () => { window.removeEventListener("online", update); window.removeEventListener("offline", update); };
  }, []);
  return <AnimatePresence>{visible && <motion.div className={online ? "network-notice is-online" : "network-notice"} initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 18, opacity: 0 }}>{online ? <Wifi size={14} /> : <WifiOff size={14} />}{online ? t("networkOnline") : t("networkOffline")}{online && <Check size={13} />}</motion.div>}</AnimatePresence>;
}
