"""Focused 1.2.3 regressions: real AOVs, animation and in-place upgrades."""
from pathlib import Path

import bpy
import numpy as np

from stylized_depth_of_field import core, nodes
from stylized_depth_of_field.transaction import Journal


def legacy_radius_graph(s):
    """Restore the exact pre-1.2.3 radius links for upgrade fault injection."""
    tree = s.effect_tree
    radius = nodes.find(tree, 'Maximum Radius').outputs[0]
    for key, into in (('Bilateral', 'Size'), ('Soft Radius', 0), ('Depth Driven Radius', 1)):
        nodes.wire(tree, radius, nodes.find(tree, key).inputs[into])
    source = nodes.find(tree, 'Render and Surface Data').outputs['Image']
    for key in ('Bilateral', 'Bilateral Soft', 'Kuwahara'):
        nodes.wire(tree, source, nodes.find(tree, key).inputs['Image'])
    for n in list(tree.nodes):
        if n.get(nodes.KEY) in nodes.DEFOCUS_NODES or n.get(nodes.KEY) in nodes.PAINT_NODES:
            if n.get(nodes.KEY) in nodes.NEW_CONTROLS:
                n.outputs[0].driver_remove('default_value')
            tree.nodes.remove(n)
    for item in list(tree.interface.items_tree):
        if item.item_type == 'SOCKET' and item.in_out == 'INPUT' and item.name in {'Paint Depth', 'Position'}:
            tree.interface.remove(item)
    tree.nodes.remove(nodes.find(tree, 'Effective Radius'))
    del tree[nodes.GRAPH_VERSION]


