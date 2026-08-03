import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, animate, motion, useMotionValue, useTransform } from "motion/react";
import { Filter, Search, SlidersHorizontal, X } from "lucide-react";
import { useTranslation } from "../i18n";
import { motionTokens } from "../motion/tokens";
import type { Product, ProductFacets, ProductQuery } from "../types";
import { ProductCard } from "./ProductCard";

function AnimatedNumber({ value }: { value: number }) {
  const motionValue = useMotionValue(value);
  const rounded = useTransform(motionValue, (latest) => Math.round(latest).toLocaleString());
  useEffect(() => {
    const controls = animate(motionValue, value, { duration: 0.42, ease: motionTokens.easing.enter });
    return controls.stop;
  }, [motionValue, value]);
  return <motion.span>{rounded}</motion.span>;
}

const constraintsFor = (query: ProductQuery) => [
  query.search && ["search", query.search],
  query.category && ["category", query.category],
  query.color && ["color", query.color],
  query.indexGroup && ["indexGroup", query.indexGroup],
  typeof query.maxPrice === "number" && ["maxPrice", `≤ ${query.maxPrice}`]
].filter(Boolean) as [keyof ProductQuery, string][];

type Props = {
  products: Product[];
  total: number;
  loading: boolean;
  facets: ProductFacets | null;
  query: ProductQuery;
  compareIds: string[];
  onChange: (patch: Partial<ProductQuery>) => void;
  onClear: () => void;
  onCompare: (id: string) => void;
  onAdd: (id: string, origin: DOMRect) => Promise<boolean>;
  onDetail: (id: string) => void;
};

