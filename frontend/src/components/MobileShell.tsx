import { AnimatePresence, motion } from "motion/react";
import { Bot, BriefcaseBusiness, Compass, Home, Languages, ShoppingBag, UserRound } from "lucide-react";
import { useTranslation } from "../i18n";
import type { User } from "../types";

type TopBarProps = {
  pathname: string;
  user: User | null;
  cartCount: number;
  onCart: () => void;
  onProfile: () => void;
};

const titles: Record<string, [string, string]> = {
  "/wardrobe": ["我的衣橱", "Wardrobe"],
  "/agent": ["FitMe Agent", "FitMe Agent"],
  "/discover": ["发现单品", "Discover"],
  "/profile": ["我的", "Profile"],
  "/compare": ["单品对比", "Compare"]
};

export function AppTopBar({ pathname, user, cartCount, onCart, onProfile }: TopBarProps) {
  const { language, setLanguage, t } = useTranslation();
  const title = titles[pathname]?.[language === "zh" ? 0 : 1];
  const firstName = user?.displayName?.split(" ")[0] || (language === "zh" ? "朋友" : "there");
  return (
    <header className="app-topbar">
      <div className="app-topbar-copy">
        {pathname === "/" ? <><strong className="app-logo">FitMe<i>✦</i></strong><p>{language === "zh" ? `你好，${firstName}` : `Hi, ${firstName}`}</p></> : <><span>{language === "zh" ? "智能穿搭助手" : "AI STYLE ASSISTANT"}</span><h1>{title || (language === "zh" ? "FitMe" : "FitMe")}</h1></>}
      </div>
      <div className="app-topbar-actions">
        <button onClick={() => setLanguage(language === "zh" ? "en" : "zh")} aria-label="Language"><Languages size={18} /></button>
        <button onClick={onProfile} aria-label={language === "zh" ? "个人中心" : "Profile"}><UserRound size={18} /></button>
        <button className="topbar-cart" onClick={onCart} aria-label={t("openCart")}><ShoppingBag size={18} />
          <AnimatePresence>{cartCount > 0 && <motion.i initial={{ scale: 0 }} animate={{ scale: 1 }} exit={{ scale: 0 }}>{cartCount}</motion.i>}</AnimatePresence>
        </button>
      </div>
    </header>
  );
}

const navigation = [
  { path: "/", zh: "首页", en: "Home", icon: Home },
  { path: "/wardrobe", zh: "衣橱", en: "Wardrobe", icon: BriefcaseBusiness },
  { path: "/agent", zh: "Agent", en: "Agent", icon: Bot, primary: true },
  { path: "/discover", zh: "发现", en: "Discover", icon: Compass },
  { path: "/profile", zh: "我的", en: "Profile", icon: UserRound }
];

export function BottomNavigation({ pathname, onNavigate }: { pathname: string; onNavigate: (path: string) => void }) {
  const { language } = useTranslation();
  return (
    <nav className="bottom-navigation" aria-label={language === "zh" ? "主要导航" : "Main navigation"}>
      {navigation.map(({ path, zh, en, icon: Icon, primary }) => {
        const active = pathname === path || (path === "/discover" && pathname.startsWith("/product/"));
        return <button key={path} data-testid={primary ? "open-stylist" : undefined} className={`${active ? "is-active" : ""}${primary ? " is-primary" : ""}`} aria-current={active ? "page" : undefined} onClick={() => onNavigate(path)}>
          <span><Icon size={primary ? 21 : 19} />{active && !primary && <motion.i layoutId="app-nav-active" />}</span><small>{language === "zh" ? zh : en}</small>
        </button>;
      })}
    </nav>
  );
}
