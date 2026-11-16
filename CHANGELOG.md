# Changelog

## 2.1.1

- Added Protect Sharp Edges for additional Defocus. Sharp silhouettes are excluded from the blur source, with surrounding colors extended behind them before blurring and painting. The final blend retains the original sharp image.
- Works with all three painterly methods and Gaussian, round and polygon blur. The protection starts on; turn it off to restore the earlier filtering behavior.
- Defocus zero bypasses the added processing. Original alpha, HDR colors, camera focus animation and bloom settings are retained.
- Existing setups upgrade in place with reversible graph changes. No additional material outputs or render-time Python handlers.
- Added rendered regressions for high-contrast outlines, thin and antialiased silhouettes, large radii, alpha, CPU/GPU compositing, motion and older saved graphs.

## 2.1.0

- Add optional actual-input-width scaling for filter/stroke radius and Defocus, with a 1920 px reference by default. Keep existing fixed-pixel behavior unless enabled.
- Use native Active Camera/Camera Info for camera focus where supported. Preserve the existing control curve as a muted fallback; retain manual focus and the driver path. Test camera replacement, rotated/scaled cameras, off-axis targets and bone animation in both Blender 5.2 and 5.3.
- Add Glow Exposure before stepping and a Falloff curve to reveal faint outer halos. Expose the complete Spread range in normal dragging, expand Amount, and rename Steps to Band Density to describe its actual behavior. Neutral new controls preserve ordinary v2.0 looks.
- Add Bloom Only preview and a panel button to inspect bands on black, with saved-output and transparency explanations.
- Decouple bloom from painterly Strength/Radius. Global Enable Effect still bypasses everything; zero Amount bypasses bloom. No material/AOV setup simplification is included.
- Upgrade older graphs transactionally, diagnose damaged fixed links before reconfiguration, retain native animation and bypass efficiency, and add 1080p/4K, high-gain, native focus, upgrade and Undo checks.

## 2.0.0

- Expose the bundled Paint Filter's Watercolor, Oil Paint and Digital Geometric brush styles, brush sharpness, hue variation, pigment pooling, fixed seed, canvas/paper choice, grain scale and amount. Retain v1.3 defaults and the original CC0 asset.
- Add optional round and polygonal aperture blur before painting, with blade count, rotation and roundness. Keep the existing Gaussian default. Convolution is scalar-radius and focus-mask blended; it does not reconstruct occluded background.
- Add optional Soft and Stepped Paint bloom. Use smooth highlight extraction, hue-preserving HDR brightness bands, softened transitions and fixed-seed texture breakup. Keep incoming alpha and bypass all extra processing when disabled or zeroed.
- Optional bloom tracking uses native Position on static surfaces, sharing the pass with Paint. Depth is requested only by tracked Paint. Preserve pre-existing passes and external consumers on mode changes/removal. No temporal cache, external dependencies or per-frame Python handlers.
- Group controls into Brush, Canvas, Defocus Shape and Bloom sections; add tooltips and offline help for the new controls and animation limits. Custom image mapping, look presets and additional artistic modes remain outside this release.
- Upgrade intact older graphs transactionally in place, retaining existing nodes, drivers, settings and animation paths. Keep new effects opt-in. Add native Cycles CPU/GPU renders, repeated/reverse-frame tests, a short camera animation, save/reopen, recovery, default-pixel comparisons, native Undo snapshots and compositor timing fixtures.

## 1.3.0

- Add **Paint Filter** alongside Bilateral and Kuwahara, using Pau Homs' pinned Blender Essentials CC0 asset. Load it lazily and save its required groups locally in the blend; no render-time downloads or machine-specific asset paths.
- Add **Defocus (px)**: optional Gaussian softness before the painterly filter, blended through the existing focus mask. Default zero preserves older images. Keep sharp pixels, alpha, camera focus bindings and native animation. Increase the radius/stroke-size ceiling from 32 to 64 without changing its default.
- Expose Paint Simplification, Edge Breakup, and optional world-space Position Tracking through native Depth/Position passes. Prepare and repair those passes on the configured view layer; preserve pre-existing passes and external user links on release/removal.
- Keep the panel compact and update native hover descriptions/offline help. Surface Guide controls remain Bilateral-specific. Position tracking requires a new render and is not deformation tracking for moving Alembic objects.
- Upgrade older native groups transactionally in place, preserving controls, drivers and compositor edits. Journal new interfaces/drivers and native pass changes. Release unused bundled groups without adopting or overwriting same-named user assets.
- Gate expensive Paint inputs while bypassed so the asset works on constant data when disabled, at zero strength or at zero radius. Active tracked-pixel comparisons and CPU/GPU bypass checks cover this optimization.
- Expand rendered tests for all modes, softness and camera keyframes, tracked CPU/GPU/Eevee, shared-scene detachment, rollback, native Undo/Redo, older saved-file upgrades and offline asset portability. Retain the restricted-registration installation fix.

