# Browser verification

Verified locally on the final static export at the GitHub Pages base path and on a development build connected to the running FastAPI service.

- Explorer: product search by code, product selection, supported price movement, revenue chart, reset and recommendation controls.
- Constraints: infeasible cost floor produces an explicit no-feasible-recommendation state. Live inventory cap restricts expected sold units.
- Backtest: all model summaries and fold rows render; WAPE/MASE switching works.
- Elasticity: all inferred groups and before/after intervals render. The zero-positive finding and lagged-price caveat match the artifacts.
- Monitoring: heatmap, WAPE gaps, actual observation dates, completed refits and final pending trigger render.
- Responsive: all four views fit the 390-pixel viewport without document-level horizontal overflow. Wide evidence grids scroll inside their panels.
- Themes: dark and light render legibly.
- Live requests: forecasts, curves and optimization return successfully; no browser errors were recorded in that check.

The seven-second demo GIF uses actual browser captures of the price slider and revenue response. The incumbent is a trailing-mean baseline, so its unit forecast is intentionally flat across prices. The social preview is rendered from the accompanying SVG.

This is functional and visual smoke verification, not a formal accessibility audit or a cross-browser compatibility certification.
