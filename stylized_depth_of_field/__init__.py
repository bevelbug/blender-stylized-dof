"""Stylized Depth of Field 1.3.0 — Blender 5.2 extension."""
import os
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup
from bpy_extras.io_utils import ImportHelper
from . import nodes as ng
from . import core
from . import migration
from .transaction import Journal
from .ui import draw_panel, SDOF_OT_help, SDOF_OT_report, SDOF_OT_check
from bpy.app.handlers import persistent

TAG, ROLE = ng.TAG, ng.ROLE
owned, effect_instance, installed, check_owner = core.owned, core.effect_instance, core.installed, core.check_owner


def _update(self, shader=False, structure=False, focus=False):
    scene = self.id_data
    if not isinstance(scene, bpy.types.Scene) or core.suspended(scene):
        return
    try:
        check_owner(scene)
        if shader and self.shader_tree:
            if structure:
                ng.update_shader(self.shader_tree, self)
            else:
                ng.validate_controls(self.shader_tree, scene, shader=True)
            self.shader_tree.update_tag()
        if not shader and self.effect_tree:
            if focus:
                ng.bind_focus(self.effect_tree, scene)
            elif structure:
                journal = Journal()
                try:
                    ng.update_effect(self.effect_tree, self, journal)
                    if self.tree:
                        core.sync_paint_tracking(scene, journal)
                    journal.commit()
                except Exception:
                    journal.rollback()
                    raise
            else:
                ng.validate_controls(self.effect_tree, scene)
            self.effect_tree.update_tag()
        scene.update_tag()
        if shader and structure:
            core.clear_error(self, 'GUIDE')
        elif focus:
            core.clear_error(self, 'FOCUS')
        elif structure:
            core.clear_error(self, 'EFFECT')
    except (ReferenceError, KeyError, RuntimeError, TypeError, AttributeError) as exc:
        core.set_error(self, exc, 'GUIDE' if shader else 'FOCUS' if focus else 'EFFECT')


def update_values(self, context):
    _update(self)


def update_shader_values(self, context):
    _update(self, shader=True)


def update_shader_controls(self, context):
    _update(self, shader=True, structure=True)


def update_controls(self, context):
    _update(self, structure=True)


def update_enabled(self, context):
    _update(self)


def update_focus(self, context):
    _update(self, focus=True)


