"""Run with Blender --background --factory-startup --python-exit-code 1.

Arguments after --: --work-dir PATH [--legacy-dir UNPACKED_V1_DIRECTORY]
The tests modify disposable factory scenes, never user preferences or projects.
"""
import argparse
import importlib.util
import json
import math
import sys
sys.dont_write_bytecode = True
import time
from pathlib import Path
from types import SimpleNamespace

import bpy
import addon_utils
import numpy as np
from mathutils import Vector

parser = argparse.ArgumentParser()
parser.add_argument('--work-dir', type=Path, required=True)
parser.add_argument('--legacy-dir', type=Path)
parser.add_argument('--eevee', action='store_true', help='Also render with Eevee; requires a supported graphics device')
parser.add_argument('--previous-blend', type=Path, help='A saved v1.1.0 setup for direct upgrade checks')
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
args.work_dir = args.work_dir.resolve()
if args.legacy_dir:
    args.legacy_dir = args.legacy_dir.resolve()
if args.previous_blend:
    args.previous_blend = args.previous_blend.resolve()
args.work_dir.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import stylized_depth_of_field as addon
from stylized_depth_of_field import core, migration, nodes, ui

checks, timings = [], {}


class Reporter:
    def report(self, level, message):
        print('REPORT', sorted(level), message)


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    checks.append(name)
    print('PASS', name, flush=True)


def close(a, b, epsilon=1e-4):
    return abs(a - b) < epsilon


def update():
    bpy.context.view_layer.update()


def focus():
    update()
    return bpy.context.scene.sdof.effect_tree.nodes['Focus Distance'].outputs[0].default_value


class LayoutProbe:
    """Validate panel properties, operators and icons without a GUI window."""
    icons = set(bpy.types.UILayout.bl_rna.functions['label'].parameters['icon'].enum_items.keys())

    def __init__(self, collapsed=False):
        self.collapsed = collapsed
        self.properties, self.operators, self.sections, self.labels = [], [], [], []

    def box(self):
        return self

    def row(self, **kwargs):
        return self

    def column(self, **kwargs):
        return self

    def separator(self, **kwargs):
        pass

    def panel(self, identifier, **kwargs):
        self.sections.append(identifier)
        return self, None if self.collapsed else self

    def label(self, **kwargs):
        if kwargs.get('icon', 'NONE') not in self.icons:
            raise AssertionError('Invalid panel icon: ' + kwargs['icon'])
        self.labels.append(kwargs.get('text', ''))

    def prop(self, owner, name, **kwargs):
        if name not in owner.bl_rna.properties:
            raise AssertionError('Invalid panel property: ' + name)
        self.properties.append(name)

    def operator(self, name, **kwargs):
        category, operation = name.split('.')
        getattr(getattr(bpy.ops, category), operation).get_rna_type()
        self.label(**kwargs)
        self.operators.append(name)
        return self

    def template_ID(self, owner, name):
        self.prop(owner, name)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=False)
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 4
    scene.render.resolution_x, scene.render.resolution_y = 256, 128
    scene.render.resolution_percentage = 100
    return scene


def render(name, scene=None):
    scene = scene or bpy.context.scene
    scene.render.image_settings.file_format = 'OPEN_EXR'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.filepath = str(args.work_dir / (name + '.exr'))
    started = time.perf_counter()
    bpy.ops.render.render(write_still=True, scene=scene.name)
    timings[name] = time.perf_counter() - started
    image = bpy.data.images.load(scene.render.filepath, check_existing=False)
    data = np.empty(len(image.pixels), dtype=np.float32)
    image.pixels.foreach_get(data)
    data = data.reshape(image.size[1], image.size[0], 4)
    bpy.data.images.remove(image)
    return data


enable_errors = []
enabled_module = addon_utils.enable('stylized_depth_of_field', default_set=False, handle_error=enable_errors.append)
check('Blender enable succeeds under real restricted registration', enabled_module is addon and not enable_errors)
check('enable queues one-time scene initialization', bpy.app.timers.is_registered(addon._initialize_once))
check('legacy schema is available immediately after enable', 'sspd' in bpy.types.Scene.bl_rna.properties)
addon_utils.disable('stylized_depth_of_field', default_set=False, handle_error=enable_errors.append)
check('disable cancels pending initialization', not bpy.app.timers.is_registered(addon._initialize_once))
check('disable removes schema and handler', not hasattr(bpy.types.Scene, 'sdof') and 'sspd' not in bpy.types.Scene.bl_rna.properties and addon._load_post not in bpy.app.handlers.load_post)
check('Blender repeated enable succeeds', addon_utils.enable('stylized_depth_of_field', default_set=False, handle_error=enable_errors.append) is addon and not enable_errors)
addon_utils.disable('stylized_depth_of_field', default_set=False, handle_error=enable_errors.append)
# Factory resets disable managed add-ons. The graph suite owns its registration
# directly so each disposable reset retains the tested property schema/handler.
addon.register()
scene = reset()
check('file load supersedes the pending enable scan', not bpy.app.timers.is_registered(addon._initialize_once))
addon.draw_panel(LayoutProbe(), bpy.context)
controls = migration.CONTROL_NAMES
check('all user controls have hover descriptions', all(scene.sdof.bl_rna.properties[name].description for name in controls))
check('all add-on operators have hover descriptions', all(getattr(cls, 'bl_description', '') for cls in addon.CLASSES if issubclass(cls, bpy.types.Operator)))
check('native collapsible layout API is available', 'panel' in bpy.types.UILayout.bl_rna.functions)
for key in ui.HELP_TOPICS:
    probe = LayoutProbe()
    ui.SDOF_OT_help.draw(SimpleNamespace(topic=key, layout=probe, bl_rna=bpy.ops.sdof.help.get_rna_type()), bpy.context)
    check('help topic draws with valid controls: ' + key, 'topic' in probe.properties and len(probe.labels) > 8)
