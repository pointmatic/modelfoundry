# concept.md — nbfoundry

This document defines why the `nbfoundry` project exists. 
- **Problem space**: problem statement, why, pain points, target users, value criteria
- **Solution space**: solution statement, goals, scope, constraints
- **Value mapping**: Pain point to solution mapping

For requirements and behavior (what), see [`features.md`](features.md). For implementation details (how), see [`tech-spec.md`](tech-spec.md). For a breakdown of the implementation plan (step-by-step tasks), see [`stories.md`](stories.md). For project-specific must-know facts (workflow rules, hidden coupling, tool-wrapper conventions that the LLM would otherwise random-walk on), see [`project-essentials.md`](project-essentials.md). For the workflow steps tailored to the current mode (cycle steps, approval gates, conventions), see [`docs/project-guide/go.md`](../project-guide/go.md) — re-read it whenever the mode changes or after context compaction.

## Problem Space

### Problem Statement

Machine learning practitioners — from working specialists to students and topic enthusiasts — spend disproportionate energy fighting their tooling rather than confronting the data and modeling problems they actually care about. Existing notebook tools, with Jupyter as the dominant example, layer brittle iPython kernel mechanics, infrastructure bias (Colab, SageMaker, Vertex), and framework lock-in (PyTorch vs. TensorFlow vs. Keras scaffolding) on top of the inherent complexity of ML work. The result: experts waste time on environment problems, newcomers face a steep climb just to tinker, and the notebooks themselves are unreliable as reproducible artifacts and unusable as embeddable components within larger learning systems.

There is also no clean separation between ML scaffolding (data loaders, training loops, evaluation harnesses) and instructional content (instructions, expected outputs, grading). Curriculum authors and exercise writers reinvent both sides every time, and a notebook authored for personal experimentation cannot be reused as a course exercise without a rewrite.

### Why the Problem Persists

- **Jupyter's execution model is structurally brittle**: out-of-order execution, hidden kernel state, and iPython quirks make notebooks unreliable, especially as content scales from one author's machine to many learners' machines.
- **Vendor-driven evolution**: the dominant notebook platforms (Colab, SageMaker, Vertex) optimize for their own infrastructure rather than for portability, locking content to a particular cloud.
- **Framework tribalism**: tutorials and exercises are written against one framework's idiosyncratic boilerplate, so content cannot be reused across PyTorch / TensorFlow / Keras stacks without rewriting the scaffolding.
- **GPU acceleration assumes CUDA on Linux**: Apple Silicon (Metal) is treated as an afterthought, even though it is the default development target for a large share of practitioners.
- **No embeddable modularity**: Jupyter notebooks are end-user tools, not components — they cannot be dropped cleanly into a larger application or curriculum without iframes, iPython hacks, or vendor-specific embeds.
- **Modeling and instructional content are conflated**: ML scaffolding and curriculum metadata (instructions, hints, grading) live tangled in the same files with no contract separating them, so neither side is reusable.
- **No dual-purpose authoring path**: a practitioner who writes a notebook for their own experimentation has no easy path to repurpose it as a curriculum exercise (or vice versa) without rewriting it from scratch.

### Pain Points

- **tool_friction_over_modeling**: ML practitioners spend more energy on environments, kernels, and platform configuration than on actual model and data work.
- **steep_newcomer_ramp**: ML students and topic enthusiasts face dense, technical tooling before they can experiment with even simple ideas.
- **infrastructure_bias**: Existing notebook tools are tightly coupled to a vendor (AWS, GCP, Colab) or a specific deployment context, fragmenting the experience and locking in content.
- **framework_lock_in**: Tutorials and exercises are written against one framework's boilerplate (PyTorch vs. TensorFlow vs. Keras), so content cannot be reused across stacks.
- **jupyter_brittleness**: Out-of-order execution, hidden state, iPython kernel quirks, and fragile dependency graphs make Jupyter notebooks unreliable as production-quality artifacts.
- **no_embeddable_modularity**: Jupyter notebooks cannot be cleanly embedded into larger applications or curricula; they are end-user tools, not components.
- **metal_hostility**: Apple Silicon developers struggle to get accelerated PyTorch / TensorFlow / Keras working; most tutorials assume CUDA on Linux.
- **modeling_content_conflation**: ML scaffolding and instructional content live in the same notebook with no contract between them, making either part hard to reuse independently.
- **no_dual_purpose_authoring**: A practitioner who writes a notebook for personal experimentation has no path to repurpose it as a curriculum exercise without rewriting it.

### Target Users

