# Thesis Plan — VR Interactive Segmentation of Forest LiDAR

_Last updated: 2026-05-19_

This plan is grounded in the Preliminary Report and the seminar slides. The thesis builds a Meta Quest 3S VR tool that (a) renders ~10M-point native forest LiDAR clouds at ≥ 90 FPS, (b) lets the user place click / box / brush prompts on individual points, and (c) closes the loop with a deep-learning interactive semantic segmentation backbone whose corrections are fed back to retrain the network. Four classes: **stem, foliage, ground, undergrowth**.

The current engineering phase covers items (a) and parts of (b). The architectural decisions below are chosen specifically so that the work done now is not thrown away when the backbone arrives.

---

## 1. Where things stand

### 1.1 Locked-in by the report
- Hardware: Meta Quest 3S (standalone, no PC tether at evaluation time).
- Engine: UE5 + LiDAR Point Cloud plugin.
- Backbone candidates: **RandLA-Net, KPConvX, PTv3** (slide 9 narrows the original five down to three).
- Interactive-segmentation reference systems: **AGILE3D, Point-SAM, Interactive4D**.
- Primary evaluation (O5): FPS, motion-to-photon latency, GPU memory, inference time, mIoU vs. ground truth, NoC@q% / IoU@k, time-per-object.
- Extension (O6): user study with NASA-TLX / SUS / SSQ.

### 1.2 Done already
- Quest 3S acquired (Thesis Funding Scheme).
- UE5 + Oculus / OpenXR / hand-tracking / eye-tracking / LidarPointCloud plugins enabled in `MyProject`.
- Initial VR visualiser: monolithic `.uasset` cloud + VR pawn + ground collider + nav volume, auto-built by `build_flat_vr_scene.py`.
- A label-via-RGB probe (`probe_label.py`) that ray-casts and prints the class at the hit point.
- Five labelled clouds prepared, with flattened variants for terrain normalisation.
- `utils/` scripts for routine point-cloud chores used in report figures: pickle→PLY/TXT with label-RGB mapping (`convert_p.py`), per-cell ground-zero flattening (`flatten.py`), label stripping (`unlabel.py`), shape probe (`check_size.py`).
- Preliminary Report draft written, seminar delivered.

### 1.3 Open gaps that this plan addresses
- The visualiser still loads the full cloud as a single asset; no perf telemetry, no Quest-3S build confirmed.
- **Plugin-sufficiency unknown.** Working assumption for this phase is that the LiDAR Point Cloud plugin can render and select points on 10M-point clouds without a custom renderer. If that proves wrong on Quest 3S, only then do we look at writing one.
- Labels are encoded as RGB. This works for a read-only viewer; it falls apart the moment a user starts editing labels in VR.
- No annotation tooling at all — click, box, brush. This is the immediate work the user just identified.
- No prompt-event abstraction, so the click / box / brush code that gets written today will not feed cleanly into AGILE3D-style prompts later.
- No segmentation-backend interface or stub. The plumbing needs to be there from the first annotation tool, or the backbone integration becomes a rewrite.
- No git history. No README. Single most expensive easy fix is one commit.

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

