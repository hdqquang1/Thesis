# Thesis Plan — VR Interactive Segmentation of Forest LiDAR

_Last updated: 2026-08-30_

This plan is grounded in the Preliminary Report and the seminar slides, revised after Thesis A learnings. The thesis builds a Meta Quest 3S VR tool (via **Quest Link**, PC-tethered) that (a) renders ~10M-point forest LiDAR clouds at interactive frame rates, (b) lets the user place click / box / brush prompts on individual points, and (c) closes the loop with a deep-learning interactive semantic segmentation backbone using **InterPCSeg-style test-time refinement** as the primary method. Four classes: **stem, foliage, ground, undergrowth**. Data: Hovermap TLS scans across five commercial pine plots (DogPark, HQP2020, OFO2021; Chinthammit et al.), all pre-labelled.

Key decisions locked since the May version: **PTv3** is the primary backbone (RandLA-Net fallback), trained via **Pointcept**; KPConvX is dropped; AGILE3D-style click-attention is deferred to future/stretch work; evaluation is strictly technical (no user study); and a **voxel hash grid** in UE5 is the interactive spatial structure, since the LiDAR plugin's octree is private and cannot be queried.

---

## 1. Where things stand

### 1.1 Locked-in (revised since the report)
- Hardware: Meta Quest 3S via **Quest Link** (PC-tethered; standalone deployment dropped — rendering and inference both run on the PC).
- Engine: UE5 (Meta's official fork) + LiDAR Point Cloud plugin.
- Backbone: **PTv3 primary, RandLA-Net fallback**, trained via **Pointcept**. KPConvX dropped (no SemanticKITTI results; experimental scope limited to S3DIS / ScanNetv2 / ScanObjectNN). Note PTv3's reported Val mIoU has community reproducibility concerns — treat published numbers as upper bounds.
- Interactive method: **InterPCSeg-style test-time refinement** (primary). AGILE3D-style click-attention adaptation is future/stretch work — it requires a Minkowski-sparse-conv backbone to pre-compute features that the click-attention module propagates through.
- Spatial structure: **voxel hash grid** maintained in UE5, parallel to the plugin's private octree.
- Evaluation is strictly technical: NoC@q, IoU@k, frame rate, inference time. **No user studies** (NASA-TLX / SUS / SSQ and HREC paperwork are out of scope).
- Framing note: the semantic-vs-instance gap between the interactive-segmentation literature and this thesis's semantic goal is a research contribution, not a weakness. SAMIRA / DIVA are cited only as demonstrations of the VR-coupled neural inference loop pattern — they operate on volumetric medical images, not point clouds.

### 1.2 Done already
- Quest 3S acquired (Thesis Funding Scheme).
- UE5 + Oculus / OpenXR / hand-tracking / eye-tracking / LidarPointCloud plugins enabled in the `ISSR_VR` project.
- Preliminary Report draft written, seminar delivered. Thesis A complete.
- Open3D 0.19 built from source on Windows with CUDA 12.6 + PyTorch ops — the ML pipeline environment exists (`environment.yml`).
- **Wire protocol implemented on both sides, kept in sync deliberately**: `ISSR_PC/src/ISSR_PC/protocol.py` (HELLO / READY / CLICK / LABELS / FULL_LABELS, struct-packed) mirrored by `ISSR_VR/Source/ISSR_VR/{Public,Private}/SegProtocol.{h,cpp}`, with `static_assert`s pinning the C++ struct sizes to the Python `struct` formats. Covered by 461 lines of tests (`ISSR_PC/tests/test_protocol.py`).
- **Python TCP server** (`server.py`: `Listener`/`Connection`, blocking single-client, length-prefixed framing) and **UE5 TCP client** (`SegClientComponent`: non-blocking socket, explicit `Disconnected → Connected → Ready → Loop` handshake state machine).
- **Point store on the UE5 side** (`SegPointStoreComponent`): builds index-stable canonical position/label arrays from a `LidarPointCloud` asset, exports them to a canonical `.bin` (positions + ground-truth labels + checksum) that the Python side loads for the handshake, supports ray-pick and exact-position lookup (sorted array + binary search — see note below), and writes label updates back onto the plugin's per-point `ClassificationID` for display. This is the real version of the "decouple labels from RGB" idea in §2.1.
- **Click tool implemented**: `SegInteractionComponent` binds a UE5 Enhanced Input action (`IA_SegClick` / `IMC_Segmentation`, committed under `ISSR_VR/Content/ISSR/`) to a motion-controller aim ray, picks a point via the point store, and sends it as a `CLICK` through `SegClientComponent`.
- **`app.py` is a working, if geometric-only, end-to-end server**: loads the canonical `.bin`, builds an Open3D KD-tree, runs the HELLO/READY handshake with checksum validation, sends the ground-truth labels as the initial `FULL_LABELS` (`seg_infer` is still a `TODO`), then on each `CLICK` does a 5000-nearest-neighbour flood-fill of the clicked class and replies with `LABELS`. Functionally this **is** the plan's `GeometricBackend` (§2.3, item 1), just written inline rather than behind an interface (see gaps below).
- **Segmentation metrics implemented**: `metrics.py` — confusion matrix, per-class IoU, mIoU, overall accuracy — with tests (`tests/test_metrics.py`). This is the scoring half of the Week 4 eval harness; the click-simulator half (`eval.py`) is still a stub.
- Test coverage beyond protocol/metrics: `test_app.py`, `test_client.py` (137 lines each).
- Forked backbone repos vendored as git submodules for training/comparison: `Pointcept` (PTv3/PTv1 training), `Pointnet_Pointnet2_pytorch` (baseline), and an `ISSR` mirror.
- `utils/` scripts carried forward and reformatted: `convert_to_laz.py`, `downsample.py`, `flatten.py`, `plot.py`.

### 1.3 Open gaps that this plan addresses
- **`model.py`, `refine.py`, `eval.py` are still empty stubs** (one-line docstrings only). The backbone (PTv3 via Pointcept), InterPCSeg-style refinement, and the automated click-simulator/NoC@q harness have not been started — this is Week 2–4 work in §3, not yet begun despite the submodules landing.
- **No `ISegmentationBackend` abstraction.** `app.py` hardcodes the KNN flood-fill directly in the message loop instead of behind the pluggable interface in §2.3. Swapping in a real model currently means editing `app.py`, not swapping a backend — worth doing before Week 2 lands to avoid the rewrite §2.3 was meant to prevent.
- **No `FPromptEvent` stream.** `FClick`/`Click` is a single-shot request/response, not the append-only, replayable prompt log described in §2.2/2.4. There is no `prompts.jsonl`, no undo, and box/brush tools have no event shape to emit into yet.
- **Point store uses a sorted array + binary search, not a voxel hash grid.** `SegPointStoreComponent::FindIndexByPosition` does exact-position lookup via `IndicesByPosition`; there's no spatial hash for radius/box/neighbourhood queries yet, so box and brush tools (and any region-around-prompt extraction for inference) have nothing to query against. §2.1/§2.6's hash-grid design is still aspirational, not built.
- Box and brush tools do not exist; only click does.
- No perf telemetry (FPS, dropped frames) has been captured through Quest Link yet.
- README still missing at the repo root.

---

## 2. Architecture for the current phase (rendering + annotation, forward-compatible)

The design rule: every piece of state and every component that will be needed when the backbone is plugged in should already be in place, just driven by a placeholder until then. This costs almost nothing now and saves a rewrite later.

### 2.1 Per-point state — replace the RGB-encoded label

The colour-as-label trick has to go. AGILE3D / Point-SAM consume the cloud's geometry and let the model produce class probabilities; user input lives in a separate prompt stream. The runtime needs the same separation:

| Buffer | dtype | Purpose |
|---|---|---|
| `geom[N]` (xyz + true RGB) | f32 + u8 | The cloud as captured by the LiDAR. Never mutated. |
| `label_pred[N]` | u8 | The backbone's current per-point prediction. Updated whenever the model runs. |
| `label_user[N]` | u8 | The user's authoritative override. |
| `has_user[N]` | bit | Whether `label_user[i]` is set. Bit-packed for memory. |
| `class_palette` | u8[4][3] | Class → display colour mapping, editable at runtime. |

The display material reads: `if has_user[i]: palette[label_user[i]] else: palette[label_pred[i]]`, optionally blended with `geom.RGB` so the operator can toggle "show me the photoreal cloud" without losing the segmentation overlay. This is exactly the toggle real annotation tools have.

Practical implementation in UE5: the LidarPointCloud plugin's octree is **private and cannot be queried**, so all interactive state lives on our side. A **voxel hash grid** owns the per-point buffers above, indexed by point id, and answers all spatial queries (nearest-point snap, box/brush membership, region-around-prompt extraction for inference). The plugin's `FLidarPointCloudPoint::ClassificationID` may still be written for display purposes if it proves cheap, but it is a rendering detail, not the source of truth — the hash grid is.

### 2.2 Prompt-event abstraction — one struct, three tools

Every annotation tool — click, box, brush — emits the same struct:

```cpp
struct FPromptEvent {
    EPromptType   Type;        // CLICK | BOX | BRUSH
    EPolarity     Polarity;    // POSITIVE | NEGATIVE
    EClassLabel   TargetClass; // STEM | FOLIAGE | GROUND | UNDERGROWTH
    int32         ObjectId;    // -1 if single-class semantic, else AGILE3D-style multi-object
    double        TimestampNs; // ordered prompt log
    FTransform    Geometry;    // location + orientation (boxes need full transform)
    FVector       Extent;      // half-size for box, radius for brush, ignored for click
    int32         FrameIndex;  // for retraining replay
};
```

The user produces a stream of these. The stream is the canonical source of truth — it can be saved to disk, replayed, fed to the refinement loop as the correction set, or used to train an "imitation" model of operator behaviour. InterPCSeg-style test-time refinement consumes user corrections in exactly this form; if AGILE3D-style click-attention is attempted later, its ordered prompt list is the same stream.

### 2.3 Segmentation backend interface (stub now, real model later)

```cpp
class ISegmentationBackend {
    virtual void Segment(
        const TArray<FPromptEvent>& Prompts,
        const FChunkRegion&          Region,
        TArray<uint8>&               OutLabels,
        TArray<float>&               OutConfidence
    ) = 0;
};
```

Three concrete implementations get written over the project, in order:

1. **`GeometricBackend`** (Week 1) — no learning. A click flood-fills points within a radius of the hit point to the chosen class. A box paints every point inside the OBB. A brush paints continuously while the trigger is held. This is the "deterministic-rule" version that exercises the whole pipeline before any model exists.
2. **`StubBackend`** (Week 1) — same outputs as `GeometricBackend`, but the call shape is the JSON-over-IPC shape that the real model will use. Lets you debug the latency budget, prompt serialisation, and label-buffer write-back without involving Python or PyTorch yet.
3. **`RefinementBackend`** (Week 3) — calls a Python inference server running PTv3 (RandLA-Net fallback) with **InterPCSeg-style test-time refinement**: initial prediction on scene load, then user corrections drive refinement passes over the affected region. The server runs on the same PC as Quest Link, so the socket is local — no Wi-Fi path needed.

The renderer, prompt-event capture, and label buffer never change across these three. Only the backend swaps.

### 2.4 Prompt history and undo

Append-only `TArray<FPromptEvent>` per scene. Undo = truncate to length N-1 and re-run the backend over the truncated set. With the geometric backend this is instantaneous; with PTv3 it costs one inference call per undo and may need a per-prompt incremental delta cache — defer that optimisation until Week 3.

### 2.5 Controller affordances

A consistent input map, applied across all three tools:

| Input | Function |
|---|---|
| Right trigger | Positive prompt (add to current class) |
| Right grip | Negative prompt (remove from current class) |
| Left thumbstick (vertical) | Adjust tool size (click radius / box scale / brush radius) |
| Left trigger | Cycle target class (stem → foliage → ground → undergrowth) |
| Left grip | Modifier: hold to select existing region for refinement (multi-object workflow reserved for future AGILE3D work) |
| Right thumbstick (vertical) | Snap-turn locomotion |
| Right thumbstick (horizontal) | Strafe locomotion |
| Menu (left) | Open palette: tool selector, stats, save/load |
| Menu (right) | Undo |
| A | Switch tool (click → box → brush) |
| B | Toggle photoreal vs. label overlay |

Locomotion is teleport for sickness safety.

### 2.6 Rendering and performance — plugin-first

The thesis's working position is that the LiDAR Point Cloud plugin handles **rendering** (built-in LOD, frustum culling, Eye-Dome Lighting). It does **not** handle interactive queries — its octree is private — so point-pick, box-pick, and brush membership go through the voxel hash grid. The plan does not invest in a custom renderer unless the measurements below force it.

What has to be measured, in order (all via **Quest Link** — rendering on the PC GPU, not on-device):

1. **Quest Link, full cloud.** Can the plugin sustain 90 FPS (or 72 as the dev threshold) on each of the five clouds through Link?
2. **PC GPU-memory headroom**, shared between the renderer and (eventually) the inference server on the same machine.
3. **Voxel-hash-grid query latency** for a 1 m, 5 m, 20 m box on a 10M-point cloud (the plugin's `get_points_in_box_as_copies` is a comparison baseline, not the production path). This sets the upper bound on per-frame brush throughput.

Three plugin-side levers to pull immediately, all cheap and all reversible:
- Fixed-foveated rendering (Oculus stereo plugin → set foveation level 2).
- Snap-turn locomotion (already in VRTemplate).
- Reduced render-target scale during teleport / movement.

**Fallback only if the plugin fails the above.** A custom renderer is a several-week distraction from the thesis's actual contribution (the segmentation backbone + VR interaction loop). The decision rule: if foveation + render-target scaling can't drag the plugin to ≥ 72 FPS, *then* consider chunked streaming. The chunked preprocessor lives in git history if it's needed.

### 2.7 Data on disk

For each annotation session:

```
sessions/2026-05-19_native2/
  prompts.jsonl     # one FPromptEvent per line
  labels.npz        # label_user[N] (u8) + has_user[N] (bit-packed)
  meta.json         # cloud_id, operator_id, start/end, fps_log
```

This format is what the refinement loop and the evaluation harness both consume. Designing it now means there's only one data path through the whole thesis.

---

## 3. Sequenced plan — 24 working days, 6 days/week, four phases

The May version phased work as A (tooling) → B (backbone) → C (eval) over ~11 weeks. The revised structure is a **walking skeleton**: get a mocked end-to-end loop running in Week 1, then replace mocks with real components week by week. Every week ends with a written retrospective that doubles as a thesis chapter fragment. Each task is tagged by ownership: **[self]** write it yourself, **[cc]** delegate to Claude Code, **[self+ccr]** write it yourself and have Claude Code review (the review direction matters for learning).

### Week 1 (days 1–6) — walking skeleton with mock components

Everything in §2 exists end-to-end, driven by placeholders:
- `UPointCloudAnnotation` subsystem: dual label buffers, `FPromptEvent`, prompt history, `ISegmentationBackend` with `GeometricBackend` wired in. Console-command driven at first. **[self+ccr]**
- Voxel hash grid built alongside cloud load; nearest-point, box, and sphere queries working. **[self+ccr]**
- Click tool: ray-cast from right controller, snap to nearest point (runtime version of `probe_label.py`), positive/negative prompts, floating debug widget. **[self]**
- `StubBackend` with the JSON-over-IPC call shape the real model will use — latency budget and serialisation debugged before Python is involved. **[cc]**
- Session save/load: `prompts.jsonl` + `labels.npz` + `meta.json`; replay reproduces labels exactly. **[cc]**
- Quest Link build running; baseline FPS on the 6 M (`ct03t1b_01`) and 13 M (`HQPLR144V1`) clouds.
- **End of week: supervisor update to Dr. Bryson.**

### Week 2 (days 7–12) — real backbone, offline inference

- Train PTv3 via Pointcept on the five labelled plots; RandLA-Net as fallback if PTv3 hits GPU-memory or reproducibility walls. Report mIoU and per-class IoU. **[self]**
- Offline inference: run the trained model over a full cloud, load predictions into `label_pred`, display in VR. No interactivity yet. **[cc]**
- Brush tool (controller-attached sphere, radius on left stick, ≥ 30 prompt-events/s throttled, coalesced on disk) and box tool (two-handed, full `FTransform`, inclusion/exclusion). **[self]**
- Trail visualisation and in-VR palette (tool/class selector, per-class counts, FPS indicator). **[cc]**

### Week 3 (days 13–18) — close the human-in-the-loop refinement loop

- Inference server (FastAPI or raw socket) wrapping the trained backbone, local to the Quest Link PC. **[self+ccr]**
- `StubBackend` → `RefinementBackend` swap: InterPCSeg-style test-time refinement consumes the prompt stream, refines the region around each correction, writes back to `label_pred`. Round-trip budget: 250 ms for the region update. **[self]**
- Undo across the refinement path (re-run over truncated prompt set; add a per-prompt delta cache only if latency demands it). **[cc]**
- Stability tuning: refinement must not oscillate or degrade untouched regions (see risk 3).

### Week 4 (days 19–24) — evaluation harness and profiling

- Automated click-simulator (AGILE3D / Point-SAM protocol): clicks at maximum-error points; measure **NoC@q and IoU@k**. Compare `GeometricBackend` baseline vs. `RefinementBackend`. **[cc harness, self analysis]**
- Technical profiling: sustained FPS through Quest Link, inference time per prompt, prompt-to-paint latency, GPU memory — scripted 5-minute session per cloud, telemetry into `meta.json`. **[cc]**
- Annotation efficiency: mean time per 1k labelled points vs. the manual plugin-selection baseline.
- Final retrospective; consolidate the four weekly retros into the methods/results chapter skeleton.

**Exit criteria.** A user can walk into a 6M-point cloud through Quest Link, place click/brush/box prompts, watch the backbone refine, undo, save, and quit at ≥ 72 FPS (tighten toward 90 before final eval). `prompts.jsonl` replay reproduces `labels.npz` exactly. NoC@q / IoU@k numbers exist for both backends on all five clouds.

### Deferred / out of scope

- **AGILE3D-style click-attention adaptation** — future/stretch work only.
- **User study (formerly O6)** — cut; evaluation is strictly technical, so no HREC paperwork.
- **Mensuration extension (ground/DTM construction)** — optional, not core scope. Ground filtering is *not* a pipeline prerequisite: the network handles the ground class directly.
- Live online fine-tuning — offline-batched retraining from session dumps is the fallback framing if attempted at all.

### Writing (continuous)

Skeleton already exists in the Preliminary Report. Weekly retrospectives are written as chapter fragments as the work happens. The final thesis adds: methods chapter expanding §2, results from Weeks 2–4, discussion of where the system breaks (refinement oscillation, prompt-storm latency under brush, stem/undergrowth confusion), and future work (mensuration extension, click-attention adaptation, live online learning, multi-user annotation).

---

## 4. Risks, ranked

Each risk has a **pre-decided fallback** so a failure mid-week costs a decision lookup, not a replanning session.

1. **GPU memory.** PTv3 at 10 M-point scale is memory-hungry, and the renderer now shares the PC GPU with the inference server. Fallbacks in order: reduce inference sub-volume size → mixed-precision / quantised inference → **switch to RandLA-Net** (fits 12–16 GB). PTv3's published numbers also have reproducibility concerns, so a RandLA-Net switch is a legitimate outcome, not a failure.
2. **Plugin friction.** The octree being private is already absorbed into the design (voxel hash grid); the residual risk is rendering performance through Quest Link. Fallbacks: aggressive plugin LOD → fixed-foveated rendering → reduced render-target scale → drop the cloud target to 5–7 M points and justify in the report → only as a last resort, a custom streamer.
3. **Refinement instability.** InterPCSeg-style test-time refinement can oscillate or degrade untouched regions. Fallbacks: constrain refinement to the prompt's spatial neighbourhood → freeze all but the final layers → cap refinement iterations → degrade gracefully to `GeometricBackend` painting with model predictions as the base layer.
4. **Label storage breaks when switching off RGB encoding.** Medium risk. Decoupling `label_pred` and `label_user` from the colour channel is intrusive. Doing it in Week 1, before any tool exists, contains the blast radius.
5. **Backbone inference latency.** Even locally, PTv3 over 10 M points is not 250 ms. The flow is: predict once per scene load, then refine only the region inside the prompt's influence. The inference server slices the cloud on its side rather than the renderer shipping chunks.
6. **Cross-domain generalisation will be worse than the published numbers suggest.** Low engineering risk, high research risk. SegmentAnyTree and TreeLearn both report degradation on dense native stands; the thesis assumes this and treats interactive correction as the whole point. (Note: these forestry pipelines are full pipelines built on general backbone families, not separate architectures — keep them in a separate report section from the backbone taxonomy.) Make sure the eval shows *how much* correction is required, not just out-of-the-box accuracy.

---

## 5. Things I want to flag from the preliminary report

These are minor but worth fixing before final submission:

- §2.4.3 says RandLA-Net is "one million points in a single forward pass roughly two orders of magnitude faster than its contemporaries" — slightly overclaimed; the original paper says ~200× faster than PointNet++ on large clouds, ~10× on smaller ones.
- Table 1: KPConv S3DIS Area-5 mIoU 67.1 is from the original paper, while the rest of the column is from PTv3 / PointNeXt. Footnote already says it, but two methods (RandLA-Net 62.4 and Point Transformer 70.4) appear to be original-paper numbers too — re-check for consistency.
- The objectives split O5 into "technical performance characterisation" and "objective annotation accuracy", which is a lot to carry under one objective number. Consider splitting into O5a (technical) and O5b (segmentation accuracy) so the eval chapter has cleaner sections.

---

## 6. Learning practices (deliberate, non-negotiable)

A stated goal of this project is rebuilding developer skill after extended vibe coding. These rules are embedded in the plan on purpose — they cost time in the short run and are the point in the long run:

- **Explain-before-commit.** Before committing, explain (aloud or in the commit message, written from memory) what the change does and why. If it can't be explained, it isn't understood.
- **30-minute self-debug rule.** Debug alone for 30 minutes before asking Claude Code or anyone else. Log what was tried — the log itself is often the answer.
- **Task ownership tags.** Every task in §3 is tagged **[self]**, **[cc]**, or **[self+ccr]**. The review direction matters: having Claude Code review self-written code teaches more than reviewing Claude Code's output.
- **Small commits, memory-written messages.** No end-of-day mega-commits.
- **Weekly retrospectives as thesis fragments.** Each week's retro is written as a chapter fragment, not a diary entry — the writing is progressive, not deferred to a final writing phase.
- **Design documents double as thesis chapters.** §2 of this plan is the methods chapter's first draft.

---

## 7. Immediate next actions

1. Write the one-page README. _(1 hour)_
2. Confirm the Quest Link build renders the existing monolithic cloud; record FPS and dropped-frame count for each of the five clouds. _(half day)_
3. Spike the voxel hash grid: build-on-load plus nearest-point and box queries, timed on the 13 M cloud. **[self+ccr]** _(1 day)_
4. Sketch `FPromptEvent` and `ISegmentationBackend` in code, with `GeometricBackend` implemented. No UI yet. **[self]** _(1 day)_
5. Prepare the Pointcept data path: train/val split of the five plots, class-mapping JSON, chunk format. _(half day)_
6. Draft the end-of-Week-1 supervisor update to Dr. Bryson as items land, not at the deadline. _(ongoing)_

---

## 8. Open questions

- Is there an existing labelled split of the five clouds suitable for training the backbone, or does that data path still need to be set up? The chunk format is one half of it; the train/val split files and class-mapping JSON are the other half.
- What GPU does the Quest Link PC have, and can it hold the renderer + PTv3 inference simultaneously? If not, RandLA-Net (12–16 GB) becomes primary earlier than planned.
- InterPCSeg refinement granularity: per-prompt, per-batch-of-prompts, or on-demand? Affects both the latency budget and the NoC@q protocol.
