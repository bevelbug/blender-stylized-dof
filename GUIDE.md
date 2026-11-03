# Stylized Depth of Field

A Blender extension for camera-driven painterly focus. Choose surface-guided Bilateral, anisotropic Kuwahara, or Blender Essentials Paint Filter. Optional Defocus adds stronger softness through the same camera focus mask.

**Version 1.3.0 · Blender 5.2 or newer · GPL-3.0-or-later**

The extension uses native Blender nodes and drivers. It needs no external Python packages, online service, fixed installation directory, or platform-specific executable. A compressed CC0 Paint Filter node asset is bundled locally; it is loaded only when Paint Filter is selected. Blender 5.2.0 LTS on Windows is the verified runtime. Later versions are allowed by the manifest and checked for required APIs during setup; they have not been independently tested.

## Install

1. Keep `Stylized_Depth_of_Field_v1.3.0.zip` zipped.
2. In Blender, open **Edit → Preferences → Add-ons → Install from Disk**.
3. Select the ZIP and enable **Stylized Depth of Field**.
4. Press **N** in the 3D View or Compositor and open **Stylized DOF**.

The source archive is for development. Use the install ZIP for **Install from Disk**.

If installing 1.2.0 reported `'_RestrictData' object has no attribute 'scenes'`, save your work and restart Blender, then install this corrected 1.3.0 ZIP. The failure was in add-on enabling; rebuilding scene setups is not required.

## Upgrade from 1.1.x or 1.2.x

Update the same extension to 1.3.0 and reopen the saved `.blend` file. Existing 1.1.x and 1.2.x setups load directly; no rebuild or legacy migration is required. Rendering defaults, saved settings and animation paths are unchanged. Intact older effect groups receive the versioned Defocus controls and inputs in place on file load or deferred enabling; existing nodes, keyframes, drivers and compositor edits are retained. No rebuild is needed. A damaged generated graph is diagnosed before upgrade edits are committed. Some display labels are shorter to fit narrow sidebars. Generated nodes receive persistent lookup keys as they are used, so later internal renaming does not break the controls. Nodes already renamed before the upgrade may still need their original names restored if they have no saved lookup key.

## Stronger focus and Paint Filter

**Defocus (px)** adds Gaussian softness before the chosen painterly filter, blended through the existing focus mask. It defaults to **0**, preserving earlier looks. Try **4–8 px** to remove more photographic detail, and increase gradually. The original sharp region and incoming alpha are retained. This is an artistic screen-space effect; it does not reconstruct hidden background detail or guarantee halo-free silhouettes.

**Method → Paint Filter** adds Blender Essentials brushwork. Start with a **Stroke Size of 12–20 px**, Strength 1, and Simplification around 2–4. Simplification reduces detail inside the paint filter. Advanced contains Edge Breakup and depth-edge protection. Higher values can erase detail and cost more. Paint uses its own procedural textures: editing Alembic UVs is not needed for its basic brushwork. The Surface Guide and brush-image controls remain specific to Bilateral.

**Advanced → Position Tracking** optionally uses the configured layer's native **Position and Depth** passes. Enable it, then render again with F12. Position provides world-space brush placement; Depth supplies the asset's distance information. This can help with camera movement and different object scales. A moving/deforming object, including an Alembic cache, can still move through the world-space pattern; this is not rest-position or deformation tracking.

Tracking is off by default. Passes enabled by this add-on are released when leaving tracked Paint or removing/detaching the setup, unless user compositor nodes also use them. Passes enabled before the add-on are preserved. Use Add / Refresh Materials to repair missing tracking links/passes, then rerender. Enabling passes cannot add them retroactively to an old render.

Paint Filter and all its helper groups are stored locally in the saved blend. They are not downloaded at registration or render time. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for Pau Homs' CC0 asset credit, source and pinned hashes. GPU compositing is recommended for large Paint renders where supported; CPU processing of this asset is substantially more expensive.

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

The main controls cover enabling the effect, method, radius, strength and preview. **Focus** opens by default. **Surface Guide**, **Advanced**, and **Setup & Maintenance** start collapsed; Blender remembers their open state in the editor region. Surface Guide and Bilateral-specific Advanced controls are shown for Bilateral only. Advanced also exposes Blender's native CPU/GPU compositor choice for either method; setup and refresh preserve the selected device. Existing guide settings are retained when changing methods.

