# Stylized Depth of Field

A Blender extension for camera-driven painterly focus. Choose surface-guided Bilateral, anisotropic Kuwahara, or Blender Essentials Paint Filter. Optional aperture blur adds stronger defocus; Soft or Stepped Paint bloom adds colored highlight washes.

**Version 2.1.1 · Blender 5.2 or newer · GPL-3.0-or-later**

The extension uses native Blender nodes and drivers. It needs no external Python packages, online service, fixed installation directory, or platform-specific executable. A compressed CC0 Paint Filter node asset is bundled locally; it is loaded only when Paint Filter is selected. Blender 5.2.0 LTS and 5.3.0 on Windows are verified runtimes. Later versions are allowed by the manifest and checked for required APIs during setup; they have not been independently tested.

## Install

1. Keep `Stylized_Depth_of_Field_v2.1.1.zip` zipped.
2. In Blender, open **Edit → Preferences → Add-ons → Install from Disk**.
3. Select the ZIP and enable **Stylized Depth of Field**.
4. Press **N** in the 3D View or Compositor and open **Stylized DOF**.

The source archive is for development. Use the install ZIP for **Install from Disk**.

## Upgrade from 1.1.x through 2.1.0

Save a copy of the shot, install 2.1.1, restart Blender and reopen the saved file. Intact setups upgrade in place. Existing settings, animation paths, numeric control curves and compositor edits are retained. Existing aperture and bloom choices are kept. Protect Sharp Edges starts on and affects shots using additional Defocus; turn it off to restore the previous filtering behavior. Resolution scaling starts off for older setups; Glow Exposure 0 and Falloff 1 retain normal v2.0 bloom brightness placement. Native camera nodes replace the active focus source where supported; the previous focus F-curve is retained and muted for fallback/manual use.

**Behavior change:** painterly Strength or Radius zero disables painting while leaving enabled bloom available. Use Bloom Amount zero to remove glow, or Enable Effect off to bypass everything. Keep an older blend copy to return to an older add-on: files saved with the new edge-protection graph need 2.1.1 or later to edit their setup.

Damaged generated nodes/links are diagnosed before upgrade changes commit. Hand edits inside generated groups are not part of the supported editing interface. Persistent keys permit renaming intact generated nodes. Newer Blender files are not assumed to open in older Blender versions even when the add-on supports both.

## Stronger focus and Paint Filter

**Defocus (px)** defaults to Gaussian softness before the chosen painterly filter, blended through the existing focus mask. It defaults to **0**, preserving earlier looks. Try **4–8 px** to remove more photographic detail, and increase gradually. The original sharp region and incoming alpha are retained. This is an artistic screen-space effect; it does not reconstruct hidden background detail or guarantee halo-free silhouettes.

**Protect Sharp Edges** appears below Defocus when its amount is above zero. It removes sharp silhouettes from the filtering input, extends surrounding colors into the holes, then applies Defocus and painting before the original sharp subject is blended back. This reduces the soft duplicate outline around a focused object. It works with Soft / Fast, Round and Aperture shapes in all three painterly modes. It starts on; off restores the earlier behavior. Defocus zero bypasses this processing. Background extension is an approximation: extreme blur, subpixel details, transparent surfaces and large depth discontinuities still need shot checks. Bloom can intentionally spread bright colors and is separate from this protection.

**Method → Paint Filter** adds Blender Essentials brushwork. Start with a **Stroke Size of 12–20 px**, Strength 1, and Simplification around 2–4. Simplification reduces detail inside the paint filter. Brush and Canvas contain style controls and Edge Breakup; depth-edge protection remains in Advanced. Higher values can erase detail and cost more. Paint uses its own procedural textures: editing Alembic UVs is not needed for its basic brushwork. The Surface Guide and brush-image controls remain specific to Bilateral.

**Brush → Position Tracking** optionally uses the configured layer's native **Position and Depth** passes. Enable it, then render again with F12. Position provides world-space brush placement; Depth supplies the asset's distance information. This can help with camera movement and different object scales. A moving/deforming object, including an Alembic cache, can still move through the world-space pattern; this is not rest-position or deformation tracking.

Tracking is off by default. Tracking shares Position with optional bloom tracking. Depth is requested only for tracked Paint. Passes added by the add-on are released when no effect needs them or on removal/detachment, unless user compositor nodes also use them. Passes enabled before the add-on are preserved. Use Add / Refresh Materials to repair missing tracking links/passes, then rerender. Enabling passes cannot add them retroactively to an old render.

