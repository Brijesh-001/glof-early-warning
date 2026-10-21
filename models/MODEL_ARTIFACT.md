# The trained model artifact (`gews_model.pkl`)

The deployable model — one Isolation Forest per lake per signal, bundled with the weights,
thresholds, and season-removal info — is **~375 MB** and is therefore **not committed** to the
repo (GitHub rejects files over 100 MB, and it bloats clones).

## Regenerate it
Run the last cell of `gews_modelling.ipynb`, or:

```python
import joblib
from sklearn.ensemble import IsolationForest
import gews_spec as G, pandas as pd

df = G.add_causal_deseason(G.load("../data/lake_data"))
bundle = {"models": {}, "climatology": {}, "signals": G.SIGNALS,
          "weights": G.WEIGHTS, "thresholds": G.THRESH, "obs_floor": G.OBS_FLOOR,
          "version": "2.1.0"}
for lake, g in df.groupby("lake"):
    bundle["models"][lake] = {}
    bundle["climatology"][lake] = {c: g.groupby("dekad")[c].median().to_dict()
                                   for c in ["lake_area_km2", "thermal_index"]}
    for c in G.SIGNALS:
        v = g.loc[g["observability"].fillna(0) >= 0.5, c + "_f"].dropna().values
        if len(v) >= 20:
            bundle["models"][lake][c] = IsolationForest(
                n_estimators=300, max_samples=min(256, len(v)),
                contamination=0.02, random_state=42).fit(v.reshape(-1, 1))
joblib.dump(bundle, "gews_model.pkl", compress=3)   # compress=3 keeps it much smaller
```

`compress=3` shrinks the file a lot; use it so the artifact is manageable. The `.pkl` is tied to
the scikit-learn version in `requirements.txt` — load it with the same version.
