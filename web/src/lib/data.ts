import type {
  Bundle,
  Constraints,
  CurvePoint,
  Product,
  Recommendation,
} from "./types";

const finite = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);
const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null;
const numericFields = (value: unknown, fields: string[]) =>
  record(value) && fields.every((field) => finite(value[field]));
const stringFields = (value: unknown, fields: string[]) =>
  record(value) && fields.every((field) => typeof value[field] === "string");

export function parseCurve(value: unknown): CurvePoint[] {
  if (
    !Array.isArray(value) ||
    value.length < 2 ||
    !value.every(
      (point: unknown) =>
        numericFields(point, [
          "price",
          "units",
          "revenue",
          "interval_low",
          "interval_high",
        ]) &&
        record(point) &&
        (point.price as number) > 0 &&
        (point.units as number) >= 0 &&
        (point.interval_low as number) >= 0 &&
        (point.interval_high as number) >= (point.interval_low as number),
    )
  )
    throw new Error(
      "The demand surface is missing or invalid. Rebuild the committed evaluation bundle.",
    );
  const curve = [...(value as CurvePoint[])].sort((a, b) => a.price - b.price);
  if (
    curve.some(
      (point, index) => index > 0 && point.price <= curve[index - 1].price,
    )
  ) {
    throw new Error("Demand surface prices must be distinct.");
  }
  return curve;
}

export function parseBundle(value: unknown): Bundle {
  if (
    !record(value) ||
    !record(value.meta) ||
    !stringFields(value.meta, [
      "generated_at",
      "dataset",
      "model_version",
      "source_note",
    ]) ||
    !finite(value.meta.nominal_coverage) ||
    value.meta.nominal_coverage <= 0 ||
    value.meta.nominal_coverage >= 1 ||
    !Array.isArray(value.products) ||
    !value.products.length ||
    !record(value.backtest) ||
    !Array.isArray(value.backtest.summary) ||
    !Array.isArray(value.backtest.folds) ||
    !Array.isArray(value.backtest.last_fold) ||
    !Array.isArray(value.elasticity) ||
    !Array.isArray(value.monitoring)
  ) {
    throw new Error(
      "Evaluation bundle unavailable or incompatible. Run the evaluation pipeline and rebuild the demo.",
    );
  }
  for (const product of value.products as unknown[]) {
    if (
      !stringFields(product, ["id", "name", "category", "as_of"]) ||
      !numericFields(product, [
        "current_price",
        "min_price",
        "max_price",
        "recommended_price",
      ]) ||
      !record(product) ||
      (product.min_price as number) <= 0 ||
      (product.max_price as number) <= (product.min_price as number)
    ) {
      throw new Error("Invalid product metadata in the evaluation bundle.");
    }
    const curve = parseCurve(product.curve);
    if (
      curve[0].price > (product.min_price as number) ||
      curve[curve.length - 1].price < (product.max_price as number) ||
      (product.current_price as number) <= 0
    ) {
      throw new Error(
        "The demand surface does not cover declared price support.",
      );
    }
    product.curve = curve;
  }
  const checks: [unknown[], string[], string[]][] = [
    [
      value.backtest.summary,
      ["model", "label"],
      ["wape_mean", "wape_std", "mase_mean", "mase_std"],
    ],
    [
      value.backtest.folds,
      ["model", "train_end", "test_start"],
      ["fold", "wape", "mase"],
    ],
    [
      value.backtest.last_fold,
      ["model", "product_id"],
      ["actual", "predicted"],
    ],
    [
      value.elasticity,
      ["category"],
      [
        "before",
        "before_low",
        "before_high",
        "after",
        "after_low",
        "after_high",
        "observations",
      ],
    ],
    [
      value.monitoring,
      ["week", "reason", "observed_at", "action", "decision_as_of"],
      ["ks"],
    ],
  ];
  for (const [rows, strings, numbers] of checks) {
    if (
      !rows.every(
        (row: unknown) =>
          stringFields(row, strings) && numericFields(row, numbers),
      )
    ) {
      throw new Error(
        "Invalid evaluation metrics. All displayed results must come from measured artifacts.",
      );
    }
  }
  if (
    !(value.monitoring as unknown[]).every(
      (row) =>
        record(row) &&
        record(row.psi) &&
        Object.values(row.psi).every(finite) &&
        typeof row.retrain === "boolean" &&
        (row.wape === null || finite(row.wape)) &&
        (row.scheduled_as_of === null ||
          typeof row.scheduled_as_of === "string") &&
        (row.refit_trigger_observed_at === null ||
          typeof row.refit_trigger_observed_at === "string"),
    )
  ) {
    throw new Error("Invalid monitoring observations.");
  }
  return value as unknown as Bundle;
}