probe = LayoutProbe()
ui.SDOF_OT_report.draw(SimpleNamespace(layout=probe), bpy.context)
check('empty setup report draws safely', any('Build a setup' in line for line in probe.labels))
mat = bpy.data.materials['Material']
original_nodes = len(mat.node_tree.nodes)
original_links = [(l.from_node.name, l.from_socket.name, l.to_node.name, l.to_socket.name) for l in mat.node_tree.links]
# An existing compositor and viewer must survive installation unchanged.
base = bpy.data.node_groups.new('Existing Compositor', 'CompositorNodeTree')
nodes.interface(base, 'Image', 'OUTPUT', 'NodeSocketColor')
out = nodes.node(base, 'NodeGroupOutput', 'Output')
render_node = nodes.node(base, 'CompositorNodeRLayers', 'Source')
viewer = nodes.node(base, 'CompositorNodeViewer', 'Viewer')
nodes.wire(base, render_node.outputs['Image'], out.inputs['Image'])
nodes.wire(base, render_node.outputs['Image'], viewer.inputs['Image'])
scene.compositing_node_group = base
base_shape = (len(base.nodes), len(base.links))
check('setup succeeds', bpy.ops.sdof.setup() == {'FINISHED'})
s = scene.sdof
addon.draw_panel(LayoutProbe(), bpy.context)
probe = LayoutProbe(collapsed=True)
addon.draw_panel(probe, bpy.context)
check('help remains available with sections collapsed', 'sdof.help' in probe.operators and 'radius' in probe.properties and 'sharp_width' not in probe.properties)
check('maintenance actions are inside collapsed section', 'sdof.remove' not in probe.operators and 'sdof_maintenance' in probe.sections)
s.method, s.guide_source = 'KUWAHARA', 'IMAGE'
probe = LayoutProbe()
addon.draw_panel(probe, bpy.context)
check('Kuwahara hides unused brush and bilateral controls', 'sdof_guide' not in probe.sections and 'texture_influence' not in probe.properties and 'quality' not in probe.properties)
s.method, s.guide_source = 'BILATERAL', 'PROCEDURAL'
probe = LayoutProbe()
addon.draw_panel(probe, bpy.context)
check('Bilateral exposes guide and advanced controls', 'sdof_guide' in probe.sections and 'quality' in probe.properties and 'focus_object' in probe.properties)
s.preview = 'FOCUS'
probe = LayoutProbe()
addon.draw_panel(probe, bpy.context)
check('diagnostic preview explains saved render output', any('saved renders' in line for line in probe.labels))
s.preview = 'RESULT'
s.focus_mode = 'MANUAL'
probe = LayoutProbe()
addon.draw_panel(probe, bpy.context)
check('manual focus replaces camera fields', 'manual_focus' in probe.properties and 'focus_object' not in probe.properties)
s.focus_mode = 'CAMERA'
check('panel properties operators and icons are valid', True)
check('original compositor untouched', base_shape == (len(base.nodes), len(base.links)) and s.tree != base)
check('three unique AOVs', len(bpy.context.view_layer.aovs) == 3)
check('surface material links unchanged', all(any((l.from_node.name, l.from_socket.name, l.to_node.name, l.to_socket.name) == pair
      for l in mat.node_tree.links) for pair in original_links))
node_count, group_count = len(mat.node_tree.nodes), len(bpy.data.node_groups)
check('repeat setup does not duplicate', bpy.ops.sdof.setup() == {'FINISHED'} and len(bpy.data.node_groups) == group_count)
check('repeat refresh does not duplicate', bpy.ops.sdof.refresh() == {'FINISHED'} and len(mat.node_tree.nodes) == node_count)
shader_links = [(l.as_pointer(), l.from_socket.as_pointer(), l.to_socket.as_pointer()) for l in s.shader_tree.links]
s.radius = 7
update()
check('radius driver updates without frame change', close(s.effect_tree.nodes['Maximum Radius'].outputs[0].default_value, 7))
check('compositor slider leaves shader links intact', shader_links == [(l.as_pointer(), l.from_socket.as_pointer(), l.to_socket.as_pointer()) for l in s.shader_tree.links])
s.tile_u = 2.25
update()
check('guide scale driver updates', close(s.shader_tree.nodes['Texture Placement'].inputs['Scale'].default_value[0], 2.25))
scene.camera.data.dof.focus_distance = 13
check('camera focus distance updates', close(focus(), 13))
target = bpy.data.objects.new('Focus Target', None)
scene.collection.objects.link(target)
scene.camera.location = (0, 0, 0)
scene.camera.rotation_euler = (0, 0, 0)
scene.camera.data.dof.focus_object = target
target.location = (8, 2, -12)
check('sync focus object succeeds', bpy.ops.sdof.sync_camera() == {'FINISHED'})
check('focus uses axial rather than radial distance', close(focus(), 12))
target.location.z = -19
check('target motion updates native driver', close(focus(), 19))
cam = scene.camera
cam.rotation_euler = (0.2, 0.6, -0.4)
cam.scale = (2, 3, 4)
update()
axis = cam.matrix_world.col[2].xyz.normalized()
target.location = cam.matrix_world.translation - axis * 14 + cam.matrix_world.col[0].xyz.normalized() * 6
check('rotated scaled camera focus projection', close(focus(), 14))
parent = bpy.data.objects.new('Target Parent', None)
scene.collection.objects.link(parent)
target.parent = parent
parent.location = -axis * 3
check('parented target world transform updates', close(focus(), 17))
cam.data.dof.focus_subtarget = 'Missing Bone'
check('invalid focus bone rejected safely', addon.SDOF_OT_sync.execute(Reporter(), bpy.context) == {'CANCELLED'})
cam.data.dof.focus_subtarget = ''
rig_data = bpy.data.armatures.new('Focus Rig')
rig = bpy.data.objects.new('Focus Rig', rig_data)
scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
bone = rig_data.edit_bones.new('Focus Bone')
bone.head, bone.tail = (0, 0, -8), (0, 0, -9)
bpy.ops.object.mode_set(mode='OBJECT')
rig.location = (0, 0, -3)
cam.location, cam.rotation_euler, cam.scale = (0, 0, 0), (0, 0, 0), (1, 1, 1)
cam.data.dof.focus_object, cam.data.dof.focus_subtarget = rig, 'Focus Bone'
check('valid armature focus bone syncs', bpy.ops.sdof.sync_camera() == {'FINISHED'})
check('focus bone world position projects correctly', close(focus(), 11))
rig.pose.bones['Focus Bone'].location.y = 2
check('animated focus bone movement updates', close(focus(), 13))
saved_driver = s.effect_tree.animation_data.drivers.find('nodes["Focus Distance"].outputs[0].default_value')
scene.camera = None
check('missing camera sync fails safely', addon.SDOF_OT_sync.execute(Reporter(), bpy.context) == {'CANCELLED'})
check('invalid sync retains working driver', s.effect_tree.animation_data.drivers.find(saved_driver.data_path) is not None)
scene.camera = cam
s.focus_mode = 'MANUAL'
s.manual_focus = 6.5
check('manual focus binding updates', close(focus(), 6.5))
check('manual focus clears stale camera state', s.bound_camera is None and s.bound_target is None and s.bound_bone == '')
s.radius = 3
s.keyframe_insert(data_path='radius', frame=1)
s.radius = 9
s.keyframe_insert(data_path='radius', frame=10)
scene.frame_set(1)
check('animated radius first frame', close(s.effect_tree.nodes['Maximum Radius'].outputs[0].default_value, 3))
scene.frame_set(10)
check('animated radius last frame', close(s.effect_tree.nodes['Maximum Radius'].outputs[0].default_value, 9))
s.enabled = False
s.keyframe_insert(data_path='enabled', frame=1)
s.enabled = True
s.keyframe_insert(data_path='enabled', frame=10)
scene.frame_set(1)
check('animated enable bypass first frame', close(s.effect_tree.nodes['Effect Enabled'].outputs[0].default_value, 0))
scene.frame_set(10)
check('animated enable bypass last frame', close(s.effect_tree.nodes['Effect Enabled'].outputs[0].default_value, 1))
# Repair a deleted pass and its lost compositor connection.
layer = bpy.context.view_layer
layer.aovs.remove(layer.aovs.get(core.aov_names(s.token)['Depth']))
layer.update_render_passes()
check('refresh repairs deleted AOV', bpy.ops.sdof.refresh() == {'FINISHED'} and len(layer.aovs) == 3)
check('refresh repairs recreated pass link', core.effect_instance(scene).inputs['Depth AOV'].is_linked)
layer.name = 'Renamed Layer'
check('refresh follows renamed view layer', bpy.ops.sdof.refresh() == {'FINISHED'} and s.layer_name == layer.name)
# Force failure after editing an existing AOV link; all prior links must return.
guide = next(n for n in mat.node_tree.nodes if n.get(core.ROLE) == 'aov_Guide')
alternate = mat.node_tree.nodes.new('ShaderNodeRGB')
mat.node_tree.links.new(alternate.outputs[0], guide.inputs['Color'])
real_attach = core.attach_material