Hover controls and action buttons for explanations, suggested starting values and rerender requirements. These are Blender's native tooltips: visibility and delay follow your Blender preferences. The extension does not change those preferences or use a hover timer. Native keyframe decorations remain available for animated controls.

**Help** stays available before setup and during error, migration or shared-scene recovery. It opens an offline popup with Getting Started, Focus, Surface Guides, Quality & Performance, and Troubleshooting topics. Choose a topic in the dropdown; click outside or press Escape to close. **Setup Report** opens the last build or refresh report, rather than performing a new scan. **Check Setup** runs a current, read-only inspection of focus, controls, generated links, passes, materials, compositor state and brush-file availability. These checks run on request, without adding frame handlers.

You can choose the camera's **Focus Object** directly in Focus. A **Sync Active Camera** button appears when the source differs from the saved binding or its driver is invalid, including a deleted target. Refresh also rebinds focus; deleting a focus object then falls back to the camera distance. A missing bone must be corrected first. It is also available in Setup & Maintenance for manually refreshing a camera binding. Moving the bound target or changing the bound distance does not need another sync. Disabled Foreground/Background sides grey their corresponding falloff control.

**Preview changes the saved render output too.** Return to **Final Effect** before producing a final image or animation. Diagnostic previews, a bypassed effect, disabled scene compositing and disconnected output show status notices. **Enable Compositing** deliberately restores Blender's scene-level compositor switch. If another compositor is active, **Restore Configured Compositor** switches back to the saved setup where its output links are intact, leaving the alternative group available. A damaged saved output needs its links restored or the setup removed and rebuilt.

## Controls

| Control | Behavior |
| --- | --- |
| Camera Focus | Use the camera's distance or project its focus object/bone onto the camera axis |
| Sync Active Camera | Rebind after changing the camera, focus object or bone; bound transforms follow animation through native drivers |
| Manual Distance / Focus Offset | Set a distance or offset the camera/manual focus plane |
| Half-width | Sharp distance on each side of the focus plane; twice this is the total sharp zone |
| Foreground / Background | Enable either side independently |
| Near / Far Falloff | Distance beyond the sharp zone needed to reach the maximum effect |
| Radius (px) | Maximum filter size in output pixels, capped at 64; larger values cost more |
| Strength | Blend with the original image |
| Defocus (px) | Extra Gaussian softness blended through the focus mask before the selected filter; zero preserves the old look |
| Paint Filter / Simplification | Essentials brushwork with additional detail reduction |
| Position Tracking | Optional native Depth/Position passes for world-space Paint brush placement; rerender after enabling |
| Enable Effect | Native bypass that also supports keyframes |
| Balanced Bilateral | Two filter sizes for a smoother transition through the focus mask |
| Fast Bilateral | One filter size blended through the focus mask; lower filtering cost with a different transition |
| Guide Weight | Strength of brush-pattern boundaries in Bilateral mode (Texture Influence) |
| Threshold | Lower preserves more boundaries; higher allows more smoothing (Boundary Threshold) |
| Depth Edges | Reject neighbors at different depths; high values can reduce smoothing on slopes (Depth Edge Protection) |

Numeric controls, near/far toggles and Enable Effect can be keyframed. Defocus, Simplification and Edge Breakup also support keyframes. Method, preview, focus mode, mapping, guide source, quality and Position Tracking are configuration choices; they are not keyframe controls.

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

Only the selected method is connected to the result. Fast Bilateral disconnects the half-radius path. Focus/guide previews disconnect the filter result; disabled effects and zero radius/strength route through a native switch and set the effective filter radius to zero through a scalar node. Paint also switches its expensive image inputs to constants while bypassed, reducing unnecessary asset processing without replacing native animation. This reduces unnecessary filtering on bypassed frames while preserving native keyframes. Image-buffer handling and render-data generation still have a cost. Actual execution cost depends on Blender's compositor, image size, filter settings and hardware. Advanced > Compositor exposes Blender's scene CPU/GPU setting. GPU can reduce filtering time on supported hardware; compare the final look when switching backends. Active filtering and fully sharp Bilateral frames still incur their normal filter cost.

