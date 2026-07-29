import { create } from "zustand";

export type Language = "zh" | "en";

const messages = {
  zh: {
    announcement: "免费造型服务 · 本地精选版", allProducts: "全部商品", women: "女装", men: "男装", kids: "童装",
    menu: "菜单", search: "搜索", openStylist: "打开私人顾问", openCart: "打开购物袋", personalEdit: "私人精选",
    pieces: "件单品", curated: "为真实生活精选", heroTitle: "安静的单品，\n清晰的主张。", heroCopy: "让私人顾问从 5,000 件真实商品中，按你的场景、颜色与参考图片建立专属衣橱提案。", consult: "咨询私人顾问",
    collection: "精选系列", essentials: "值得考虑的日常单品", items: "件商品", loading: "正在加载商品…",
    searchPlaceholder: "搜索商品名称或描述", allCategories: "全部分类", allColors: "全部颜色", allCollections: "全部系列",
    category: "分类", color: "颜色", collectionLabel: "系列", sort: "排序", popular: "热度优先", nameSort: "名称排序", idSort: "商品编号", maxPrice: "最高数据集价格",
    previous: "上一页", next: "下一页", page: "第 {current} / {total} 页", selected: "已选择 {count} 件", compareStart: "开始对比", clear: "清除",
    close: "关闭", cart: "购物袋", remove: "移除", emptyCart: "购物袋还是空的",
    compare: "单品对比", addCompare: "加入对比", viewDetails: "查看 {name} 详情", match: "匹配", dataPriceShort: "数据价格", group: "分组", detail: "商品详情", noDescription: "暂无商品描述", inventory: "库存", sizes: "尺码", unavailable: "数据源未提供", datasetPrice: "数据集价格", addCart: "加入购物袋",
    chatIntro: "描述场景与偏好，或上传参考图片。顾问只会推荐目录中真实存在的商品。", dressingFor: "你在为什么场合穿搭？", chatHelp: "可描述场景、颜色、风格与预算，也可以上传一张参考图片。",
    prompt1: "适合夏天通勤的白色衬衫", prompt2: "简约但有质感的约会穿搭", prompt3: "帮我找类似图片的款式", uploadAlt: "上传参考", preview: "预览", visualSearch: "将用于视觉相似检索", upload: "上传图片", request: "导购需求", chatPlaceholder: "描述你想找的单品或场景…", send: "发送",
    currentBrief: "当前需求", trace: "服务轨迹", preferenceHint: "你的偏好会随对话逐步形成。", traceHint: "检索和工具调用将在这里透明展示。", appointment: "私人预约", stylist: "Atelier 私人顾问",
    added: "已加入购物袋", requestFailed: "请求失败", unable: "暂时无法完成请求：", addFailed: "加购失败", compareFailed: "对比失败", detailFailed: "详情加载失败", removeFailed: "移除失败", similarImage: "查找类似图片",
    login: "登录", register: "注册", logout: "退出登录", email: "邮箱", password: "密码", displayName: "昵称",
    needAccount: "没有账号？立即注册", haveAccount: "已有账号？返回登录", authFailed: "认证失败",
    authSuccess: "登录成功", loggedOut: "已退出登录", loginForCart: "请先登录后使用购物袋",
    clearCart: "清空购物袋", clearCartFailed: "清空购物袋失败"
  },
  en: {
    announcement: "Complimentary styling · Local curated edition", allProducts: "All products", women: "Women", men: "Men", kids: "Kids",
    menu: "Menu", search: "Search", openStylist: "Open personal stylist", openCart: "Open shopping bag", personalEdit: "The personal edit",
    pieces: "pieces", curated: "Curated for real life", heroTitle: "Quiet pieces.\nClear point of view.", heroCopy: "Build a personal edit from 5,000 real products using your occasion, colors and reference images.", consult: "Consult the stylist",
    collection: "The collection", essentials: "Considered essentials", items: "items", loading: "Loading products…",
    searchPlaceholder: "Search names or descriptions", allCategories: "All categories", allColors: "All colors", allCollections: "All collections",
    category: "Category", color: "Color", collectionLabel: "Collection", sort: "Sort", popular: "Most popular", nameSort: "Name", idSort: "Product ID", maxPrice: "Maximum dataset price",
    previous: "Previous", next: "Next", page: "Page {current} of {total}", selected: "{count} selected", compareStart: "Compare", clear: "Clear",
    close: "Close", cart: "Shopping bag", remove: "Remove", emptyCart: "Your shopping bag is empty",
    compare: "Compare pieces", addCompare: "Add to comparison", viewDetails: "View {name} details", match: "Match", dataPriceShort: "Data price", group: "Group", detail: "Product details", noDescription: "No description available", inventory: "Inventory", sizes: "Sizes", unavailable: "Not provided by source", datasetPrice: "Dataset price", addCart: "Add to bag",
    chatIntro: "Describe an occasion or preference, or upload a reference image. Only real catalog products are recommended.", dressingFor: "What are you dressing for?", chatHelp: "Describe an occasion, color, style or budget, or upload a reference image.",
    prompt1: "A white shirt for a summer commute", prompt2: "A refined minimalist date outfit", prompt3: "Find styles similar to this image", uploadAlt: "Uploaded reference", preview: "Preview", visualSearch: "Used for visual similarity search", upload: "Upload image", request: "Styling request", chatPlaceholder: "Describe the piece or occasion you need…", send: "Send",
    currentBrief: "Current brief", trace: "Service trace", preferenceHint: "Your preferences will develop through the conversation.", traceHint: "Retrieval and tool calls will appear here.", appointment: "Private appointment", stylist: "Atelier Stylist",
    added: "Added to shopping bag", requestFailed: "Request failed", unable: "Unable to complete request: ", addFailed: "Could not add item", compareFailed: "Comparison failed", detailFailed: "Could not load details", removeFailed: "Could not remove item", similarImage: "Find similar image",
    login: "Sign in", register: "Register", logout: "Sign out", email: "Email", password: "Password", displayName: "Display name",
    needAccount: "Need an account? Register", haveAccount: "Already registered? Sign in", authFailed: "Authentication failed",
    authSuccess: "Signed in", loggedOut: "Signed out", loginForCart: "Sign in to use your shopping bag",
    clearCart: "Clear shopping bag", clearCartFailed: "Could not clear shopping bag"
  }
} as const;

type Key = keyof typeof messages.zh;
const initial = (localStorage.getItem("atelier-language") === "en" ? "en" : "zh") as Language;
document.documentElement.lang = initial === "zh" ? "zh-CN" : "en";

export const useI18n = create<{ language: Language; setLanguage: (value: Language) => void }>((set) => ({
  language: initial,
  setLanguage: (language) => { localStorage.setItem("atelier-language", language); document.documentElement.lang = language === "zh" ? "zh-CN" : "en"; set({ language }); }
}));

export function useTranslation() {
  const { language, setLanguage } = useI18n();
  const t = (key: Key, variables?: Record<string, string | number>) => {
    let value: string = messages[language][key];
    for (const [name, replacement] of Object.entries(variables || {})) value = value.replace(`{${name}}`, String(replacement));
    return value;
  };
  return { language, setLanguage, t };
}
