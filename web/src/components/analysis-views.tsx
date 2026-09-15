"use client";

import { useState } from "react";
import type { Bundle } from "../lib/types";
import { number, percent, shortDate } from "../lib/data";
import { LastFoldCharts, MonitoringChart } from "./charts";

export function Backtest({ bundle }: { bundle: Bundle }) {
  const [metric, setMetric] = useState<"wape" | "mase">("wape");
  const folds = [...new Set(bundle.backtest.folds.map((row) => row.fold))];
  const best = [...bundle.backtest.summary].sort(
    (a, b) => a.wape_mean - b.wape_mean,
  )[0];
  return (
    <section className="analysis-view">
      <div className="view-heading">
        <div>
          <div className="eyebrow">02 / TEMPORAL EVALUATION</div>
          <h1>
            Every fold.
            <br />
            <span className="quiet">Nothing hidden.</span>
          </h1>
        </div>
        <p>
          Expanding training windows. One week ahead.
          <br />
          One week of decision lag. No shuffled splits.
        </p>
      </div>
      <div className="section-label">
        <h2>Models against the baselines</h2>
        <span>{folds.length} rolling origins · lower is better</span>
      </div>
      <div className="metric-cards">
        {bundle.backtest.summary.map((model) => (
          <article
            className={`model-card ${model.model === best?.model ? "best-model" : ""}`}
            key={model.model}
          >
            <div className="eyebrow">
              {model.model}
              {model.model === best?.model && (
                <span className="tiny-tag">LOWEST WAPE</span>
              )}
            </div>
            <h3>{model.label}</h3>
            <div className="model-score">{percent(model.wape_mean)}</div>
            <p>
              WAPE <span>± {percent(model.wape_std)} SD</span>
            </p>
            <div className="model-secondary">
              MASE <strong>{number(model.mase_mean, 3)}</strong>
              <span>± {number(model.mase_std, 3)} SD</span>
            </div>
          </article>
        ))}
      </div>
      <div className="panel fold-panel">
        <div className="panel-heading">
          <div>
            <h2>The complete backtest</h2>
            <p>Held-out results for each temporal fold</p>
          </div>
          <div className="segmented">
            <button
              className={metric === "wape" ? "selected" : ""}
              onClick={() => setMetric("wape")}
            >
              WAPE
            </button>
            <button
              className={metric === "mase" ? "selected" : ""}
              onClick={() => setMetric("mase")}
            >
              MASE
            </button>
          </div>
        </div>
        <div className="table-scroll">
          <table>
            <caption className="sr-only">
              Per-fold {metric.toUpperCase()} by model
            </caption>
            <thead>
              <tr>
                <th>Fold / test week</th>
                {bundle.backtest.summary.map((model) => (
                  <th key={model.model}>{model.model}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {folds.map((fold) => {
                const rows = bundle.backtest.folds.filter(
                  (row) => row.fold === fold,
                );
                return (
                  <tr key={fold}>
                    <th>
                      <span>{String(fold).padStart(2, "0")}</span>{" "}
                      {rows[0] ? shortDate(rows[0].test_start) : ""}
                    </th>
                    {bundle.backtest.summary.map((model) => {
                      const row = rows.find(
                        (entry) => entry.model === model.model,
                      );
                      return (
                        <td key={model.model}>
                          {row
                            ? metric === "wape"
                              ? percent(row.wape)
                              : number(row.mase, 3)
                            : "Unavailable"}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
              <tr className="summary-row">
                <th>Mean ± SD</th>
                {bundle.backtest.summary.map((model) => (
                  <td key={model.model}>
                    {metric === "wape" ? (
                      <>
                        {percent(model.wape_mean)}
                        <small>± {percent(model.wape_std)}</small>
                      </>
                    ) : (
                      <>
                        {number(model.mase_mean, 3)}
                        <small>± {number(model.mase_std, 3)}</small>
                      </>
                    )}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
        <div className="panel-note">
          WAPE weights errors by sales volume. MASE compares error with a naive
          forecast. MAPE is undefined at zero, so it is unsuitable for a retail
          panel with weeks of no sales.
        </div>
      </div>
      <div className="section-label">
        <h2>One last look at the last fold</h2>
        <div className="legend">
          <span>
            <i className="legend-line muted-line" />
            Observed
          </span>
          <span>
            <i className="legend-line" />
            Predicted
          </span>
        </div>
      </div>
      <LastFoldCharts bundle={bundle} />
    </section>
  );
}

export function Elasticity({ bundle }: { bundle: Bundle }) {
  const positive = bundle.elasticity.filter((row) => row.after > 0).length;
  const endpoints = bundle.elasticity.flatMap((row) => [
    row.before_low,
    row.before_high,
    row.after_low,
    row.after_high,
  ]);
  const low = Math.floor(Math.min(-1, ...endpoints));
  const high = Math.ceil(Math.max(1, ...endpoints));
  const position = (value: number) => (100 * (value - low)) / (high - low);
  return (
    <section className="analysis-view">
      <div className="view-heading">
        <div>
          <div className="eyebrow">03 / OBSERVATIONAL ELASTICITY</div>
          <h1>
            Price moves.
            <br />
            <span className="quiet">So does the story.</span>
          </h1>
        </div>
        <p>
          Association is measurable.
          <br />
          Causation needs an experiment.
        </p>
      </div>
      <div className="elasticity-grid">
        <div className="panel coefficients-panel">
          <div className="panel-heading">
            <div>
              <h2>The lagged-price coefficient, by category</h2>
              <p>Point estimates with 95% confidence intervals</p>
            </div>
          </div>
          <div className="legend coefficient-legend">
            <span>
              <i className="legend-dot muted-dot" />
              Before controls
            </span>
            <span>
              <i className="legend-dot" />
              After controls
            </span>
            <span>
              <i className="legend-dot warning-dot" />
              Positive after controls
            </span>
          </div>
          <div className="coefficient-chart">
            <div className="coefficient-axis">
              <span>{number(low, 1)}</span>
              <span>Lagged log-price coefficient</span>
              <span>{number(high, 1)}</span>
            </div>
            {bundle.elasticity.map((row) => (
              <div className="coefficient-row" key={row.category}>
                <div className="coefficient-label">
                  <strong>{row.category}</strong>
                  <span className={row.after > 0 ? "warning-text" : ""}>
                    {number(row.after, 2)}
                    {row.after > 0 ? " ↑" : ""}
                  </span>
                </div>
                <div
                  className="whisker-track"
                  role="img"
                  aria-label={`${row.category}: before ${row.before.toFixed(2)}, interval ${row.before_low.toFixed(2)} to ${row.before_high.toFixed(2)}; after ${row.after.toFixed(2)}, interval ${row.after_low.toFixed(2)} to ${row.after_high.toFixed(2)}`}
                >
                  <div
                    className="zero-rule"
                    style={{ left: `${position(0)}%` }}
                  />
                  <div
                    className="whisker before"
                    style={{
                      left: `${position(row.before_low)}%`,
                      width: `${position(row.before_high) - position(row.before_low)}%`,
                    }}
                  />
                  <div
                    className="whisker-point before"
                    style={{ left: `${position(row.before)}%` }}
                  />
                  <div
                    className={`whisker after ${row.after > 0 ? "positive" : ""}`}
                    style={{
                      left: `${position(row.after_low)}%`,
                      width: `${position(row.after_high) - position(row.after_low)}%`,
                    }}
                  />
                  <div
                    className={`whisker-point after ${row.after > 0 ? "positive" : ""}`}
                    style={{ left: `${position(row.after)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
          <div className="panel-note">
            A coefficient of -1 suggests a 1% higher previously observed price
            is associated with roughly 1% fewer subsequent units, conditional on
            the model. This past-known feature is not a contemporaneous
            randomized price or a causal estimate.
          </div>
        </div>
        <aside className="finding-card">
          <div className="eyebrow">THE FINDING</div>
          <div className="finding-number">
            {positive}
            <span> / {bundle.elasticity.length}</span>
          </div>
          <h2>
            {positive === 0
              ? "No positive coefficients in this run."
              : "Categories still have a positive price coefficient."}
          </h2>
          <p>
            The feature is the price known before the sales week. Retailers set
            those past prices in response to demand, inventory, and the season.
            Negative estimates do not resolve that confounding.
          </p>
          <div className="finding-divider" />
          <h3>What controls can do</h3>
          <p>
            Seasonality, trend, product effects, and stock-out proxies explain
            some variation. The chart shows how much the estimate moves.
          </p>
          <h3>What would settle it</h3>
          <p>
            Randomize prices within product and time blocks, set a guardrail on
            stock availability, and measure demand through a prespecified
            experiment.
          </p>
          <span className="note-label">
            A demand curve is a decision aid.
            <br />
            It is not permission to claim causality.
          </span>
        </aside>
      </div>
    </section>
  );
}

export function Monitoring({ bundle }: { bundle: Bundle }) {
  const features = [
    ...new Set(bundle.monitoring.flatMap((row) => Object.keys(row.psi))),
  ];
  const triggers = bundle.monitoring.filter((row) => row.retrain);
  const latest = bundle.monitoring[bundle.monitoring.length - 1];
  const maxPsi = latest ? Math.max(0, ...Object.values(latest.psi)) : 0;
  return (
    <section className="analysis-view">
      <div className="view-heading">
        <div>
          <div className="eyebrow">04 / HISTORICAL MONITORING</div>
          <h1>
            Models change.
            <br />
            <span className="quiet">Keep watching.</span>
          </h1>
        </div>
        <p>
          Historical simulation on public retail data.
          <br />A retraining trigger is a signal to investigate.
        </p>
      </div>
      <div className="monitor-stats">
        <article className="panel">
          <span className="eyebrow">LATEST MAX FEATURE PSI</span>
          <strong className={maxPsi > 0.25 ? "warning-text" : "accent-text"}>
            {number(maxPsi, 3)}
          </strong>
          <p>
            {maxPsi > 0.25
              ? "Retraining threshold exceeded"
              : maxPsi > 0.1
                ? "Moderate distribution shift"
                : "Within conventional drift threshold"}
          </p>
        </article>
        <article className="panel">
          <span className="eyebrow">LATEST ROLLING WAPE</span>
          <strong>
            {latest
              ? latest.wape === null
                ? "Undefined"
                : percent(latest.wape)
              : "Unavailable"}
          </strong>
          <p>
            {latest?.wape === null
              ? "No actual sales in this window"
              : "Against realized weekly sales"}
          </p>
        </article>
        <article className="panel">
          <span className="eyebrow">SIMULATED TRIGGERS</span>
          <strong>{triggers.length}</strong>
          <p>Two-week cooldown between triggers</p>
        </article>
        <article className="panel">
          <span className="eyebrow">LATEST PREDICTION KS</span>
          <strong>{latest ? number(latest.ks, 3) : "Unavailable"}</strong>
          <p>Distribution distance from training</p>
        </article>
      </div>
      <div className="panel heatmap-panel">
        <div className="panel-heading">
          <div>
            <h2>Where the inputs drift</h2>
            <p>Population stability index, by feature and sales week</p>
          </div>
          <div className="heatmap-legend">
            <span>Stable</span>
            <i />
            <i />
            <i />
            <span>Shifted</span>
          </div>
        </div>
        <div className="heatmap-scroll">
          <div
            className="heatmap"
            style={{
              gridTemplateColumns: `165px repeat(${bundle.monitoring.length}, minmax(13px, 1fr))`,
            }}
          >
            <span className="heatmap-corner">FEATURE / SALES WEEK</span>
            {bundle.monitoring.map((row, index) => (
              <span className="heatmap-date" key={row.week}>
                {index %
                  Math.max(1, Math.floor(bundle.monitoring.length / 7)) ===
                0
                  ? shortDate(row.week)
                  : ""}
              </span>
            ))}
            {features.map((feature) => (
              <FeatureRow
                key={feature}
                feature={feature}
                rows={bundle.monitoring}
              />
            ))}
          </div>
        </div>
        <div className="panel-note">
          PSI thresholds of 0.10 and 0.25 are conventions, not universal tests.
          Hover or focus any cell for its measured value.
        </div>
      </div>
      <div className="panel">
        <div className="panel-heading">
          <div>
            <h2>Forecast error, with a response</h2>
            <p>
              Rolling WAPE and triggers, on the date outcomes became observable
            </p>
          </div>
          <div className="legend">
            <span>
              <i className="legend-line" />
              WAPE
            </span>
            <span>
              <i className="legend-rule" />
              Trigger observed
            </span>
          </div>
        </div>
        <MonitoringChart bundle={bundle} />
        <div className="panel-note">
          Dates show when completed sales weeks became observable, not when the
          sales occurred. A trigger fires if any feature PSI exceeds 0.25 or
          rolling WAPE degrades more than 10% across four weeks, subject to a
          two-week cooldown. Gaps indicate weeks with zero actual sales, when
          WAPE is undefined.
        </div>
      </div>
      <div className="section-label">
        <h2>Trigger history</h2>
        <span>{triggers.length} events in the simulation</span>
      </div>
      <div className="trigger-list">
        {triggers.length ? (
          triggers.map((row) => (
            <TriggerEvent
              key={row.observed_at}
              row={row}
              timeline={bundle.monitoring}
            />
          ))
        ) : (
          <div className="panel empty-state">
            No retraining thresholds were crossed in this simulation.
          </div>
        )}
      </div>
    </section>
  );
}

function TriggerEvent({
  row,
  timeline,
}: {
  row: Bundle["monitoring"][number];
  timeline: Bundle["monitoring"];
}) {
  const completion = timeline.find(
    (entry) => entry.refit_trigger_observed_at === row.observed_at,
  );
  return (
    <article>
      <span className="trigger-dot" />
      <time dateTime={row.observed_at}>{row.observed_at.slice(0, 10)}</time>
      <div>
        <h3>Retraining requested</h3>
        <p>{row.reason}</p>
        <p className="trigger-evidence">
          Flagged sales week: {row.week.slice(0, 10)}. Scheduled decision
          cutoff: {row.scheduled_as_of?.slice(0, 10) ?? "none recorded"}.
        </p>
        <p className="trigger-outcome">
          {completion ? (
            <>
              Outcome: {completion.action}. Decision cutoff{" "}
              {completion.decision_as_of.slice(0, 10)}.
            </>
          ) : (
            "Outcome: pending at the end of the historical simulation."
          )}
        </p>
      </div>
      <span className="tiny-tag">
        {completion ? "REFIT COMPLETED" : "PENDING"}
      </span>
    </article>
  );
}

function FeatureRow({
  feature,
  rows,
}: {
  feature: string;
  rows: Bundle["monitoring"];
}) {
  return (
    <>
      <span className="heatmap-feature" title={feature}>
        {feature.replaceAll("_", " ")}
      </span>
      {rows.map((row) => {
        const value = row.psi[feature];
        return (
          <div
            key={row.week}
            tabIndex={0}
            className={`heat-cell ${value === undefined ? "missing" : value > 0.25 ? "high" : value > 0.1 ? "medium" : "low"}`}
            title={`${feature} · ${row.week.slice(0, 10)} · PSI ${value === undefined ? "unavailable" : value.toFixed(4)}`}
            aria-label={`${feature}, ${row.week.slice(0, 10)}, PSI ${value === undefined ? "unavailable" : value.toFixed(4)}`}
          />
        );
      })}
    </>
  );
}
