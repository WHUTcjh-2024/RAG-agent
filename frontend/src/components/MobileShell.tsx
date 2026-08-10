import { AnimatePresence, motion } from "motion/react";
import { Compass, Home, ShoppingBag, UserRound } from "lucide-react";
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
  "/wardrobe": ["我的收藏", "Saved items"],
  "/agent": ["图片找同款", "Image search"],
  "/discover": ["商品列表", "Products"],
  "/profile": ["我的", "Profile"],
  "/orders": ["我的订单", "Orders"],
  "/compare": ["单品对比", "Compare"]
};

export function AppTopBar({ pathname, user, cartCount, onCart, onProfile }: TopBarProps) {
  const { language } = useTranslation();
  const title = titles[pathname]?.[language === "zh" ? 0 : 1];
  const firstName = user?.displayName?.split(" ")[0];
  return (
    <header className="app-topbar">
      <div className="app-topbar-copy">
        {pathname === "/" ? <><strong className="app-logo">FitMe<i>✦</i></strong><p>{firstName ? (language === "zh" ? `你好，${firstName}` : `Hi, ${firstName}`) : (language === "zh" ? "发现你的日常灵感" : "Welcome")}</p></> : <><span>{language === "zh" ? "FitMe 精选" : "FITME"}</span><h1>{title || (language === "zh" ? "FitMe" : "FitMe")}</h1></>}
      </div>
      <div className="app-topbar-actions">
        <button onClick={onProfile} aria-label="个人中心"><UserRound size={18} /></button>
        <button className="topbar-cart" data-cart-target onClick={onCart} aria-label={language === "zh" ? "顶部购物车" : "Top cart"}><ShoppingBag size={18} />
          <AnimatePresence>{cartCount > 0 && <motion.i initial={{ scale: 0 }} animate={{ scale: 1 }} exit={{ scale: 0 }}>{cartCount}</motion.i>}</AnimatePresence>
        </button>
      </div>
    </header>
  );
}

const navigation = [
  { path: "/", zh: "首页", en: "Home", icon: Home },
  { path: "/discover", zh: "商品", en: "Products", icon: Compass },
  { path: "/profile", zh: "我的", en: "Account", icon: UserRound }
];

export function BottomNavigation({ pathname, onNavigate, onCart }: { pathname: string; onNavigate: (path: string) => void; onCart: () => void }) {
  const { language, t } = useTranslation();
  return (
    <nav className="bottom-navigation" aria-label={language === "zh" ? "主要导航" : "Main navigation"}>
      {navigation.slice(0, 2).map(({ path, zh, en, icon: Icon }) => {
        const active = pathname === path || (path === "/discover" && pathname.startsWith("/product/"));
        return <button key={path} className={active ? "is-active" : ""} aria-current={active ? "page" : undefined} onClick={() => onNavigate(path)}>
          <span><Icon size={19} />{active && <motion.i layoutId="app-nav-active" />}</span><small>{language === "zh" ? zh : en}</small>
        </button>;
      })}
      <button className="bottom-cart" data-cart-target onClick={onCart} aria-label={t("openCart")}><span><ShoppingBag size={19} /></span><small>{language === "zh" ? "购物车" : "Cart"}</small></button>
      {navigation.slice(2).map(({ path, zh, en, icon: Icon }) => {
        const active = pathname === path;
        return <button key={path} className={active ? "is-active" : ""} aria-current={active ? "page" : undefined} onClick={() => onNavigate(path)}><span><Icon size={19} />{active && <motion.i layoutId="app-nav-active" />}</span><small>{language === "zh" ? zh : en}</small></button>;
      })}
    </nav>
  );
}