export function ProductCollection(props: Props) {
  const { t } = useTranslation();
  const [filterOpen, setFilterOpen] = useState(false);
  const [searchFocused, setSearchFocused] = useState(false);
  const searchShell = useRef<HTMLDivElement>(null);
  const constraints = constraintsFor(props.query);
  const suggestions = useMemo(() => {
    const term = (props.query.search || "").toLowerCase();
    if (!term) return props.products.slice(0, 4);
    return props.products.filter((product) => `${product.prod_name} ${product.product_type_name}`.toLowerCase().includes(term)).slice(0, 4);
  }, [props.products, props.query.search]);

  const removeConstraint = (key: keyof ProductQuery) => {
    props.onChange({ [key]: key === "maxPrice" ? undefined : "", page: 1 });
  };

  return (
    <section id="collection" className="collection-section">
      <header className="collection-header">
        <div><p className="section-kicker">{t("collection")}</p><h2>{t("essentials")}</h2></div>
        <p className="result-count"><AnimatedNumber value={props.total} /> {t("items")}</p>
      </header>

      <div className="catalog-toolbar">
        <motion.div ref={searchShell} layoutId="narrative-search-shell" className="catalog-search">
          <Search size={17} />
          <input
            value={props.query.search || ""}
            onFocus={() => setSearchFocused(true)}
            onBlur={() => window.setTimeout(() => setSearchFocused(false), 140)}
            onChange={(event) => props.onChange({ search: event.target.value, page: 1 })}
            placeholder={t("searchPlaceholder")}
            aria-label={t("search")}
          />
          {props.query.search && <button onClick={() => removeConstraint("search")} aria-label={t("clear")}><X size={14} /></button>}
          <AnimatePresence>
            {searchFocused && suggestions.length > 0 && (
              <motion.div className="search-suggestions" initial={{ opacity: 0, y: -8, height: 0 }} animate={{ opacity: 1, y: 0, height: "auto" }} exit={{ opacity: 0, y: -6, height: 0 }}>
                {suggestions.map((product) => <button key={product.article_id} onClick={() => props.onChange({ search: product.prod_name, page: 1 })}><span>{product.prod_name}</span><small>{product.product_type_name} · {product.colour_group_name}</small></button>)}
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
        <button className="filter-toggle" onClick={() => setFilterOpen((value) => !value)}><SlidersHorizontal size={16} />{t("sort")}/{t("category")}</button>
      </div>

      <AnimatePresence initial={false}>
        {filterOpen && (
          <motion.div className="filter-panel" initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={motionTokens.spring.drawer}>
            <div className="filter-grid">
              <label><span>{t("category")}</span><select aria-label={t("category")} value={props.query.category || ""} onChange={(event) => props.onChange({ category: event.target.value, page: 1 })}><option value="">{t("allCategories")}</option>{props.facets?.categories.map((item) => <option key={item}>{item}</option>)}</select></label>
              <label><span>{t("color")}</span><select aria-label={t("color")} value={props.query.color || ""} onChange={(event) => props.onChange({ color: event.target.value, page: 1 })}><option value="">{t("allColors")}</option>{props.facets?.colors.map((item) => <option key={item}>{item}</option>)}</select></label>
              <label><span>{t("collectionLabel")}</span><select aria-label={t("collectionLabel")} value={props.query.indexGroup || ""} onChange={(event) => props.onChange({ indexGroup: event.target.value, page: 1 })}><option value="">{t("allCollections")}</option>{props.facets?.index_groups.map((item) => <option key={item}>{item}</option>)}</select></label>
              <label><span>{t("sort")}</span><select aria-label={t("sort")} value={props.query.sort || "popular"} onChange={(event) => props.onChange({ sort: event.target.value as ProductQuery["sort"], page: 1 })}><option value="popular">{t("popular")}</option><option value="name">{t("nameSort")}</option><option value="article_id">{t("idSort")}</option></select></label>
              <label><span>{t("maxPrice")}</span><input aria-label={t("maxPrice")} type="number" step="0.001" min={props.facets?.price_range?.[0] || 0} max={props.facets?.price_range?.[1]} value={props.query.maxPrice ?? ""} onChange={(event) => props.onChange({ maxPrice: event.target.value ? Number(event.target.value) : undefined, page: 1 })} /></label>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="constraint-row">
        <span><Filter size={13} />{constraints.length}</span>
        <AnimatePresence mode="popLayout">
          {constraints.map(([key, label]) => <motion.button layout key={key} initial={{ opacity: 0, scale: 0.86 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.8 }} onClick={() => removeConstraint(key)}>{label}<X size={11} /></motion.button>)}
        </AnimatePresence>
        {constraints.length > 1 && <button className="clear-constraints" onClick={props.onClear}>{t("clear")}</button>}
      </div>

      <div className="result-stage" aria-busy={props.loading}>
        <AnimatePresence>{props.loading && props.products.length > 0 && <motion.div className="result-loading-line" initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.8 }} />}</AnimatePresence>
        {props.loading && props.products.length === 0 ? (
          <div className="skeleton-grid" aria-label={t("loading")}>{Array.from({ length: 8 }, (_, index) => <div className="product-skeleton" key={index}><span /><i /><i /></div>)}</div>
        ) : props.products.length ? (
          <motion.div className="product-grid" layout>
            <AnimatePresence mode="popLayout">
              {props.products.map((product, index) => (
                <ProductCard
                  key={product.article_id}
                  product={product}
                  index={index}
                  featured={index === 0 || index === 7}
                  selected={props.compareIds.includes(product.article_id)}
                  onCompare={props.onCompare}
                  onAdd={props.onAdd}
                  onDetail={props.onDetail}
                />
              ))}
            </AnimatePresence>
          </motion.div>
        ) : (
          <motion.div className="no-results" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            <div className="constraint-diagram">{constraints.map(([, label], index) => <motion.span key={label} initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: index * 0.07 }}>{label}</motion.span>)}</div>
            <h3>{t("noResults")}</h3><p>{t("noResultsCopy")}</p><button onClick={props.onClear}>{t("clearFilters")}</button>
          </motion.div>
        )}
      </div>

      {props.total > (props.query.pageSize || 12) && (
        <nav className="pagination" aria-label="Pagination">
          <button disabled={(props.query.page || 1) <= 1} onClick={() => props.onChange({ page: (props.query.page || 1) - 1 })}>{t("previous")}</button>
          <span>{t("page", { current: props.query.page || 1, total: Math.ceil(props.total / (props.query.pageSize || 12)) })}</span>
          <button disabled={(props.query.page || 1) >= Math.ceil(props.total / (props.query.pageSize || 12))} onClick={() => props.onChange({ page: (props.query.page || 1) + 1 })}>{t("next")}</button>
        </nav>
      )}
    </section>
  );
}