def fail_after_attach(*values):
    real_attach(*values)
    raise RuntimeError('Injected refresh failure')


core.attach_material = fail_after_attach
check('failed refresh reports cancellation', core.execute_refresh(Reporter(), bpy.context) == {'CANCELLED'})
check('failed refresh restores existing source link', guide.inputs['Color'].links[0].from_node == alternate)
core.attach_material = real_attach
mat.node_tree.nodes.remove(alternate)
bpy.ops.sdof.refresh()
# Shared scene edits must never delete the original material branches.
copy = scene.copy()
original_tree = scene.compositing_node_group
with bpy.context.temp_override(scene=copy, view_layer=copy.view_layers[0]):
    check('shared scene removal refused', core.execute_remove(Reporter(), bpy.context) == {'CANCELLED'})
    check('shared scene detach succeeds', core.execute_detach(Reporter(), bpy.context) == {'FINISHED'})
    check('detach removes copied owned AOVs', len(copy.view_layers[0].aovs) == 0)
    source_node = next(n for n in copy.compositing_node_group.nodes if n.bl_idname == 'CompositorNodeRLayers')
    check('detached copy keeps valid current-scene image source', source_node.scene in (None, copy))
    check('detached copy rebuild succeeds', core.execute_setup(Reporter(), bpy.context) == {'FINISHED'})
    instance = core.effect_instance(copy)
    check('rebuilt copy uses matching image and depth scenes', instance.inputs['Image'].links[0].from_node.scene in (None, copy) and instance.inputs['Depth AOV'].links[0].from_node.scene == copy)
    check('rebuilt copy creates exactly three AOVs', len(copy.view_layers[0].aovs) == 3)
    check('independent scene copy removes cleanly', core.execute_remove(Reporter(), bpy.context) == {'FINISHED'})
