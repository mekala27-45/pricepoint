# Pricepoint web

Four views of the stored retail evaluation, built with Next.js 15, strict TypeScript, Tailwind CSS v4, and Recharts. The default client reads the measured `public/bundle.json` artifact without a server or key.

```sh
npm ci
npm run typecheck
npm test
npm run build
npm run serve
```

The static preview listens at `http://127.0.0.1:3000/`. Set `PORT` to change its port.

## Two data sources

Set `NEXT_PUBLIC_API_URL` before building to route Explorer predictions, curves, and recommendations to the FastAPI service. Analytical views continue to show the committed backtest and monitoring evidence. The product universe and decision dates come from the bundle in both modes. Requests are debounced and aborted when controls change, and responses are matched to the active selection before display.

Set `NEXT_PUBLIC_BASE_PATH=/pricepoint` when building for a GitHub project page. Set the same variable when running the local static server to inspect that export.

## Decision semantics

The price control interpolates stored demand and interval endpoints. Revenue always equals the selected price times interpolated demand. The chart readouts show unconstrained predicted demand. The recommendation searches every feasible penny price using the interpolated stored demand surface, caps sales at the entered inventory, and restricts prices to historical support, cost floor, and markdown bounds. Margin is price less the entered cost floor, multiplied by capped sales. An infeasible constraint set produces an explicit empty result.

The measured incumbent can be a price-insensitive baseline when a candidate fails promotion. The serving evidence note identifies that outcome. Positive observational coefficients, failed candidates, and undefined WAPE during zero-sales weeks remain visible in the evidence.

Theme, contrast, chart labels, keyboard controls, reduced motion, and small-screen layouts are handled in the app. Browser storage is optional and only remembers the chosen theme.

## Checks

`npm test` runs behavioral tests for interpolation, grid optimization, support, inventory, objective selection, malformed artifacts, the complete committed bundle, and undefined WAPE. `npm run format:check` verifies Prettier formatting. The lockfile records exact resolved dependencies; a PostCSS override patches the version bundled transitively by Next.js 15.
