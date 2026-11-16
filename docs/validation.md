# Validation — 2.1.1

Checked on Windows with Blender 5.2.0 LTS (fbe6228777e7) and 5.3.0 (02f0899d78e3). The source suites passed **1,137 assertions**: 311 integration/recovery checks per Blender version, 98 focus-edge checks per version, 91 native-focus/sizing/bloom checks per version, and 137 optional-effects checks on 5.2. Counts include finite-render and repeated-frame assertions. Details are in [test-results.json](test-results.json).

## Focus-edge correction

Native compositor renders compare protection on/off for Bilateral, Kuwahara and Paint Filter, each with Gaussian, round and polygon blur. In a controlled HDR red-subject/blue-background fixture, the measured red halo outside the sharp silhouette falls by more than 99% in every combination. The fully sharp region matches the input within 0.00001, and incoming alpha is preserved.

Additional fixtures cover antialiased curved silhouettes, a narrow sharp stem, varied alpha, and Defocus values of 8, 32 and 64. Fully sharp and fully defocused masks remain unchanged. Defocus zero matches protection off within 0.00001. CPU/GPU reference renders agree with a mean difference below 0.002. Moving silhouettes repeat deterministically in arbitrary order. These are selected synthetic tests, not a guarantee for all transparent, motion-blurred or subpixel geometry.

The extension uses existing focus/coverage data and native Inpaint/Dilate nodes; it does not add shader AOVs, render callbacks, temporal history or external dependencies. The protected source is used by the blur and subsequent painterly filter, while the final blend retains the original sharp image. Protection off restores the previous filtering path. Defocus zero bypasses the added processing. Active protection adds an image-extension operation; the patch does not claim zero overhead.

## Animation, bloom and upgrades

Camera focus-distance and lens keys, off-axis focus targets, rotated/scaled cameras, bone animation, camera/target replacement, manual focus and the fallback driver path pass. 1080p/4K sizing, broad bloom, bloom keyframes, alpha preservation and independent bloom enable/bypass remain covered. Bloom calculations and controls are unchanged; their image input can naturally differ when edge protection changes the painterly result.

Real older saved graphs upgrade in place. An explicit v2.1 schema-5 fixture upgrades to schema 6 and validates; rolling back a staged upgrade restores the original nodes, links, drivers and version. Saved edge controls survive reopening without changing the rendered result. The older v2 fixture comparison disables edge protection to isolate unchanged bloom behavior. Schema-6 files need 2.1.1 or newer to edit their generated setup.

A repaired production room scene also rendered in Blender 5.3 at 1920 × 1080 with Cycles OptiX, CPU denoising, GPU compositing, and Lens Optics Lite 1.5.0 registered alongside the extension. Protection on/off comparisons used the same shot and settings. No original project, installed extension or personal preferences were overwritten. This does not validate the separate screenshot's source scene or a complete production animation.

## Limits

Background extension estimates nearby visible colors; it cannot reconstruct hidden scenery. Extreme blur, large depth discontinuities, partial transparency, reflections and very thin details can still show artifacts. Bloom intentionally spreads highlights independently. World-position brush tracking is not deformation tracking for Alembic objects.

The earlier room's GPU failure involving material AOVs and emissive light sampling is a separate issue. This patch keeps material setup unchanged; it does not remove the need for an already established scene workaround. Other operating systems, GPU vendors and Blender versions remain unverified. Deliberate fault-injection errors in test logs are expected.
