"""Native Blender panels and offline help; no timers or saved UI settings."""
import textwrap

import bpy
from bpy.props import EnumProperty, StringProperty
from bpy.types import Operator

from . import core, migration, nodes


HELP_TOPICS = {
    'LOOKS': ("Paint & Bokeh", (
        ("Brush styles", "Paint Filter offers Watercolor, Oil Paint and Digital Geometric patterns from the bundled Blender Essentials asset. Brush Sharpness controls how closely shapes follow that pattern. Color Variation shifts hue between strokes; Pigment Pooling darkens their edges. Start with small changes."),
        ("Canvas", "Canvas and Rough Paper add surface grain and drive Edge Breakup. Texture Amount controls the visible overlay; zero keeps the breakup. None removes the canvas pattern. Texture Scale changes grain frequency. Keep seeds fixed during animation. Custom images are reserved for a later version."),
        ("Defocus shape", "Defocus Shape selects the additional blur before painting. Soft / Fast preserves the original Gaussian result. Round Bokeh uses a circular aperture; Aperture Bokeh exposes blade count, rotation and roundness. Raise Defocus above zero to see it. Painting can reshape the blurred highlights afterward."),
        ("Blur limits", "Large aperture blur costs more. This compositor effect cannot recover hidden background behind a foreground silhouette and may show edge bleeding. Camera optical DOF can stay off; camera focus animation still drives the focus plane."),
    )),
    'BLOOM': ("Bloom & Animation", (
        ("Highlight glow", "Enable Bloom for an additive glow over the painted result. Soft makes a smooth glow. Stepped Paint divides only the glow into brightness bands, preserving its hue and HDR range. Amount controls intensity, Spread controls reach, and Highlight Threshold chooses which scene-linear highlights contribute."),
        ("Bigger, visible glow", "Spread controls spatial reach; its full 0 to 1 range is available. Broad glow from small highlights can be faint. Glow Exposure boosts it before stepping: try +2 to +5 stops. Falloff below 1 lifts the faint outer tail; try 0.5 to 0.8. Amount controls final intensity after stepping. Scene size does not directly set the halo size."),
        ("Painted bands", "Use Preview Bloom Only to see the added glow on black. Band Density sets levels per brightness stop: try 2 to 4 for broad bands, then use Glow Exposure to place them. Edge Softness blends transitions; 0.3 to 0.6 is a useful range, with softer edges safer for motion. Painterly Breakup adds fixed irregularity. Soft mode ignores band and texture controls."),
        ("Motion and tracking", "Position Tracking anchors breakup in world space on static surfaces. Render again after enabling it. Empty background uses screen coordinates. Moving or deforming objects can slide through the texture, and hard bands or noisy highlights can still flicker. Use a fixed seed and test a short animation before a long render."),
        ("Scope and alpha", "Bloom affects highlights across the image, including the focused subject, and works even with painterly Radius or Strength zero. Enable Effect off bypasses everything; Amount zero bypasses bloom. Original alpha is preserved, so transparent areas can hide a halo in the final composite. Bloom Only is opaque for inspection and changes saved output: return to Final Effect before final rendering."),
    )),
    'START': ("Getting Started", (
        ("Build once, then render", "Choose Cycles or Eevee, set the scene camera and assign node materials. Choose a material scope and click Build Setup. Render with F12 to generate the depth and surface guide data used by the effect."),
        ("Find your focus", "Start with Bilateral, Starter Patches and a radius around 5 px. Choose Preview > Focus Mask: black stays sharp, white receives the maximum effect. Adjust focus and falloffs, then return to Final Effect."),
        ("Adjust without rebuilding", "Effect and focus controls can update an existing full render in the Compositor. Guide placement, materials, geometry and camera movement need a new render. Add / Refresh Materials handles newly imported materials."),
        ("Hover for explanations", "Hover a control to see its Blender tooltip. Tooltip visibility and delay follow Blender's own preferences. Numeric controls, Foreground, Background and Enable Effect can be keyframed using the usual Blender controls."),
    )),
    'FOCUS': ("Focus", (
        ("Camera or manual distance", "Camera Focus uses the active scene camera's focus distance or focus object/bone, even with optical DOF off. Manual Distance places the sharp plane at a distance along the camera's viewing axis. Focus Offset shifts either plane; positive values move it farther away."),
        ("A sharp zone with a gradual transition", "Sharp Half-width keeps that distance on each side of the focus plane fully sharp. Foreground and Background choose which side receives the effect. Each falloff is the additional distance beyond the sharp zone needed to reach maximum effect; larger values make a gentler transition."),
        ("Changing the target", "Choose a Focus Object in this panel or the camera's data settings. Native camera nodes follow camera, target and bone changes automatically where supported. A driver fallback remains available on other builds; Sync Active Camera or Refresh repairs that binding after source changes. A missing bone must be corrected. Use one camera per scene."),
        ("Optical DOF", "If the camera's optical DOF is enabled, the extension stylizes an already blurred render. Disable optical DOF in the camera settings for painterly focus alone. Painterly focus leaves the world background unchanged; optional bloom can affect highlights anywhere in the image."),
    )),
    'GUIDE': ("Surface Guides", (
        ("A guide, rather than painted pixels", "Bilateral uses a surface pattern to decide where smoothing can cross boundaries. The pattern is not stamped onto the image. Starter Patches are procedural and need no external file. Kuwahara follows rendered image edges and ignores the surface guide."),
        ("UV or Generated", "Use UV for animated or deforming surfaces, with an active render UV map on each mesh. Missing UVs produce a flat guide and appear in the Setup Report. Generated mapping suits static props; changing bounds or deformation can make its pattern move."),
        ("Brush images and portability", "Load Brush Image loads a separate Non-Color image. Pack Loaded Image embeds it in the blend when you save. Direct selection of an existing image keeps its color space and packing. An empty image choice falls back to Starter Patches. Prefer tileable images."),
        ("Placement and boundaries", "Higher Tile U/V values make smaller patches; higher V than U elongates starter patches horizontally. Rotation changes their direction. Rerender after placement changes. In Advanced, Guide Weight weights pattern boundaries, Threshold controls tolerance, and Depth Edges protects depth differences."),
    )),
    'PERFORMANCE': ("Quality & Performance", (
        ("Stronger defocus", "Defocus adds mask-driven softness before painting. Zero preserves the previous look; try 4 to 8 pixels. The sharp zone and alpha are retained. Strength or Radius zero bypasses painting while optional bloom remains available. Enable Effect off bypasses everything."),
        ("Resolution scaling", "Advanced > Scale with Resolution keeps filter/stroke and Defocus size proportional to the actual input image width. Reference Width 1920 means a 3840-wide image uses twice the pixel radius. Render percentage and upstream image sizes are respected. Leave it off for fixed pixel sizes. Bloom Spread is already relative to the image."),
        ("Paint Filter", "Paint Filter uses Pau Homs' Blender Essentials asset, bundled locally under CC0. Stroke Size sets its uniform screen-space size; the focus mask blends it into the image. Simplification removes more detail. Brush and Canvas contain the style controls; depth protection is in Advanced. The surface guide is used only by Bilateral."),
        ("Position tracking", "Brush > Position Tracking uses native Position and Depth passes on the configured layer; render again after enabling it. It maps brush patterns through world positions, which can help with camera movement and different object sizes. Objects moving or deforming through that space can still move through the strokes; this is not deformation tracking or guaranteed flicker removal. Passes are shared with optional bloom tracking and released when unused, unless your compositor also uses them."),
        ("Start small", "Radius is measured in output pixels, or reference pixels when resolution scaling is on. Larger radii and renders cost more. Zero strength/radius reduces painterly filtering; zero bloom Amount skips glow. Enable Effect off passes through the original image. Render data and compositor overhead still have a cost."),
        ("Compositor device", "Advanced > Compositor uses Blender's native CPU/GPU choice for this scene. Try GPU for large images on supported hardware. Availability and speed depend on Blender and your device. Setup and refresh preserve this choice; compare your final renders before switching a production job."),
        ("Bilateral quality", "Advanced > Quality offers Balanced, with two filter sizes for a smoother focus transition, and Fast, with one filter pass and a different transition. Use Fast when you need a lower filtering cost. Actual speed depends on Blender, resolution and hardware."),
        ("Render data", "AOVs are extra render outputs carrying surface guide, depth and coverage. Use a full F12 render for these outputs; viewport compositor support is not assumed. The configured view layer is listed in Setup & Maintenance."),
        ("Keep final renders on Final Effect", "Focus Mask, Surface Guide and Bloom Only previews also change saved output. Return to Preview > Final Effect before producing a final image or animation. There are no per-frame Python handlers."),
    )),
    'TROUBLE': ("Troubleshooting", (
        ("Missing or weak effect", "Enable the effect, choose Final Effect and use a nonzero radius and strength. Render again after building or changing the guide. Check Focus Mask for the sharp zone, and Surface Guide for missing patterns. If Bilateral is too weak, raise Threshold or reduce Depth Edges in Advanced."),
        ("Check the setup", "Setup & Maintenance > Check Setup inspects focus, controls, passes, compositor status, brush files and materials without changing the setup. If scene compositing is off, use Enable Compositing. A disconnected saved setup offers compositor restoration where possible; the alternative compositor remains available."),
        ("New materials or missing passes", "Use Add / Refresh Materials, then rerender. Scans use the configured view layer, its material override, original slots, evaluated geometry and instances at the current frame. Render-only Geometry Nodes can assign materials absent from the scan: enable those modifiers in the viewport before Refresh, or add their render materials to the original slots. Setup Report records the last scan; Check Setup inspects the current state."),
        ("Saved files and copied scenes", "Existing 1.1 setups open directly. For an original v1 setup, disable the old add-on and reopen the file, then use Migrate Saved Setup. A copied scene may need Detach Shared Setup before building its own effect. Finish Cleanup retries an interrupted legacy cleanup."),
        ("Repair or remove", "Check Setup names muted generated nodes. Unmute them in the node editor, then Refresh Materials and rerender. Deleted or replaced generated nodes may require restoring the original node and its links/drivers, or removing and rebuilding. Remove Setup preserves user shader/compositor edits and loaded images, and supports Blender Undo."),
        ("Practical limits", "This is a screen-space painterly filter. Transparency, refraction, silhouettes and motion blur can show artifacts, and animated strokes are not guaranteed to be flicker-free. Use one configured view layer and matching image framing per scene."),
    )),
}


