import { ChevronRight, CircleUserRound, GitCompareArrows, LogIn, ReceiptText, ShoppingCart } from "lucide-react";
import { useTranslation } from "../i18n";
import type { User } from "../types";

export function ProfileScreen({ user, cartCount, compareCount, onAuth, onLogout, onOrders }: { user: User | null; cartCount: number; compareCount: number; onAuth: () => void; onLogout: () => void; onOrders: () => void }) {
  const { language } = useTranslation();
  const zh = language === "zh";
  return <main className="profile-screen app-screen">
    <section className="profile-identity app-card"><span><CircleUserRound size={32} /></span><div><h2>{user?.displayName || (zh ? "欢迎来到 FitMe" : "Welcome")}</h2><p>{user?.email || (zh ? "登录后可使用购物车和订单功能" : "Sign in")}</p></div><button onClick={user ? onLogout : onAuth}>{user ? (zh ? "退出登录" : "Log out") : <><LogIn size={15} />{zh ? "登录" : "Sign in"}</>}</button></section>
    <section className="profile-metrics app-card"><div><ShoppingCart size={18} /><strong>{cartCount}</strong><span>{zh ? "购物车商品" : "Cart items"}</span></div><div><GitCompareArrows size={18} /><strong>{compareCount}</strong><span>{zh ? "对比商品" : "Compared"}</span></div></section>
    <section className="profile-list app-card"><h3>账户与设置</h3><button onClick={user ? onOrders : onAuth}><span><ReceiptText size={17} />我的订单</span><ChevronRight size={15} /></button></section>
  </main>;
}
