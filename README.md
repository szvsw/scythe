# Scythe

[![Release](https://img.shields.io/github/v/release/szvsw/scythe)](https://img.shields.io/github/v/release/szvsw/scythe)
[![Build status](https://img.shields.io/github/actions/workflow/status/szvsw/scythe/main.yml?branch=main)](https://github.com/szvsw/scythe/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/szvsw/scythe/branch/main/graph/badge.svg)](https://codecov.io/gh/szvsw/scythe)
[![Commit activity](https://img.shields.io/github/commit-activity/m/szvsw/scythe)](https://img.shields.io/github/commit-activity/m/szvsw/scythe)
[![License](https://img.shields.io/github/license/szvsw/scythe)](https://img.shields.io/github/license/szvsw/scythe)

Scythe is a lightweight tool which helps you seed and reap (scatter and gather)
emabarassingly parallel experiments via the asynchronous distributed queue [Hatchet](https://hatchet.run).

> The project is still in the VERY EARLY stages, and will likely evolve quite a bit in the
> second half of 2025.

- **Github repository**: <https://github.com/szvsw/scythe/>
- **Documentation** <https://szvsw.github.io/scythe/>

## Motivation

In my experience helping colleagues with their research projects,
academic researchers and engineers often have the ability to define their
experiments via input and output specs fairly well and would love to run at large scales,
but often get limited by a lack of experience with distributed computing techniques,
eg. artifact infil- and exfiltration, handling errors, interacting with supercomputing schedulers,
dealing with cloud infrastructure, etc.

The goal of Scythe is to abstract away some of these
details to let researchers focus on what they are familiar with (i.e. writing consistent
input and output schemas and the computation logic that transforms data from inputs into
outputs) while automating the boring but necessary work to run millions of simulations (e.g.
serializing data to and from cloud buckets, configuring queues, etc).

There are of course lots of data engineering orchestration tools out there already, but this
is a bit more lightweight and hopefully a little simpler to use, at the expense of less things
like (for now) not robustly tracking data lineage, etc. Somet

[Hatchet](https://hatchet.run) is already very easy (and fun!) to use for newcomers to
distributed computing, so I recommend checking out their docs - you might be better off
simply directly running Hatchet! Scythe is just a lightweight modular layer on top of it
which is really tailored to the use case of generating large datasets of consistently structured
experiment inputs and outputs. Another option you might check out would be something like [Coiled + Dask](https://coiled.io/).

## Documentation

Coming soon...

However, in the meantime, check out the [example project](https://github.com/szvsw/scythe-example)
to get an idea of what using Scythe with Hatchet looks like.

## To-dos (help wanted!)

- Start documenting
- ExperimentRun class
- Results downloaders
- Automatic local artifact conversion to cloud artifacts