Paint Filter and all its helper groups are stored locally in the saved blend. They are not downloaded at registration or render time. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for Pau Homs' CC0 asset credit, source and pinned hashes. GPU compositing is recommended for large Paint renders where supported; CPU processing of this asset is substantially more expensive.

## Paint styles and canvas

**Brush Style** chooses Watercolor, Oil Paint or Digital Geometric from the bundled asset. In **Brush**, Sharpness controls how closely shapes follow the brush texture; it is not an ordinary sharpening filter. Color Variation shifts hue per stroke. Pigment Pooling darkens stroke edges. Keep the Brush Seed fixed throughout a shot. The old Watercolor, sharpness 0.6, color variation 0.2 and pooling 0.1 defaults are retained.

**Canvas** offers Canvas, Rough Paper or None. Texture Amount overlays grain; zero hides the overlay but retains canvas-driven Edge Breakup. None removes the pattern and that breakup. Higher Texture Scale gives finer grain. Custom brush/canvas images in Paint Filter are deferred; the existing Bilateral brush-image controls remain available for its surface guide.

## Aperture blur

**Defocus Shape → Blur Shape** offers Soft / Fast, Round Bokeh and Aperture Bokeh. Raise the main Defocus amount above zero. Aperture Bokeh adds blade count, rotation and roundness; roundness 1 approaches a circle. Shapes can be softened or changed by the painterly filter afterward.

The aperture uses a uniform-radius convolution blended through the focus mask, preserving the sharp zone and incoming alpha. It is an artistic compositor blur, not a camera optics solver or occlusion reconstruction. Strong settings can spill foreground colors across silhouettes. Square-looking filter patches can originate from Bilateral/Kuwahara sampling rather than the aperture. Keep the camera's optical DOF off unless you intentionally want both effects.

## Bloom

Enable **Bloom**, choose **Soft** or **Stepped Paint**, then use **Preview Bloom Only** to inspect the glow on black. Return to Final Effect before rendering your final image or animation: previews also change saved output.

For a broad, clearly stepped starting point try Amount **0.2–0.4**, Spread **0.3–0.6**, Glow Exposure **+3 to +4**, Falloff **0.7–0.8**, Band Density **2–3**, and Edge Softness **0.35–0.6**. These are artistic starting values, not universal settings; your highlight brightness still matters.

- **Spread:** spatial reach relative to the image. Its full 0–1 range is available by dragging. Larger spreads distribute a small light's energy more thinly.
- **Glow Exposure:** brightness boost BEFORE stepping, in stops. +1 doubles that signal. This reveals faint outer bands that raising Amount could not recover in 2.0. Zero retains old placement.
- **Falloff:** shapes glow brightness before stepping. Below 1 lifts faint outer tails for a fuller halo; above 1 concentrates it. Default 1 preserves the previous curve.
- **Amount:** final intensity AFTER stepping. Its range is expanded to 32. Zero skips bloom processing. High settings can wash out the image; work upward from a small value.
- **Highlight Threshold:** scene-linear brightness contributing to glow, with a smooth transition. Increase it if too many diffuse surfaces glow; reduce it if the intended lights do not contribute.
- **Band Density:** brightness levels per stop, not an exact count of spatial rings. Lower gives broader bands. Use Glow Exposure to move where bands appear and Falloff to reshape their distribution.
- **Edge Softness:** transition width between bands. Softer boundaries are safer for animation; very hard bands can pop as highlights move/change.
- **Painterly Breakup:** fixed irregularity along the band boundaries. Start low for animation.
- **Texture:** scale, fixed seed and optional Position Tracking. Tracking is world-space placement on static surfaces, with screen coordinates on empty background. Render again after enabling it. Moving/deforming geometry can slide through the pattern; glow beyond a silhouette has no matching surface position.

Bloom is an image-space effect; the physical size of a scene does not directly set its halo size. It affects highlights across the frame, including the focused subject and world. Bloom works with painting Strength or Radius zero. Enable Effect off bypasses everything.

Original alpha is preserved. A transparent background or an upstream alpha mask can hide parts of a halo in the final alpha composite; Bloom Only is opaque so you can inspect the full glow. Alpha expansion, a focus-only glow scope and custom Paint image mapping are outside this update.

## Resolution scaling

