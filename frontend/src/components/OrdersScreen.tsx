import { AlertCircle, LoaderCircle, PackageOpen, ReceiptText, XCircle } from "lucide-react";
import { useTranslation } from "../i18n";
import type { OrderDetail } from "../types";

type OrdersScreenProps = {
  authenticated: boolean;
  orders: OrderDetail[];
  loading: boolean;
  error: string;
  cancellingOrderId: string | null;
  onLogin: () => void;
  onDiscover: () => void;
  onCancel: (orderId: string) => void;
};

export function OrdersScreen({ authenticated, orders, loading, error, cancellingOrderId, onLogin, onDiscover, onCancel }: OrdersScreenProps) {
  const { t } = useTranslation();

  if (!authenticated) {
    return <main className="orders-screen app-screen orders-empty-state">
      <ReceiptText size={34} /><h2>{t("orders")}</h2><p>{t("ordersLoginCopy")}</p><button onClick={onLogin}>{t("login")}</button>
    </main>;
  }

  if (loading) {
    return <main className="orders-screen app-screen orders-empty-state" aria-live="polite">
      <LoaderCircle className="orders-spinner" size={28} /><p>{t("ordersLoading")}</p>
    </main>;
  }

  if (error) {
    return <main className="orders-screen app-screen orders-empty-state"><AlertCircle size={32} /><h2>{t("ordersLoadFailed")}</h2><p>{error}</p></main>;
  }

  if (orders.length === 0) {
    return <main className="orders-screen app-screen orders-empty-state">
      <PackageOpen size={34} /><h2>{t("ordersEmpty")}</h2><p>{t("ordersEmptyCopy")}</p><button onClick={onDiscover}>{t("ordersEmptyAction")}</button>
    </main>;
  }

  return <main className="orders-screen app-screen">
    <div className="orders-heading"><span>FITME ORDERS</span><h2>{t("orders")}</h2></div>
    <section className="orders-list" aria-label={t("orders")}>
      {orders.map((order) => {
        const pending = order.status === "PENDING_PAYMENT";
        const status = pending ? t("orderPendingPayment") : t("orderCancelled");
        return <article className="order-card" key={order.id}>
          <header className="order-card-header">
            <div><span>{t("orderNumber")}</span><strong>#{order.id.slice(0, 8)}</strong><small>{new Date(order.createdAt).toLocaleString()}</small></div>
            <b className={pending ? "order-status is-pending" : "order-status"}>{status}</b>
          </header>
          <div className="order-items">
            {order.items.map((item) => <div className="order-item" key={item.id}>
              <img src={item.productImageUrl || ""} alt={item.productName} />
              <div><h3>{item.productName}</h3><p>{item.unitPrice.toFixed(4)} x {item.quantity}</p></div>
              <strong>{item.subtotal.toFixed(4)}</strong>
            </div>)}
          </div>
          <footer><div><span>{t("orderTotal")}</span><strong>{order.totalAmount.toFixed(4)}</strong></div>
            {pending && <button disabled={cancellingOrderId === order.id} onClick={() => onCancel(order.id)}>{cancellingOrderId === order.id ? t("cancellingOrder") : <><XCircle size={14} />{t("cancelOrder")}</>}</button>}
          </footer>
        </article>;
      })}
    </section>
  </main>;
}