Compositor controls invalidate the compositor group; guide placement controls invalidate the shader group. Repeated refresh and unchanged wiring avoid redundant link edits. Multi-node validation builds its lookup index once per check. Numeric edits inspect only control bindings; detailed graph/material scans run during maintenance or on demand. Node layout builds an adjacency map once. There is no per-frame Python handler; a file-load handler upgrades intact older effect groups and restores focus bindings once when opening a file. Enabling the extension queues one nonpersistent initialization callback so an already open file can be checked after Blender's registration restrictions end. It stops after one run and is cancelled on disable or superseded by a file load.

## Limits and troubleshooting

These are screen-space filters, not physically accurate optical blur or guaranteed flicker-free painted strokes. Coverage leaves the world background unchanged. Transparency, refraction, motion blur, antialiased silhouettes and overlapping geometry retain screen-space limitations. Incoming alpha is preserved, but that does not eliminate all color halos.

Use one configured view layer and matching image framing per scene. Combining different scenes/layers, transformed images, stereo views or cropped inputs requires manual compositor work. Camera focus-distance and lens keyframes, moving focus objects and focus-bone animation use Blender's native evaluation; render each frame after changing framing or geometry. Focal length changes framing, while focus distance controls the sharp plane. Automatic camera-marker rebinding is not implemented: sync after camera/target changes and configure cuts as separate shots/scenes where needed. Shader AOVs in the viewport compositor are not assumed; use full renders.

If the effect is missing, rerender after setup or a guide change, inspect the Focus Mask and Surface Guide previews, then use Check Setup and inspect the camera sync notice. Weak Bilateral smoothing often means a very low Threshold or high Depth Edges setting. Generated internal names can change once their persistent keys are present. Deleted/replaced nodes still require restoring the original node with its links/drivers, or removing and rebuilding the setup. Check Setup follows constant switch branches and native muted-node bypasses. Linked/animated switches and opaque user groups are reported as uncertain connections; inspect their final output. Guide errors remain visible when unrelated sliders change; brush loading reports success only after the guide hookup completes.

## Development and validation

See the [changelog](CHANGELOG.md) and [validation notes](docs/validation.md). Run these commands from the repository root. The source includes a background integration suite using Blender's bundled Python and NumPy:

```text
blender --background --factory-startup --python-exit-code 1 --python stylized_depth_of_field/tests/integration.py -- --work-dir ./test-output
```

Add `--legacy-dir PATH_TO_UNPACKED_V1` after the work directory to run migration against the original v1 package. Add `--eevee` to include Eevee render checks on a machine with a supported graphics device. Pass `--previous-blend PATH_TO_V1_1_0_BLEND` to check a direct 1.1.0 saved-file upgrade. All test outputs use the resolved work directory. The suite uses disposable factory scenes; it does not save preferences or install add-ons.

Build and validate the install ZIP with Python 3.11+ and Blender 5.2:

```text
python scripts/build_release.py --blender blender
```

Pass the full path to the Blender executable if it isn't on your PATH. The ZIP goes into `dist/`.

For deterministic three-mode and Defocus compositor timings, run `stylized_depth_of_field/tests/performance.py` in background with `--threads 8` and `--work-dir ./performance-output`. It uses full-frame image inputs with a minimal Workbench carrier; its timings do not predict whole-scene render times.

The source also contains `stylized_depth_of_field/tests/event_loop.py`. Run it without `--background`, using `--factory-startup --python stylized_depth_of_field/tests/event_loop.py -- --work-dir ./event-loop-output`, to verify deferred initialization and native undo snapshots. The timer harness explicitly pushes snapshots; it does not automate clicking panel buttons. Pass `--previous-blend PATH_TO_OLDER_BLEND` to also test the deferred upgrade of a file opened before enabling. It closes its disposable Blender session automatically.

Relevant Blender references: [compositor migration/API changes](https://developer.blender.org/docs/release_notes/5.0/migration/compositor_migration/), [Bilateral Blur](https://docs.blender.org/manual/en/latest/compositing/types/filter/blur/bilateral_blur.html), [Kuwahara](https://docs.blender.org/manual/en/latest/compositing/types/creative/kuwahara.html), [native UI layout API](https://docs.blender.org/api/current/bpy.types.UILayout.html).

License: [GNU GPL v3 or later](LICENSE).