In **Advanced**, enable **Scale with Resolution**. The default Reference Width is **1920**: an 8 px reference radius becomes 16 px on a 3840-wide image, and 4 px on a 960-wide image. Stroke/filter radius and additional Defocus scale together. Bloom Spread is already image-relative.

Sizing uses actual input width, including render percentage. Labels change to **ref px** when enabled. Leave the checkbox off for fixed pixel sizes. Scene units, guide UV density and individual object scale are not changed. Existing image/pass framing restrictions still apply. Larger images and radii increase processing cost; this keeps the look consistent, not the render time.

## Animation workflow

Camera focus distance, focal length, focus-target/bone motion and numeric look controls evaluate through Blender's native drivers/nodes. Use one camera per scene. Native camera nodes follow camera/target/bone changes automatically on supported builds. Sync Active Camera remains a repair/fallback action. Optical camera DOF may remain off.

Keep style selectors, texture seeds, Band Density and tracking choices fixed for a shot. Numeric paint, bokeh and bloom controls marked with native keyframe decorations can be animated. Configuration choices are not intended for animation. Turn on tracking before rendering the sequence, then use a fresh full render so the required passes exist.

World tracking helps camera moves across static scenery. It is not deformation/rest-position tracking for Alembic and does not guarantee flicker-free strokes or glow. Use moderate breakup, softened band edges and adequately sampled/denoised Cycles highlights. Render a short section containing your brightest lights and fastest movement before a long sequence. Repeated-frame tests verify that the add-on has no previous-frame history, but they do not prove every scene is temporally artifact-free.

## Upgrade an existing v1 setup

1. Save a copy of the original `.blend` file before upgrading.
2. Disable the old add-on in Preferences. Leave its saved scene nodes in place; do **not** use its Remove Setup button.
3. Install and enable this extension, then reopen the saved file.
4. In **Stylized DOF**, click **Migrate Saved Setup** for each configured scene.
5. Render again to populate the new AOV names, then save the migrated file.

Migration preserves panel settings, brush image references, numeric keyframes, the Enable Effect animation, scene actions, NLA strips, and scene property drivers. It copies affected actions before rewriting their paths, preserving actions shared by other IDs. Common driver references on scenes, objects, cameras, materials, embedded material node trees and node groups are updated too.

Existing material surface connections and upstream/downstream compositor edits are retained. Generated guide/effect groups are rebuilt, so hand edits **inside** those generated groups must be reapplied. Existing brush images remain packed if they were already packed; unpacked images still require their external files.

Old scene copies can be migrated in any order. Each receives independent settings and groups; old shared material branches remain until the last scene using them is migrated. The extension keeps a hidden compatibility schema and a few old storage identifiers solely to read saved v1 data. New panels, extension identity, node names, groups and AOVs use neutral names.

Linked brush images remain linked and keep their library names. Migration finishes its reversible work before retiring old data. If final cleanup fails, the updated setup and animation stay usable and the panel offers **Finish Cleanup** to retry; the old setup marker remains until cleanup succeeds.

## First use

1. Choose Cycles or Eevee and set the scene camera. Keep the camera's optical DOF off if you want only this effect.
2. Assign editable node materials. Use stable UVs for animated or deforming geometry.
3. Choose **Entire Scene** or **Selected Objects**, then click **Build Setup**.
4. Leave **Starter Patches** selected for the guide and render with **F12**.
5. Inspect **Preview → Focus Mask**. Black stays sharp; white receives the maximum effect.
6. Adjust focus distance, **Half-width** and the near/far falloffs. Return to **Final Effect** and start around a 5 px radius.

Turn **Foreground** off for background-only stylization. The camera's focus object or distance drives the focus plane even with optical DOF disabled. If optical DOF is enabled, this extension processes the already blurred render.

## Panel and help

The main controls cover enabling the effect, method, radius, strength and preview. **Focus** opens by default. **Brush**, **Canvas**, **Defocus Shape**, **Bloom**, **Surface Guide**, **Advanced**, and **Setup & Maintenance** start collapsed; Blender remembers their open state in the editor region. Surface Guide and Bilateral-specific Advanced controls are shown for Bilateral only. Advanced also exposes Blender's native CPU/GPU compositor choice for either method; setup and refresh preserve the selected device. Existing guide settings are retained when changing methods.