class SDOF_Settings(PropertyGroup):
    token: StringProperty(options={"HIDDEN"})
    tree: PointerProperty(type=bpy.types.NodeTree)
    backup_tree: PointerProperty(type=bpy.types.NodeTree)
    effect_tree: PointerProperty(type=bpy.types.NodeTree)
    shader_tree: PointerProperty(type=bpy.types.NodeTree)
    bound_camera: PointerProperty(type=bpy.types.Object)
    bound_target: PointerProperty(type=bpy.types.Object)
    bound_bone: StringProperty()
    layer_name: StringProperty()
    original_compositing: BoolProperty(default=True)
    paint_depth_added: BoolProperty(options={'HIDDEN'})
    paint_position_added: BoolProperty(options={'HIDDEN'})
    last_error: StringProperty()
    error_source: StringProperty(options={"HIDDEN"})
    last_report: StringProperty()
    enabled: BoolProperty(name="Enable Effect", default=True, update=update_enabled,
                         description="Enable painterly focus. Turn off to pass through the original image; can be keyframed")
    scope: EnumProperty(name="Materials", items=[
        ("SCENE", "Entire Scene", "Existing materials on supported objects in the configured view layer"),
        ("SELECTED", "Selected Objects", "Existing materials on the selected objects; shared materials affect all their users")], default="SCENE", options=set(),
        description="Materials to process when building or refreshing. Changing this alone does not add or remove material branches")
    method: EnumProperty(name="Method", items=[
        ("BILATERAL", "Bilateral", "Smooth within surface brush patches while protecting depth boundaries"),
        ("KUWAHARA", "Kuwahara", "Anisotropic painterly smoothing from rendered image edges; ignores the surface brush guide"),
        ("PAINT", "Paint Filter", "Blender Essentials paint strokes with optional position/depth tracking; render again after enabling tracking")],
        default="BILATERAL", options=set(), update=update_controls,
        description="Bilateral follows surface guides, Kuwahara smooths image edges, and Paint Filter adds Blender Essentials brushwork")
    quality: EnumProperty(name="Quality", items=[
        ("BALANCED", "Balanced", "Two radius levels for a smoother focus transition"),
        ("FAST", "Fast", "One filter pass; transition blends directly with the original image")],
        default="BALANCED", options=set(), update=update_controls,
        description="Balanced uses two filter sizes for smoother focus transitions; Fast uses one pass to reduce filtering cost")
    preview: EnumProperty(name="Preview", items=[
        ("RESULT", "Final Effect", "Composited result; choose this before saving a final render"),
        ("FOCUS", "Focus Mask", "Black stays sharp; white receives maximum effect"),
        ("GUIDE", "Surface Guide", "Rendered brush AOV before depth protection; render again after changing the guide")], default="RESULT", options=set(), update=update_controls,
        description="Choose the final image or diagnostic render data. Preview selection also affects saved renders; return to Final Effect when finished")
    radius: FloatProperty(update=update_values, name="Radius (px)", default=5, min=0, max=64, soft_max=12,
                          description="Maximum filter radius or Paint stroke size in output pixels. Start around 5 px for Bilateral/Kuwahara, or 12–20 for Paint. Larger values cost more; zero bypasses the entire effect")
    strength: FloatProperty(update=update_values, name="Strength", default=1, min=0, max=1, subtype="FACTOR",
                            description="Blend the painterly result with the original image in out-of-focus areas. Zero keeps the original; one applies the full effect")
    defocus: FloatProperty(update=update_values, name="Defocus (px)", default=0, min=0, max=64, soft_max=16,
                          description="Additional focus-mask-driven softness before the painterly filter. Zero preserves the original look. Larger values remove detail and cost more; supports keyframes")
    paint_simplification: FloatProperty(update=update_values, name="Simplification", default=4, min=0, max=16, soft_max=8,
                                       description="Additional detail reduction inside Paint Filter. Zero disables its Kuwahara simplification; supports keyframes")
    paint_edge_breakup: FloatProperty(update=update_values, name="Edge Breakup", default=1, min=0, max=8, soft_max=3,
                                     description="Canvas-driven irregularity in Paint Filter edges. Start small for animation; supports keyframes")
    paint_tracking: BoolProperty(update=update_controls, name="Position Tracking", default=False,
                                description="Map Paint Filter strokes using native Position and Depth passes. Enables those passes on the configured layer; render again. World-space tracking does not lock strokes to deforming or moving objects")
    focus_mode: EnumProperty(name="Focus Source", items=[
        ("CAMERA", "Camera Focus", "Follow camera focus distance or its focus object"),
        ("MANUAL", "Manual Distance", "Use the distance below")], default="CAMERA", options=set(), update=update_focus,
        description="Use the scene camera's focus distance/object, or set a manual distance along its viewing axis")
    manual_focus: FloatProperty(update=update_values, name="Focus Distance", default=10, min=0.001, soft_max=100, subtype="DISTANCE", unit="LENGTH",
                                description="Distance from the camera to the sharp plane, measured along its viewing axis in scene units")
    focus_offset: FloatProperty(update=update_values, name="Focus Offset", default=0, soft_min=-10, soft_max=10, subtype="DISTANCE", unit="LENGTH",
                               description="Shift the sharp plane from the camera or manual focus distance. Positive moves it farther from the camera")
    sharp_width: FloatProperty(update=update_values, name="Sharp Half-width", default=0.25, min=0, soft_max=5, subtype="DISTANCE", unit="LENGTH",
                              description="Distance kept fully sharp on each side of the focus plane. The total sharp zone is twice this width")
    near_enabled: BoolProperty(name="Foreground", default=True, update=update_values,
                              description="Apply painterly focus to geometry nearer than the sharp zone. Turn off for background-only stylization")
    far_enabled: BoolProperty(name="Background", default=True, update=update_values,
                             description="Apply painterly focus to geometry farther than the sharp zone. The world background is left unchanged")
    near_falloff: FloatProperty(update=update_values, name="Foreground Falloff", default=2, min=0.001, soft_max=20, subtype="DISTANCE", unit="LENGTH",
                                description="Distance from the near edge of the sharp zone to maximum effect. Larger values make a gentler foreground transition")
    far_falloff: FloatProperty(update=update_values, name="Background Falloff", default=4, min=0.001, soft_max=40, subtype="DISTANCE", unit="LENGTH",
                               description="Distance from the far edge of the sharp zone to maximum effect. Larger values make a gentler background transition")
    guide_source: EnumProperty(name="Source", items=[
        ("PROCEDURAL", "Starter Patches", "Procedural surface mapped patches; no external image needed"),
        ("IMAGE", "Brush Image", "Use your own grayscale or color brush pattern")], default="PROCEDURAL", options=set(), update=update_shader_controls,
        description="Surface pattern used to steer Bilateral smoothing. Starter Patches need no image. Guide changes require a new render")
    brush_image: PointerProperty(name="Brush Image", type=bpy.types.Image, update=update_shader_controls,
                                 description="Image used as the surface guide. Direct selection keeps its current color space and packing; Load Brush Image creates a separate Non-Color copy")
    pack_image: BoolProperty(name="Pack Loaded Image", default=True,
                             description="When using Load Brush Image, embed the loaded image in the blend on save for portability. Does not pack an image selected directly")
    mapping: EnumProperty(name="Mapping", items=[
        ("UV", "UV • Animation", "Use active render UVs; recommended for deforming characters and Alembic"),
        ("GENERATED", "Generated • Static Props", "Box map images with generated coordinates; may shift during deformation")],
        default="UV", options=set(), update=update_shader_controls,
        description="UV uses active render UVs for stable animated surfaces; Generated suits static props and can shift during deformation. Rerender after changing")
    tile_u: FloatProperty(update=update_shader_values, name="Tile U", default=1, min=0.01, soft_max=20,
                         description="Repeat the guide along its U coordinate. Higher values make smaller patches in this direction; rerender to see changes")
    tile_v: FloatProperty(update=update_shader_values, name="Tile V", default=3, min=0.01, soft_max=20,
                         description="Repeat the guide along its V coordinate. Higher V than U elongates starter patches horizontally; rerender to see changes")
    texture_rotation: FloatProperty(update=update_shader_values, name="Rotation", default=0, subtype="ANGLE",
                                    description="Rotate the surface guide in its mapping coordinates; rerender to see changes")
    texture_influence: FloatProperty(update=update_values, name="Texture Influence", default=1, min=0, max=10, soft_max=3,
                                     description="Weight of brush-pattern boundaries in Bilateral smoothing. Higher keeps more patches separate; zero ignores the brush pattern")
    threshold: FloatProperty(update=update_values, name="Boundary Threshold", default=0.12, min=0.001, max=2, soft_max=0.5,
                             description="Bilateral tolerance for guide differences. Lower preserves more boundaries; higher blends across more patches. Very low values can suppress smoothing")
    edge_protection: FloatProperty(update=update_values, name="Depth Edge Protection", default=1, min=0, soft_max=10, max=100,
                                   description="Protect depth boundaries in Bilateral smoothing. Higher rejects more samples at different depths, but can reduce smoothing on sloping surfaces")


