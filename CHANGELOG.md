# Changelog

All notable changes to **scythe-engine** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-03-28

### Added

- `computed_features` property on `ExperimentInputSpec` for attaching derived
  scalar index levels to the `MultiIndex` without defining them as Pydantic
  fields. Override in subclasses to return a `dict[str, ComputedFeatureValue]`.
- `ComputedFeatureValue` type alias (`int | float | str`).

### Changed

- `make_multiindex` now tracks index keys cumulatively to detect overlaps
  between Pydantic fields, computed features, and `additional_index_data`.

## [1.1.0] - 2026-03-28

### Added

- Support for Hatchet `Workflow` runnables alongside `Standalone` tasks.
  `ExperimentRegistry.Include()` now accepts both types, and `BaseExperiment`
  can wrap either for versioned experiment allocation.
- Single-spec allocation: pass a single `TInput` to `allocate()` instead of a
  list to trigger the runnable directly on Hatchet, bypassing scatter/gather.
  Returns a `WorkflowRunRef` instead of `TaskRunRef`.
- `ScytheWorkerLabel` enum (`HIGH_MEMORY`, `HIGH_CPU`, `HAS_GPU`) for type-safe
  worker label specification via `.worker_label` property.
- `HAS_GPU` flag on `ScytheWorkerConfig` (env: `SCYTHE_WORKER_HAS_GPU`).
- `additional_workflows` parameter on `ScytheWorkerConfig.start()` for serving
  `Workflow` runnables alongside the built-in scatter/gather and leaf tasks.
- New documentation guide for workflow and single-run experiments.

### Changed

- **BREAKING**: `BaseExperiment.experiment` field renamed to `runnable` to
  reflect that it now accepts both `Standalone` and `Workflow` types.
- **BREAKING**: `ExperimentRegistry.get_experiment()` renamed to
  `get_runnable()` and returns `Standalone | Workflow`.
- **BREAKING**: Internal registry storage split from `_experiments_dict` into
  `_standalones_dict` and `_workflows_dict`.
- Extracted `SerializableRunnable` base class from `BaseExperiment` to handle
  runnable serialization/deserialization via the experiment registry.
- Worker labels are now only emitted for flags set to `True` (previously
  all labels were always included with boolean values).
- Dropped Python 3.10 support; `requires-python` is now `>=3.11,<3.13`.
  Removed `typing_extensions` fallback for `Self`.
- Deferred `hatchet` client import in `ScytheWorkerConfig.start()` to avoid
  import-time side effects.

[1.2.0]: https://github.com/szvsw/scythe/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/szvsw/scythe/compare/v1.0.0...v1.1.0