export function interpolate(curve: CurvePoint[], price: number): CurvePoint {
  const bounded = Math.min(
    curve[curve.length - 1].price,
    Math.max(curve[0].price, price),
  );
  const upperIndex = curve.findIndex((point) => point.price >= bounded);
  if (upperIndex <= 0) return { ...curve[0] };
  const low = curve[upperIndex - 1];
  const high = curve[upperIndex];
  const weight = (bounded - low.price) / (high.price - low.price);
  const units = low.units + (high.units - low.units) * weight;
  return {
    price: bounded,
    units,
    revenue: bounded * units,
    interval_low:
      low.interval_low + (high.interval_low - low.interval_low) * weight,
    interval_high:
      low.interval_high + (high.interval_high - low.interval_high) * weight,
  };
}

export function optimize(
  product: Product,
  constraints: Constraints,
): Recommendation | null {
  if (
    ![
      constraints.cost_floor,
      constraints.inventory,
      constraints.min_markdown,
      constraints.max_markdown,
    ].every(Number.isFinite) ||
    constraints.cost_floor < 0 ||
    constraints.inventory < 0 ||
    constraints.min_markdown < 0 ||
    constraints.max_markdown > 1
  )
    return null;
  const lower = Math.max(
    product.min_price,
    constraints.cost_floor,
    product.current_price * (1 - constraints.max_markdown),
  );
  const upper = Math.min(
    product.max_price,
    product.current_price * (1 - constraints.min_markdown),
  );
  if (
    lower > upper ||
    constraints.inventory < 0 ||
    constraints.min_markdown > constraints.max_markdown
  )
    return null;
  // Remove binary floating point noise before rounding to feasible pennies.
  const lowPenny = Math.ceil(lower * 100 - 1e-9);
  const highPenny = Math.floor(upper * 100 + 1e-9);
  const supportLowPenny = Math.ceil(product.min_price * 100 - 1e-9);
  const supportHighPenny = Math.floor(product.max_price * 100 + 1e-9);
  let best: Recommendation | null = null;
  for (let penny = lowPenny; penny <= highPenny; penny += 1) {
    const price = penny / 100;
    const point = interpolate(product.curve, price);
    const units = Math.min(constraints.inventory, point.units);
    const revenue = units * price;
    const margin = units * (price - constraints.cost_floor);
    const score = constraints.objective === "margin" ? margin : revenue;
    const previous = best
      ? constraints.objective === "margin"
        ? best.expected_margin
        : best.expected_revenue
      : -Infinity;
    if (score > previous) {
      best = {
        recommended_price: price,
        expected_units: units,
        expected_revenue: revenue,
        expected_margin: margin,
        interval: [
          Math.min(constraints.inventory, point.interval_low),
          Math.min(constraints.inventory, point.interval_high),
        ],
        extrapolation_warning:
          penny === supportLowPenny || penny === supportHighPenny
            ? "The optimum touches historical price support. The model cannot justify prices beyond this boundary."
            : null,
      };
    }
  }
  return best;
}

export const money = (value: number) =>
  new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
    maximumFractionDigits: 2,
  }).format(value);
export const number = (value: number, digits = 0) =>
  new Intl.NumberFormat("en-GB", { maximumFractionDigits: digits }).format(
    value,
  );
export const percent = (value: number, digits = 1) =>
  `${number(value * 100, digits)}%`;
export const shortDate = (value: string) =>
  new Date(`${value.slice(0, 10)}T12:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