aov_names, materials_for = core.aov_names, core.materials_for


class SDOF_OT_setup(Operator):
    bl_idname = "sdof.setup"
    bl_label = "Build Setup"
    bl_description = "Build painterly focus for this scene and view layer using the chosen materials. Preserve existing shader/compositor links; render with F12 afterward"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        return core.execute_setup(self, context)



class SDOF_OT_refresh(Operator):
    bl_idname = "sdof.refresh"
    bl_label = "Add / Refresh Materials"
    bl_description = "Scan materials and overrides on the configured view layer, repair render-pass links and sync focus. Muted generated nodes must be unmuted in the node editor first. Render again afterward"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        return core.execute_refresh(self, context)



class SDOF_OT_sync(Operator):
    bl_idname = "sdof.sync_camera"
    bl_label = "Sync Active Camera"
    bl_description = "Link focus to the current scene camera and its focus object/bone. Use after changing that selection; distance and target animation then follow through native drivers"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            check_owner(context.scene)
            if not context.scene.sdof.effect_tree:
                raise RuntimeError("Build the setup first.")
            ng.bind_focus(context.scene.sdof.effect_tree, context.scene)
            update_values(context.scene.sdof, context)
            context.view_layer.update()
            core.clear_error(context.scene.sdof, 'FOCUS')
            self.report({"INFO"}, "Focus linked. Camera and target animation now drive it directly.")
            return {"FINISHED"}
        except Exception as exc:
            core.set_error(context.scene.sdof, exc, 'FOCUS')
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class SDOF_OT_image(Operator, ImportHelper):
    bl_idname = "sdof.load_brush"
    bl_label = "Load Brush Image"
    bl_description = "Load a separate Non-Color brush guide, optionally packed into the blend. Preserve other uses of the image; render again to see the new pattern"
    bl_options = {"REGISTER", "UNDO"}
    filter_glob: StringProperty(default="*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.exr;*.bmp;*.webp", options={"HIDDEN"})

    def execute(self, context):
        image = None
        scene, s = context.scene, context.scene.sdof
        journal, component = Journal(), 'IMAGE'
        try:
            check_owner(scene)
            path = bpy.path.abspath(self.filepath)
            if not os.path.isfile(path):
                raise RuntimeError("Choose an existing brush image file.")
            if s.shader_tree:
                component = 'GUIDE'
                ng.validate_shader(s.shader_tree)
            component = 'IMAGE'
            image = bpy.data.images.load(path, check_existing=False)
            image.name = "Brush Guide • " + os.path.basename(path)
            image.colorspace_settings.name = "Non-Color"
            if s.pack_image:
                image.pack()
            component = 'GUIDE'
            with core.suspend(scene):
                journal.set(s, 'brush_image', image)
                journal.set(s, 'guide_source', 'IMAGE')
                if s.shader_tree:
                    ng.update_shader(s.shader_tree, s, journal)
                    s.shader_tree.update_tag()
                scene.update_tag()
            context.view_layer.update()
            journal.commit()
            core.clear_error(s, 'GUIDE', 'IMAGE')
            self.report({"INFO"}, "Brush loaded. Rerender to update its AOV.")
            return {"FINISHED"}
        except Exception as exc:
            with core.suspend(scene):
                journal.rollback()
            if image and image.users == 0:
                bpy.data.images.remove(image)
            core.set_error(s, exc, component)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class SDOF_OT_remove(Operator):
    bl_idname = "sdof.remove"
    bl_label = "Remove Setup"
    bl_description = "Remove this scene's generated effect and material branches, reconnecting the original image while preserving user edits. Loaded brush images and panel values remain; supports Undo"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        return core.execute_remove(self, context)