check('detach preserves original tree and materials', scene.compositing_node_group == original_tree and len(mat.node_tree.nodes) == node_count)
bpy.data.scenes.remove(copy)
# Preserve user edits made after setup.
tree = s.tree
extra = nodes.node(tree, 'ShaderNodeMath', 'User Edit')
extra.inputs[0].default_value = 0.75
check('remove succeeds', bpy.ops.sdof.remove() == {'FINISHED'})
check('remove restores material node count', len(mat.node_tree.nodes) == original_nodes)
check('remove deletes only owned AOVs', len(layer.aovs) == 0)
check('remove retains user compositor edit', scene.compositing_node_group.nodes.get('User Edit') is not None)
check('remove restores output and viewer links', all(n.inputs[0].is_linked for n in scene.compositing_node_group.nodes if n.bl_idname in {'NodeGroupOutput', 'CompositorNodeViewer'}))
check('owned groups released after removal', not any(g.get(core.TAG) for g in bpy.data.node_groups))
# Existing unlinked outputs can intentionally contain a constant image.
scene = reset()
constant_tree = bpy.data.node_groups.new('Constant Compositor', 'CompositorNodeTree')
nodes.interface(constant_tree, 'Image', 'OUTPUT', 'NodeSocketColor')
constant_out = nodes.node(constant_tree, 'NodeGroupOutput', 'Constant Output')
constant_out.inputs['Image'].default_value = (0.2, 0.3, 0.4, 0.5)
scene.compositing_node_group = constant_tree
scene.render.use_compositing = False
bpy.ops.sdof.setup()
image_input = core.effect_instance(scene).inputs['Image']
check('setup preserves unlinked compositor image', not image_input.is_linked and close(image_input.default_value[0], 0.2))
bpy.ops.sdof.remove()
restored = scene.compositing_node_group.nodes['Constant Output'].inputs['Image']
check('removal restores unlinked compositor constant', not restored.is_linked and all(close(a, b) for a, b in zip(restored.default_value, (0.2, 0.3, 0.4, 0.5))))
check('removal restores disabled compositing setting', not scene.render.use_compositing)
# Direct copies, inactive copies and nested compositor references stay removable.
scene = reset()
bpy.ops.sdof.setup()
original_tree = scene.sdof.tree
active_copy, inactive_copy = original_tree.copy(), original_tree.copy()
inactive_copy.use_fake_user = True
scene.compositing_node_group = active_copy
nodes.node(active_copy, 'ShaderNodeMath', 'User Copy Edit')
check('refresh reconciles copied active compositor', bpy.ops.sdof.refresh() == {'FINISHED'} and scene.sdof.tree == active_copy)
check('copied compositor removal succeeds', bpy.ops.sdof.remove() == {'FINISHED'})
check('copied active compositor has no leftover effect', not any(n.bl_idname == 'CompositorNodeGroup' for n in scene.compositing_node_group.nodes))
check('inactive compositor copies are also bypassed', not any(n.bl_idname == 'CompositorNodeGroup' for n in inactive_copy.nodes))
check('copied compositor user edits survive removal', scene.compositing_node_group.nodes.get('User Copy Edit') is not None)
scene = reset()
bpy.ops.sdof.setup()
effect_root = scene.sdof.tree
nested = bpy.data.node_groups.new('User Root', 'CompositorNodeTree')
nodes.interface(nested, 'Image', 'OUTPUT', 'NodeSocketColor')
nested_output = nodes.node(nested, 'NodeGroupOutput', 'Output')
nested_group = nodes.node(nested, 'CompositorNodeGroup', 'Nested Setup')
nested_group.node_tree = effect_root
nodes.wire(nested, nested_group.outputs['Image'], nested_output.inputs['Image'])
scene.compositing_node_group = nested
check('nested compositor removal succeeds', bpy.ops.sdof.remove() == {'FINISHED'})
check('nested user compositor remains connected', nested_output.inputs['Image'].is_linked and not any(n.bl_idname == 'CompositorNodeGroup' for n in effect_root.nodes))
scene = reset()
bpy.ops.sdof.setup()
other = bpy.data.scenes.new('Manual Shared Compositor User')
other.compositing_node_group = scene.sdof.tree
shape = (len(bpy.data.materials['Material'].node_tree.nodes), len(bpy.context.view_layer.aovs))
check('manual sharing without copied settings refuses removal', core.execute_remove(Reporter(), bpy.context) == {'CANCELLED'})
check('manual shared refusal changes no materials or passes', shape == (len(bpy.data.materials['Material'].node_tree.nodes), len(bpy.context.view_layer.aovs)) and bool(scene.sdof.token))
bpy.data.scenes.remove(other)
# Internal names no longer determine generated-node identity.
scene = reset()
bpy.ops.sdof.setup()
s = scene.sdof
placement = s.shader_tree.nodes['Texture Placement']
placement.name = 'Custom Placement Name'
s.mapping = 'GENERATED'
check('renamed shader node still updates mapping', placement.inputs['Vector'].links[0].from_socket.name == 'Generated' and not s.last_error)
s.tile_u = 2.5
update()
check('renamed shader node retains native drivers', close(placement.inputs['Scale'].default_value[0], 2.5))
focus_node = s.effect_tree.nodes['Focus Distance']
focus_node.name = 'Custom Focus Name'
check('renamed focus node can rebind', bpy.ops.sdof.sync_camera() == {'FINISHED'})
effect_node = s.effect_tree.nodes['Effect Bypass']
effect_node.name = 'Custom Bypass Name'
s.preview = 'FOCUS'
check('renamed effect node still updates preview', effect_node.inputs['On'].links[0].from_node.get(nodes.KEY) == 'Covered Focus Mask' and not s.last_error)
duplicate = s.shader_tree.nodes.new('ShaderNodeMapping')
duplicate[nodes.KEY] = 'Texture Placement'
s.mapping = 'UV'
check('duplicate internal key fails explicitly', 'Duplicate generated node' in s.last_error)
s.shader_tree.nodes.remove(duplicate)
s.mapping = 'GENERATED'
check('valid guide update clears its own error', not s.last_error)
# Missing nodes preserve errors and image loading rolls back as one operation.
scene = reset()
bpy.ops.sdof.setup()
s = scene.sdof
image_node = s.shader_tree.nodes['Your Brush Image']
original_key = image_node[nodes.KEY]
del image_node[nodes.KEY]
image_node.name = 'Unidentified Image Node'
s.guide_source = 'IMAGE'
error = s.last_error
s.radius = 7
check('unrelated numeric slider preserves guide error', bool(error) and s.last_error == error)
s.preview = 'FOCUS'
check('unrelated valid effect update preserves guide error', s.last_error == error)
placement = nodes.find(s.shader_tree, 'Texture Placement')
s.mapping = 'GENERATED'
check('failed guide update leaves prior coordinate link intact', placement.inputs['Vector'].links[0].from_socket.name == 'UV')
brush = bpy.data.images.new('Regression Brush', width=4, height=4)
brush.pixels[:] = [0.5, 0.5, 0.5, 1] * 16
brush.filepath_raw, brush.file_format = str(args.work_dir / 'regression_brush.png'), 'PNG'
brush.save()
op = Reporter()
op.filepath = brush.filepath_raw
image_count, previous_image = len(bpy.data.images), s.brush_image
check('damaged guide refuses brush load', addon.SDOF_OT_image.execute(op, bpy.context) == {'CANCELLED'})
check('refused brush load leaves image settings and data intact', s.brush_image == previous_image and len(bpy.data.images) == image_count)
image_node[nodes.KEY] = original_key
check('refresh reapplies pending guide settings after restoration', bpy.ops.sdof.refresh() == {'FINISHED'} and placement.inputs['Vector'].links[0].from_socket.name == 'Generated' and not s.last_error)
s.guide_source = 'PROCEDURAL'
old_links = [(l.from_socket.as_pointer(), l.to_socket.as_pointer()) for l in s.shader_tree.links]
real_update_shader = nodes.update_shader


def fail_after_image_update(*values, **kwargs):
    real_update_shader(*values, **kwargs)
    raise RuntimeError('Injected image assignment failure')


nodes.update_shader = fail_after_image_update
check('failed image hookup cancels load', addon.SDOF_OT_image.execute(op, bpy.context) == {'CANCELLED'})
nodes.update_shader = real_update_shader
check('failed image hookup restores prior settings', s.brush_image is None and s.guide_source == 'PROCEDURAL' and image_node.image is None)
check('failed image hookup restores links and removes loaded image', sorted(old_links) == sorted((l.from_socket.as_pointer(), l.to_socket.as_pointer()) for l in s.shader_tree.links) and len(bpy.data.images) == image_count)
check('valid brush load succeeds after failure', addon.SDOF_OT_image.execute(op, bpy.context) == {'FINISHED'} and not s.last_error)
# Inject a late setup failure and verify complete recovery.
scene = reset()
mat = bpy.data.materials['Material']
counts = (len(mat.node_tree.nodes), len(bpy.data.node_groups), len(bpy.context.view_layer.aovs))
real_make = core.make_compositor
core.make_compositor = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('Injected setup failure'))
check('failed setup reports cancellation', core.execute_setup(Reporter(), bpy.context) == {'CANCELLED'})
check('failed setup restores node/pass/group counts', counts == (len(mat.node_tree.nodes), len(bpy.data.node_groups), len(bpy.context.view_layer.aovs)))
check('failed setup restores scene state', scene.compositing_node_group is None and not scene.sdof.token and scene.sdof.effect_tree is None)
core.make_compositor = real_make
# Render a textured scene at three depths with transparent background.
scene = reset()
for obj in list(scene.objects):
    if obj.type != 'CAMERA':
        bpy.data.objects.remove(obj, do_unlink=True)
