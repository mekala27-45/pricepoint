export interface CurvePoint {
  price: number;
  units: number;
  revenue: number;
  interval_low: number;
  interval_high: number;
}

export interface Product {
  id: string;
  name: string;
  category: string;
  current_price: number;
  min_price: number;
  max_price: number;
  as_of: string;
  recommended_price: number;
  curve: CurvePoint[];
}

export interface ModelSummary {
  model: string;
  label: string;
  wape_mean: number;
  wape_std: number;
  mase_mean: number;
  mase_std: number;
  coverage?: number;
}

export interface Bundle {
  meta: {
    generated_at: string;
    dataset: string;
    model_version: string;
    nominal_coverage: number;
    source_note: string;
  };
  products: Product[];
  backtest: {
    summary: ModelSummary[];
    folds: {
      fold: number;
      model: string;
      train_end: string;
      test_start: string;
      wape: number;
      mase: number;
    }[];
    last_fold: {
      model: string;
      product_id: string;
      actual: number;
      predicted: number;
    }[];
  };
  elasticity: {
    category: string;
    before: number;
    before_low: number;
    before_high: number;
    after: number;
    after_low: number;
    after_high: number;
    observations: number;
  }[];
  monitoring: {
    week: string;
    observed_at: string;
    action: string;
    decision_as_of: string;
    scheduled_as_of: string | null;
    refit_trigger_observed_at: string | null;
    psi: Record<string, number>;
    ks: number;
    wape: number | null;
    retrain: boolean;
    reason: string;
  }[];
}

export interface Constraints {
  cost_floor: number;
  inventory: number;
  min_markdown: number;
  max_markdown: number;
  objective: "revenue" | "margin";
}

export interface Recommendation {
  recommended_price: number;
  expected_units: number;
  expected_revenue: number;
  expected_margin: number;
  interval: [number, number];
  extrapolation_warning: string | boolean | null;
}
