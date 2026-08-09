import { create } from "zustand";

export type Language = "zh" | "en";

const copy = {
  zh: {
    announcement: "时尚穿搭应用",
    allProducts: "全部商品",
    women: "女装",
    men: "男装",
    kids: "童装",
    discover: "商品",
    agent: "图片找同款",
    menu: "菜单",
    search: "搜索",
    searchPlaceholder: "搜索商品名称或描述",
    openStylist: "打开私人顾问",
    openCart: "打开购物车",
    login: "登录",
    register: "注册",
    logout: "退出登录",
    close: "关闭",
    curated: "热门推荐",
    heroTitleA: "精选商品。",
    heroTitleB: "轻松选购。",
    heroCopy: "浏览精选商品图片和基础信息。",
    heroSearch: "描述场景、颜色、预算或你正在寻找的单品",
    startSearch: "开始探索",
    consult: "咨询客服",
    scroll: "继续滚动",
    storyLabel: "精选商品",
    storyOneTitle: "快速浏览商品",
    storyOneCopy: "按名称、分类、颜色和价格筛选商品。",
    storyTwoTitle: "查看商品信息",
    storyTwoCopy: "在详情页查看图片、价格和基础属性。",
    storyThreeTitle: "加入购物车",
    storyThreeCopy: "完成简单、清晰的下单演示流程。",
    collection: "商品列表",
    essentials: "全部商品",
    items: "件商品",
    loading: "加载中…",
    category: "分类",
    color: "颜色",
    collectionLabel: "系列",
    sort: "排序",
    allCategories: "全部分类",
    allColors: "全部颜色",
    allCollections: "全部系列",
    popular: "热度优先",
    nameSort: "名称排序",
    idSort: "商品编号",
    maxPrice: "最高价格",
    previous: "上一页",
    next: "下一页",
    page: "第 {current} / {total} 页",
    selected: "已选择 {count} 件",
    compareStart: "开始对比",
    clear: "清除",
    clearFilters: "清除全部筛选",
    noResults: "没有找到相关商品",
    noResultsCopy: "试试更换关键词或清除筛选条件。",
    addCompare: "加入对比",
    removeCompare: "移出对比",
    addCart: "加入购物车",
    added: "已加入购物车",
    favorite: "收藏",
    unfavorite: "取消收藏",
    viewDetails: "查看 {name} 详情",
    match: "匹配",
    recommendationReason: "推荐依据",
    dataPriceShort: "数据价格",
    detail: "商品详情",
    productStory: "商品信息",
    productOverview: "商品信息",
    productMaterial: "商品描述",
    productDecision: "购买建议",
    noDescription: "暂无商品描述。",
    inventory: "库存",
    sizes: "尺码",
    unavailable: "暂未提供",
    datasetPrice: "商品价格",
    sourceTruth: "商品说明",
    sourceTruthCopy: "商品信息以当前目录提供的内容为准。",
    reviewsUnavailable: "暂时没有商品评价",
    compare: "单品对比",
    compareSubtitle: "对比商品的基础信息和价格。",
    different: "存在差异",
    group: "分组",
    cart: "购物车",
    emptyCart: "购物车还是空的",
    remove: "移除",
    decreaseQuantity: "减少数量",
    increaseQuantity: "增加数量",
    clearCart: "清空购物车",
    clearCartFailed: "清空购物车失败",
    quantityUpdateFailed: "更新商品数量失败",
    loginForCart: "登录后可使用购物车",
    email: "邮箱",
    password: "密码",
    displayName: "昵称",
    needAccount: "没有账号？立即注册",
    haveAccount: "已有账号？返回登录",
    authFailed: "认证失败",
    authSuccess: "登录成功",
    loggedOut: "已退出登录",
    studio: "图片找同款",
    stylist: "图片找同款",
    agentIntro: "上传图片或输入关键词，查找目录中的相似商品。",
    dressingFor: "想找什么商品？",
    chatHelp: "输入关键词，或上传一张图片开始搜索。",
    prompt1: "适合夏天通勤的白色衬衫",
    prompt2: "简约但有质感的约会穿搭",
    prompt3: "帮我找类似参考图片的款式",
    upload: "上传图片",
    uploadAlt: "上传参考图",
    preview: "预览",
    visualSearch: "用于搜索相似商品",
    request: "搜索需求",
    chatPlaceholder: "输入商品名称、颜色，或上传图片…",
    send: "发送",
    stop: "停止生成",
    constraints: "筛选条件",
    execution: "搜索进度",
    candidates: "搜索结果",
    evidence: "商品信息",
    waiting: "等待你的补充",
    noExecution: "搜索后，结果会显示在这里。",
    confirmAdd: "确认加入购物车",
    wardrobe: "我的收藏",
    adoptPlan: "采纳方案",
    networkOffline: "网络已断开，核心浏览仍可继续",
    networkOnline: "网络已恢复",
    retry: "重试",
    requestFailed: "请求失败",
    unable: "暂时无法完成请求：",
    addFailed: "加入购物车失败",
    compareFailed: "对比失败",
    detailFailed: "详情加载失败",
    removeFailed: "移除失败",
    similarImage: "查找类似图片"
  },
  en: {
    announcement: "Private intelligent styling · Grounded in real product data",
    allProducts: "All products", women: "Women", men: "Men", kids: "Kids", discover: "Discover", agent: "AI Stylist",
    menu: "Menu", search: "Search", searchPlaceholder: "Search names or descriptions", openStylist: "Open personal stylist", openCart: "Open shopping bag",
    login: "Sign in", register: "Register", logout: "Sign out", close: "Close", curated: "INTELLIGENT EDIT 01",
    heroTitleA: "Not more choice.", heroTitleB: "A clearer decision.", heroCopy: "Build a personal buying decision from a real catalog, your preferences and verifiable evidence.",
    heroSearch: "Describe an occasion, color, budget or piece", startSearch: "Start exploring", consult: "Consult the stylist", scroll: "Continue scrolling",
    storyLabel: "A considered wardrobe", storyOneTitle: "Start with the need, not the shelf", storyOneCopy: "Natural language becomes visible constraints while retrieval stays transparent.",
    storyTwoTitle: "Understand products in context", storyTwoCopy: "Color, category, price and recommendation evidence occupy one connected space.",
    storyThreeTitle: "End with one clear decision", storyThreeCopy: "No manufactured urgency—only a grounded reason to buy or wait.",
    collection: "Live catalog", essentials: "Recomposed for the current context", items: "items", loading: "Updating results…",
    category: "Category", color: "Color", collectionLabel: "Collection", sort: "Sort", allCategories: "All categories", allColors: "All colors", allCollections: "All collections",
    popular: "Most popular", nameSort: "Name", idSort: "Product ID", maxPrice: "Maximum dataset price", previous: "Previous", next: "Next", page: "Page {current} of {total}",
    selected: "{count} selected", compareStart: "Compare", clear: "Clear", clearFilters: "Relax all constraints", noResults: "No products match these constraints",
    noResultsCopy: "Remove a condition and results will re-enter without losing context.", addCompare: "Add to comparison", removeCompare: "Remove from comparison",
    addCart: "Add to bag", added: "Added to bag", favorite: "Save", unfavorite: "Unsave", viewDetails: "View {name} details", match: "Match",
    recommendationReason: "Recommendation evidence", dataPriceShort: "Data price", detail: "Product details", productStory: "PRODUCT STUDY",
    productOverview: "Verified product profile", productMaterial: "Material and description", productDecision: "Return to the decision", noDescription: "No detailed description was provided by the source.",
    inventory: "Inventory", sizes: "Sizes", unavailable: "Not provided by source", datasetPrice: "Dataset price", sourceTruth: "Data transparency",
    sourceTruthCopy: "Only verifiable catalog fields are shown; missing information is never inferred.", reviewsUnavailable: "No verified reviews in the current source",
    compare: "Compare products", compareSubtitle: "Product identity stays continuous while real differences come forward.", different: "Different", group: "Group",
    cart: "Shopping bag", emptyCart: "Your shopping bag is empty", remove: "Remove", decreaseQuantity: "Decrease quantity", increaseQuantity: "Increase quantity", clearCart: "Clear shopping bag", clearCartFailed: "Could not clear shopping bag",
    quantityUpdateFailed: "Could not update item quantity", loginForCart: "Sign in to use the real shopping bag", email: "Email", password: "Password", displayName: "Display name", needAccount: "Need an account? Register",
    haveAccount: "Already registered? Sign in", authFailed: "Authentication failed", authSuccess: "Signed in", loggedOut: "Signed out",
    studio: "AGENT DECISION STUDIO", stylist: "Atelier AI Stylist", agentIntro: "Every state comes from the real workflow. No fake progress and no hidden waiting.",
    dressingFor: "What are you dressing for?", chatHelp: "Describe an occasion, color, category or budget, or upload a reference image.",
    prompt1: "A white shirt for a summer commute", prompt2: "A refined minimalist date outfit", prompt3: "Find styles similar to this image",
    upload: "Upload image", uploadAlt: "Uploaded reference", preview: "Preview", visualSearch: "Used for real visual similarity retrieval", request: "Styling request",
    chatPlaceholder: "Describe a piece, occasion, budget or preference…", send: "Send", stop: "Stop generating", constraints: "Current constraints", execution: "Execution trace",
    candidates: "Candidate set", evidence: "Recommendation evidence", waiting: "Waiting for your input", noExecution: "Submit a request and real workflow nodes will appear here.",
    confirmAdd: "Confirm add to cart", wardrobe: "Digital wardrobe plan", adoptPlan: "Adopt plan", networkOffline: "Network is offline; core browsing remains available",
    networkOnline: "Network restored", retry: "Retry", requestFailed: "Request failed", unable: "Unable to complete request: ", addFailed: "Could not add item",
    compareFailed: "Comparison failed", detailFailed: "Could not load details", removeFailed: "Could not remove item", similarImage: "Find similar image",
    submitOrder: "Place order", submittingOrder: "Placing order...", orderCreated: "Order created", orderCreateFailed: "Could not place order",
    orders: "My orders", ordersLoginCopy: "Sign in to view your order history", ordersLoading: "Loading orders...", ordersLoadFailed: "Could not load orders",
    ordersEmpty: "No orders yet", ordersEmptyCopy: "Your completed checkout will appear here.", ordersEmptyAction: "Discover products",
    orderNumber: "ORDER", orderTotal: "Total", orderPendingPayment: "Pending payment", orderCancelled: "Cancelled", cancelOrder: "Cancel order", cancellingOrder: "Cancelling...", orderCancelFailed: "Could not cancel order"
  }
} as const;