Hover controls and action buttons for explanations, suggested starting values and rerender requirements. These are Blender's native tooltips: visibility and delay follow your Blender preferences. The extension does not change those preferences or use a hover timer. Native keyframe decorations remain available for animated controls.

**Help** stays available before setup and during error, migration or shared-scene recovery. It opens an offline popup with Paint & Bokeh, Bloom & Animation, Getting Started, Focus, Surface Guides, Quality & Performance, and Troubleshooting topics. Choose a topic in the dropdown; click outside or press Escape to close. **Setup Report** opens the last build or refresh report, rather than performing a new scan. **Check Setup** runs a current, read-only inspection of focus, controls, generated links, passes, materials, compositor state and brush-file availability. These checks run on request, without adding frame handlers.

Choose **Focus Object** directly in Focus. Native camera nodes read the current camera's distance, target and bone without per-frame Python. They update automatically after source changes. Missing bones remain an actionable error. The established driver path is retained as a fallback, and manual distance still uses native property drivers. Sync Active Camera or Refresh repairs bindings when needed. Disabled Foreground/Background sides grey their falloff control.

**Preview changes the saved render output too.** Return to **Final Effect** before producing a final image or animation. Diagnostic previews, a bypassed effect, disabled scene compositing and disconnected output show status notices. **Enable Compositing** deliberately restores Blender's scene-level compositor switch. If another compositor is active, **Restore Configured Compositor** switches back to the saved setup where its output links are intact, leaving the alternative group available. A damaged saved output needs its links restored or the setup removed and rebuilt.

## Controls

| Control | Behavior |
| --- | --- |
| Camera Focus | Use the camera's distance or project its focus object/bone onto the camera axis |
| Sync Active Camera | Repair/rebind focus when needed; native camera information normally follows source changes automatically |
| Manual Distance / Focus Offset | Set a distance or offset the camera/manual focus plane |
| Half-width | Sharp distance on each side of the focus plane; twice this is the total sharp zone |
| Foreground / Background | Enable either side independently |
| Near / Far Falloff | Distance beyond the sharp zone needed to reach the maximum effect |
| Radius (px) | Maximum filter size in output pixels, capped at 64; larger values cost more |
| Strength | Blend with the original image |
| Defocus (px) | Extra softness using Defocus Shape, blended through the focus mask; zero preserves the old look |
| Paint Filter / Simplification | Essentials brushwork with additional detail reduction |
| Position Tracking | Optional native Depth/Position passes for world-space Paint brush placement; rerender after enabling |
| Enable Effect | Native bypass that also supports keyframes |
| Balanced Bilateral | Two filter sizes for a smoother transition through the focus mask |
| Fast Bilateral | One filter size blended through the focus mask; lower filtering cost with a different transition |
| Guide Weight | Strength of brush-pattern boundaries in Bilateral mode (Texture Influence) |
| Threshold | Lower preserves more boundaries; higher allows more smoothing (Boundary Threshold) |
| Depth Edges | Reject neighbors at different depths; high values can reduce smoothing on slopes (Depth Edge Protection) |

Numeric controls with keyframe decorations, near/far toggles and Enable Effect can be keyframed. Brush Seed, bloom Texture Seed and Band Density are fixed shot settings. Defocus, Simplification and Edge Breakup also support keyframes. Method, preview, focus mode, mapping, guide source, quality and Position Tracking are configuration choices; they are not keyframe controls.

Focus, strength, radius and Bilateral boundary controls can update from an existing render in the Compositor. Guide placement, material, camera pose and geometry changes require a new render.

## Brush guides and portability

Use **Load Brush Image** for a tileable grayscale or color pattern. It loads a separate Non-Color image, leaving other image uses alone. **Pack Loaded Image** is on by default, embedding the loaded image in the `.blend` file when saved. A directly selected image is not automatically repacked or recolored.

Use **UV** mapping for deforming objects. **Generated** mapping uses box projection for images and suits static objects; its pattern can move when bounds or deformation change. Higher tiling produces smaller patches. Higher V tiling stretches procedural patches horizontally. Missing mesh UVs give a flat guide in UV mode and are listed in the Setup Report. Modern hair receives depth and coverage AOVs, but its surface coordinates differ from mesh UVs; inspect Surface Guide and choose mapping appropriate to the hair setup. Generated coordinates on deforming hair are not guaranteed to be stable.

The guide defines smoothing boundaries; it is not stamped onto the rendered image. Kuwahara follows rendered image edges and does not use the brush pattern.