def run(addon, check, reset, render, LayoutProbe, Reporter, work_dir):
    scene = reset()
    layer = bpy.context.view_layer
    override = bpy.data.materials.new('Disposable Override')
    override.use_nodes = True
    layer.material_override = override
    scene.sdof.focus_mode, scene.sdof.manual_focus = 'MANUAL', 1
    bpy.ops.sdof.setup()
    s = scene.sdof
    check('view-layer override is included in material discovery', override in core.materials_for(bpy.context)[0])
    s.preview = 'FOCUS'
    pixels = render('override_focus_mask')
    check('material override writes real depth and coverage', pixels[:, :, 0].max() > .95)
    other = scene.view_layers.new('Other Active Layer')
    other_override = bpy.data.materials.new('Other Override')
    other_override.use_nodes = True
    other.material_override = other_override
    with bpy.context.temp_override(view_layer=other):
        bpy.ops.sdof.refresh()
        report = core.health_report(bpy.context)
    check('refresh and diagnostics follow configured rather than active layer', 'Checks passed' in report and not any(core.owned(n, s.token) for n in other_override.node_tree.nodes))
    check('GPU compositor control is available for both methods', all(device_ui(addon, s, method, LayoutProbe) for method in ('BILATERAL', 'KUWAHARA')))
    scene.render.compositor_device = 'GPU'
    bpy.ops.sdof.refresh()
    check('refresh preserves native compositor device choice', scene.render.compositor_device == 'GPU')
    scene.render.compositor_device = 'CPU'

    group = next(n for n in override.node_tree.nodes if n.get(core.ROLE) == 'material_group')
    # Blender 5.2 disallows muting ShaderNodeOutputAOV itself.
    for n in (group,):
        n.mute = True
        check('muted material data is diagnosed: ' + n.get(core.ROLE), 'Muted surface-data node' in core.health_report(bpy.context))
        check('refresh preserves intentional mute with actionable error: ' + n.get(core.ROLE), core.execute_refresh(Reporter(), bpy.context) == {'CANCELLED'} and n.mute and 'Unmute' in s.last_error)
        n.mute = False
    bpy.ops.sdof.refresh()
    render_data = next(n for n in s.tree.nodes if n.get(core.ROLE) == 'render_data')
    render_data.mute = True
    check('muted Render Layers is diagnosed', 'Render Layers node is muted' in core.health_report(bpy.context))
    render_data.mute = False
    internal = nodes.find(s.effect_tree, 'Bilateral')
    internal.mute = True
    check('muted internal filter is diagnosed', 'Generated node is muted: Bilateral' in core.health_report(bpy.context))
    internal.mute = False

    tree, instance = s.tree, core.effect_instance(scene)
    output = next(n for n in tree.nodes if n.bl_idname == 'NodeGroupOutput')
    switch = tree.nodes.new('CompositorNodeSwitch')
    tree.links.new(instance.outputs[0], switch.inputs['On'])
    tree.links.new(render_data.outputs['Image'], switch.inputs['Off'])
    tree.links.new(switch.outputs[0], output.inputs[0])
    switch.inputs['Switch'].default_value = False
    check('inactive compositor switch branch is disconnected', core.output_status(scene) == 'DISCONNECTED' and 'does not feed' in core.health_report(bpy.context))
    switch.inputs['Switch'].default_value = True
    check('active compositor switch branch is connected', core.output_status(scene) == 'CONNECTED')
    value = tree.nodes.new('ShaderNodeValue')
    tree.links.new(value.outputs[0], switch.inputs['Switch'])
    check('linked switch is reported as uncertain', core.output_status(scene) == 'UNCERTAIN' and 'cannot be confirmed' in core.health_report(bpy.context))
    tree.links.new(instance.outputs[0], output.inputs[0])
    mix = tree.nodes.new('ShaderNodeMixRGB')
    tree.links.new(render_data.outputs['Image'], mix.inputs[1])
    tree.links.new(instance.outputs[0], mix.inputs[2])
    tree.links.new(mix.outputs[0], output.inputs[0])
    mix.inputs[0].default_value = 0
    check('zero mix factor excludes the unused effect branch', core.output_status(scene) == 'DISCONNECTED')
    mix.mute = True
    check('muted mix follows native internal bypass links', core.output_status(scene) == 'DISCONNECTED')
    tree.links.new(instance.outputs[0], output.inputs[0])
    root = bpy.data.node_groups.new('Opaque User Root', 'CompositorNodeTree')
    nodes.interface(root, 'Image', 'OUTPUT', 'NodeSocketColor')
    nested = root.nodes.new('CompositorNodeGroup')
    nested.node_tree = tree
    root_output = root.nodes.new('NodeGroupOutput')
    root.links.new(nested.outputs[0], root_output.inputs[0])
    scene.compositing_node_group = root
    check('effect inside a nested user compositor is structurally uncertain', core.output_status(scene) == 'UNCERTAIN')

    scene = reset()
    linked_source = bpy.data.materials.new('Read Only Override')
    linked_source.use_nodes = True
    library = Path(work_dir) / 'override_library.blend'
    bpy.data.libraries.write(str(library), {linked_source})
    bpy.data.materials.remove(linked_source)
    with bpy.data.libraries.load(str(library), link=True) as (source, target):
        target.materials = ['Read Only Override']
    bpy.context.view_layer.material_override = target.materials[0]
    bpy.ops.sdof.setup()
    check('read-only material override is reported without editing its library', 'Read Only Override' in scene.sdof.last_report and not any(core.owned(n, scene.sdof.token) for n in target.materials[0].node_tree.nodes))
    check('read-only override prevents a false all-clear diagnostic', 'Read Only Override' in core.health_report(bpy.context) and not core.health_report(bpy.context).startswith('Checks passed'))
    interface = next(item for item in scene.sdof.shader_tree.interface.items_tree if item.item_type == 'SOCKET' and item.name == 'Coverage')
    scene.sdof.shader_tree.interface.remove(interface)
    check('missing coverage socket gives an actionable diagnostic', 'Missing socket' in core.health_report(bpy.context) and 'Coverage' in core.health_report(bpy.context))

    scene = reset()
    cube = bpy.data.objects['Cube']
    procedural = bpy.data.node_groups.new('Render Only Procedural', 'GeometryNodeTree')
    procedural.interface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    procedural.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    inp, output = procedural.nodes.new('NodeGroupInput'), procedural.nodes.new('NodeGroupOutput')
    procedural.links.new(inp.outputs[0], output.inputs[0])
    modifier = cube.modifiers.new('Render Only', 'NODES')
    modifier.node_group, modifier.show_viewport, modifier.show_render = procedural, False, True
    bpy.ops.sdof.setup()
    check('render-only procedural visibility is in setup report', 'render/viewport visibility differs' in scene.sdof.last_report)
    check('render-only procedural visibility is in current diagnostics', 'render/viewport visibility differs' in core.health_report(bpy.context))
    modifier.show_viewport = True
    bpy.ops.sdof.refresh()
    check('resolved procedural warning clears on refresh', 'render/viewport visibility differs' not in scene.sdof.last_report)

    # Upgrade all critical links atomically; retain F-curves and node identities.
    s = scene.sdof
    legacy_radius_graph(s)
    ids = [n.as_pointer() for n in s.effect_tree.nodes]
    fc = nodes.binding(nodes.find(s.effect_tree, 'Maximum Radius').outputs[0])
    curve_id = fc.as_pointer()
    real_wire = Journal.wire
    def fail_wire(self, tree, source, sink):
        real_wire(self, tree, source, sink)
        if sink.node.get(nodes.KEY) == 'Soft Radius':
            raise RuntimeError('Injected upgrade failure')
    Journal.wire = fail_wire
    try:
        try:
            nodes.upgrade_effect(s.effect_tree, s)
        except RuntimeError:
            pass
    finally:
        Journal.wire = real_wire
    check('failed radius upgrade rolls back nodes and schema', ids == [n.as_pointer() for n in s.effect_tree.nodes] and nodes.GRAPH_VERSION not in s.effect_tree)
    check('failed radius upgrade restores all old filter links', all(nodes.find(s.effect_tree, key).inputs[into].links[0].from_node.get(nodes.KEY) == 'Maximum Radius' for key, into in (('Bilateral', 'Size'), ('Soft Radius', 0), ('Depth Driven Radius', 1))))
    nodes.upgrade_effect(s.effect_tree, s)
    check('in-place upgrade adds the versioned features and preserves drivers', len(s.effect_tree.nodes) == len(ids) + 1 + len(nodes.DEFOCUS_NODES) and curve_id == nodes.binding(nodes.find(s.effect_tree, 'Maximum Radius').outputs[0]).as_pointer())
    nodes.upgrade_effect(s.effect_tree, s)
    check('repeat upgrade is idempotent', len(s.effect_tree.nodes) == len(ids) + 1 + len(nodes.DEFOCUS_NODES))
    s.effect_tree.nodes.remove(nodes.find(s.effect_tree, 'Effective Radius'))
    check('deleted upgraded radius node is diagnosed instead of silently rebuilt', core.execute_refresh(Reporter(), bpy.context) == {'CANCELLED'} and 'Effective Radius' in s.last_error)

    # Render a genuine camera animation, then revisit frames and reopen the file.
    scene = reset()
    scene.render.resolution_x, scene.render.resolution_y = 128, 128
    cam, cube = scene.camera, bpy.data.objects['Cube']
    cam.location, cam.rotation_euler = (0, 0, 0), (0, 0, 0)
    cube.location, cube.scale = (0, 0, -8), (1, 1, .05)
    for frame, distance, lens, aperture in ((1, 8, 35, 8), (2, 3, 70, 2.8), (3, 8, 50, 5.6)):
        cam.data.dof.focus_distance, cam.data.lens, cam.data.dof.aperture_fstop = distance, lens, aperture
        cam.data.dof.keyframe_insert(data_path='focus_distance', frame=frame)
        cam.data.keyframe_insert(data_path='lens', frame=frame)
        cam.data.dof.keyframe_insert(data_path='aperture_fstop', frame=frame)
    bpy.ops.sdof.setup()
    s = scene.sdof
    s.preview, s.sharp_width, s.near_falloff, s.far_falloff = 'FOCUS', .25, 1, 1
    scene.frame_start, scene.frame_end = 1, 3
    prefix = Path(work_dir) / 'camera_animation_'
    scene.render.image_settings.file_format = 'OPEN_EXR'
    scene.render.image_settings.color_depth = '32'
    scene.render.filepath = str(prefix)
    bpy.ops.render.render(animation=True)
    animation_peaks = []
    for frame in (1, 2, 3):
        im = bpy.data.images.load(str(prefix) + '%04d.exr' % frame, check_existing=False)
        animation_peaks.append(float(np.asarray(im.pixels).reshape(-1, 4)[:, 0].max()))
        bpy.data.images.remove(im)
    check('native animation render evaluates camera focus for every frame', animation_peaks[0] < .01 and animation_peaks[1] > .95 and animation_peaks[2] < .01)
    for visit, (frame, distance) in enumerate(((3, 8), (1, 8), (2, 3), (1, 8)), 1):
        scene.frame_set(frame)
        pixels = render('camera_frame_%d' % frame)
        expected = distance == 3
        check('rendered camera focus and lens keys at frame %d visit %d' % (frame, visit), bool(pixels[:, :, 0].max() > .95) == expected and abs(nodes.find(s.effect_tree, 'Focus Distance').outputs[0].default_value - distance) < 1e-4)
    check('native animation renderer wrote all camera frames', all(Path(str(prefix) + '%04d.exr' % f).is_file() for f in (1, 2, 3)))
    # Fixed off-focus mask reveals the independent lens/framing animation.
    s.focus_mode, s.manual_focus = 'MANUAL', 3
    coverage = []
    for frame in (1, 2):
        scene.frame_set(frame)
        coverage.append(int(np.count_nonzero(render('lens_frame_%d' % frame)[:, :, 0] > .95)))
    check('focal-length keyframes change rendered framing with stable manual focus', coverage[1] > coverage[0] * 2)
    s.focus_mode = 'CAMERA'
    blend = Path(work_dir) / 'camera_keyframes.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    bpy.ops.wm.open_mainfile(filepath=str(blend))
    scene, s = bpy.context.scene, bpy.context.scene.sdof
    scene.frame_set(2)
    check('camera keyframes still render after save and reopen', render('camera_reopened')[:, :, 0].max() > .95 and not nodes.focus_status(s.effect_tree, scene))
    target = bpy.data.objects.new('Animated Focus Target', None)
    scene.collection.objects.link(target)
    for frame, z in ((1, -8), (2, -3)):
        target.location.z = z
        target.keyframe_insert(data_path='location', frame=frame)
    scene.camera.data.dof.focus_object = target
    bpy.ops.sdof.sync_camera()
    for frame, distance in ((2, 3), (1, 8), (2, 3)):
        scene.frame_set(frame)
        pixels = render('target_frame_%d' % frame)
        check('rendered animated focus target follows frame %d' % frame, bool(pixels[:, :, 0].max() > .95) == (distance == 3) and abs(nodes.find(s.effect_tree, 'Focus Distance').outputs[0].default_value - distance) < 1e-4)
    rig = bpy.data.objects.new('Animated Focus Rig', bpy.data.armatures.new('Animated Focus Rig'))
    scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bone = rig.data.edit_bones.new('Focus')
    bone.head, bone.tail = (0, 0, -8), (0, 0, -9)
    bpy.ops.object.mode_set(mode='OBJECT')
    pose = rig.pose.bones['Focus']
    for frame, y in ((1, 0), (2, -5)):
        pose.location.y = y
        pose.keyframe_insert(data_path='location', frame=frame)
    scene.camera.data.dof.focus_object, scene.camera.data.dof.focus_subtarget = rig, 'Focus'
    bpy.ops.sdof.sync_camera()
    for frame, distance in ((1, 8), (2, 3), (1, 8)):
        scene.frame_set(frame)
        pixels = render('bone_frame_%d' % frame)
        check('rendered focus bone keyframes follow frame %d' % frame, bool(pixels[:, :, 0].max() > .95) == (distance == 3) and abs(nodes.find(s.effect_tree, 'Focus Distance').outputs[0].default_value - distance) < 1e-4)

    # Use deterministic full-frame images to compare active and bypassed filters.
    scene = reset()
    scene.render.image_settings.file_format = 'OPEN_EXR'
    scene.render.image_settings.color_depth = '32'
    scene.sdof.focus_mode, scene.sdof.manual_focus = 'MANUAL', 1
    bpy.ops.sdof.setup()
    s, tree = scene.sdof, scene.sdof.tree
    instance = core.effect_instance(scene)
    width, height = scene.render.resolution_x, scene.render.resolution_y
    yy, xx = np.ogrid[:height, :width]
    data = np.ones((height, width, 4), np.float32)
    data[:, :, :3] = (((xx // 3 + yy // 3) % 2) * .8 + .1)[:, :, None]
    image = bpy.data.images.new('Animation Checker', width=width, height=height, float_buffer=True)
    image.colorspace_settings.name = 'Non-Color'
    image.pixels.foreach_set(data.reshape(-1))
    source = tree.nodes.new('CompositorNodeImage')
    source.image = image
    for key in ('Image', 'Guide AOV'):
        tree.links.new(source.outputs['Image'], instance.inputs[key])
    for key in ('Depth AOV', 'Coverage AOV'):
        for link in list(instance.inputs[key].links):
            tree.links.remove(link)
        instance.inputs[key].default_value = 10 if key == 'Depth AOV' else 1
    s.radius, s.threshold, s.edge_protection = 6, 2, .01
    for frame, enabled, strength, radius in ((1, False, 1, 6), (2, True, 1, 6), (3, True, 0, 6), (4, True, 1, 0)):
        s.enabled, s.strength, s.radius = enabled, strength, radius
        for prop in ('enabled', 'strength', 'radius'):
            s.keyframe_insert(data_path=prop, frame=frame)
    for method in ('BILATERAL', 'KUWAHARA'):
        s.method = method
        for frame in (1, 2, 3, 4, 2, 1):
            scene.frame_set(frame)
            pixels = render('gated_%s_%d' % (method, frame))
            difference = float(np.abs(pixels - data).max())
            check('rendered %s radius/strength/enable keys at frame %d' % (method, frame), (difference > .01) if frame == 2 else (difference < 1e-5))
    legacy_radius_graph(s)
    scene.frame_set(2)
    before = render('pre_upgrade_active')
    nodes.upgrade_effect(s.effect_tree, s)
    after = render('post_upgrade_active')
    check('radius upgrade preserves active filtered pixels', np.max(np.abs(before - after)) < 1e-6)
    scene.render.compositor_device = 'GPU'
    for method in ('BILATERAL', 'KUWAHARA'):
        s.method = method
        for frame in (2, 1, 3, 4, 2):
            scene.frame_set(frame)
            difference = float(np.abs(render('gpu_gated_%s_%d' % (method, frame)) - data).max())
            check('GPU rendered %s animated bypass at frame %d' % (method, frame), (difference > .01) if frame == 2 else (difference < 1e-5))


def device_ui(addon, settings, method, LayoutProbe):
    settings.method = method
    probe = LayoutProbe()
    addon.draw_panel(probe, bpy.context)
    return 'compositor_device' in probe.properties