def paragraph(layout, text, width=76, icon='NONE'):
    """Wrap plain help/status text; labels have no automatic word wrapping."""
    for index, line in enumerate(textwrap.wrap(text, width) or [""]):
        layout.label(text=line, icon=icon if index == 0 else 'NONE')


def panel_width(context):
    region = getattr(context, 'region', None)
    scale = context.preferences.system.ui_scale
    return max(24, min(80, int((region.width / scale - 40) / 7))) if region else 42


def section(layout, identifier, title, icon='NONE', closed=False):
    header, body = layout.panel(identifier, default_closed=closed)
    header.label(text=title, icon=icon)
    return body


class SDOF_OT_help(Operator):
    bl_idname = "sdof.help"
    bl_label = "Stylized Depth of Field Help"
    bl_description = "Read offline setup, focus, brush guide, performance and troubleshooting advice"
    topic: EnumProperty(name="Topic", description="Choose a help topic", options={'SKIP_SAVE'},
                        items=[(key, value[0], "Read about " + value[0].lower())
                               for key, value in HELP_TOPICS.items()], default='START')

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=600)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Stylized Depth of Field", icon='HELP')
        layout.prop(self, 'topic')
        for title, text in HELP_TOPICS[self.topic][1]:
            layout.separator()
            layout.label(text=title)
            paragraph(layout, text)