cam = scene.camera
cam.location, cam.rotation_euler = (0, 0, 0), (0, 0, 0)
cam.data.type, cam.data.ortho_scale = 'ORTHO', 8
cam.data.dof.focus_distance = 10
cam.data.dof.use_dof = False
scene.render.film_transparent = True
mat = bpy.data.materials.new('Test Surface')
mat.use_nodes = True
tree = mat.node_tree
tree.nodes.clear()
tex = tree.nodes.new('ShaderNodeTexChecker')
tex.inputs['Scale'].default_value = 22
tex.inputs['Color1'].default_value = (0.05, 0.15, 0.3, 1)
tex.inputs['Color2'].default_value = (0.8, 0.4, 0.1, 1)
uv = tree.nodes.new('ShaderNodeTexCoord')
emission = tree.nodes.new('ShaderNodeEmission')
out = tree.nodes.new('ShaderNodeOutputMaterial')
tree.links.new(uv.outputs['UV'], tex.inputs['Vector'])
tree.links.new(tex.outputs['Color'], emission.inputs['Color'])
tree.links.new(emission.outputs[0], out.inputs['Surface'])
for x, depth in ((-2.5, 4), (0, 10), (2.5, 18)):
    bpy.ops.mesh.primitive_plane_add(size=2, location=(x, 0, -depth))
    bpy.context.object.data.materials.append(mat)
bpy.ops.sdof.setup()
s = scene.sdof
s.radius, s.threshold, s.edge_protection = 5, 2, 0.2
s.enabled = False
baseline = render('baseline')
# A rebuilt scene copy must render its own camera image, not the original's.
copy = scene.copy()
copy.name = 'Render Copy Regression'
copy_camera = scene.camera.copy()
copy_camera.data = scene.camera.data.copy()
copy.collection.objects.link(copy_camera)
copy.camera = copy_camera
copy_camera.location.x = 1.0
copy.render.use_compositing = False
expected_copy = render('copy_expected', copy)
check('different copied camera produces a different image', float(np.abs(expected_copy - baseline).mean()) > 0.01)
with bpy.context.temp_override(scene=copy, view_layer=copy.view_layers[0]):
    core.execute_detach(Reporter(), bpy.context)
    core.execute_setup(Reporter(), bpy.context)
    image_source = core.effect_instance(copy).inputs['Image'].links[0].from_node
    check('fresh detached setup retargets owned render source', image_source.scene == copy)
rebuilt_copy = render('copy_rebuilt', copy)
check('detached rebuilt copy renders its own image', float(np.abs(rebuilt_copy - expected_copy).max()) < 0.002)
with bpy.context.temp_override(scene=copy, view_layer=copy.view_layers[0]):
    core.execute_remove(Reporter(), bpy.context)
bpy.data.scenes.remove(copy)
s.enabled = True
s.preview = 'FOCUS'
mask = render('focus_mask')
near, middle, far = (slice(44, 84), slice(20, 44)), (slice(44, 84), slice(114, 142)), (slice(44, 84), slice(212, 236))
check('focus mask keeps focal plane sharp', float(mask[middle][:, :, 0].max()) < 0.001)
check('focus mask selects foreground/background', float(mask[near][:, :, 0].mean()) > 0.9 and float(mask[far][:, :, 0].mean()) > 0.9)
s.preview = 'GUIDE'
guide_pixels = render('guide')
check('surface AOV guide varies across geometry', float(guide_pixels[far][:, :, 0].std()) > 0.05)
s.preview, s.method = 'RESULT', 'BILATERAL'
bilateral = render('bilateral_balanced')
check('bilateral changes defocused image', float(np.abs(bilateral[far][:, :, :3] - baseline[far][:, :, :3]).mean()) > 0.01)
check('bilateral preserves focal-plane pixels', float(np.abs(bilateral[middle] - baseline[middle]).max()) < 0.002)
check('bilateral preserves incoming alpha', float(np.abs(bilateral[:, :, 3] - baseline[:, :, 3]).max()) < 0.002)
s.quality = 'FAST'
fast = render('bilateral_fast')
check('fast bilateral changes defocused image', float(np.abs(fast[far][:, :, :3] - baseline[far][:, :, :3]).mean()) > 0.01)
check('fast quality bypasses half-radius path', s.effect_tree.nodes['Mix Painterly Result'].inputs[2].links[0].from_node.name == 'Bilateral Fast Level')
s.method = 'KUWAHARA'
kuwahara = render('kuwahara')
check('kuwahara changes defocused image', float(np.abs(kuwahara[far][:, :, :3] - baseline[far][:, :, :3]).mean()) > 0.01)
check('kuwahara preserves focal-plane pixels', float(np.abs(kuwahara[middle] - baseline[middle]).max()) < 0.002)
check('kuwahara preserves incoming alpha', float(np.abs(kuwahara[:, :, 3] - baseline[:, :, 3]).max()) < 0.002)
s.radius = 0
zero = render('zero_radius')
check('zero radius returns original image', float(np.abs(zero - baseline).max()) < 0.002)
s.radius, s.strength = 5, 0
zero_strength = render('zero_strength')
check('zero strength returns original image', float(np.abs(zero_strength - baseline).max()) < 0.002)
s.strength, s.enabled = 1, False
disabled = render('disabled')
check('disabled effect returns original image', float(np.abs(disabled - baseline).max()) < 0.002)
s.enabled, s.preview, s.near_enabled = True, 'FOCUS', False
far_only = render('far_only')
check('foreground toggle is independent', float(far_only[near][:, :, 0].max()) < 0.001 and float(far_only[far][:, :, 0].mean()) > 0.9)
# Load an actual packed brush and reopen the saved scene.
brush = bpy.data.images.new('Temporary Brush', width=8, height=8)
brush.pixels[:] = [v for y in range(8) for x in range(8) for v in ((x+y)%2, (x+y)%2, (x+y)%2, 1)]
brush.filepath_raw, brush.file_format = str(args.work_dir / 'brush.png'), 'PNG'
brush.save()
check('brush image loader succeeds', bpy.ops.sdof.load_brush(filepath=brush.filepath_raw) == {'FINISHED'})
check('loaded brush packed for portability', s.brush_image.packed_file is not None)
check('loaded brush does not change existing image', brush.colorspace_settings.name != s.brush_image.colorspace_settings.name)
s.preview, s.near_enabled = 'RESULT', True
custom = render('custom_brush')
check('custom brush renders finite pixels', np.isfinite(custom).all())
if args.eevee:
    scene.render.engine = 'BLENDER_EEVEE'
    s.enabled = False
    eevee_base = render('eevee_baseline')
    s.enabled, s.preview = True, 'FOCUS'
    eevee_mask = render('eevee_focus')
    check('Eevee focus AOV matches geometry', float(eevee_mask[middle][:, :, 0].max()) < 0.002 and float(eevee_mask[far][:, :, 0].mean()) > 0.9)
    s.preview = 'GUIDE'
    eevee_guide = render('eevee_guide')
    check('Eevee brush AOV varies across geometry', float(eevee_guide[far][:, :, 0].std()) > 0.05)
    s.preview, s.method = 'RESULT', 'BILATERAL'
    eevee_bi = render('eevee_bilateral')
    check('Eevee bilateral changes defocused image', float(np.abs(eevee_bi[far][:, :, :3] - eevee_base[far][:, :, :3]).mean()) > 0.01)
    check('Eevee bilateral preserves focal plane', float(np.abs(eevee_bi[middle] - eevee_base[middle]).max()) < 0.002)
    check('Eevee bilateral preserves alpha', float(np.abs(eevee_bi[:, :, 3] - eevee_base[:, :, 3]).max()) < 0.002)
    s.method = 'KUWAHARA'
    eevee_kw = render('eevee_kuwahara')
    check('Eevee kuwahara changes defocused image', float(np.abs(eevee_kw[far][:, :, :3] - eevee_base[far][:, :, :3]).mean()) > 0.01)
    check('Eevee kuwahara preserves focal plane', float(np.abs(eevee_kw[middle] - eevee_base[middle]).max()) < 0.002)
    check('Eevee kuwahara preserves alpha', float(np.abs(eevee_kw[:, :, 3] - eevee_base[:, :, 3]).max()) < 0.002)
    scene.render.engine = 'CYCLES'
