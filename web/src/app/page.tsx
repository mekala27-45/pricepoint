"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Backtest, Elasticity, Monitoring } from "../components/analysis-views";
import { DemandChart } from "../components/charts";
import {
  apiUrl,
  basePath,
  fetchCurve,
  fetchOptimization,
  fetchPrediction,
} from "../lib/api";
import {
  interpolate,
  money,
  number,
  optimize,
  parseBundle,
  percent,
} from "../lib/data";
import type {
  Bundle,
  Constraints,
  CurvePoint,
  Product,
  Recommendation,
} from "../lib/types";

const views = ["Explorer", "Backtest", "Elasticity", "Monitoring"] as const;
type View = (typeof views)[number];

function Icon({
  name,
  size = 18,
}: {
  name:
    | "sun"
    | "moon"
    | "arrow"
    | "search"
    | "chevron"
    | "settings"
    | "check"
    | "close";
  size?: number;
}) {
  const paths = {
    sun: (
      <>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.4 1.4m11.2 11.2L19 19M5 19l1.4-1.4M17.6 6.4L19 5" />
      </>
    ),
    moon: <path d="M20.5 13A8.6 8.6 0 0 1 11 3.5 8.6 8.6 0 1 0 20.5 13Z" />,
    arrow: <path d="M5 12h14m-6-6 6 6-6 6" />,
    search: (
      <>
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="m16 16 4.5 4.5" />
      </>
    ),
    chevron: <path d="m6 9 6 6 6-6" />,
    settings: (
      <>
        <path d="M4 7h16M4 17h16" />
        <circle cx="9" cy="7" r="3" fill="var(--surface)" />
        <circle cx="15" cy="17" r="3" fill="var(--surface)" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
    close: <path d="m6 6 12 12M6 18 18 6" />,
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

export default function Home() {
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [view, setView] = useState<View>("Explorer");
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  useEffect(() => {
    try {
      if (localStorage.getItem("pricepoint-theme") === "light")
        setTheme("light");
    } catch {
      /* Theme still works when browser storage is disabled. */
    }
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  useEffect(() => {
    const controller = new AbortController();
    setError("");
    fetch(`${basePath}/bundle.json`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok)
          throw new Error(
            `The evaluation bundle could not be loaded (${response.status}).`,
          );
        const data: unknown = await response.json();
        return parseBundle(data);
      })
      .then(setBundle)
      .catch((failure: unknown) => {
        if (!controller.signal.aborted)
          setError(
            failure instanceof Error
              ? failure.message
              : "Could not read the evaluation bundle.",
          );
      });
    return () => controller.abort();
  }, [reload]);
  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    try {
      localStorage.setItem("pricepoint-theme", next);
    } catch {
      /* Browser storage is optional. */
    }
  }
  return (
    <>
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <header className="site-header">
        <a
          className="brand"
          href={basePath || "/"}
          aria-label="Pricepoint home"
        >
          <span className="brand-symbol">
            <i />
            <i />
            <i />
          </span>
          pricepoint<span className="brand-period">.</span>
        </a>
        <nav className="main-nav" aria-label="Analysis views">
          {views.map((name, index) => (
            <button
              aria-current={view === name ? "page" : undefined}
              onClick={() => setView(name)}
              key={name}
            >
              <span className="nav-index">0{index + 1}</span>
              {name}
            </button>
          ))}
        </nav>
        <div className="header-tools">
          <span className="source-badge">
            <i />
            {apiUrl ? "LIVE API" : "ARTIFACT MODE"}
          </span>
          <button
            className="icon-button"
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
            onClick={toggleTheme}
          >
            <Icon name={theme === "dark" ? "sun" : "moon"} />
          </button>
        </div>
      </header>
      <main id="main">
        {error ? (
          <div className="load-state">
            <div className="eyebrow">EVALUATION ARTIFACT REQUIRED</div>
            <h1>The data is not here yet.</h1>
            <p role="alert">{error}</p>
            <button
              className="primary-button"
              onClick={() => setReload((value) => value + 1)}
            >
              Try loading again <Icon name="arrow" />
            </button>
          </div>
        ) : !bundle ? (
          <div className="load-state" role="status">
            <span className="loading-orbit" />
            <div className="eyebrow">LOADING MEASURED ARTIFACTS</div>
            <h1>Reading the shape of demand.</h1>
          </div>
        ) : view === "Explorer" ? (
          <Explorer bundle={bundle} />
        ) : view === "Backtest" ? (
          <Backtest bundle={bundle} />
        ) : view === "Elasticity" ? (
          <Elasticity bundle={bundle} />
        ) : (
          <Monitoring bundle={bundle} />
        )}
      </main>
      <footer className="site-footer">
        <span>
          <span className="footer-dot" />
          Independent work. Public retail data.
        </span>
        <span>
          {bundle ? bundle.meta.dataset : "UCI Online Retail II"}
          <span className="footer-separator">/</span>
          {bundle
            ? `Artifact ${bundle.meta.generated_at.slice(0, 10)}`
            : "Price and demand, in context"}
        </span>
      </footer>
    </>
  );
}

function Explorer({ bundle }: { bundle: Bundle }) {
  const [productId, setProductId] = useState(bundle.products[0].id);
  const product =
    bundle.products.find((entry) => entry.id === productId) ??
    bundle.products[0];
  return (
    <section className="explorer-view">
      <div className="hero">
        <div>
          <div className="eyebrow">
            <span className="eyebrow-line" /> PRICE ELASTICITY, WITH CONTEXT
          </div>
          <h1>
            Find the price.
            <br />
            <span className="quiet">Understand the trade-off.</span>
          </h1>
          <p>
            A clearer view of price, demand, and the uncertainty between them.
            <br className="desktop-break" /> Explore a real retail demand model,
            one decision at a time.
          </p>
        </div>
        <div className="hero-note">
          <span className="hero-note-symbol">↗</span>
          <span>
            PUBLIC DATA
            <br />
            MEASURED RESULTS
            <br />
            <strong>NO BLACK BOX</strong>
          </span>
        </div>
      </div>
      <div className="evidence-note">
        <span className="eyebrow">SERVING EVIDENCE</span>
        <p>{bundle.meta.source_note}</p>
      </div>
      <div className="workspace-label">
        <span>01 / PRICE EXPLORER</span>
        <span>
          <i className="status-dot" />
          {apiUrl
            ? "Connected to live inference"
            : "Precomputed demand surfaces"}
        </span>
      </div>
      <div className="explorer-workspace">
        <ProductExplorer
          key={product.id}
          bundle={bundle}
          product={product}
          onSelect={setProductId}
        />
      </div>
      <div className="principles">
        <div>
          <span>01</span>
          <div>
            <h3>Bounded by evidence</h3>
            <p>Recommendations stay inside observed prices.</p>
          </div>
        </div>
        <div>
          <span>02</span>
          <div>
            <h3>Uncertainty included</h3>
            <p>A calibrated interval accompanies every estimate.</p>
          </div>
        </div>
        <div>
          <span>03</span>
          <div>
            <h3>Association, carefully</h3>
            <p>Observational demand is not causal elasticity.</p>
          </div>
        </div>
      </div>
      <div className="source-note">
        <span className="eyebrow">DATA PROVENANCE</span>
        <p>{bundle.meta.source_note}</p>
      </div>
    </section>
  );
}

function ProductExplorer({
  bundle,
  product,
  onSelect,
}: {
  bundle: Bundle;
  product: Product;
  onSelect: (id: string) => void;
}) {
  const [price, setPrice] = useState(
    Math.min(
      product.max_price,
      Math.max(product.min_price, product.current_price),
    ),
  );
  const [metric, setMetric] = useState<"units" | "revenue">("units");
  const [constraints, setConstraints] = useState<Constraints>({
    cost_floor: 0,
    inventory: Math.max(
      1,
      Math.ceil(Math.max(...product.curve.map((row) => row.interval_high)) * 2),
    ),
    min_markdown: 0,
    max_markdown: 0.5,
    objective: "revenue",
  });
  const [curve, setCurve] = useState<CurvePoint[] | null>(
    apiUrl ? null : product.curve,
  );
  const [curveError, setCurveError] = useState("");
  const [predictionState, setPredictionState] = useState<{
    price: number;
    data: CurvePoint | null;
    error: string;
  } | null>(null);
  const [optimizationState, setOptimizationState] = useState<{
    key: string;
    data: Recommendation | null;
    error: string;
  } | null>(null);
  const constraintKey = JSON.stringify(constraints);
  useEffect(() => {
    if (!apiUrl) return;
    const controller = new AbortController();
    fetchCurve(product, controller.signal)
      .then(setCurve)
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setCurveError(
            error instanceof Error
              ? error.message
              : "Unable to score the live curve.",
          );
      });
    return () => controller.abort();
  }, [product]);
  useEffect(() => {
    if (!apiUrl) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      fetchPrediction(product, price, controller.signal)
        .then((data) => {
          if (!controller.signal.aborted)
            setPredictionState({ price, data, error: "" });
        })
        .catch((error: unknown) => {
          if (!controller.signal.aborted)
            setPredictionState({
              price,
              data: null,
              error:
                error instanceof Error
                  ? error.message
                  : "Live prediction unavailable.",
            });
        });
    }, 100);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [product, price]);
  useEffect(() => {
    if (!apiUrl) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      fetchOptimization(product, constraints, controller.signal)
        .then((data) => {
          if (!controller.signal.aborted)
            setOptimizationState({ key: constraintKey, data, error: "" });
        })
        .catch((error: unknown) => {
          if (!controller.signal.aborted)
            setOptimizationState({
              key: constraintKey,
              data: null,
              error:
                error instanceof Error
                  ? error.message
                  : "Live recommendation unavailable.",
            });
        });
    }, 180);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [product, constraints, constraintKey]);
  const staticPrediction = useMemo(
    () => interpolate(product.curve, price),
    [product.curve, price],
  );
  const staticRecommendation = useMemo(
    () => optimize(product, constraints),
    [product, constraints],
  );
  const prediction = apiUrl
    ? predictionState?.price === price
      ? predictionState.data
      : null
    : staticPrediction;
  const recommendation = apiUrl
    ? optimizationState?.key === constraintKey
      ? optimizationState.data
      : null
    : staticRecommendation;
  const error =
    curveError ||
    (predictionState?.price === price ? predictionState.error : "") ||
    (optimizationState?.key === constraintKey ? optimizationState.error : "");
  const markdown = 1 - price / product.current_price;
  const sliderFill =
    (100 * (price - product.min_price)) /
    (product.max_price - product.min_price);
  function update(field: keyof Omit<Constraints, "objective">, value: number) {
    setConstraints((current) => ({
      ...current,
      [field]: Math.max(0, Number.isFinite(value) ? value : 0),
    }));
  }
  return (
    <>
      <div className="controls-panel">
        <ProductPicker
          products={bundle.products}
          selected={product}
          onSelect={onSelect}
        />
        <div className="control-divider" />
        <div className="price-control">
          <div className="label-row">
            <label htmlFor="price-slider">CANDIDATE PRICE</label>
            <span className={markdown < 0 ? "muted-text" : "accent-text"}>
              {markdown >= 0
                ? `${percent(markdown)} markdown`
                : `${percent(-markdown)} increase`}
            </span>
          </div>
          <div className="price-readout">
            <span>£</span>
            {price.toFixed(2)}
            <span className="per-unit">/ unit</span>
          </div>
          <div className="slider-shell">
            <div className="slider-ticks" />
            <input
              id="price-slider"
              aria-label="Candidate price"
              type="range"
              min={product.min_price}
              max={product.max_price}
              step="0.01"
              value={price}
              onChange={(event) => setPrice(Number(event.target.value))}
              style={{ "--slider-fill": `${sliderFill}%` }}
            />
            <div className="slider-labels">
              <span>{money(product.min_price)}</span>
              <span>{money(product.max_price)}</span>
            </div>
          </div>
          <div className="current-price">
            <span>Observed current price</span>
            <button
              onClick={() =>
                setPrice(
                  Math.min(
                    product.max_price,
                    Math.max(product.min_price, product.current_price),
                  ),
                )
              }
              title="Reset to current price"
            >
              {money(product.current_price)} <span>↺</span>
            </button>
          </div>
        </div>
        <div className="control-divider" />
        <div className="constraints-heading">
          <Icon name="settings" />
          <h3>Business constraints</h3>
          <span>EDITABLE</span>
        </div>
        <div className="objective-control">
          <span className="field-label">OPTIMIZE FOR</span>
          <div className="segmented">
            <button
              className={constraints.objective === "revenue" ? "selected" : ""}
              onClick={() =>
                setConstraints((current) => ({
                  ...current,
                  objective: "revenue",
                }))
              }
            >
              Revenue
            </button>
            <button
              className={constraints.objective === "margin" ? "selected" : ""}
              onClick={() =>
                setConstraints((current) => ({
                  ...current,
                  objective: "margin",
                }))
              }
            >
              Margin
            </button>
          </div>
        </div>
        <div className="input-grid">
          <label>
            Cost floor{" "}
            <span className="input-wrap">
              <span>£</span>
              <input
                aria-label="Cost floor"
                type="number"
                min="0"
                step="0.01"
                value={constraints.cost_floor}
                onChange={(event) =>
                  update("cost_floor", event.target.valueAsNumber)
                }
              />
            </span>
          </label>
          <label>
            Inventory{" "}
            <span className="input-wrap">
              <input
                aria-label="Inventory"
                type="number"
                min="0"
                step="1"
                value={constraints.inventory}
                onChange={(event) =>
                  update("inventory", event.target.valueAsNumber)
                }
              />
              <span>u</span>
            </span>
          </label>
          <label>
            Min markdown{" "}
            <span className="input-wrap">
              <input
                aria-label="Minimum markdown percent"
                type="number"
                min="0"
                max="100"
                step="1"
                value={Math.round(constraints.min_markdown * 100)}
                onChange={(event) =>
                  update(
                    "min_markdown",
                    Math.min(100, event.target.valueAsNumber) / 100,
                  )
                }
              />
              <span>%</span>
            </span>
          </label>
          <label>
            Max markdown{" "}
            <span className="input-wrap">
              <input
                aria-label="Maximum markdown percent"
                type="number"
                min="0"
                max="100"
                step="1"
                value={Math.round(constraints.max_markdown * 100)}
                onChange={(event) =>
                  update(
                    "max_markdown",
                    Math.min(100, event.target.valueAsNumber) / 100,
                  )
                }
              />
              <span>%</span>
            </span>
          </label>
        </div>
        <div className="support-check">
          <Icon name="check" size={14} />
          <span>Historical price support enforced</span>
        </div>
      </div>
      <div className="surface-panel">
        <div className="surface-heading">
          <div>
            <span className="eyebrow">THE DEMAND SURFACE</span>
            <h2>A small move. A different outcome.</h2>
          </div>
          <div className="segmented chart-switch">
            <button
              className={metric === "units" ? "selected" : ""}
              onClick={() => setMetric("units")}
            >
              Demand
            </button>
            <button
              className={metric === "revenue" ? "selected" : ""}
              onClick={() => setMetric("revenue")}
            >
              Revenue
            </button>
          </div>
        </div>
        <div className="chart-meta">
          <span>
            {metric === "units" ? "UNITS / WEEK" : "REVENUE / WEEK (GBP)"}
          </span>
          <div className="legend">
            <span>
              <i className="legend-line" />
              Estimate
            </span>
            <span>
              <i className="legend-band" />
              {percent(bundle.meta.nominal_coverage, 0)} interval
            </span>
          </div>
        </div>
        {curve ? (
          <DemandChart
            curve={curve}
            price={price}
            recommended={recommendation}
            metric={metric}
          />
        ) : (
          <div className="chart-loading" role="status">
            {curveError || "Scoring the live demand surface..."}
          </div>
        )}
        <div className="chart-x-label">PRICE PER UNIT (GBP)</div>
        <div className="readout-grid" aria-live="polite">
          <div>
            <span className="eyebrow">EXPECTED DEMAND</span>
            <strong>
              {prediction ? number(prediction.units, 1) : "···"}
              <small>units</small>
            </strong>
            <p>per week at {money(price)}</p>
          </div>
          <div>
            <span className="eyebrow">EXPECTED REVENUE</span>
            <strong>{prediction ? money(prediction.revenue) : "···"}</strong>
            <p>before inventory constraints</p>
          </div>
          <div>
            <span className="eyebrow">DEMAND INTERVAL</span>
            <strong className="interval-readout">
              {prediction
                ? `${number(prediction.interval_low, 1)} to ${number(prediction.interval_high, 1)}`
                : "···"}
            </strong>
            <p>
              {percent(bundle.meta.nominal_coverage, 0)} nominal coverage ·
              units
            </p>
          </div>
        </div>
        {error && (
          <div className="inline-error" role="alert">
            {error}
          </div>
        )}
        <div
          className={`recommendation ${recommendation ? "" : "unavailable"}`}
        >
          <div className="recommendation-mark">
            <Icon name="arrow" size={22} />
          </div>
          <div className="recommendation-copy">
            <span className="eyebrow">
              {recommendation
                ? `${constraints.objective.toUpperCase()}-MAXIMIZING PRICE`
                : apiUrl && !error
                  ? "SCORING CONSTRAINTS"
                  : "NO FEASIBLE RECOMMENDATION"}
            </span>
            {recommendation ? (
              <>
                <div>
                  <strong>{money(recommendation.recommended_price)}</strong>
                  <span>
                    {percent(
                      1 -
                        recommendation.recommended_price /
                          product.current_price,
                    )}{" "}
                    markdown<span className="rec-dot">·</span>
                    {number(recommendation.expected_units, 1)} units
                  </span>
                </div>
                <p>
                  {recommendation.extrapolation_warning
                    ? "At the observed price boundary. Treat the optimum with caution."
                    : `Within observed prices, with inventory capped at ${number(constraints.inventory)} units.`}
                </p>
              </>
            ) : (
              <p>
                {apiUrl && !error
                  ? "Waiting for the live optimization response."
                  : "Adjust the cost floor and markdown limits to allow a price inside historical support."}
              </p>
            )}
          </div>
          {recommendation && (
            <button
              className="apply-button"
              onClick={() => setPrice(recommendation.recommended_price)}
              aria-label="Apply recommended price"
            >
              Explore price <Icon name="arrow" size={15} />
            </button>
          )}
        </div>
        <div className="surface-footer">
          <span>AS OF {product.as_of.slice(0, 10)}</span>
          <span>MODEL {bundle.meta.model_version}</span>
        </div>
      </div>
    </>
  );
}

