"""Rendered feature and recovery regressions for the 1.3 update."""
from pathlib import Path

import bpy
import numpy as np

from stylized_depth_of_field import core, nodes, paint
from stylized_depth_of_field.transaction import Journal


def run(addon, check, reset, render, LayoutProbe, Reporter, work_dir):
    scene = reset()
    for obj in list(scene.objects):
        if obj.type != 'CAMERA':
            bpy.data.objects.remove(obj, do_unlink=True)
    cam = scene.camera
    cam.location, cam.rotation_euler = (0, 0, 0), (0, 0, 0)
    cam.data.type, cam.data.ortho_scale, cam.data.dof.focus_distance = 'ORTHO', 8, 10
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = 'OPEN_EXR'
    scene.render.image_settings.color_depth = '32'
    mat = bpy.data.materials.new('Paint Feature Checker')
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    tex, uv = tree.nodes.new('ShaderNodeTexChecker'), tree.nodes.new('ShaderNodeTexCoord')
    tex.inputs['Scale'].default_value = 18
    tex.inputs['Color1'].default_value, tex.inputs['Color2'].default_value = (.05, .1, .2, 1), (.8, .4, .1, 1)
    emission, output = tree.nodes.new('ShaderNodeEmission'), tree.nodes.new('ShaderNodeOutputMaterial')
    tree.links.new(uv.outputs['UV'], tex.inputs['Vector'])
    tree.links.new(tex.outputs['Color'], emission.inputs['Color'])
    tree.links.new(emission.outputs[0], output.inputs[0])
    for x, depth in ((-2.5, 4), (0, 10), (2.5, 18)):
        bpy.ops.mesh.primitive_plane_add(size=2, location=(x, 0, -depth))
        bpy.context.object.data.materials.append(mat)
    bpy.ops.sdof.setup()
    s, layer = scene.sdof, bpy.context.view_layer
    check('default old modes do not load Paint asset', not any(g.get(paint.ASSET_TAG) for g in bpy.data.node_groups))
    check('all new controls have native hover descriptions', all(s.bl_rna.properties[name].description for name in (*nodes.NEW_CONTROLS.values(),)))
    s.radius, s.threshold, s.edge_protection = 8, 2, .1
    s.enabled = False
    baseline = render('paint_features_original')
    s.enabled = True
    sharp, far = (slice(44, 84), slice(114, 142)), (slice(44, 84), slice(212, 236))
    original_passes = layer.use_pass_z, layer.use_pass_position
    images = {}
    for method in ('BILATERAL', 'KUWAHARA', 'PAINT'):
        s.method, s.defocus = method, 0
        check('method configures cleanly: ' + method, not s.last_error)
        before = render('no_defocus_' + method)
        s.defocus = 8
        after = render('defocus_' + method)
        check('Defocus further changes out-of-focus pixels: ' + method, np.abs(after[far][:, :, :3] - before[far][:, :, :3]).mean() > .002)
        check('Defocus preserves sharp pixels: ' + method, np.abs(after[sharp] - baseline[sharp]).max() < .002)
        check('Defocus preserves incoming alpha: ' + method, np.abs(after[:, :, 3] - baseline[:, :, 3]).max() < .002)
        check('new mode produces finite visible filtering: ' + method, np.isfinite(after).all() and np.abs(after[far] - baseline[far]).mean() > .01)
        images[method] = before
        for prop, value in (('enabled', False), ('strength', 0), ('radius', 0)):
            old = getattr(s, prop)
            setattr(s, prop, value)
            bypass = render('feature_bypass_' + method + '_' + prop)
            check('Defocus respects ' + prop + ' bypass: ' + method, np.abs(bypass - baseline).max() < .002)
            setattr(s, prop, old)
    check('Paint mode is distinct from Kuwahara', np.abs(images['PAINT'][far] - images['KUWAHARA'][far]).mean() > .005)
    check('untracked Paint leaves native passes unchanged', original_passes == (layer.use_pass_z, layer.use_pass_position))
    counts = len(bpy.data.node_groups), len(s.effect_tree.nodes)
    for _ in range(2):
        bpy.ops.sdof.refresh()
        s.method = 'KUWAHARA'
        s.method = 'PAINT'
    check('Paint load and repeated refresh are idempotent', counts == (len(bpy.data.node_groups), len(s.effect_tree.nodes)))
    panel = LayoutProbe()
    addon.draw_panel(panel, bpy.context)
    check('Paint panel exposes its relevant controls', all(k in panel.properties for k in ('defocus', 'paint_simplification', 'paint_edge_breakup', 'paint_tracking', 'compositor_device')) and 'sdof_guide' not in panel.sections)

    s.paint_tracking = True
    check('tracking enables native passes on configured layer', layer.use_pass_z and layer.use_pass_position and s.paint_depth_added and s.paint_position_added and not s.last_error)
    instance = core.effect_instance(scene)
    check('tracking connects actual native Depth and Position', instance.inputs['Paint Depth'].links[0].from_socket.name == 'Depth' and instance.inputs['Position'].links[0].from_socket.name == 'Position')
    tracked = render('paint_tracking_cpu')
    check('position-tracked Paint renders visible finite pixels', np.isfinite(tracked).all() and tracked[:, :, :3].max() > .1)
    journal = Journal()
    paint_node = nodes.find(s.effect_tree, 'Paint Filter')
    for key in ('Image', 'Constraints', 'Position', 'Depth'):
        gate = nodes.find(s.effect_tree, 'Paint ' + key + ' Input')
        journal.wire(s.effect_tree, gate.inputs['On'].links[0].from_socket, paint_node.inputs[key])
    try:
        direct = render('paint_tracking_without_input_gates')
    finally:
        journal.rollback()
    check('Paint bypass optimization preserves active tracked pixels', np.abs(tracked - direct).max() < 1e-6)
    for device in ('CPU', 'GPU'):
        scene.render.compositor_device = device
        for prop, value in (('enabled', False), ('strength', 0), ('radius', 0)):
            old = getattr(s, prop)
            setattr(s, prop, value)
            bypass = render('tracked_bypass_' + device + '_' + prop)
            check('tracked Paint preserves %s bypass on %s' % (prop, device), np.abs(bypass - baseline).max() < .002)
            setattr(s, prop, old)
    scene.render.compositor_device = 'CPU'
    check('tracking passes current diagnostics', core.health_report(bpy.context).startswith('Checks passed'))
    layer.use_pass_position = False
    check('disabled tracking pass is diagnosed', 'Paint tracking needs its Position pass' in core.health_report(bpy.context))
    bpy.ops.sdof.refresh()
    check('refresh repairs missing tracking pass', layer.use_pass_position and not s.last_error)
    s.method = 'BILATERAL'
    check('leaving Paint releases unneeded added passes', not layer.use_pass_z and not layer.use_pass_position)
    s.method = 'PAINT'
    check('returning to tracked Paint prepares its passes again', layer.use_pass_z and layer.use_pass_position)

    # A user branch sharing a native pass must survive mode changes and removal.
    render_node = next(n for n in s.tree.nodes if n.get(core.ROLE) == 'render_data')
    user = s.tree.nodes.new('ShaderNodeMath')
    s.tree.links.new(render_node.outputs['Position'], user.inputs[0])
    s.paint_tracking = False
    check('tracking release preserves a pass used by user nodes', layer.use_pass_position and not layer.use_pass_z and user.inputs[0].is_linked)
    s.tree.links.remove(user.inputs[0].links[0])
    layer.use_pass_position = False
    layer.update_render_passes()

    # Reject failures late in tracking preparation without orphan drivers/assets.
    real_wire = Journal.wire
    snapshot = (layer.use_pass_z, layer.use_pass_position, s.paint_depth_added, s.paint_position_added)
    def fail_position(self, tree, source, sink):
        real_wire(self, tree, source, sink)
        if sink.name == 'Position' and sink.node.get(core.ROLE) == 'instance':
            raise RuntimeError('Injected position-link failure')
    Journal.wire = fail_position
    try:
        s.paint_tracking = True
    finally:
        Journal.wire = real_wire
    check('failed tracking update restores native flags and ownership', snapshot == (layer.use_pass_z, layer.use_pass_position, s.paint_depth_added, s.paint_position_added) and 'Injected position-link failure' in s.last_error)
    bpy.ops.sdof.refresh()
    check('tracking recovers after failed preparation', not s.last_error and layer.use_pass_z and layer.use_pass_position)

    # Keyed softness and camera focus evaluate natively in arbitrary frame order.
    cam.data.type, cam.data.lens = 'PERSP', 40
    for frame, focus, softness in ((1, 10, 0), (2, 4, 8), (3, 10, 12)):
        cam.data.dof.focus_distance = focus
        cam.data.dof.keyframe_insert(data_path='focus_distance', frame=frame)
        s.defocus = softness
        s.keyframe_insert(data_path='defocus', frame=frame)
        s.paint_simplification = 2 if frame == 1 else 5
        s.keyframe_insert(data_path='paint_simplification', frame=frame)
    for device in ('CPU', 'GPU'):
        scene.render.compositor_device = device
        for frame, softness in ((3, 12), (1, 0), (2, 8), (1, 0)):
            scene.frame_set(frame)
            pixels = render('paint_keys_%s_%d' % (device, frame))
            check('native Paint/Defocus/camera keys render on %s frame %d' % (device, frame), np.isfinite(pixels).all() and pixels[:, :, :3].max() > .1 and abs(nodes.find(s.effect_tree, 'Defocus Amount').outputs[0].default_value - softness) < 1e-4)
    blend = Path(work_dir) / 'paint_tracked_keyframes.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    bpy.ops.wm.open_mainfile(filepath=str(blend))
    scene, s = bpy.context.scene, bpy.context.scene.sdof
    scene.frame_set(2)
    reopened = render('paint_tracked_reopened')
    check('saved Paint asset and native tracking survive reopen', np.isfinite(reopened).all() and not s.last_error and core.health_report(bpy.context).startswith('Checks passed'))
    if 'BLENDER_EEVEE' in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items.keys():
        scene.render.engine = 'BLENDER_EEVEE'
        eevee = render('paint_tracking_eevee')
        check('Eevee renders Paint with native tracking', np.isfinite(eevee).all() and eevee[:, :, :3].max() > .1)
    copy = scene.copy()
    with bpy.context.temp_override(scene=copy, view_layer=copy.view_layers[0]):
        check('tracked shared copy detaches cleanly', core.execute_detach(Reporter(), bpy.context) == {'FINISHED'})
        check('detach releases copied tracking passes only', not copy.view_layers[0].use_pass_z and not copy.view_layers[0].use_pass_position and scene.view_layers[0].use_pass_z and scene.view_layers[0].use_pass_position)
    bpy.data.scenes.remove(copy)
    check('tracked Paint removes cleanly', bpy.ops.sdof.remove() == {'FINISHED'})
    check('removal releases owned native tracking passes', not scene.view_layers[0].use_pass_z and not scene.view_layers[0].use_pass_position)
    check('removal frees unreferenced bundled Paint groups', not any(g.get(paint.ASSET_TAG) for g in bpy.data.node_groups))

    # A failed first Paint load must not leave bundled groups in a BI scene.
    scene = reset()
    bpy.ops.sdof.setup()
    s = scene.sdof
    counts = len(bpy.data.node_groups), len(s.effect_tree.nodes), len(s.effect_tree.animation_data.drivers)
    real_validate = paint.validate
    paint.validate = lambda instance: (_ for _ in ()).throw(RuntimeError('Injected Paint-load failure'))
    try:
        s.method = 'PAINT'
    finally:
        paint.validate = real_validate
    check('failed first Paint load leaves no asset or node residue', counts == (len(bpy.data.node_groups), len(s.effect_tree.nodes), len(s.effect_tree.animation_data.drivers)) and not any(g.get(paint.ASSET_TAG) for g in bpy.data.node_groups))
    bpy.ops.sdof.refresh()
    check('first Paint load can be retried', not s.last_error and core.health_report(bpy.context).startswith('Checks passed'))
    bpy.ops.sdof.remove()
    layer = bpy.context.view_layer
    layer.use_pass_z = layer.use_pass_position = True
    s.paint_tracking = True
    bpy.ops.sdof.setup()
    check('pre-existing native passes are not claimed', not s.paint_depth_added and not s.paint_position_added)
    bpy.ops.sdof.remove()
    check('removal preserves pre-existing native passes', layer.use_pass_z and layer.use_pass_position)

    scene = reset()
    user_group = bpy.data.node_groups.new('Stylized DOF • Paint Filter', 'CompositorNodeTree')
    user_group.use_fake_user = True
    user_group.nodes.new('ShaderNodeValue')
    bpy.ops.sdof.setup()
    scene.sdof.method = 'PAINT'
    check('Paint loading preserves same-named user groups', not user_group.get(paint.ASSET_TAG) and len(user_group.nodes) == 1 and nodes.find(scene.sdof.effect_tree, 'Paint Filter').node_tree != user_group)
    bpy.ops.sdof.remove()
    check('Paint removal retains same-named user groups', bpy.data.node_groups.get(user_group.name) == user_group)

    # Fail after all new scalar drivers and interfaces exist in an old graph.
    scene = reset()
    bpy.ops.sdof.setup()
    s = scene.sdof
    from .cleanup import legacy_radius_graph
    legacy_radius_graph(s)
    tree = s.effect_tree
    snapshot = len(tree.nodes), len(tree.links), len(tree.animation_data.drivers), len(tree.interface.items_tree)
    real_feature = nodes.feature_node
    def fail_feature(*args, **kwargs):
        result = real_feature(*args, **kwargs)
        if args[2] == 'Softened Source':
            raise RuntimeError('Injected late feature-upgrade failure')
        return result
    nodes.feature_node = fail_feature
    try:
        try:
            nodes.upgrade_effect(tree, s)
        except RuntimeError:
            pass
    finally:
        nodes.feature_node = real_feature
    check('late feature-upgrade failure rolls back drivers, sockets and links', snapshot == (len(tree.nodes), len(tree.links), len(tree.animation_data.drivers), len(tree.interface.items_tree)) and nodes.GRAPH_VERSION not in tree)
    nodes.upgrade_effect(tree, s)
    check('late feature upgrade can be retried', tree.get(nodes.GRAPH_VERSION) == 3 and not nodes.validate_effect(tree, s, configured=True).get('missing'))
