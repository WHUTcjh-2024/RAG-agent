import { ChevronRight, CircleUserRound, GitCompareArrows, Languages, LogIn, ShieldCheck, ShoppingBag, Sparkles } from "lucide-react";
import { useTranslation } from "../i18n";
import type { User } from "../types";

export function ProfileScreen({ user, cartCount, wardrobeCount, compareCount, onAuth, onLogout }: { user: User | null; cartCount: number; wardrobeCount: number; compareCount: number; onAuth: () => void; onLogout: () => void }) {
  const { language, setLanguage } = useTranslation();
  const zh = language === "zh";
  return <div className="profile-screen app-screen">
    <section className="profile-identity app-card"><span><CircleUserRound size={32} /></span><div><h2>{user?.displayName || (zh ? "欢迎使用 FitMe" : "Welcome to FitMe")}</h2><p>{user?.email || (zh ? "登录后同步衣橱和购物清单" : "Sign in to sync wardrobe and lists")}</p></div><button onClick={user ? onLogout : onAuth}>{user ? (zh ? "退出" : "Log out") : <><LogIn size={15} />{zh ? "登录" : "Sign in"}</>}</button></section>
    <section className="profile-metrics app-card"><div><ShoppingBag size={17} /><strong>{cartCount}</strong><span>{zh ? "购物清单" : "Cart"}</span></div><div><Sparkles size={17} /><strong>{wardrobeCount}</strong><span>{zh ? "衣橱" : "Wardrobe"}</span></div><div><GitCompareArrows size={17} /><strong>{compareCount}</strong><span>{zh ? "对比" : "Compare"}</span></div></section>
    <section className="profile-list app-card"><h3>{zh ? "应用设置" : "APP SETTINGS"}</h3><button onClick={() => setLanguage(language === "zh" ? "en" : "zh")}><span><Languages size={17} />{zh ? "界面语言" : "Language"}</span><small>{zh ? "中文" : "English"}</small><ChevronRight size={15} /></button><button><span><ShieldCheck size={17} />{zh ? "数据与隐私" : "Data & privacy"}</span><ChevronRight size={15} /></button></section>
    <section className="profile-capabilities"><span>{zh ? "Agent 能力" : "AGENT CAPABILITIES"}</span><h3>{zh ? "不是聊天机器人，是你的穿搭执行助手" : "Not a chatbot. Your style execution assistant."}</h3><div><p><i>01</i>{zh ? "理解需求与提取约束" : "Understand and structure needs"}</p><p><i>02</i>{zh ? "检索商品与知识库" : "Retrieve catalog and knowledge"}</p><p><i>03</i>{zh ? "比较参数与验证依据" : "Compare and verify evidence"}</p><p><i>04</i>{zh ? "规划衣橱与确认购买" : "Plan wardrobe and confirm actions"}</p></div></section>
  </div>;
}