function ProductPicker({
  products,
  selected,
  onSelect,
}: {
  products: Product[];
  selected: Product;
  onSelect: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const container = useRef<HTMLDivElement>(null);
  const filtered = products.filter((product) =>
    `${product.id} ${product.name} ${product.category}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (
        container.current &&
        !container.current.contains(event.target as Node)
      )
        setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  return (
    <div className="product-picker" ref={container}>
      <span className="field-label">SELECT A PRODUCT</span>
      <button
        className="product-selected"
        aria-expanded={open}
        aria-controls="product-options"
        onClick={() => setOpen(!open)}
      >
        <div className="product-art" aria-hidden="true">
          <svg width="32" height="36" viewBox="0 0 32 36" fill="none">
            <path
              d="m4 11 12-7 12 7v15l-12 7L4 26V11Z"
              stroke="currentColor"
              strokeWidth="1.3"
            />
            <path
              d="m4 11 12 7 12-7M16 18v15M10 7.5l12 7v7"
              stroke="currentColor"
              strokeWidth="1.3"
            />
          </svg>
        </div>
        <div className="selected-product-text">
          <strong>{selected.name}</strong>
          <span>
            {selected.id} · {selected.category}
          </span>
        </div>
        <Icon name="chevron" size={16} />
      </button>
      {open && (
        <div className="product-dropdown" id="product-options">
          <div className="product-search">
            <Icon name="search" size={16} />
            <input
              autoFocus
              aria-label="Search products"
              placeholder="Search name, code, category"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Escape") setOpen(false);
              }}
            />
          </div>
          <div className="product-options">
            {filtered.length ? (
              filtered.map((product) => (
                <button
                  key={product.id}
                  className={selected.id === product.id ? "active" : ""}
                  onClick={() => {
                    onSelect(product.id);
                    setOpen(false);
                    setSearch("");
                  }}
                >
                  <strong>{product.name}</strong>
                  <span>
                    {product.id} · {product.category}
                  </span>
                  {selected.id === product.id && (
                    <Icon name="check" size={14} />
                  )}
                </button>
              ))
            ) : (
              <p className="no-products">No products match your search.</p>
            )}
          </div>
          <div className="product-count">
            {filtered.length} products with observed price variation
          </div>
        </div>
      )}
    </div>
  );
}
