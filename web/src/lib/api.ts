import { parseCurve } from "./data";
import type { Constraints, CurvePoint, Product, Recommendation } from "./types";

export const apiUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
export const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

async function post(
  path: string,
  body: unknown,
  signal: AbortSignal,
): Promise<unknown> {
  const response = await fetch(`${apiUrl}${path}`, {
    method: "POST",
    signal,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok)
    throw new Error(
      `Live service returned ${response.status}. Your selection has not been scored.`,
    );
  return response.json() as Promise<unknown>;
}

function object(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null)
    throw new Error("Invalid response from the live service.");
  return value as Record<string, unknown>;
}

function finite(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value))
    throw new Error("Live service returned an invalid prediction.");
  return value;
}

export async function fetchCurve(
  product: Product,
  signal: AbortSignal,
): Promise<CurvePoint[]> {
  const response = await post(
    "/v1/curve",
    {
      product_id: product.id,
      price_grid: product.curve.map((point) => point.price),
      as_of: product.as_of,
    },
    signal,
  );
  const points = Array.isArray(response)
    ? response
    : (object(response).curve ?? object(response).points);
  return parseCurve(points);
}

export async function fetchPrediction(
  product: Product,
  price: number,
  signal: AbortSignal,
): Promise<CurvePoint> {
  const response = object(
    await post(
      "/v1/predict",
      { product_id: product.id, price, as_of: product.as_of },
      signal,
    ),
  );
  return {
    price,
    units: finite(response.units),
    revenue: finite(response.revenue),
    interval_low: finite(response.interval_low),
    interval_high: finite(response.interval_high),
  };
}

export async function fetchOptimization(
  product: Product,
  constraints: Constraints,
  signal: AbortSignal,
): Promise<Recommendation> {
  const response = object(
    await post(
      "/v1/optimize",
      {
        product_id: product.id,
        current_price: product.current_price,
        ...constraints,
        as_of: product.as_of,
      },
      signal,
    ),
  );
  const interval = response.interval;
  const limits = Array.isArray(interval)
    ? interval
    : [object(interval).low, object(interval).high];
  return {
    recommended_price: finite(response.recommended_price),
    expected_units: finite(response.expected_units),
    expected_revenue: finite(response.expected_revenue),
    expected_margin: finite(response.expected_margin),
    interval: [finite(limits[0]), finite(limits[1])],
    extrapolation_warning:
      typeof response.extrapolation_warning === "string" ||
      typeof response.extrapolation_warning === "boolean"
        ? response.extrapolation_warning
        : null,
  };
}