## Setup, refresh and removal

- Setup copies the current compositor and inserts the effect before its first Color output. Viewer nodes using the same upstream image are rerouted with it.
- Three uniquely named AOVs carry Guide, Depth and Coverage on the configured view layer. Material scans include that layer's material override, original slots, evaluated materials such as Geometry Nodes Set Material, collection/object instances and modern hair curves. Evaluated IDs are resolved to their editable originals. Discovery consistently uses the configured view layer, even when Refresh or Check Setup is invoked from another active layer. Procedural discovery uses the current frame; refresh again if frame-dependent geometry introduces new materials. Complex geometry components or render-only modifier branches outside the evaluated viewport data may require adding their materials to original slots before refreshing. Differing Geometry Nodes viewport/render visibility produces an explicit warning; enable the modifier in the viewport before Refresh or add its render materials to original slots. Material surface shader links are preserved. Unsupported geometry, empty material slots and read-only/non-node materials are reported.
- Shared materials are processed once. Selected Objects is a material-based scope, so their other users can receive the same guide.
- **Add / Refresh Materials** adds missing branches, repairs missing AOV links, validates generated control nodes/drivers and important fixed links, reapplies valid guide/effect settings, and rebinds focus. It also follows a copied active compositor. Setup and refresh failures roll back created nodes/passes, changed links and focus bindings. Refresh respects a deliberately disabled scene compositor. Muted generated nodes receive an instruction to unmute them in the node editor; Refresh does not silently override that edit.
- **Remove Setup** validates bypasses on temporary copies, then removes the owned effect from its editable compositor copies/references while retaining user edits. It removes only this setup's material branches/passes and refuses removal if another scene still uses those compositors. It retains loaded images. Predictable failures stop before deletion. An unexpected failure after deletion reports that Undo is required and retains the operator's Undo step; it is not an automatic deletion rollback.
- A newly duplicated configured scene shares node groups. Use **Detach Shared Setup** on the copy, then build its own setup. Detachment retargets direct Render Layers references to that copy and removes its copied owned passes; references to unrelated scenes are preserved. Detachment restores the prior compositor, owned passes and saved state on failure, and discards its temporary graph. Edits and removal are guarded while a setup is shared.
- Operators support Blender Undo. Disabling the extension does not automatically remove scene nodes. Keep it enabled to evaluate panel-driven settings in saved files and background renders.

## Performance

Only the selected painterly method is connected to the result. Optional bokeh and bloom nodes are created on first use and reused without growth. Bloom uses one native glare pass; Soft mode disconnects band/noise processing. Zero bloom amount and disabled bokeh feed constant data to their optional image operations. Bokeh uses a scalar radius to avoid a costly variable-radius convolution. Fast Bilateral disconnects the half-radius path. Focus/guide previews disconnect the filter result; global disabling routes through a native switch; zero radius/strength sets the effective painterly radius to zero while optional bloom remains available. Paint also switches its expensive image inputs to constants while bypassed, reducing unnecessary asset processing without replacing native animation. This reduces unnecessary filtering on bypassed frames while preserving native keyframes. Image-buffer handling and render-data generation still have a cost. Actual execution cost depends on Blender's compositor, image size, filter settings and hardware. Advanced > Compositor exposes Blender's scene CPU/GPU setting. GPU can reduce filtering time on supported hardware; compare the final look when switching backends. Active filtering and fully sharp Bilateral frames still incur their normal filter cost.

Compositor controls invalidate the compositor group; guide placement controls invalidate the shader group. Repeated refresh and unchanged wiring avoid redundant link edits. Core multi-node validation uses a lookup index. Numeric edits inspect only control bindings; detailed graph/material scans run during maintenance or on demand. Node layout builds an adjacency map once. There is no per-frame Python handler; a file-load handler upgrades intact older effect groups and restores focus bindings once when opening a file. Enabling the extension queues one nonpersistent initialization callback so an already open file can be checked after Blender's registration restrictions end. It stops after one run and is cancelled on disable or superseded by a file load.

## Limits and troubleshooting

These are screen-space filters, not physically accurate optical blur or guaranteed flicker-free painted strokes. Painterly focus leaves the world background unchanged; optional bloom can affect highlights across the image. Transparency, refraction, motion blur, antialiased silhouettes and overlapping geometry retain screen-space limitations. Incoming alpha is preserved, but that does not eliminate all color halos.

