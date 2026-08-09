export function formatCatalogPrice(amount: number, currency = "CNY"): string {
  const safeAmount = Number.isFinite(amount) ? amount : 0;
  const hasFraction = Math.abs(safeAmount - Math.round(safeAmount)) > 0.000001;
  const value = new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: hasFraction ? 2 : 0,
    maximumFractionDigits: 2
  }).format(safeAmount);

  return currency === "CNY" ? `¥${value}` : `${value} ${currency}`;
}