bpy.ops.wm.save_as_mainfile(filepath=str(args.work_dir / 'new_setup.blend'))
bpy.ops.wm.open_mainfile(filepath=str(args.work_dir / 'new_setup.blend'))
scene, s = bpy.context.scene, bpy.context.scene.sdof
check('saved setup reopens with valid ownership', core.installed(scene) and not core.foreign_setup(scene))
check('packed brush survives reopen', s.brush_image.packed_file is not None)
scene.camera.data.dof.focus_distance = 16
check('focus driver survives reopen', close(focus(), 16))
# Exercise the exact original package, not a mocked migration fixture.
if args.legacy_dir:
    scene = reset()
    migration.unregister_bridge()
    spec = importlib.util.spec_from_file_location('legacy_fixture', args.legacy_dir / '__init__.py', submodule_search_locations=[str(args.legacy_dir)])
    legacy = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = legacy
    spec.loader.exec_module(legacy)
    legacy.register()
    legacy_base = bpy.data.node_groups.new('Legacy User Compositor', 'CompositorNodeTree')
    nodes.interface(legacy_base, 'Image', 'OUTPUT', 'NodeSocketColor')
    legacy_output = nodes.node(legacy_base, 'NodeGroupOutput', 'Output')
    legacy_source = nodes.node(legacy_base, 'CompositorNodeRLayers', 'Legacy Base Image')
    nodes.wire(legacy_base, legacy_source.outputs['Image'], legacy_output.inputs['Image'])
    scene.compositing_node_group = legacy_base
    bpy.ops.sspd.setup()
    old = scene.sspd
    old.radius, old.manual_focus, old.focus_mode = 7.5, 6.25, 'MANUAL'
    old.tile_u, old.method, old.enabled = 2.5, 'KUWAHARA', False
    old.radius = 3
    old.keyframe_insert(data_path='radius', frame=1)
    old.radius = 11
    old.keyframe_insert(data_path='radius', frame=12)
    old_compositor = scene.compositing_node_group
    nodes.node(old_compositor, 'ShaderNodeMath', 'Retained Custom Node')
    old_token = old.token
    legacy_copy = scene.copy()
    legacy_copy.name = 'Legacy Scene Copy'
    legacy_copy.use_fake_user = True
    check('migration refuses simultaneously enabled old add-on', migration.execute(Reporter(), bpy.context) == {'CANCELLED'})
    bpy.ops.wm.save_as_mainfile(filepath=str(args.work_dir / 'legacy_setup.blend'))
    legacy.unregister()
    bpy.ops.wm.open_mainfile(filepath=str(args.work_dir / 'legacy_setup.blend'))
    scene = bpy.context.scene
    check('saved legacy setup detected after reopen', migration.has_legacy(scene))
    # An injected construction failure must leave the old scene usable.
    core.make_compositor = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('Injected migration failure'))
    legacy_shape = (len(bpy.data.node_groups), len(bpy.data.materials['Material'].node_tree.nodes), len(bpy.context.view_layer.aovs))
    check('failed migration reports cancellation', migration.execute(Reporter(), bpy.context) == {'CANCELLED'})
    check('failed migration retains original scene', migration.has_legacy(scene) and scene.compositing_node_group == migration.legacy_settings(scene).tree)
    check('failed migration rolls back staged resources', legacy_shape == (len(bpy.data.node_groups), len(bpy.data.materials['Material'].node_tree.nodes), len(bpy.context.view_layer.aovs)))
    core.make_compositor = real_make
    check('legacy migration succeeds', bpy.ops.sdof.migrate() == {'FINISHED'})
    s = scene.sdof
    check('migration preserves saved enum controls', s.method == 'KUWAHARA' and s.focus_mode == 'MANUAL' and not s.enabled)
    check('migration preserves numeric controls', close(s.manual_focus, 6.25) and close(s.tile_u, 2.5))
    check('migration retires old setup pointers', not migration.has_legacy(scene) and migration.legacy_settings(scene).effect_tree is None)
    check('migration renames AOVs', len(bpy.context.view_layer.aovs) == 3 and all(a.name.startswith('SDOF_') for a in bpy.context.view_layer.aovs))
    check('migration retains compositor edits', s.tree.nodes.get('Retained Custom Node') is not None)
    legacy_copy = bpy.data.scenes['Legacy Scene Copy']
    check('migration preserves pending scene copy branches', any(n.get(migration.LEGACY_TAG) == old_token for n in bpy.data.materials['Material'].node_tree.nodes))
    with bpy.context.temp_override(scene=legacy_copy, view_layer=legacy_copy.view_layers[0]):
        check('shared legacy scene copy migrates independently', bpy.ops.sdof.migrate() == {'FINISHED'})
        check('migrated scene copy owns its groups', not core.foreign_setup(legacy_copy) and legacy_copy.sdof.token != scene.sdof.token)
        data_node = next(n for n in legacy_copy.sdof.tree.nodes if n.get(core.ROLE) == 'render_data')
        check('migrated scene copy uses its own AOV scene', data_node.scene == legacy_copy)
        image_node = core.effect_instance(legacy_copy).inputs['Image'].links[0].from_node
        check('migrated copy retargets pre-existing image source', image_node.scene == legacy_copy)
    check('last migration retires old shared material branches', not any(n.get(migration.LEGACY_TAG) == old_token for n in bpy.data.materials['Material'].node_tree.nodes))
    scene.frame_set(1)
    check('migrated animation first frame', close(s.effect_tree.nodes['Maximum Radius'].outputs[0].default_value, 3))
    scene.frame_set(12)
    check('migrated animation last frame', close(s.effect_tree.nodes['Maximum Radius'].outputs[0].default_value, 11))
    bpy.ops.wm.save_as_mainfile(filepath=str(args.work_dir / 'migrated_setup.blend'))
    bpy.ops.wm.open_mainfile(filepath=str(args.work_dir / 'migrated_setup.blend'))
    check('migrated setup survives saved-file reopen', core.installed(bpy.context.scene) and close(focus(), 6.25))
    check('migrated setup removes cleanly', bpy.ops.sdof.remove() == {'FINISHED'})
    # A scene action in an NLA strip and scene drivers must migrate too.
    scene = reset()
    migration.unregister_bridge()
    legacy.register()
    bpy.ops.sspd.setup()
    old = scene.sspd
    old.focus_mode = 'MANUAL'
    old.strength = 0.2
    old.keyframe_insert(data_path='strength', frame=1)
    old.strength = 0.8
    old.keyframe_insert(data_path='strength', frame=9)
    animation = scene.animation_data
    action, slot_handle = animation.action, animation.action_slot_handle
    track = animation.nla_tracks.new()
    strip = track.strips.new('Effect Strip', 1, action)
    strip.action_slot_handle = slot_handle
    animation.action = None
    scene['FocusSource'] = 9.0
    driver = scene.driver_add('sspd.manual_focus').driver
    driver.type = 'AVERAGE'
    var = driver.variables.new()
    var.type, var.name = 'SINGLE_PROP', 'value'
    var.targets[0].id_type, var.targets[0].id, var.targets[0].data_path = 'SCENE', scene, '["FocusSource"]'
    cam = scene.camera
    cam['ObservedRadius'] = 0.0
    driver = cam.driver_add('["ObservedRadius"]').driver
    driver.type = 'AVERAGE'
    var = driver.variables.new()
    var.type, var.name = 'SINGLE_PROP', 'value'
    var.targets[0].id_type, var.targets[0].id, var.targets[0].data_path = 'SCENE', scene, 'sspd.radius'
    legacy.unregister()
    migration.register_bridge()
    check('NLA and scene driver migration succeeds', bpy.ops.sdof.migrate() == {'FINISHED'})
    scene.frame_set(1)
    check('migrated NLA first frame', close(scene.sdof.effect_tree.nodes['Effect Strength'].outputs[0].default_value, 0.2))
    scene.frame_set(9)
    check('migrated NLA last frame', close(scene.sdof.effect_tree.nodes['Effect Strength'].outputs[0].default_value, 0.8))
    check('migrated scene property driver evaluates', close(focus(), 9))
    scene['FocusSource'] = 15.0
    scene.update_tag()
    check('migrated scene driver remains live', close(focus(), 15))
    scene.sdof.radius = 6.25
    update()
    check('external driver references remap', close(cam['ObservedRadius'], 6.25))
    # Library-linked old brush images must remain linked and never be renamed.
    scene = reset()
    migration.unregister_bridge()
    legacy.register()
    bpy.ops.sspd.setup()
    library_brush = bpy.data.images.new('SS Guide • Linked Regression', width=4, height=4)
    library_brush.pixels[:] = [0.5, 0.5, 0.5, 1] * 16
    library_brush.pack()
    library_path = args.work_dir / 'linked_brush_library.blend'
    bpy.data.libraries.write(str(library_path), {library_brush}, fake_user=True)
    bpy.data.images.remove(library_brush)
    with bpy.data.libraries.load(str(library_path), link=True) as (source, target):
        target.images = ['SS Guide • Linked Regression']
    old = scene.sspd
    old.brush_image, old.guide_source = target.images[0], 'IMAGE'
    old.radius = 3
    old.keyframe_insert(data_path='radius', frame=1)
    old.radius = 11
    old.keyframe_insert(data_path='radius', frame=12)
    # An external driver embedded in a material also needs its path remapped.
    material_tree = bpy.data.materials['Material'].node_tree
    observed = nodes.node(material_tree, 'ShaderNodeValue', 'User Observed Radius')
    driver = observed.outputs[0].driver_add('default_value').driver
    driver.type = 'AVERAGE'
    variable = driver.variables.new()
    variable.type, variable.name = 'SINGLE_PROP', 'value'
    variable.targets[0].id_type, variable.targets[0].id = 'SCENE', scene
    variable.targets[0].data_path = 'sspd.radius'
    scene.frame_set(12)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.work_dir / 'linked_legacy_setup.blend'))
    legacy.unregister()
    bpy.ops.wm.open_mainfile(filepath=str(args.work_dir / 'linked_legacy_setup.blend'))
    scene = bpy.context.scene
    check('linked brush migration completes without crash', bpy.ops.sdof.migrate() == {'FINISHED'})
    check('linked brush remains linked and retains library name', scene.sdof.brush_image.library is not None and scene.sdof.brush_image.name == 'SS Guide • Linked Regression')
    scene.frame_set(1)
    check('linked migration preserves first animation frame', close(scene.sdof.effect_tree.nodes['Maximum Radius'].outputs[0].default_value, 3))
    check('embedded material driver reference is remapped', close(bpy.data.materials['Material'].node_tree.nodes['User Observed Radius'].outputs[0].default_value, 3))
    scene.frame_set(12)
    check('linked migration preserves last animation frame', close(scene.sdof.effect_tree.nodes['Maximum Radius'].outputs[0].default_value, 11))
    check('linked migration retires old setup resources', not migration.has_legacy(scene) and len(bpy.context.view_layer.aovs) == 3 and not any(g.get(migration.LEGACY_TAG) for g in bpy.data.node_groups))
    bpy.ops.wm.save_as_mainfile(filepath=str(args.work_dir / 'linked_migrated_setup.blend'))
    bpy.ops.wm.open_mainfile(filepath=str(args.work_dir / 'linked_migrated_setup.blend'))
    check('linked migrated setup reopens correctly', core.installed(bpy.context.scene) and bpy.context.scene.sdof.brush_image.library is not None)
    check('linked migrated setup removes cleanly', bpy.ops.sdof.remove() == {'FINISHED'})
    # Late cleanup failures preserve the committed setup and remain retryable.
    scene = reset()
    migration.unregister_bridge()
    legacy.register()
    bpy.ops.sspd.setup()
    old = scene.sspd
    old.radius = 4
    old.keyframe_insert(data_path='radius', frame=1)
    old.radius = 12
    old.keyframe_insert(data_path='radius', frame=10)
    scene.frame_set(10)
    legacy.unregister()
    migration.register_bridge()
    real_retire = migration.retire_legacy

    def fail_partial_cleanup(scene, old):
        mat_tree = bpy.data.materials['Material'].node_tree
        old_instance = next(n for n in mat_tree.nodes if n.get(migration.LEGACY_TAG) == old.token and n.get(migration.LEGACY_ROLE) == 'material_group')
        mat_tree.nodes.remove(old_instance)
        aov = scene.view_layers[0].aovs.get('SSPD_' + old.token + '_Guide')
        scene.view_layers[0].aovs.remove(aov)
        scene.view_layers[0].update_render_passes()
        raise RuntimeError('Injected cleanup failure after retiring some resources')

    migration.retire_legacy = fail_partial_cleanup
    check('late cleanup failure retains committed migration', migration.execute(Reporter(), bpy.context) == {'FINISHED'} and core.installed(scene))
    migration.retire_legacy = real_retire
    error = scene.sdof.last_error
    check('late cleanup keeps retry marker and clear error', migration.has_legacy(scene) and scene.sdof.error_source == 'CLEANUP' and bool(error))
    scene.frame_set(1)
    check('late cleanup failure preserves new animation', close(scene.sdof.effect_tree.nodes['Maximum Radius'].outputs[0].default_value, 4))
    scene.sdof.strength = 0.75
    check('unrelated slider preserves cleanup error', scene.sdof.last_error == error)
    addon.draw_panel(LayoutProbe(), bpy.context)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.work_dir / 'pending_cleanup.blend'))
    bpy.ops.wm.open_mainfile(filepath=str(args.work_dir / 'pending_cleanup.blend'))
    scene = bpy.context.scene
    check('pending cleanup survives reopen', migration.has_legacy(scene) and scene.sdof.error_source == 'CLEANUP' and core.installed(scene))
    check('finish cleanup retry succeeds', bpy.ops.sdof.migrate() == {'FINISHED'})
    check('cleanup retry removes old passes and marker', not migration.has_legacy(scene) and len(bpy.context.view_layer.aovs) == 3 and not scene.sdof.last_error)
    check('cleanup retry keeps new animation intact', close(scene.sdof.effect_tree.nodes['Maximum Radius'].outputs[0].default_value, 4))
