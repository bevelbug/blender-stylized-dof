"""Native Blender panels and offline help; no timers or saved UI settings."""
import textwrap

import bpy
from bpy.props import EnumProperty, StringProperty
from bpy.types import Operator

from . import core, migration, nodes


HELP_TOPICS = {
    'START': ("Getting Started", (
        ("Build once, then render", "Choose Cycles or Eevee, set the scene camera and assign node materials. Choose a material scope and click Build Setup. Render with F12 to generate the depth and surface guide data used by the effect."),
        ("Find your focus", "Start with Bilateral, Starter Patches and a radius around 5 px. Choose Preview > Focus Mask: black stays sharp, white receives the maximum effect. Adjust focus and falloffs, then return to Final Effect."),
        ("Adjust without rebuilding", "Effect and focus controls can update an existing full render in the Compositor. Guide placement, materials, geometry and camera movement need a new render. Add / Refresh Materials handles newly imported materials."),
        ("Hover for explanations", "Hover a control to see its Blender tooltip. Tooltip visibility and delay follow Blender's own preferences. Numeric controls, Foreground, Background and Enable Effect can be keyframed using the usual Blender controls."),
    )),
    'FOCUS': ("Focus", (
        ("Camera or manual distance", "Camera Focus uses the active scene camera's focus distance or focus object/bone, even with optical DOF off. Manual Distance places the sharp plane at a distance along the camera's viewing axis. Focus Offset shifts either plane; positive values move it farther away."),
        ("A sharp zone with a gradual transition", "Sharp Half-width keeps that distance on each side of the focus plane fully sharp. Foreground and Background choose which side receives the effect. Each falloff is the additional distance beyond the sharp zone needed to reach maximum effect; larger values make a gentler transition."),
        ("Changing the target", "Choose a Focus Object in this panel or the camera's data settings. After changing or deleting the camera, focus object or bone, use Sync Active Camera or Refresh Materials. A deleted object falls back to the camera distance on sync/refresh; a missing bone must be corrected first. Bound animation follows through native drivers. Use one camera per scene."),
        ("Optical DOF", "If the camera's optical DOF is enabled, the extension stylizes an already blurred render. Disable optical DOF in the camera settings for painterly focus alone. The world background is left unchanged."),
    )),
    'GUIDE': ("Surface Guides", (
        ("A guide, rather than painted pixels", "Bilateral uses a surface pattern to decide where smoothing can cross boundaries. The pattern is not stamped onto the image. Starter Patches are procedural and need no external file. Kuwahara follows rendered image edges and ignores the surface guide."),
        ("UV or Generated", "Use UV for animated or deforming surfaces, with an active render UV map on each mesh. Missing UVs produce a flat guide and appear in the Setup Report. Generated mapping suits static props; changing bounds or deformation can make its pattern move."),
        ("Brush images and portability", "Load Brush Image loads a separate Non-Color image. Pack Loaded Image embeds it in the blend when you save. Direct selection of an existing image keeps its color space and packing. An empty image choice falls back to Starter Patches. Prefer tileable images."),
        ("Placement and boundaries", "Higher Tile U/V values make smaller patches; higher V than U elongates starter patches horizontally. Rotation changes their direction. Rerender after placement changes. In Advanced, Guide Weight weights pattern boundaries, Threshold controls tolerance, and Depth Edges protects depth differences."),
    )),
    'PERFORMANCE': ("Quality & Performance", (
        ("Stronger defocus", "Defocus adds mask-driven softness before the selected painterly filter. Zero preserves the previous look; try 4 to 8 pixels for stronger loss of detail. The sharp zone and incoming alpha are retained. Strength still controls the final blend; Radius zero bypasses the entire effect."),
        ("Paint Filter", "Paint Filter uses Pau Homs' Blender Essentials asset, bundled locally under CC0. Stroke Size sets its uniform screen-space size; the focus mask blends it into the image. Simplification removes more detail. Edge Breakup and depth protection are in Advanced. The surface guide is used only by Bilateral."),
        ("Position tracking", "Advanced > Position Tracking uses native Position and Depth passes on the configured layer; render again after enabling it. It maps brush patterns through world positions, which can help with camera movement and different object sizes. Objects moving or deforming through that space can still move through the strokes; this is not deformation tracking or guaranteed flicker removal. Passes added by the add-on are released when tracking is unused, unless your compositor also uses them."),
        ("Start small", "Radius is measured in output pixels. Larger radii and larger renders increase filtering cost. Zero strength, zero radius and a disabled effect pass through the original image and reduce filter work. Render data and compositor overhead still have a cost."),
        ("Compositor device", "Advanced > Compositor uses Blender's native CPU/GPU choice for this scene. Try GPU for large images on supported hardware. Availability and speed depend on Blender and your device. Setup and refresh preserve this choice; compare your final renders before switching a production job."),
        ("Bilateral quality", "Advanced > Quality offers Balanced, with two filter sizes for a smoother focus transition, and Fast, with one filter pass and a different transition. Use Fast when you need a lower filtering cost. Actual speed depends on Blender, resolution and hardware."),
        ("Render data", "AOVs are extra render outputs carrying surface guide, depth and coverage. Use a full F12 render for these outputs; viewport compositor support is not assumed. The configured view layer is listed in Setup & Maintenance."),
        ("Keep final renders on Final Effect", "Focus Mask and Surface Guide previews also change the saved render output. Return to Preview > Final Effect before producing a final image or animation. There are no per-frame Python handlers."),
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
        layout.prop(s, 'radius', text="Stroke Size (px)" if s.method == 'PAINT' else "Radius (px)")
        layout.prop(s, 'defocus')
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
            if s.method == 'BILATERAL':
                body.prop(s, 'quality')
                body.separator()
                body.prop(s, 'texture_influence', text="Guide Weight")
                body.prop(s, 'threshold', text="Threshold")
                body.prop(s, 'edge_protection', text="Depth Edges")
            elif s.method == 'PAINT':
                body.prop(s, 'paint_edge_breakup')
                body.prop(s, 'edge_protection', text="Depth Edges")
                body.prop(s, 'paint_tracking')
                if s.paint_tracking:
                    paragraph(body, 'Tracking needs a new F12 render after enabling.', width, 'INFO')

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