Use one configured view layer and matching image framing per scene. Combining different scenes/layers, transformed images, stereo views or cropped inputs requires manual compositor work. Camera focus-distance and lens keyframes, moving focus objects and focus-bone animation use Blender's native evaluation; render each frame after changing framing or geometry. Focal length changes framing, while focus distance controls the sharp plane. Automatic camera-marker rebinding is not implemented: sync after camera/target changes and configure cuts as separate shots/scenes where needed. Shader AOVs in the viewport compositor are not assumed; use full renders.

If the effect is missing, rerender after setup or a guide change, inspect the Focus Mask and Surface Guide previews, then use Check Setup and inspect the camera sync notice. Weak Bilateral smoothing often means a very low Threshold or high Depth Edges setting. Generated internal names can change once their persistent keys are present. Deleted/replaced nodes still require restoring the original node with its links/drivers, or removing and rebuilding the setup. Check Setup follows constant switch branches and native muted-node bypasses. Linked/animated switches and opaque user groups are reported as uncertain connections; inspect their final output. Guide errors remain visible when unrelated sliders change; brush loading reports success only after the guide hookup completes.

## Development and validation

See the [changelog](CHANGELOG.md) and [validation notes](docs/validation.md). Run these commands from the repository root. The source includes a background integration suite using Blender's bundled Python and NumPy:

```text
blender --background --factory-startup --python-exit-code 1 --python stylized_depth_of_field/tests/integration.py -- --work-dir ./test-output
```

Add `--legacy-dir PATH_TO_UNPACKED_V1` after the work directory to run migration against the original v1 package. Add `--eevee` to include Eevee render checks on a machine with a supported graphics device. Pass `--previous-blend PATH_TO_V1_1_0_BLEND` to check a direct 1.1.0 saved-file upgrade. All test outputs use the resolved work directory. The established integration suite explicitly exercises the driver fallback; the v21 suite exercises native camera nodes. Both use disposable scenes. The suite uses disposable factory scenes; it does not save preferences or install add-ons.

Build and validate the install ZIP with Python 3.11+ and Blender 5.2:

```text
python scripts/build_release.py --blender blender
```

Pass the full path to the Blender executable if it isn't on your PATH. The ZIP goes into `dist/`.

Run `stylized_depth_of_field/tests/v21.py` with `--work-dir ./v21-output` for native camera/bone/replacement tests, actual 1080p/4K sizing, broad bloom, keyed exposure/falloff, CPU/GPU agreement and save/reopen. An optional `--previous-blend PATH_TO_V2_BLEND` exercises transactional upgrade recovery.

Run `stylized_depth_of_field/tests/v2.py` with `--work-dir ./v2-output` for native Cycles feature, bypass, repeated/reverse-frame, save/reopen and recovery tests. Add `--previous-blend PATH_TO_V1_3_BLEND` for late upgrade rollback checks.

For deterministic three-mode and Defocus compositor timings, run `stylized_depth_of_field/tests/performance.py` in background with `--threads 8` and `--work-dir ./performance-output`. It uses full-frame image inputs with a minimal Workbench carrier; its timings do not predict whole-scene render times. Add `--v2` for optional aperture/bloom cases with HDR highlights, and `--device CPU` or `--device GPU` to choose the compositor backend. Compare a shot before switching devices; native Paint Filter can produce small backend differences around HDR edges.

The source also contains `stylized_depth_of_field/tests/event_loop.py`. Run it without `--background`, using `--factory-startup --python stylized_depth_of_field/tests/event_loop.py -- --work-dir ./event-loop-output`, to verify deferred initialization and native undo snapshots. The timer harness explicitly pushes snapshots; it does not automate clicking panel buttons. Pass `--previous-blend PATH_TO_OLDER_BLEND` to also test the deferred upgrade of a file opened before enabling. It closes its disposable Blender session automatically.

Relevant Blender references: [compositor migration/API changes](https://developer.blender.org/docs/release_notes/5.0/migration/compositor_migration/), [Bilateral Blur](https://docs.blender.org/manual/en/latest/compositing/types/filter/blur/bilateral_blur.html), [Kuwahara](https://docs.blender.org/manual/en/latest/compositing/types/creative/kuwahara.html), [native UI layout API](https://docs.blender.org/api/current/bpy.types.UILayout.html).

License: [GNU GPL v3 or later](LICENSE).
