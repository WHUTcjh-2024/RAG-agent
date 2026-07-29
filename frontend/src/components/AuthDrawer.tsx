import { useState } from "react";
import { LoaderCircle, X } from "lucide-react";
import { useTranslation } from "../i18n";

type Credentials = {
  email: string;
  password: string;
  displayName?: string;
};

type Props = {
  open: boolean;
  onClose: () => void;
  onSubmit: (mode: "login" | "register", credentials: Credentials) => Promise<void>;
};

export function AuthDrawer({ open, onClose, onSubmit }: Props) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (!open) return null;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await onSubmit(mode, { email, password, displayName });
      setPassword("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t("authFailed"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50">
      <button onClick={onClose} className="absolute inset-0 bg-ink/35 backdrop-blur-[2px]" aria-label={t("close")} />
      <aside className="absolute right-0 top-0 flex h-full w-full max-w-md flex-col bg-paper shadow-2xl animate-slide-in">
        <div className="flex h-16 items-center justify-between border-b border-ink/10 px-6">
          <h2 className="font-display text-2xl">{mode === "login" ? t("login") : t("register")}</h2>
          <button className="icon-button" onClick={onClose} aria-label={t("close")}><X size={18} /></button>
        </div>
        <form onSubmit={submit} className="space-y-5 p-6">
          {mode === "register" && (
            <label className="block text-xs">
              <span className="mb-2 block text-muted">{t("displayName")}</span>
              <input required maxLength={80} value={displayName} onChange={(event) => setDisplayName(event.target.value)} className="w-full border border-ink/15 bg-white px-3 py-3 outline-none" />
            </label>
          )}
          <label className="block text-xs">
            <span className="mb-2 block text-muted">{t("email")}</span>
            <input required type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} className="w-full border border-ink/15 bg-white px-3 py-3 outline-none" />
          </label>
          <label className="block text-xs">
            <span className="mb-2 block text-muted">{t("password")}</span>
            <input required minLength={8} type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} value={password} onChange={(event) => setPassword(event.target.value)} className="w-full border border-ink/15 bg-white px-3 py-3 outline-none" />
          </label>
          {error && <p role="alert" className="text-xs text-accent">{error}</p>}
          <button disabled={submitting} className="flex w-full items-center justify-center gap-2 bg-ink px-5 py-4 text-xs uppercase tracking-[.18em] text-white disabled:opacity-50">
            {submitting && <LoaderCircle size={15} className="animate-spin" />}
            {mode === "login" ? t("login") : t("register")}
          </button>
          <button type="button" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }} className="w-full text-xs text-muted hover:text-ink">
            {mode === "login" ? t("needAccount") : t("haveAccount")}
          </button>
        </form>
      </aside>
    </div>
  );
}