class SDOF_OT_report(Operator):
    bl_idname = "sdof.report"
    bl_label = "Setup Report"
    bl_description = "Read the most recent build or refresh report, including skipped materials and missing UV maps"

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=650)

    def draw(self, context):
        self.layout.label(text="Setup Report", icon='INFO')
        paragraph(self.layout, 'Last build or refresh. Use Check Setup for current diagnostics.', width=82)
        text = context.scene.sdof.last_report or "Build a setup to see the material report."
        for line in text.splitlines():
            paragraph(self.layout, line, width=82)


class SDOF_OT_check(Operator):
    bl_idname = 'sdof.check'
    bl_label = 'Check Setup'
    bl_description = 'Inspect focus, generated controls, render passes, compositor status, materials and brush files without changing the setup'
    result: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        self.result = core.health_report(context)
        self.report({'INFO'}, self.result.splitlines()[0])
        return {'FINISHED'}

    def invoke(self, context, event):
        self.result = core.health_report(context)
        return context.window_manager.invoke_popup(self, width=650)

    def draw(self, context):
        self.layout.label(text='Setup Check', icon='INFO')
        for line in self.result.splitlines():
            paragraph(self.layout, line, width=82)


class SDOF_OT_bloom_preview(Operator):
    bl_idname = 'sdof.preview_bloom'
    bl_label = 'Preview Bloom'
    bl_description = 'Toggle isolated glow on black to see its bands and reach. This changes saved render output too; return to Final Effect for final renders'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            core.check_owner(context.scene)
            s = context.scene.sdof
            s.preview = 'RESULT' if s.preview == 'BLOOM' else 'BLOOM'
            if s.last_error:
                self.report({'ERROR'}, s.last_error)
                return {'CANCELLED'}
            return {'FINISHED'}
        except RuntimeError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


