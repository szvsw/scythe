# API Reference

Auto-generated reference documentation for Scythe's public Python API.

## scythe.base

Core base classes for experiment input and output schemas.

::: scythe.base
options:
members: - BaseSpec - ExperimentInputSpec - ExperimentOutputSpec - ComputedFeatureValue
show_root_heading: false

## scythe.registry

Experiment registration and middleware.

::: scythe.registry
options:
members: - ExperimentRegistry
show_root_heading: false

## scythe.experiments

Experiment allocation, versioning, and result retrieval.

::: scythe.experiments
options:
members: - SerializableRunnable - BaseExperiment - VersionedExperiment - ExperimentRun - SemVer - ExperimentRunManifest - InputArtifactLocations
show_root_heading: false

## scythe.scatter_gather

Recursive scatter/gather workflow implementation.

::: scythe.scatter_gather
options:
members: - RecursionMap - RecursionSpec - ScatterGatherInput - ScatterGatherResult - GatheredExperimentRuns
show_root_heading: false

## scythe.worker

Worker configuration and startup.

::: scythe.worker
options:
members: - ScytheWorkerLabel - ScytheWorkerConfig - WorkerNameConfig
show_root_heading: false

## scythe.settings

Environment-based settings for storage and timeouts.

::: scythe.settings
options:
members: - ScytheStorageSettings - TimeoutSettings
show_root_heading: false

## scythe.utils.filesys

File reference types and URI fetching utilities.

::: scythe.utils.filesys
options:
members: - FileReference - OptionalFileReference - S3Url - FileReferenceMixin - fetch_uri
show_root_heading: false

## scythe.utils.results

DataFrame serialization and S3 upload helpers.

::: scythe.utils.results
options:
show_root_heading: false

## scythe.utils.s3

S3 client utilities.

::: scythe.utils.s3
options:
show_root_heading: false