## 1.2.3

A focused cleanup and performance patch. Existing controls, animation paths, rendering defaults and the one-camera workflow are preserved.

- Include the configured view layer's material override in setup, refresh and diagnosis. Consistently scan that layer when another layer is active; report a read-only override instead of giving a false all-clear.
- Diagnose muted generated material groups, render-data nodes and critical internal nodes. Give an explicit unmute/refresh instruction, preserving deliberate node edits. Missing coverage sockets use an actionable message.
- Trace compositor output sockets through constant switches, constant endpoint mixes and native mute bypasses. Report linked/animated switches and opaque user-group routing as uncertain rather than guaranteeing an effect contribution.
- Warn when Geometry Nodes viewport/render visibility differs and explain how to make render materials discoverable. Full render-graph evaluation remains outside the material scan.
- Add one scalar Effective Radius node so disabled and zero-strength frames use radius zero. Native enable/radius/strength animation is retained; no filter nodes or per-frame handlers are added. Upgrade intact older native groups transactionally in place, without rebuilding their controls or animation.
- Expose Blender's native CPU/GPU compositor setting in Advanced for both methods. Preserve the user's device choice. Clarify last-scan Setup Report versus current Check Setup, and update offline performance/recovery help.
- Add rendered camera focus-distance/lens, focus-target and focus-bone keyframe checks, native animation output, save/reopen and out-of-order frame checks. Verify animated effect bypass on CPU and GPU, upgrade rollback, deferred old-file enabling and native Undo snapshots. Include a reproducible before/after compositor benchmark.
- No GitHub setup, creative features, camera-cut handling, dependencies or custom compute backend.

## 1.2.2

A focused reliability patch. Rendering defaults, saved settings/animation paths and the one-camera workflow remain unchanged.

- Detect stale focus drivers after target deletion. Sync/Refresh falls back to camera distance; invalid bones are rejected before replacing a working binding. Refresh journals focus changes, and syncing retains the existing F-curve and its modifiers.
- Scan editable original materials from evaluated geometry and instances, including Geometry Nodes Set Material and modern hair curves. Report unsupported point-cloud, volume and Grease Pencil geometry instead of silently omitting it.
- Validate essential guide/effect nodes, numeric drivers and important internal connections. Numeric edits check only control bindings; full validation uses one node lookup index per check. Damaged generated nodes receive an actionable message rather than a false-success refresh.
- Add a compact, on-demand **Check Setup** popup covering focus, graph/control damage, passes, material branches, brush files and compositor state.
- Show scene-level compositing bypass and disconnected saved setups. Add explicit **Enable Compositing** and **Restore Configured Compositor** recovery actions with Undo. Refresh does not override an intentionally disabled compositor.
- Roll back copied-scene detachment after late failures, including metadata cleared before failure, and discard the staged compositor. Unexpected late removal failures retain an Undo step and explain recovery; removal preflight still guards predictable failures before deletion.
- Extend factory-scene regression coverage with procedural and hair renders, stale-focus recovery, damaged-node/driver/link diagnostics, read-only inspection, detachment failure and undo-snapshot checks. Preserve native restricted enabling and original v1 migration coverage.
- No additional render/filter nodes, dependencies, presets, creative outputs or per-frame handlers.

## 1.2.1

- Fixed `'_RestrictData' object has no attribute 'scenes'` during installation/enabling. Registration now defines classes, properties and handlers without scanning scene data inside Blender's restricted context.
- Restores open-file focus bindings through a one-time deferred initialization callback. File loading supersedes it; disabling the add-on cancels it. It adds no per-frame work or hover timer.
- Added tests through Blender's real enable/disable path, covering repeated enable, immediate disable, compatibility schema availability and callback cleanup.
- UI, rendering defaults, saved settings and migration behavior are unchanged from 1.2.0.

## 1.2.0

A focused interface and documentation update. Rendering algorithms, defaults, saved property paths and migration behavior remain unchanged.