- **ML practitioners and data scientists** working on real model development who want to spend their time on data and modeling rather than on tooling.
- **ML students and topic enthusiasts** climbing a steep tooling hill who need opinionated, vetted scaffolding that works end-to-end out of the box.
- **Curriculum authors** building ML/DS courses in learningfoundry who need a reliable, embeddable exercise provider for hands-on content.
- **Apple Silicon developers** (indirect) who need a first-class GPU/Metal acceleration story.
- **Learners enrolled in learningfoundry courses** (indirect) who consume nbfoundry exercises through `ExerciseBlock` in the SvelteKit app.

### Value Criteria

- **Time-on-modeling vs. time-on-tooling**: practitioners spend more time on data and model decisions and less time on environment, kernel, and platform issues.
- **Newcomer time-to-first-meaningful-experiment**: a topic enthusiast can run a working data-and-model experiment within minutes of installing nbfoundry, without prior infrastructure expertise.
- **Reproducibility across machines**: an nbfoundry notebook runs deterministically on a teammate's or learner's machine after a single environment install step.
- **Content reusability**: a single notebook source can serve as both a standalone exploration tool and a learningfoundry curriculum exercise, with no rewrite required when its purpose changes.
- **Acceleration footprint**: GPU/Metal acceleration works out of the box on Apple Silicon, with PyTorch / TensorFlow / Keras all functional.
- **Embedding friction**: a curriculum author can drop a compiled nbfoundry exercise into a learningfoundry course in a single step, governed by the dependency-spec contract.

---

## Solution Space

### One-Liner

This project **delivers ML/DS notebooks as modular Marimo-based building blocks — equally usable as standalone exploration tools and as embeddable learningfoundry curriculum exercises, without Jupyter's brittleness or vendor lock-in.**

### Solution Statement

nbfoundry is a Marimo-based notebook framework built specifically for ML/DS work, sitting as a thin orchestration layer over modelfoundry's data and modeling primitives. Authors begin with opinionated notebook templates following a five-stage lifecycle (data exploration → data preparation → model experimentation → model optimization → model evaluation), and nbfoundry compiles each notebook (or tree of notebooks) into two interchangeable artifacts: a **standalone Python application** the author runs locally with full GPU/Metal acceleration, and an **`ExerciseBlock`-compatible compiled artifact** that drops into a learningfoundry curriculum per `learningfoundry-dependency-spec.md`. Because Marimo provides pure-Python notebooks with reactive cells and clean embedding semantics — no iPython kernel, no hidden state, no Jupyter cruft — the same source can serve a practitioner experimenting on a real model or a learner inside a structured course, extending the value of every notebook the author writes.

### Goals

- **Eliminate tool friction** so ML practitioners spend their time on model and data problems, not on infrastructure setup or kernel debugging.
- **Lower the ramp for newcomers** by shipping opinionated five-stage lifecycle templates that work end-to-end out of the box on Apple Silicon.
- **One source, two surfaces**: every nbfoundry notebook is simultaneously a standalone tool and an embeddable curriculum exercise — no rewrite required when purpose shifts.
- **Replace Jupyter's brittle execution model** with Marimo's reactive, embeddable, pure-Python substrate.
- **First-class GPU/Metal acceleration** through a verified Pyve + micromamba + Python 3.12.13 stack with Metal-compatible PyTorch / TensorFlow / Keras.
- **Honor the learningfoundry contract** so nbfoundry slots cleanly into the broader ecosystem as the canonical ML/DS exercise provider, with `<ExerciseBlock>` as one (of several) flavors of experiential learning object.
- **Stay loosely coupled to modelfoundry** so the heavy ML lifting stays where it belongs while nbfoundry remains a thin, opinionated orchestration layer.

### Scope

**In scope:**

- Python library and CLI that compile authored Marimo notebooks (single notebook or tree) into two artifacts: a standalone runnable app and an `ExerciseBlock`-compatible compiled exercise dict per the dependency spec.
- Opinionated five-stage notebook templates covering the model lifecycle: **data exploration, data preparation, model experimentation, model optimization, model evaluation**.
- Thin orchestration interface to modelfoundry for data prep, training, optimization, and evaluation primitives.
- v1 static-display embed path (Option B from `learningfoundry-dependency-spec.md`): rendered sections, expected outputs, hints, optional `submission` schema with paste-in fields and client-side grading per BR-4.
- Aggregate completion event back to learningfoundry — one response regardless of whether the embedded artifact is a single notebook or a tree.
- Pyve + micromamba + Python 3.12.13 environment with Metal-compatible PyTorch / TensorFlow / Keras pinned for first-class Apple Silicon support.
- Validation API (`compile_exercise`, `validate_exercise`, `ExerciseError`) per dependency-spec BR-1 / BR-2 / BR-3.

**Out of scope (deferred or owned elsewhere):**

