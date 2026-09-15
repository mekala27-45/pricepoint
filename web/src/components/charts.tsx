"use client";

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Bundle, CurvePoint, Recommendation } from "../lib/types";
import { money, number, percent, shortDate } from "../lib/data";

const axis = {
  fontSize: 11,
  fill: "var(--muted)",
  fontFamily: "var(--font-mono)",
};
const tip = {
  background: "var(--surface-raised)",
  border: "1px solid var(--line)",
  borderRadius: 10,
  color: "var(--ink)",
  fontSize: 12,
  fontFamily: "var(--font-mono)",
};

export function DemandChart({
  curve,
  price,
  recommended,
  metric,
}: {
  curve: CurvePoint[];
  price: number;
  recommended: Recommendation | null;
  metric: "units" | "revenue";
}) {
  const rows = curve.map((point) => ({
    ...point,
    band:
      metric === "units"
        ? [point.interval_low, point.interval_high]
        : [point.interval_low * point.price, point.interval_high * point.price],
  }));
  return (
    <div
      className="demand-chart"
      role="img"
      aria-label={`${metric === "units" ? "Demand in weekly units" : "Revenue in pounds"} by price, with uncertainty interval, selected price and recommended price`}
    >
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart
          data={rows}
          margin={{ top: 22, right: 12, bottom: 12, left: -12 }}
        >
          <CartesianGrid
            stroke="var(--line)"
            vertical={false}
            strokeDasharray="3 6"
          />
          <XAxis
            type="number"
            dataKey="price"
            domain={["dataMin", "dataMax"]}
            axisLine={false}
            tickLine={false}
            tick={axis}
            minTickGap={35}
            tickFormatter={(value: number) => money(value)}
            dy={10}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={axis}
            width={65}
            tickFormatter={(value: number) =>
              metric === "units" ? number(value) : `£${number(value)}`
            }
          />
          <Tooltip
            contentStyle={tip}
            labelFormatter={(value) => `Price ${money(Number(value))}`}
            formatter={(value, name) =>
              name === "band"
                ? [
                    Array.isArray(value)
                      ? value
                          .map((entry) => number(Number(entry), 1))
                          .join(" to ")
                      : value,
                    "Interval",
                  ]
                : [
                    metric === "units"
                      ? `${number(Number(value), 1)} units`
                      : money(Number(value)),
                    metric === "units" ? "Demand" : "Revenue",
                  ]
            }
          />
          <Area
            type="monotone"
            dataKey="band"
            stroke="none"
            fill="var(--accent)"
            fillOpacity={0.09}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey={metric}
            stroke="var(--accent)"
            strokeWidth={2.6}
            dot={false}
            isAnimationActive={false}
          />
          {recommended && (
            <ReferenceLine
              x={recommended.recommended_price}
              stroke="var(--accent)"
              strokeDasharray="4 5"
              label={{
                value: "OPTIMUM",
                position: "insideTopRight",
                ...axis,
                fill: "var(--accent)",
                fontSize: 9,
              }}
            />
          )}
          <ReferenceLine
            x={price}
            stroke="var(--ink)"
            strokeOpacity={0.7}
            strokeWidth={1.5}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export function LastFoldCharts({ bundle }: { bundle: Bundle }) {
  return (
    <div className="small-multiples">
      {bundle.backtest.summary.map((model) => {
        const rows = bundle.backtest.last_fold.filter(
          (row) => row.model === model.model,
        );
        return (
          <div className="mini-chart" key={model.model}>
            <h4>{model.label}</h4>
            <div style={{ height: 155 }}>
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart
                  data={rows}
                  margin={{ left: -20, top: 8, right: 8, bottom: 5 }}
                >
                  <CartesianGrid stroke="var(--line)" vertical={false} />
                  <XAxis dataKey="product_id" hide />
                  <YAxis
                    tick={axis}
                    axisLine={false}
                    tickLine={false}
                    width={55}
                  />
                  <Tooltip contentStyle={tip} />
                  <Line
                    dataKey="actual"
                    name="Observed units"
                    stroke="var(--muted)"
                    dot={false}
                    strokeWidth={1.5}
                    isAnimationActive={false}
                  />
                  <Line
                    dataKey="predicted"
                    name="Predicted units"
                    stroke="var(--accent)"
                    dot={false}
                    strokeWidth={1.7}
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <p className="chart-footnote">
              Products ordered by artifact · units / week
            </p>
          </div>
        );
      })}
    </div>
  );
}

export function MonitoringChart({ bundle }: { bundle: Bundle }) {
  return (
    <div
      className="monitoring-chart"
      role="img"
      aria-label="Rolling WAPE by the date completed sales became observable, with retraining requests marked on their actual observation dates"
    >
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart
          data={bundle.monitoring}
          margin={{ left: -16, right: 18, top: 18, bottom: 10 }}
        >
          <CartesianGrid
            stroke="var(--line)"
            vertical={false}
            strokeDasharray="3 6"
          />
          <XAxis
            dataKey="observed_at"
            tickFormatter={shortDate}
            minTickGap={45}
            tick={axis}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            tickFormatter={(value: number) => percent(value, 0)}
            tick={axis}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            contentStyle={tip}
            labelFormatter={(value) => `Observed ${shortDate(String(value))}`}
            formatter={(value) => [
              value == null
                ? "Undefined: no actual sales"
                : percent(Number(value)),
              "Rolling WAPE",
            ]}
          />
          <Area
            dataKey="wape"
            connectNulls={false}
            stroke="var(--accent)"
            strokeWidth={2}
            fill="var(--accent)"
            fillOpacity={0.06}
            isAnimationActive={false}
          />
          {bundle.monitoring
            .filter((row) => row.retrain)
            .map((row) => (
              <ReferenceLine
                key={row.week}
                x={row.observed_at}
                stroke="var(--warning)"
                strokeDasharray="3 4"
              />
            ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