class SDOF_PT_view(Panel):
    bl_label = "Stylized Depth of Field"
    bl_idname = "SDOF_PT_view"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Stylized DOF"
    def draw(self, context):
        draw_panel(self.layout, context)


class SDOF_PT_compositor(Panel):
    bl_label = "Stylized Depth of Field"
    bl_idname = "SDOF_PT_compositor"
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Stylized DOF"
    @classmethod
    def poll(cls, context):
        return context.space_data.tree_type == "CompositorNodeTree"
    def draw(self, context):
        draw_panel(self.layout, context)


class SDOF_OT_migrate(Operator):
    bl_idname = "sdof.migrate"
    bl_label = "Migrate Saved Setup"
    bl_description = "Preserve saved controls and animation while updating the setup to the new add-on"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        return migration.execute(self, context)


class SDOF_OT_detach(Operator):
    bl_idname = "sdof.detach"
    bl_label = "Detach Shared Setup"
    bl_description = "Detach this copied scene without changing the original scene's shared materials"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        return core.execute_detach(self, context)


class SDOF_OT_compositing(Operator):
    bl_idname = 'sdof.enable_compositing'
    bl_label = 'Enable Compositing'
    bl_description = 'Enable scene compositing so renders include the configured effect and other compositor nodes; supports Undo'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            check_owner(context.scene)
            context.scene.render.use_compositing = True
            return {'FINISHED'}
        except RuntimeError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class SDOF_OT_restore_compositor(Operator):
    bl_idname = 'sdof.restore_compositor'
    bl_label = 'Restore Configured Compositor'
    bl_description = 'Switch this scene back to its saved setup compositor. The current compositor remains available in Blender; supports Undo'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        try:
            check_owner(scene)
            if not scene.sdof.tree or not core.output_connected(scene, scene.sdof.tree):
                raise RuntimeError('The configured compositor output is disconnected. Restore its links or remove and rebuild the setup.')
            scene.compositing_node_group = scene.sdof.tree
            return {'FINISHED'}
        except RuntimeError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