- Marimo WASM in-browser execution (Option A from the dependency spec) — future, post-v1.
- Authoring tools beyond what the compile contract requires — no WYSIWYG notebook editor; notebooks are authored directly in Marimo.
- Non-ML/DS exercise flavors (interactive NN animations, simulations) — those fill the same generic `<ExerciseBlock>` scaffold but are produced by other tools, not nbfoundry.
- knowledgefoundry, datafoundry — separate future projects.
- Managed cloud platform — nbfoundry is local-first.
- Real-time multi-user collaboration on a notebook.
- User accounts, authentication, telemetry — those belong to learningfoundry, if anywhere.
- modelfoundry's internals — nbfoundry depends on modelfoundry but does not own its scope.

### Constraints

- **License and copyright**: Apache-2.0; copyright Pointmatic. SPDX identifier `Apache-2.0` on all new source files.
- **Python version**: 3.12.13 specifically, for verified Metal-acceleration compatibility with PyTorch / TensorFlow / Keras.
- **Environment manager**: Pyve + micromamba is the required runtime stack — no pip-only or conda-only alternatives.
- **Notebook substrate**: Marimo only. No Jupyter or iPython compatibility layer.
- **v1 embed contract**: locked to `docs/specs/learningfoundry-dependency-spec.md` — `compile_exercise` / `validate_exercise` / `ExerciseError`, `<ExerciseBlock>` props and events, BR-4 submission schema and scoring formula.
- **Static deployability**: the standalone artifact must run locally without any server infrastructure.
- **Apple Silicon Metal**: first-class acceleration target, not a footnote.
- **Modelfoundry interface — TBD**: the precise contract between nbfoundry and modelfoundry is unresolved at concept stage. nbfoundry's internal design must stay loosely coupled enough to absorb that interface when defined, without rewrites to the two-surface compiler.

---

## Pain Point → Solution Mapping

**tool_friction_over_modeling**:
  - The Pyve + micromamba + Python 3.12.13 stack is pinned and reproducible, so practitioners stop fighting environments and kernels.
  - Opinionated five-stage lifecycle templates absorb the boilerplate (data loaders, training loops, evaluation harnesses), letting practitioners focus on the modeling decisions that matter.

**steep_newcomer_ramp**:
  - The five-stage templates give newcomers a working end-to-end scaffold from the first run — they change parameters and experiment, not assemble infrastructure.
  - When the same notebook is consumed inside a learningfoundry course, the curriculum author layers instructions, hints, and expected outputs on top of it, providing guided context without modifying the underlying ML scaffolding.

**infrastructure_bias**:
  - nbfoundry runs locally on the practitioner's machine with no Colab / SageMaker / Vertex assumption built in.
  - Compiled artifacts are self-contained: a standalone app, or an `ExerciseBlock` dict the host SvelteKit app renders without server infrastructure.

**framework_lock_in**:
  - The five-stage lifecycle is a *workflow contract*, not a framework binding — PyTorch, TensorFlow, and Keras can each fill the same slots without rewriting the surrounding scaffolding.
  - Modelfoundry encapsulates framework-specific details below nbfoundry, so the same notebook structure can target multiple frameworks through a uniform API.

**jupyter_brittleness**:
  - Marimo replaces Jupyter as the substrate: pure Python files, reactive cells, no iPython kernel, no hidden state, no out-of-order execution mysteries.
  - Notebooks are reproducible from a clean environment via the pinned micromamba stack — what runs on the author's machine runs on the learner's machine.

**no_embeddable_modularity**:
  - Marimo's clean embedding semantics let nbfoundry compile a single source into both a standalone app and an `<ExerciseBlock>`-compatible artifact, with the same source reusable across both surfaces.
  - The two-surface architecture is built into the compiler from day one, not bolted on later — mirrors the proven Quizazz pattern.

**metal_hostility**:
  - The pinned Pyve + micromamba + Python 3.12.13 stack provides verified Metal-accelerated PyTorch / TensorFlow / Keras out of the box.
  - Apple Silicon developers are a primary target audience, not an edge case.

**modeling_content_conflation**:
  - The dependency spec's `ExerciseBlock` schema cleanly separates instructional metadata (instructions, hints, sections, optional `submission` block) from the underlying notebook content, enforced by `compile_exercise`.
  - A practitioner can author the ML notebook first and have a curriculum author add the instructional layer later, without either side bleeding into the other.

**no_dual_purpose_authoring**:
  - One source, two surfaces: every nbfoundry notebook is simultaneously a standalone exploration tool and an embeddable curriculum exercise — no rewrite when its purpose shifts.
  - This extends the value of authoring effort: a notebook the author writes for their own model experimentation can later be wrapped as a learningfoundry exercise without modification to the modeling work itself.
