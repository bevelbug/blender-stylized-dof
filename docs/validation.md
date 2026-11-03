# Validation — 1.3.0

Validated October 31, 2026 on Blender **5.2.0 LTS**, build `fbe6228777e7`, Windows x64. **368 background checks and 21 native event-loop/Undo snapshot checks passed.** Separate default-pixel comparisons, extension packaging/native enabling, six older native saved-file upgrades and offline Paint portability checks also pass. Other platforms and later Blender versions remain unverified.

## Visual behavior and animation

- Cycles renders verify that Defocus changes out-of-focus pixels in Bilateral, Kuwahara and Paint while preserving the sharp region and incoming alpha. All three respect enabled, zero-strength and zero-radius bypasses with softness present.
- Paint produces a distinct result from Kuwahara before additional softness. Its four input gates preserve active tracked pixels exactly while reducing bypass work. Tracked bypass is verified on CPU and GPU.
- Camera focus-distance, lens, moving focus-object and pose-bone animation retain the earlier rendered regression coverage. New Paint, Simplification and Defocus keys render in repeated/reverse frame order on CPU and GPU; tracked Paint also renders with Eevee.
- A saved tracked Paint scene reopens with its controls, drivers, local asset groups and passes. The extracted ZIP renders that scene with the installed asset file temporarily unavailable: no cache, network or original-machine asset path is required for an already-built file.
- Ten retained fixtures — baseline, both Bilateral qualities, Kuwahara, focus mask, disabled/zero-radius/zero-strength and Eevee filter results — match v1.2.3 with **maximum pixel difference 0.0** at Defocus zero.

Defocus is Gaussian softening blended through the depth-derived focus mask before the selected painterly filter. It is not optical aperture simulation or an occlusion-correct reconstruction. Strong settings can introduce silhouette/color spill. Paint's Size is uniform within the filter; its result is blended through the focus mask. This avoids passing a varying image into its scalar size input.

## Tracking, ownership and recovery

- Position Tracking enables native Depth/Position on the configured layer and repairs their links on Refresh. Missing passes are diagnosed. Leaving tracked Paint, removal and copied-scene detachment release passes added by the add-on, while preserving pre-existing passes and user compositor consumers.
- An injected late tracking-link failure restores native flags and ownership markers. Retrying Refresh succeeds. A failed first Paint load restores node/group/driver counts; same-named user groups are neither adopted nor deleted.
- Older graphs upgrade in place. A late failure after new drivers, sockets and links exist restores the prior graph/schema and can be retried. Native source-node identity, existing camera/control drivers and saved settings are retained.
- The CC0 asset is loaded only on first Paint selection. Removing the last setup frees imported unused helper groups; referenced groups remain. The bundled asset has no linked libraries, external image files or weak library references. Its original author/license metadata and pinned hashes are documented in THIRD_PARTY_NOTICES.md.

World-position tracking can help camera motion and consistent spatial placement. Objects moving/deforming through world space can still move through the strokes. This is not rest-position/deformation tracking for Alembic and does not guarantee flicker-free animation. Native passes need a new full render after being enabled.

## Enabling, saved-file upgrades and Undo

The real restricted `addon_utils.enable()` path passes, retaining the earlier installation fix. Registration does not inspect scene data inside Blender's guard. A real 1.2.3 file opened before enabling receives its deferred upgrade once; clean disable removes the handler, timer and property schema.

The separate event-loop test uses native Undo/Redo snapshots for compositor enabling/selection, copied-scene detachment, interrupted removal and complete tracked Paint removal. It restores asset groups, native passes and Defocus state. The timer harness explicitly pushes snapshots; actual panel-button Undo dispatch is not automated.

The final installation ZIP is built/validated with Blender's tools, extracted to a separate workspace directory, enabled through Blender's loader, and tested with fresh setup/refresh/Paint/removal. Real 1.1.0, 1.1.1, 1.2.0, 1.2.1, 1.2.2 and 1.2.3 files render immediately after loading, then refresh without duplicating the upgraded graph or changing saved controls. Original v1 migration, linked brushes/actions/NLA and retryable cleanup remain in the full suite.

Fault-injection checks deliberately print errors/recovery reports. The reset-heavy background suite can print Blender's existing Python-context shutdown warnings after all checks pass; the separate enabling/event-loop sessions are checked independently. No personal preferences or project files were saved.

## 4K compositor fixture timings

Blender 5.2.0 LTS, eight CPU threads or NVIDIA RTX 5080 GPU, 3840 × 2160, radius 8, median of three warm runs after a warm-up. Deterministic full-frame image/depth inputs use an empty Workbench scene as carrier. CPU and GPU runs are sequential, without competing Blender tests. These are compositor fixture times, not total production render times.

| Method / state | CPU | GPU |
| --- | ---: | ---: |
| BILATERAL / active | 1.369 s | 0.216 s |
| BILATERAL / defocus_8px | 1.496 s | 0.247 s |
| BILATERAL / disabled | 0.248 s | 0.207 s |
| KUWAHARA / active | 3.462 s | 0.222 s |
| KUWAHARA / defocus_8px | 3.591 s | 0.234 s |
| KUWAHARA / disabled | 0.286 s | 0.223 s |
| PAINT / active | 12.431 s | 0.280 s |
| PAINT / defocus_8px | 12.623 s | 0.288 s |
| PAINT / disabled | 0.212 s | 0.218 s |

Paint Filter is substantially more expensive on CPU; prefer the native GPU compositor on supported hardware for large Paint renders. CPU/GPU output is not promised to be byte-identical. Softness and large radii add work, and image-buffer/render-data overhead remains when bypassed. Earlier v1.2.3 speedup percentages are not generalized to this new pipeline.

The bundled asset remains a shared, lazily loaded native graph; other modes do not load it. Native input switches reduce bypassed Paint processing by presenting constant inputs to expensive asset operations. No render-time downloads, external Python packages, custom compute backend or per-frame Python handlers were added.

## Reproduce and remaining limits

The [guide](../GUIDE.md#development-and-validation) documents the integration, event-loop, and performance tests. [Test results](test-results.json) record the named checks, default comparisons and raw timing samples. Tests use Blender's bundled Python/NumPy and disposable scenes.

One camera and configured view layer per scene remain the supported workflow. Existing screen-space transparency, refraction, motion-blur, antialiased-edge, deforming-hair and complex-compositor limitations remain. Material discovery uses current-frame viewport evaluation; render-only/later-frame material changes can need Refresh or explicit material slots. Deleted/replaced generated nodes generally require restoring the original structure or rebuilding. Unexpected late removal failure retains Undo recovery rather than reconstructing every deleted resource automatically.

Long production animations, other GPU vendors/backends, later Blender releases, stereo and alternative OCIO configurations remain outside the test matrix.
