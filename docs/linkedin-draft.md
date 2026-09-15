# LinkedIn draft

I built a price-elasticity service on public retail transactions. The demand model did not earn deployment.

A trailing-mean baseline had lower held-out error than LightGBM, and the candidate also failed the category regression gate. The service keeps the baseline and scores the candidate in shadow mode.

The price coefficients were negative, but that does not make them causal. Prices were not randomized, inventory is missing, and the available feature is a historical price at the decision cutoff. Those limits matter more than a plausible-looking demand curve.

The work I found most useful was around the model: independent training and serving features, deliberately broken promotion gates, event-time credit accounting, and a retraining simulation that waits until the triggering sales actually become observable.

The demo and results include the failed promotion, the complete temporal backtest, and the assumptions behind a price-experiment plan.

Demo: https://mekala27-45.github.io/pricepoint/
Code and methodology: https://github.com/mekala27-45/pricepoint

#MachineLearning #MLOps #RetailAnalytics