Practical implementation in UE5: the LidarPointCloud plugin exposes `FLidarPointCloudPoint::ClassificationID` (a uint8 per point). Use it for `label_pred`. Keep `label_user + has_user` either in the same struct (if the plugin's per-point data path is mutable from C++ — it is) or in a side-array indexed by point id. Decision point: confirm during the first sprint of Phase A whether `ClassificationID` is writable from Blueprint / Python at acceptable cost. If not, fall back to a custom `UPointCloudOverlayComponent` that maintains the side-array and a GPU texture sampled by a custom material.

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

The user produces a stream of these. The stream is the canonical source of truth — it can be saved to disk, replayed, fed to the backbone as the prompt set, or used to train an "imitation" model of operator behaviour. AGILE3D's click-attention module literally consumes this kind of ordered prompt list.

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

1. **`GeometricBackend`** (Phase A) — no learning. A click flood-fills points within a radius of the hit point to the chosen class. A box paints every point inside the OBB. A brush paints continuously while the trigger is held. This is the "deterministic-rule" version that exercises the whole pipeline before any model exists.
2. **`StubBackend`** (Phase B, Sprint 1) — same outputs as `GeometricBackend`, but the call shape is the JSON-over-IPC shape that the real model will use. Lets you debug the latency budget, prompt serialisation, and label-buffer write-back without involving Python or PyTorch yet.
3. **`PTv3Backend`** (Phase B, Sprint 2+) — calls a Python inference server running PTv3 (or RandLA-Net / KPConvX, depending on the O2 benchmark winner) over a local socket. The server runs on a tethered PC during development. For untethered evaluation, the server runs on a workstation reached over Wi-Fi.

The renderer, prompt-event capture, and label buffer never change across these three. Only the backend swaps.

### 2.4 Prompt history and undo

Append-only `TArray<FPromptEvent>` per scene. Undo = truncate to length N-1 and re-run the backend over the truncated set. With the geometric backend this is instantaneous; with PTv3 it costs one inference call per undo and may need a per-prompt incremental delta cache — defer that optimisation until Phase B.

### 2.5 Controller affordances

A consistent input map, applied across all three tools:

| Input | Function |
|---|---|
| Right trigger | Positive prompt (add to current class) |
| Right grip | Negative prompt (remove from current class) |
| Left thumbstick (vertical) | Adjust tool size (click radius / box scale / brush radius) |
| Left trigger | Cycle target class (stem → foliage → ground → undergrowth) |
| Left grip | Modifier: hold to select existing object for refinement (AGILE3D multi-object workflow) |
| Right thumbstick (vertical) | Snap-turn locomotion |
| Right thumbstick (horizontal) | Strafe locomotion |
| Menu (left) | Open palette: tool selector, stats, save/load |
| Menu (right) | Undo |
| A | Switch tool (click → box → brush) |
| B | Toggle photoreal vs. label overlay |

Locomotion is teleport for sickness safety unless smooth locomotion is explicitly requested in user studies.

### 2.6 Rendering and performance — plugin-first

The thesis's working position for this phase is that the LiDAR Point Cloud plugin is enough. Its built-in LOD, frustum culling, Eye-Dome Lighting, and `get_points_in_box_as_copies` selection API cover the rendering, point-pick, and box-pick needs out of the box. The plan does not invest in a custom renderer unless the measurements below force it.

What has to be measured, in order:

1. **Quest 3S, untethered, full cloud.** Can the plugin sustain 90 FPS (or 72 as the dev threshold) on each of the five clouds? The seminar reports a working visualiser — pin down whether that's on Quest 3S directly or PCVR-tethered.
2. **GPU-memory headroom.** Quest 3S has 8 GB shared; the OS and runtime take a substantial slice.
3. **Selection latency.** How long does `get_points_in_box_as_copies` take for a 1 m, 5 m, 20 m box on a 10M-point cloud? This sets the upper bound on per-frame brush throughput.

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

This format is what the Phase C retraining loop will consume. It's also what the user study export will produce. Designing it now means there's only one data path through the whole thesis.

---

## 3. Sequenced plan

### Phase 0 — repo hygiene (this week, 1 day)

- Commit everything: `git init` is already done, but there are zero commits. One `Initial snapshot` commit, push to a private remote.
- Top-level `README.md`: dataset summary, what each `utils/` script does, how to build the VR scene.
- `.gitignore` already covers `Saved/`, `Intermediate/`, `DerivedDataCache/`, `__pycache__/`, and `__MACOSX/`. Confirm before first commit.

### Phase A — rendering + annotation tooling (current focus, ~4–6 weeks)

**Sprint A1 — Foundations (1 week).** Land the architecture decisions in §2 before building any tool.
- Build a minimal `UPointCloudAnnotation` UE5 subsystem with: the dual label-buffer model, the `FPromptEvent` struct, the prompt history, and the `ISegmentationBackend` interface with `GeometricBackend` wired in. No UI yet — drive it from a console command for now.
- Confirm or replace the colour-as-label encoding. Test whether `FLidarPointCloudPoint::ClassificationID` is writable from C++ at runtime cost <1 ms for a 10 k-point selection. If not, fall back to the overlay-component approach.
- Deploy a first build to Quest 3S, untethered. Measure baseline FPS on the 6 M (`ct03t1b_01`) and 13 M (`HQPLR144V1`) clouds. This is the realism check — everything downstream depends on the cloud actually rendering on-device.

**Sprint A2 — Click tool (1 week).**
- Ray-cast from the right controller, snap to the nearest point within a screen-space tolerance (the existing `probe_label.py` already proves the ray-cast works; this is its runtime version).
- Trigger = positive click → emits `FPromptEvent{CLICK, POS, currentClass, ...}` → `GeometricBackend.Segment` → paints points within `r` of the hit to `currentClass`. Grip = negative.
- Floating crosshair / debug widget showing currentClass, currentTool, click radius.
- Save / load prompts.jsonl + labels.npz.
- Undo (last 32 events, room-to-grow buffer).

**Sprint A3 — Brush tool (1 week).**
- Replace the snap-to-point with a controller-attached sphere whose radius is on the left stick.
- While trigger is held, every frame emit `FPromptEvent{BRUSH, ...}` and apply to all points inside the sphere. Throttle to ≥ 30 prompt-events/s; coalesce identical-radius events on disk to keep the JSONL small.
- Trail visualisation: every brushed point lights up at full label colour for ~200 ms before fading to the steady-state overlay.

**Sprint A4 — Box tool (1 week).**
- Two-handed box: position with both controllers, trigger to "lock in" → emits `FPromptEvent{BOX, ...}` with full `FTransform` (the box can be rotated, not just AABB).
- Wireframe preview + transparent fill in the target-class colour while sizing.
- Treats the box as an inclusion (positive) or exclusion (negative) region.

**Sprint A5 — UX polish + telemetry (1 week, can run in parallel with A4).**
- In-VR palette (left menu button): tool selector, class selector, per-class point-count readout, FPS / dropped-frame indicator.
- Telemetry: `meta.json` includes frame-time histogram, dropped-frame count, peak GPU memory, total prompts, prompt-to-paint latency. These are the raw inputs to the O5 evaluation.
- Decide on the locomotion default (probably snap-turn + teleport).

**Phase A exit criteria.** A naive user can: walk into a 6M-point cloud, place positive and negative click prompts, brush around, drop a box, switch classes, undo, save, and quit — all on Quest 3S, with on-device FPS ≥ 72 (relax 90 to 72 as a development threshold; tighten before final eval). `prompts.jsonl` from a session can be replayed to reproduce `labels.npz` exactly.

### Phase B — backbone integration (~4 weeks, starts after A1, runs in parallel with A2-A5)

- **B1 Backbone benchmarking (O2).** Train / fine-tune RandLA-Net, KPConvX, PTv3 on FOR-instance / ForestSemantic / the in-house labelled clouds. Report mIoU and per-class IoU. Choose one to integrate.
- **B2 Inference server.** Wrap the chosen backbone behind a small Python service (FastAPI or raw socket) exposing `segment(prompts, chunk_indices) -> labels`. Quantise / batch as needed.
- **B3 `StubBackend` → `PTv3Backend` swap.** UE5 calls the server. Round-trip latency budget: 250 ms end-to-end. Test with a tethered workstation first, then a Wi-Fi-reachable PC.
- **B4 Online learning loop (O3 core).** Periodically dump `prompts.jsonl + labels.npz` from completed sessions, fine-tune the backbone on the new annotations, push the updated weights back to the server. Keep this offline-batched first; live fine-tuning is a stretch.

### Phase C — evaluation (~3 weeks)

- **C1 Technical (O5, primary).** Sustained FPS, motion-to-photon latency, GPU memory occupancy, inference time per prompt, all measured on Quest 3S over a scripted 5-minute session per cloud.
- **C2 Annotation accuracy (O5).** Run the automated click-simulator from AGILE3D / Point-SAM literature: place clicks at the point of maximum current error, measure NoC@q% and IoU@k. Compare GeometricBackend baseline vs. PTv3Backend.
- **C3 Annotation efficiency (O5).** Mean time per annotated tree / per 1k labelled points. Manual baseline = stock Lidar Point Cloud plugin selection + the current colour-coding. VR baseline = the system in this thesis.
- **C4 User study (O6, if time).** n=6–10 participants annotate two clouds, one per condition (VR vs. desktop). Outcomes: completion time, IoU vs. ground truth, NASA-TLX, SUS, SSQ. Needs ethics approval — start that paperwork at the start of Phase B.

### Phase D — writing (continuous, ~3 weeks dedicated at the end)

Skeleton already exists in the Preliminary Report. The final thesis adds:
- Methods chapter expanding §2 of this plan.
- Results from Phases B and C.
- Discussion of where the system breaks (and it will — chunk-edge artefacts, prompt-storm latency under brush, class confusion at the stem/undergrowth boundary).
- Future work: the mensuration extension (O4), full live online learning, multi-user collaborative annotation.

---

## 4. Risks, ranked

1. **Quest 3S can't sustain 90 FPS on 10 M points with the plugin alone.** Highest risk and the gate on the plugin-first decision. The seminar shows a working visualiser but doesn't pin down which platform or how many points. Mitigate by getting a Quest build *this week* and measuring. Fallbacks in order: aggressive plugin LOD settings → fixed-foveated rendering at level 3 → reduced render-target scale → drop the cloud target to 5–7 M points and justify in the report → only as a last resort, build a custom streamer.
2. **Label storage breaks when switching off RGB encoding.** Medium risk. Decoupling `label_pred` and `label_user` from the colour channel is intrusive. Doing it in Sprint A1, before any tool exists, contains the blast radius.
3. **Backbone inference latency.** Even on a beefy PC, PTv3 over 10 M points is not 250 ms. The realistic flow is: predict once per scene load, then update only the region inside the prompt's influence. The natural inference unit is a spatial sub-volume around the prompt; the inference server slices the cloud on its side rather than the renderer needing to ship chunks.
4. **User-study ethics approval lead time.** Medium risk if O6 happens at all. USyd HREC turnaround is 4–8 weeks. Submit at the start of Phase B.
5. **Cross-domain generalisation will be worse than the published numbers suggest.** Low engineering risk, high research risk. SegmentAnyTree and TreeLearn both report degradation on dense native stands; the thesis assumes this and treats interactive correction as the whole point. Make sure the eval is structured to show *how much* correction is required, not just whether the model is accurate out of the box.
6. **No backup of any of this code yet.** Zero risk to mitigate (Phase 0, 15 min).

---

## 5. Things I want to flag from the preliminary report

These are minor but worth fixing before final submission:

- §2.4.3 says RandLA-Net is "one million points in a single forward pass roughly two orders of magnitude faster than its contemporaries" — slightly overclaimed; the original paper says ~200× faster than PointNet++ on large clouds, ~10× on smaller ones.
- Table 1: KPConv S3DIS Area-5 mIoU 67.1 is from the original paper, while the rest of the column is from PTv3 / PointNeXt. Footnote already says it, but two methods (RandLA-Net 62.4 and Point Transformer 70.4) appear to be original-paper numbers too — re-check for consistency.
- The objectives split O5 into "technical performance characterisation" and "objective annotation accuracy", which is a lot to carry under one objective number. Consider splitting into O5a (technical) and O5b (segmentation accuracy) so the eval chapter has cleaner sections.

---

## 6. Immediate next actions (this week)

1. Commit everything currently in the repo and push to a remote. _(15 min)_
2. Write a one-page README. _(1 hour)_
3. Build the project to Quest 3S, untethered, with the existing monolithic cloud. Record FPS and dropped-frame count for each of the five clouds. _(half day)_
4. Decide between `ClassificationID` and a custom overlay component for the dual-label buffer (see §2.1). Build a 50-line spike to test the writable-at-runtime question. _(half day)_
5. Sketch the `FPromptEvent` and `ISegmentationBackend` in code, with `GeometricBackend` implemented. No UI yet. _(1 day)_
6. Start the HREC application for O6 if there's any chance of running a user study. _(half day)_

---

## 7. Open questions

- Is the seminar-stage visualiser running on Quest 3S already, or only PCVR-tethered? This determines whether Phase A starts from "make it run on Quest" or "extend what already runs on Quest".
- Is there an existing labelled split of the five clouds suitable for training the backbone, or does that data path still need to be set up? The chunk format is one half of it; the train/val split files and class-mapping JSON are the other half.
- Do you have an inference workstation available? A 24 GB-VRAM GPU is roughly the minimum for PTv3 at 10 M-point scale; without one, the backbone story has to be RandLA-Net or KPConvX, both of which fit in 12–16 GB.
- Is the user study a hard "if time permits" or a "we'd really like to run it"? The answer changes when to start the ethics paperwork.