def draw_panel(layout, context):
    scene, s = context.scene, context.scene.sdof
    ready, width = core.installed(scene), panel_width(context)
    layout.use_property_split = True
    layout.use_property_decorate = True
    row = layout.row(align=True)
    row.use_property_split = False
    row.use_property_decorate = False
    if ready and not core.foreign_setup(scene):
        row.prop(s, 'enabled')
    else:
        row.label(text="Painterly focus")
    row.operator('sdof.help', text="Help", icon='HELP')

    if s.last_error:
        box = layout.box()
        box.label(text="Setup needs attention", icon='ERROR')
        paragraph(box, s.last_error, width)
    if migration.has_legacy(scene):
        if not s.token:
            paragraph(layout, "A saved setup is ready to migrate.", width, 'INFO')
            layout.operator('sdof.migrate', icon='FILE_REFRESH')
            return
        paragraph(layout, "Older setup cleanup remains.", width, 'INFO')
        layout.operator('sdof.migrate', text="Finish Cleanup", icon='FILE_REFRESH')
    if core.foreign_setup(scene):
        paragraph(layout, "This scene shares another scene's setup. Detach it to edit independently.", width, 'INFO')
        layout.operator('sdof.detach', icon='UNLINKED')
        return

    if s.token and not core.output_connected(scene):
        paragraph(layout, 'Saved setup is disconnected from the active output.', width, 'ERROR')
        if scene.compositing_node_group != s.tree and s.tree and core.output_connected(scene, s.tree):
            layout.operator('sdof.restore_compositor', icon='FILE_REFRESH')
        else:
            paragraph(layout, 'Restore the compositor output links, or remove the setup before rebuilding.', width)
    if s.token and not scene.render.use_compositing:
        paragraph(layout, 'Scene compositing is off. Renders bypass the effect.', width, 'INFO')
        layout.operator('sdof.enable_compositing', icon='RENDER_STILL')

    if not s.token:
        paragraph(layout, "Build once, then render with F12.", width, 'INFO')
        layout.prop(s, 'scope')
        layout.operator('sdof.setup', icon='NODETREE')
    else:
        layout.prop(s, 'method')
        if s.method == 'PAINT':
            layout.prop(s, 'paint_style')
        units = ' (ref px)' if s.scale_with_resolution else ' (px)'
        layout.prop(s, 'radius', text=("Stroke Size" if s.method == 'PAINT' else "Radius") + units)
        layout.prop(s, 'defocus', text='Defocus' + units)
        if s.defocus > 0:
            layout.prop(s, 'protect_focus_edges')
        if s.method == 'PAINT':
            layout.prop(s, 'paint_simplification')
        layout.prop(s, 'strength', slider=True)
        layout.prop(s, 'preview')
        if s.preview != 'RESULT':
            paragraph(layout, "Preview also changes saved renders. Return to Final Effect when finished.", width, 'INFO')
        if not s.enabled:
            paragraph(layout, "Effect bypassed: original image output.", width, 'INFO')

    body = section(layout, 'sdof_focus', "Focus", 'CAMERA_DATA')
    if body:
        body.prop(s, 'focus_mode')
        if s.focus_mode == 'MANUAL':
            body.prop(s, 'manual_focus', text="Distance")
        elif scene.camera and scene.camera.type == 'CAMERA':
            paragraph(body, "Camera: " + scene.camera.name, width)
            dof = scene.camera.data.dof
            body.prop(dof, 'focus_object', text="Focus Object")
            if dof.focus_object:
                if dof.focus_subtarget:
                    paragraph(body, "Bone: " + dof.focus_subtarget, width)
            else:
                body.prop(dof, 'focus_distance', text="Distance")
            status = nodes.focus_status(s.effect_tree, scene) if s.effect_tree else ''
            if s.effect_tree and nodes.camera_focus.active(s.effect_tree):
                paragraph(body, 'Focus follows native camera data.', width)
            if status:
                paragraph(body, status, width, 'INFO')
                body.operator('sdof.sync_camera', icon='FILE_REFRESH')
            if dof.use_dof:
                paragraph(body, "Optical DOF is also enabled on the camera.", width, 'INFO')
        else:
            paragraph(body, "Choose an active scene camera.", width, 'INFO')
        body.prop(s, 'sharp_width', text="Half-width")
        body.prop(s, 'focus_offset', text="Offset")
        row = body.row(align=True)
        row.use_property_split = False
        row.prop(s, 'near_enabled', toggle=True)
        row.prop(s, 'far_enabled', toggle=True)
        col = body.column()
        col.active = s.near_enabled
        col.prop(s, 'near_falloff', text="Near Falloff")
        col = body.column()
        col.active = s.far_enabled
        col.prop(s, 'far_falloff', text="Far Falloff")

    if ready:
        body = section(layout, 'sdof_aperture', "Defocus Shape", 'CAMERA_DATA', closed=True)
        if body:
            body.prop(s, 'bokeh_shape')
            if s.bokeh_shape == 'POLYGON':
                body.prop(s, 'bokeh_blades')
                body.prop(s, 'bokeh_rotation')
                body.prop(s, 'bokeh_roundness', slider=True)
            if s.defocus == 0:
                paragraph(body, "Raise Defocus to see the blur shape.", width, 'INFO')

        if s.method == 'PAINT':
            body = section(layout, 'sdof_brush', "Brush", 'BRUSH_DATA', closed=True)
            if body:
                body.prop(s, 'paint_sharpness', slider=True)
                body.prop(s, 'paint_colors', slider=True)
                body.prop(s, 'paint_pooling', slider=True)
                body.prop(s, 'paint_seed')
                body.prop(s, 'paint_tracking')
                if s.paint_tracking:
                    paragraph(body, "Tracking needs a new F12 render after enabling.", width, 'INFO')
            body = section(layout, 'sdof_canvas', "Canvas", 'TEXTURE', closed=True)
            if body:
                body.prop(s, 'paint_canvas')
                col = body.column()
                col.active = s.paint_canvas != 'NONE'
                col.prop(s, 'paint_canvas_amount', slider=True)
                col.prop(s, 'paint_canvas_scale')
                col.prop(s, 'paint_edge_breakup')

        header, body = layout.panel('sdof_bloom', default_closed=True)
        header.prop(s, 'bloom_enabled')
        if body:
            col = body.column()
            col.active = s.bloom_enabled
            col.prop(s, 'bloom_style')
            col.operator('sdof.preview_bloom', text='Back to Final Effect' if s.preview == 'BLOOM' else 'Preview Bloom Only', icon='HIDE_OFF')
            col.prop(s, 'bloom_amount')
            col.prop(s, 'bloom_spread', slider=True)
            col.prop(s, 'bloom_exposure')
            col.prop(s, 'bloom_falloff')
            col.prop(s, 'bloom_threshold')
            if s.bloom_style == 'STEPPED':
                col.prop(s, 'bloom_steps')
                col.prop(s, 'bloom_softness', slider=True)
                col.prop(s, 'bloom_breakup', slider=True)
                detail = section(col, 'sdof_bloom_texture', "Texture", closed=True)
                if detail:
                    detail.prop(s, 'bloom_texture_scale')
                    detail.prop(s, 'bloom_seed')
                    detail.prop(s, 'bloom_tracking')
                    if s.bloom_tracking:
                        paragraph(detail, "Static world-space tracking. Rerender after enabling.", width, 'INFO')
            if s.preview == 'BLOOM':
                paragraph(body, 'Showing glow on black. Return to Final Effect before final rendering.', width, 'INFO')
            if scene.render.film_transparent:
                paragraph(body, 'Final output preserves alpha; transparent areas can hide the halo. Bloom Only shows the full glow.', width, 'INFO')

    if s.method == 'BILATERAL':
        body = section(layout, 'sdof_guide', "Surface Guide", 'TEXTURE', closed=True)
        if body:
            body.prop(s, 'guide_source')
            if s.guide_source == 'IMAGE':
                body.template_ID(s, 'brush_image')
                body.prop(s, 'pack_image')
                body.operator('sdof.load_brush', icon='FILE_FOLDER')
                if not s.brush_image:
                    paragraph(body, "No image: using Starter Patches.", width, 'INFO')
            body.prop(s, 'mapping')
            body.prop(s, 'tile_u')
            body.prop(s, 'tile_v')
            body.prop(s, 'texture_rotation')
            paragraph(body, "Guide changes need a new render.", width, 'INFO')
    if ready:
        body = section(layout, 'sdof_advanced', "Advanced", 'PREFERENCES', closed=True)
        if body:
            body.prop(scene.render, 'compositor_device', text="Compositor")
            body.prop(s, 'scale_with_resolution')
            if s.scale_with_resolution:
                body.prop(s, 'reference_width')
            if s.method == 'BILATERAL':
                body.prop(s, 'quality')
                body.separator()
                body.prop(s, 'texture_influence', text="Guide Weight")
                body.prop(s, 'threshold', text="Threshold")
                body.prop(s, 'edge_protection', text="Depth Edges")
            elif s.method == 'PAINT':
                body.prop(s, 'edge_protection', text="Depth Edges")

    if ready or s.token:
        body = section(layout, 'sdof_maintenance', "Setup & Maintenance", 'TOOL_SETTINGS', closed=True)
        if body:
            paragraph(body, "Configured layer: " + s.layer_name, width)
            body.prop(s, 'scope')
            body.operator('sdof.refresh', icon='FILE_REFRESH')
            if ready and s.focus_mode == 'CAMERA':
                body.operator('sdof.sync_camera', icon='FILE_REFRESH')
            body.operator('sdof.report', icon='INFO')
            body.operator('sdof.check', icon='CHECKMARK')
            body.separator()
            body.operator('sdof.remove', icon='X')
    layout.separator()
    paragraph(layout, "Render with F12 after setup or guide changes.", width, 'RENDER_STILL')