- Added practical native hover descriptions to every add-on control and action, including quality, performance, portability and rerender guidance. Tooltip visibility and delay follow Blender preferences.
- Grouped the panel into collapsible Focus, Surface Guide, Advanced, and Setup & Maintenance sections. Less frequently used sections start closed; Blender stores their open state in the editor region.
- Hid unused brush and Bilateral settings in Kuwahara mode while retaining their saved values.
- Added offline Help with five selectable topics, available before building and during setup recovery.
- Made Setup Report a read-only popup with its own description.
- Added a native camera focus-object picker and show Sync Active Camera when the binding changes; manual sync remains available in Setup & Maintenance.
- Shortened display labels for narrow sidebars, enabled native animation decorations, and greyed falloff controls for disabled foreground/background sides.
- Added clear notices for effect bypass and diagnostic previews affecting saved render output.
- Moved layout and help into a small UI module. No dependencies, render nodes, hover timers or per-frame handlers were added.

## 1.1.1

A focused reliability patch. Rendering algorithms, defaults and the one-camera-per-scene workflow remain unchanged.

### Fixed

- Linked old brush images are no longer renamed during migration. Editable image renaming occurs before commit and can be rolled back safely.
- Migration no longer rewrites old generated-group drivers that are about to be retired, and clears every reversible handle before deleting legacy resources.
- A late cleanup failure retains the working new setup and its animation, reports a warning and offers a retry through the existing migration operator. The retry marker survives saving/reopening.
- Detachment and shared legacy migration retarget direct image/depth sources to the copied scene, including an existing compositor's matching Render Layers references.
- Detachment removes copied owned AOVs, preventing six-pass accumulation after rebuilding.
- Removal finds direct, nested and inactive compositor copies using the owned effect; preserves user edits; and checks actual use by other scenes before changing data.
- Refresh follows a copied active compositor and transactionally reapplies guide/effect settings and AOV links.
- Persistent internal node keys protect generated-node lookup from later renaming. Existing 1.1.0 groups use a compatible name fallback without rebuilding.
- Errors retain their component identity and remain visible when unrelated controls change.
- Brush loading validates the guide first, applies assignment/wiring as one operation, restores prior settings/links on failure and removes the failed loaded image.
- Legacy driver-reference migration also includes embedded material node trees.

### Scope

- No new filters, presets, camera-cut handlers, automatic rebuilds or runtime packages.
- Native render graphs keep the same nodes. Added checks run during setup, editing, removal or file loading rather than on each frame.
- Missing/replaced generated nodes are diagnosed; restoring the original node or rebuilding remains the recovery path.

## 1.1.0

### Fixed

- Focus-object projection used transposed matrix indices in RNA driver paths, producing incorrect distances for rotated cameras. The driver now reads the actual camera axis and normalizes scale.
- Camera/bone validation runs before replacing a working focus driver. Manual mode clears stale binding metadata. Effective focus distance is kept positive.
- Refresh restores compositor links when deleted AOV passes recreate their Render Layers sockets. It follows renamed view layers and reports replaced/missing generated nodes.
- Refresh rollback restores previously existing links and AOV-node properties, in addition to removing new resources.
- Ownership checks protect both guide and effect groups, and removal refuses to change shared or read-only setup data.
- Removal prepares a private compositor copy, preserves downstream edits and restores unlinked image constants. Owned unused groups are released.
- Setup preserves an existing unlinked compositor output's constant image instead of replacing it with Render Layers.
- Errors remain visible in the panel during migration and shared-setup recovery.
- Brush loading accepts Blender-relative paths and checks for an existing file.
- Registration failures unwind registered classes/properties; unregister removes the load handler.

### Improved

- Renamed the extension, sidebar, operator namespace, settings, nodes, groups and new AOVs to neutral project names.
- Replaced the Blender 5.2-only upper bound with a 5.2 minimum and required-API checks. Later Blender releases are allowed, subject to API compatibility.
- Added explicit saved-v1 migration, including numeric controls, image references, actions, NLA strips and common driver references. Shared old scene setups become independent without stripping pending scene copies.
- Added Detach Shared Setup for newly duplicated configured scenes.
- Added Fast Bilateral, using one filter pass instead of Balanced's two levels.
- Added a native animated bypass, with zero-radius/zero-strength bypass and exact sharp-zone blending.
- Split shader and compositor update paths and avoid recreating unchanged links.
- Reduced node-layout traversal overhead by indexing graph edges once.
- Replaced project-specific documentation with installation, upgrade, portability, development and validation instructions.

### Compatibility

- Defaults preserve the previous Balanced Bilateral appearance where possible; corrected camera projection changes previously incorrect focus distances.
- Generated internal groups are rebuilt during migration. Manual edits inside those groups must be reapplied.
- Structural choices such as method, quality, mapping and focus mode are not keyframe controls. Numeric settings, near/far toggles and Enable Effect remain animatable.
- Minimal hidden v1 storage identifiers remain only for saved-data compatibility.
- No hard-coded local file paths, network access, platform-specific imports or external runtime dependencies are included.