const orderCopy = {
  zh: {
    submitOrder: "提交订单", submittingOrder: "正在提交订单...", orderCreated: "订单已创建", orderCreateFailed: "提交订单失败",
    orders: "我的订单", ordersLoginCopy: "登录后可查看订单记录", ordersLoading: "正在加载订单...", ordersLoadFailed: "订单加载失败",
    ordersEmpty: "还没有订单", ordersEmptyCopy: "完成结算后的订单会显示在这里。", ordersEmptyAction: "去发现商品",
    orderNumber: "订单号", orderTotal: "合计", orderPendingPayment: "待支付", orderCancelled: "已取消", cancelOrder: "取消订单", cancellingOrder: "正在取消...", orderCancelFailed: "取消订单失败"
  },
  en: {
    submitOrder: "Place order", submittingOrder: "Placing order...", orderCreated: "Order created", orderCreateFailed: "Could not place order",
    orders: "My orders", ordersLoginCopy: "Sign in to view your order history", ordersLoading: "Loading orders...", ordersLoadFailed: "Could not load orders",
    ordersEmpty: "No orders yet", ordersEmptyCopy: "Your completed checkout will appear here.", ordersEmptyAction: "Discover products",
    orderNumber: "ORDER", orderTotal: "Total", orderPendingPayment: "Pending payment", orderCancelled: "Cancelled", cancelOrder: "Cancel order", cancellingOrder: "Cancelling...", orderCancelFailed: "Could not cancel order"
  }
} as const;

export const chineseCopy = { ...copy.zh, ...orderCopy.zh } as const;

type CopyKey = keyof typeof copy.zh | keyof typeof orderCopy.zh;

const initial: Language = "zh";
if (typeof document !== "undefined") document.documentElement.lang = "zh-CN";

export const useI18n = create<{ language: Language; setLanguage: (language: Language) => void }>((set) => ({
  language: initial,
  setLanguage: () => {
    if (typeof window !== "undefined") window.localStorage.setItem("atelier-language", "zh");
    if (typeof document !== "undefined") document.documentElement.lang = "zh-CN";
    set({ language: "zh" });
  }
}));

export function useTranslation() {
  const { language, setLanguage } = useI18n();
  const t = (key: CopyKey, variables?: Record<string, string | number>) => {
    let value: string = (orderCopy[language] as Record<string, string>)[key]
      ?? (copy[language] as Record<string, string>)[key];
    for (const [name, replacement] of Object.entries(variables || {})) {
      value = value.replace(`{${name}}`, String(replacement));
    }
    return value;
  };
  return { language, setLanguage, t };
}
