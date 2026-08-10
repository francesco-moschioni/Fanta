---
name: data-modeling
description: Load canonical source, data layer, entity-resolution, feature, generative modeling, validation, uncertainty, and degradation rules.
---

# Data and modeling workflow

Read `docs/DECISIONS.md`, `docs/DATA_AND_MODELING.md`, `docs/SOURCE_REGISTER.md`, relevant scoring/auction rules, and only then the relevant research sections.

Required sequence: state observation unit, target, horizon and decision timestamp; identify knowable data; validate access/rights/provenance; preserve raw and stage separately; resolve stable IDs with confidence/review queue; define `available_at`; use temporal folds with all preprocessing inside; compare declared baselines; report point/probabilistic/calibration metrics and subgroup slices; record snapshot/config/commit/seed; add leakage/schema/join/reproducibility tests; validate forecast-to-bid through roster-aware replay rather than direct conversion.

Do not select from in-sample fit or one metric. Do not hide missing modules: apply the documented fallback and label proxy/confidence. Do not treat a community archive as official or an undocumented endpoint as permitted.