CLASSES = (SDOF_Settings, SDOF_OT_setup, SDOF_OT_refresh, SDOF_OT_sync, SDOF_OT_image,
           SDOF_OT_remove, SDOF_OT_report, SDOF_OT_help, SDOF_OT_check, SDOF_OT_migrate, SDOF_OT_detach,
           SDOF_OT_compositing, SDOF_OT_restore_compositor,
           SDOF_PT_view, SDOF_PT_compositor)


def _restore_bindings():
    # Scene access is allowed after registration and after a file loads.
    migration.register_bridge(SDOF_Settings)
    for scene in bpy.data.scenes:
        s = scene.sdof
        if s.effect_tree and not core.foreign_setup(scene):
            try:
                if not scene.is_editable or not s.effect_tree.is_editable:
                    continue
                journal = Journal()
                try:
                    ng.upgrade_effect(s.effect_tree, s, journal)
                    if s.tree:
                        core.sync_paint_tracking(scene, journal)
                    journal.commit()
                except Exception:
                    journal.rollback()
                    raise
            except (ReferenceError, RuntimeError, TypeError, AttributeError, KeyError) as exc:
                core.set_error(s, exc, 'EFFECT')
                continue
            update_focus(s, None)


def _cancel_initialize():
    if bpy.app.timers.is_registered(_initialize_once):
        bpy.app.timers.unregister(_initialize_once)


def _initialize_once():
    _restore_bindings()
    return None


@persistent
def _load_post(_):
    # A file load supersedes the pending enable-time scan. No per-frame handler.
    _cancel_initialize()
    _restore_bindings()


def register():
    registered = []
    try:
        for cls in CLASSES:
            bpy.utils.register_class(cls)
            registered.append(cls)
        bpy.types.Scene.sdof = PointerProperty(type=SDOF_Settings)
        migration.register_bridge(SDOF_Settings)
        if _load_post not in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.append(_load_post)
        # Blender hides bpy.data/context during add-on enabling. A nonpersistent,
        # one-shot callback restores an already open file once that guard ends.
        bpy.app.timers.register(_initialize_once, first_interval=0.0)
    except Exception:
        _cancel_initialize()
        migration.unregister_bridge()
        if _load_post in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.remove(_load_post)
        if hasattr(bpy.types.Scene, "sdof"):
            del bpy.types.Scene.sdof
        for cls in reversed(registered):
            bpy.utils.unregister_class(cls)
        raise


def unregister():
    _cancel_initialize()
    migration.unregister_bridge()
    if _load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load_post)
    if hasattr(bpy.types.Scene, "sdof"):
        del bpy.types.Scene.sdof
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
