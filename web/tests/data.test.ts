import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  interpolate,
  optimize,
  parseBundle,
  parseCurve,
} from "../src/lib/data.ts";
import type { Constraints, Product } from "../src/lib/types.ts";

// Deliberately simple unit fixtures. These are never shipped as evaluation artifacts.
const product: Product = {
  id: "unit-fixture",
  name: "Unit fixture",
  category: "test",
  as_of: "2011-12-05",
  current_price: 10,
  min_price: 5,
  max_price: 10,
  recommended_price: 5,
  curve: [
    { price: 5, units: 20, revenue: 100, interval_low: 15, interval_high: 25 },
    { price: 10, units: 8, revenue: 80, interval_low: 6, interval_high: 10 },
  ],
};
const constraints: Constraints = {
  cost_floor: 0,
  inventory: 100,
  min_markdown: 0,
  max_markdown: 0.5,
  objective: "revenue",
};

test("interpolation preserves the price-times-units revenue identity", () => {
  const point = interpolate(product.curve, 7.5);
  assert.equal(point.units, 14);
  assert.equal(point.revenue, 105);
  assert.equal(point.interval_low, 10.5);
  assert.equal(point.interval_high, 17.5);
});

test("interpolation cannot silently extrapolate outside the stored support", () => {
  assert.deepEqual(interpolate(product.curve, -100), product.curve[0]);
  assert.deepEqual(interpolate(product.curve, 100), product.curve[1]);
});

test("optimization enforces cost floor, support, markdown and inventory simultaneously", () => {
  const result = optimize(product, {
    ...constraints,
    cost_floor: 7,
    inventory: 3,
    min_markdown: 0.1,
    max_markdown: 0.25,
  });
  assert.ok(result);
  assert.equal(result.recommended_price, 9);
  assert.equal(result.expected_units, 3);
  assert.equal(result.expected_revenue, 27);
  assert.deepEqual(result.interval, [3, 3]);
  assert.ok(result.recommended_price >= 7.5 && result.recommended_price <= 9);
});

test("support boundaries carry an explicit warning", () => {
  const result = optimize(product, { ...constraints, inventory: 3 });
  assert.ok(result?.extrapolation_warning);
  assert.equal(result?.recommended_price, 10);
});

test("infeasible constraint combinations produce no recommendation", () => {
  assert.equal(optimize(product, { ...constraints, cost_floor: 11 }), null);
  assert.equal(
    optimize(product, { ...constraints, min_markdown: 0.8, max_markdown: 0.1 }),
    null,
  );
});

test("revenue and margin objectives can make different recommendations", () => {
  const revenue = optimize(product, { ...constraints, cost_floor: 4 });
  const margin = optimize(product, {
    ...constraints,
    cost_floor: 4,
    objective: "margin",
  });
  assert.equal(revenue?.recommended_price, 6.67);
  assert.equal(margin?.recommended_price, 8.67);
});

test("fractional-penny bounds round inward and can make a decision infeasible", () => {
  const result = optimize(product, { ...constraints, cost_floor: 9.981 });
  assert.equal(result?.recommended_price, 9.99);
  assert.equal(
    optimize(product, {
      ...constraints,
      cost_floor: 9.991,
      min_markdown: 0.0001,
    }),
    null,
  );
});

test("invalid and duplicate price surfaces are refused", () => {
  assert.throws(
    () => parseCurve([product.curve[0], product.curve[0]]),
    /distinct/,
  );
  assert.throws(
    () => parseCurve([{ ...product.curve[0], units: NaN }, product.curve[1]]),
    /invalid/,
  );
  assert.throws(() => parseBundle({ products: [] }), /unavailable/);
});

test("the committed measured bundle satisfies the complete client contract", () => {
  const value: unknown = JSON.parse(
    readFileSync(new URL("../public/bundle.json", import.meta.url), "utf8"),
  );
  const bundle = parseBundle(value);
  assert.ok(bundle.products.length > 0);
  assert.ok(bundle.backtest.summary.length > 0);
  for (const entry of bundle.products) {
    const result = optimize(entry, {
      ...constraints,
      inventory: 1000,
      max_markdown: 1,
    });
    assert.ok(result);
    assert.ok(result.recommended_price >= entry.min_price);
    assert.ok(result.recommended_price <= entry.max_price);
  }
});

test("undefined zero-sales WAPE remains null in the client contract", () => {
  const value = JSON.parse(
    readFileSync(new URL("../public/bundle.json", import.meta.url), "utf8"),
  ) as Record<string, unknown>;
  value.monitoring = [
    {
      week: "2011-01-03",
      observed_at: "2011-01-10",
      action: "continued incumbent",
      decision_as_of: "2010-12-27",
      scheduled_as_of: null,
      refit_trigger_observed_at: null,
      psi: { price: 0.1 },
      ks: 0.2,
      wape: null,
      retrain: false,
      reason: "No realized sales",
    },
  ];
  assert.equal(parseBundle(value).monitoring[0].wape, null);
});
