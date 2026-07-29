import { useState } from "react";
import { LogOut, Menu, MessageCircle, Search, ShoppingBag, UserRound, X } from "lucide-react";
import { useTranslation } from "../i18n";
import type { User } from "../types";

type Props = {
  cartCount: number;
  user: User | null;
  onAuth: () => void;
  onLogout: () => void;
  onCart: () => void;
  onStylist: () => void;
  onBrowse: (indexGroup?: string) => void;
};

export function Header({ cartCount, user, onAuth, onLogout, onCart, onStylist, onBrowse }: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const { language, setLanguage, t } = useTranslation();
  const links: [string, string | undefined][] = [[t("allProducts"), undefined], [t("women"), "Ladieswear"], [t("men"), "Menswear"], [t("kids"), "Baby/Children"]];
  return (
    <>
      <div className="overflow-hidden whitespace-nowrap bg-ink px-4 py-2 text-center text-[8px] uppercase tracking-[.18em] text-white sm:text-[9px] sm:tracking-[.22em]">
        {t("announcement")}
      </div>
      <header className="sticky top-0 z-40 border-b border-ink/10 bg-paper/95 backdrop-blur-md">
        <div className="mx-auto grid h-[72px] max-w-[1600px] grid-cols-[1fr_auto_1fr] items-center px-5 lg:px-10">
          <nav className="hidden items-center gap-7 lg:flex">
            {links.map(([item, group]) => (
              <button key={item} onClick={() => onBrowse(group)} className="nav-link">{item}</button>
            ))}
          </nav>
          <button onClick={() => setMenuOpen((value) => !value)} className="justify-self-start p-2 lg:hidden" aria-label={t("menu")}>{menuOpen ? <X size={20} /> : <Menu size={20} />}</button>
          <div className="text-center">
            <div className="font-display text-[22px] tracking-[.28em]">ATELIER</div>
            <div className="mt-0.5 text-[7px] uppercase tracking-[.34em] text-muted">Objects of style</div>
          </div>
          <div className="flex items-center justify-end gap-1 sm:gap-2">
            <button onClick={() => setLanguage(language === "zh" ? "en" : "zh")} className="px-2 py-2 font-mono text-[10px]" aria-label="Language">{language === "zh" ? "EN" : "中文"}</button>
            <button onClick={() => onBrowse()} className="icon-button icon-button-hidden" aria-label={t("search")}><Search size={18} strokeWidth={1.4} /></button>
            <button className="icon-button icon-button-hidden" onClick={onStylist} aria-label={t("openStylist")}><MessageCircle size={18} strokeWidth={1.4} /></button>
            <button className="icon-button icon-button-hidden" onClick={user ? onLogout : onAuth} aria-label={user ? t("logout") : t("login")}>
              {user ? <LogOut size={17} strokeWidth={1.4} /> : <UserRound size={17} strokeWidth={1.4} />}
            </button>
            <button className="icon-button relative" onClick={onCart} aria-label={t("openCart")}>
              <ShoppingBag size={18} strokeWidth={1.4} />
              {cartCount > 0 && <span className="absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-accent px-1 text-[9px] text-white">{cartCount}</span>}
            </button>
          </div>
        </div>
        {menuOpen && <nav className="border-t border-ink/10 bg-paper px-5 py-4 lg:hidden">{links.map(([item, group]) => <button key={item} onClick={() => { onBrowse(group); setMenuOpen(false); }} className="block w-full border-b border-ink/10 py-3 text-left text-xs uppercase tracking-wider">{item}</button>)}</nav>}
      </header>
    </>
  );
}