from stylized_depth_of_field.tests.reliability import run as reliability_checks
reliability_checks(addon, check, reset, render, LayoutProbe, Reporter)
from stylized_depth_of_field.tests.cleanup import run as cleanup_checks
cleanup_checks(addon, check, reset, render, LayoutProbe, Reporter, args.work_dir)
from stylized_depth_of_field.tests.painterly import run as painterly_checks
painterly_checks(addon, check, reset, render, LayoutProbe, Reporter, args.work_dir)

if args.previous_blend:
    bpy.ops.wm.open_mainfile(filepath=str(args.previous_blend))
    scene, s = bpy.context.scene, bpy.context.scene.sdof
    check('saved v1.1.0 setup opens directly in patch', core.installed(scene) and not core.foreign_setup(scene))
    keys_before = [(n.name, tuple(n.keys())) for tree in (s.shader_tree, s.effect_tree) for n in tree.nodes]
    core.health_report(bpy.context)
    check('health inspection does not add keys to old saved groups', keys_before == [(n.name, tuple(n.keys())) for tree in (s.shader_tree, s.effect_tree) for n in tree.nodes])
    immediate = render('v1_1_0_immediate')
    check('v1.1.0 file renders before any control changes', np.isfinite(immediate).all())
    counts = (len(s.shader_tree.nodes), len(s.effect_tree.nodes))
    s.mapping, s.method, s.preview = 'GENERATED', 'BILATERAL', 'RESULT'
    check('v1.1.0 guide gains persistent lookup keys', nodes.find(s.shader_tree, 'Texture Placement').get(nodes.KEY) == 'Texture Placement')
    check('v1.1.0 controls work without rebuilding groups', not s.last_error and counts == (len(s.shader_tree.nodes), len(s.effect_tree.nodes)))
    placement = nodes.find(s.shader_tree, 'Texture Placement')
    placement.name = 'Renamed After Upgrade'
    s.mapping = 'UV'
    check('upgraded group remains functional after renaming', placement.inputs['Vector'].links[0].from_socket.name == 'UV' and not s.last_error)
    upgraded = render('upgraded_v1_1_0')
    check('directly upgraded v1.1.0 setup renders', np.isfinite(upgraded).all())
    check('directly upgraded v1.1.0 setup removes', bpy.ops.sdof.remove() == {'FINISHED'})
addon.unregister()
check('unregister removes load handler', addon._load_post not in bpy.app.handlers.load_post)
check('unregister removes registered scene property', 'sdof' not in bpy.types.Scene.bl_rna.properties)
check('unregister leaves no initialization timer', not bpy.app.timers.is_registered(addon._initialize_once))
report = {'blender': bpy.app.version_string, 'build': bpy.app.build_hash.decode(),
          'platform': sys.platform, 'passed': len(checks), 'checks': checks, 'render_seconds': timings}
(args.work_dir / 'test_results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print('ALL CHECKS PASSED:', len(checks), flush=True)
