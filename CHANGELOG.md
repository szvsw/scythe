# Changelog

All notable changes to **scythe-engine** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.1] - Unreleased

### Added

- `ScatterGatherInput.validated_specs` cached property for synchronous spec
  access (replaces the previous synchronous `specs` property).
- `ScatterGatherInput.create_bulk_run_experiment_specs()` method for preparing
  bulk-run trigger configs from a list of specs.
- `ScatterGatherInput.gather_outputs()` method for collecting results from
  child scatter/gather tasks using a thread pool.
- `log` parameter on `save_and_upload_parquets()` to control per-file upload
  logging.

### Changed

- **BREAKING** `ScatterGatherInput.specs` is now an async property; use
  `validated_specs` for synchronous access.
- Scatter/gather operations offload blocking I/O and CPU-heavy work to
  background threads via `asyncio.to_thread()`, preventing event-loop
  starvation during spec validation, result sifting, result combining,
  parquet uploads, and error concatenation.
- `ScatterGatherResult` now reads parquet files directly from S3 URLs via
  PyArrow instead of downloading to temporary files.
- `save_and_upload_parquets()` writes DataFrames directly to S3 via
  `df.to_parquet(uri)` instead of writing to temp files and uploading with
  the S3 client.
- `fetch_uri()` log messages downgraded from `info` to `debug` to reduce
  noise during bulk operations.
- `sort_index` is now included in `additional_metadata` when dispatching
  bulk experiment runs.

### Removed

- **BREAKING** `s3` parameter from `save_and_upload_parquets()`. The S3
  client is no longer needed as PyArrow handles S3 writes natively.

## [1.3.0] - 2026-04-09

### Added

- `log_interval()` utility in `scythe.utils` for computing dynamic periodic
  logging intervals (at most 20 log calls per loop, never more frequent than
  every 5 steps).
- `tqdm` progress bars and periodic `logger.info` calls throughout allocation
  and scatter/gather for better observability of long-running spec processing.
  Affected areas: spec validation, metadata overwriting, file-reference
  rewriting, spec serialization, experiment dispatch, result sifting, and
  parquet upload.
- Module-level loggers (`logging.getLogger(__name__)`) in `experiments.py` and
  `scatter_gather.py`.

### Changed

- All logging now uses standard Python `logging` instead of Hatchet
  `context.log()` or injectable logger callables. Hatchet automatically
  captures stdlib log output in recent SDK versions, so the old bridging
  mechanisms are no longer needed.

### Removed

- **BREAKING** `BaseSpec.log()` method. Use a module-level
  `logger = logging.getLogger(__name__)` instead.
- **BREAKING** `overwrite_log_method` parameter from
  `ExperimentRegistry.Register()` and the `context.log` lambda bridge it
  controlled.
- **BREAKING** `logger_fn` parameter from `fetch_uri()`. The function now
  logs directly via its module-level logger.
- **BREAKING** `logger` parameter from
  `ScatterGatherResult.to_gathered_experiment_runs()`.

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

[1.3.1]: https://github.com/szvsw/scythe/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/szvsw/scythe/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/szvsw/scythe/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/szvsw/scythe/compare/v1.0.0...v1.1.0
