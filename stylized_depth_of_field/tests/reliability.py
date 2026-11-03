"""Focused regressions for 1.2.2; called by integration.py in factory scenes."""
import bpy
import numpy as np

from stylized_depth_of_field import core, nodes


def run(addon, check, reset, render, LayoutProbe, Reporter):
    scene = reset()
    cam = scene.camera
    cam.location, cam.rotation_euler = (0, 0, 0), (0, 0, 0)
    cam.data.dof.focus_distance = 3
    target = bpy.data.objects.new('Disposable Focus', None)
    scene.collection.objects.link(target)
    target.location = (0, 0, -10)
    cam.data.dof.focus_object = target
    bpy.ops.sdof.setup()
    s = scene.sdof
    bpy.context.view_layer.update()
    check('valid target binding passes focus inspection', not nodes.focus_status(s.effect_tree, scene))
    bpy.data.objects.remove(target, do_unlink=True)
    bpy.context.view_layer.update()
    check('deleted target is diagnosed despite both pointers clearing', bool(nodes.focus_status(s.effect_tree, scene)) and s.bound_target is None and cam.data.dof.focus_object is None)
    panel = LayoutProbe()
    addon.draw_panel(panel, bpy.context)
    check('deleted target displays a focus sync notice', any('binding needs syncing' in line for line in panel.labels))
    check('refresh repairs deleted target binding', bpy.ops.sdof.refresh() == {'FINISHED'} and not nodes.focus_status(s.effect_tree, scene))
    out = nodes.find(s.effect_tree, 'Focus Distance').outputs[0]
    check('deleted target falls back to camera distance', abs(out.default_value - 3) < 1e-4)

    # Fail after rebinding: restore the exact prior source and F-curve modifiers.
    fc = nodes.binding(out)
    fc.modifiers.new('GENERATOR')
    modifier_count = len(fc.modifiers)
    original_type, original_id = fc.driver.type, fc.driver.variables[0].targets[0].id
    old_report = s.last_report
    target = bpy.data.objects.new('New Focus', None)
    scene.collection.objects.link(target)
    target.location = (0, 0, -9)
    cam.data.dof.focus_object = target
    real_bind = nodes.bind_focus

    def fail_bind(*args, **kwargs):
        real_bind(*args, **kwargs)
        raise RuntimeError('Injected failure after binding')

    nodes.bind_focus = fail_bind
    try:
        result = core.execute_refresh(Reporter(), bpy.context)
    finally:
        nodes.bind_focus = real_bind
    fc = nodes.binding(out)
    check('late refresh failure cancels with original focus binding', result == {'CANCELLED'} and fc.driver.type == original_type and fc.driver.variables[0].targets[0].id == original_id)
    check('late refresh rollback retains focus modifiers and metadata', len(fc.modifiers) == modifier_count and s.bound_target is None and s.last_report == old_report)
    bpy.ops.sdof.refresh()
    check('refresh succeeds after binding failure', s.bound_target == target and not s.last_error)
    check('sync reuses the existing focus F-curve', len(nodes.binding(out).modifiers) == modifier_count)

    # Set Material without an original material slot must write real render AOVs.
    scene = reset()
    cube = bpy.data.objects['Cube']
    mat = bpy.data.materials.new('Procedural Only Material')
    mat.use_nodes = True
    tree = bpy.data.node_groups.new('Disposable Set Material', 'GeometryNodeTree')
    tree.interface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    tree.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    inp, output = tree.nodes.new('NodeGroupInput'), tree.nodes.new('NodeGroupOutput')
    assign = tree.nodes.new('GeometryNodeSetMaterial')
    assign.inputs['Material'].default_value = mat
    tree.links.new(inp.outputs['Geometry'], assign.inputs['Geometry'])
    tree.links.new(assign.outputs['Geometry'], output.inputs['Geometry'])
    cube.modifiers.new('Geometry Nodes', 'NODES').node_group = tree
    found, *_ = core.materials_for(bpy.context)
    check('evaluated material discovery finds Geometry Nodes Set Material', mat in found and mat not in [slot.material for slot in cube.material_slots])
    scene.sdof.focus_mode, scene.sdof.manual_focus = 'MANUAL', 1
    bpy.ops.sdof.setup()
    s = scene.sdof
    check('procedural material receives generated AOV branches', len([n for n in mat.node_tree.nodes if core.owned(n, s.token)]) == 4)
    s.preview = 'FOCUS'
    pixels = render('geometry_nodes_focus_mask')
    check('Geometry Nodes surface renders a nonblack focus mask', np.isfinite(pixels).all() and pixels[:, :, 0].max() > 0.95)
    counts = len(mat.node_tree.nodes), len(s.effect_tree.nodes), len(s.shader_tree.nodes)
    bpy.ops.sdof.refresh()
    check('evaluated discovery remains idempotent', counts == (len(mat.node_tree.nodes), len(s.effect_tree.nodes), len(s.shader_tree.nodes)))

    # A selected collection instancer includes its evaluated source material.
    scene = reset()
    source = bpy.data.objects['Cube']
    collection = bpy.data.collections.new('Instance Library')
    scene.collection.children.link(collection)
    for old_collection in list(source.users_collection):
        old_collection.objects.unlink(source)
    collection.objects.link(source)
    instancer = bpy.data.objects.new('Selected Instancer', None)
    scene.collection.objects.link(instancer)
    instancer.instance_type, instancer.instance_collection = 'COLLECTION', collection
    bpy.ops.object.select_all(action='DESELECT')
    instancer.select_set(True)
    bpy.context.view_layer.objects.active = instancer
    scene.sdof.scope = 'SELECTED'
    found, *_ = core.materials_for(bpy.context)
    check('selected instance discovery includes its material', source.material_slots[0].material in found)

    # Modern native hair curves, rather than legacy Curve objects.
    scene = reset()
    bpy.data.objects.remove(bpy.data.objects['Cube'], do_unlink=True)
    cam = scene.camera
    cam.location, cam.rotation_euler = (0, 0, 0), (0, 0, 0)
    hair_data = bpy.data.hair_curves.new('Disposable Hair')
    hair_data.add_curves([2])
    hair_data.attributes['position'].data.foreach_set('vector', [-0.5, 0, -5, 0.5, 0, -5])
    radius = hair_data.attributes.new('radius', 'FLOAT', 'POINT')
    radius.data.foreach_set('value', [0.15, 0.15])
    hair = bpy.data.objects.new('Disposable Hair', hair_data)
    scene.collection.objects.link(hair)
    mat = bpy.data.materials.new('Hair Material')
    mat.use_nodes = True
    hair_data.materials.append(mat)
    found, *_ = core.materials_for(bpy.context)
    check('modern CURVES material is discovered', hair.type == 'CURVES' and mat in found)
    scene.sdof.focus_mode, scene.sdof.manual_focus, scene.sdof.mapping = 'MANUAL', 1, 'GENERATED'
    bpy.ops.sdof.setup()
    scene.sdof.preview = 'FOCUS'
    pixels = render('hair_focus_mask')
    check('modern hair writes depth and coverage AOVs', np.isfinite(pixels).all() and pixels[:, :, 0].max() > 0.95)

    # Broken generated controls/links produce actionable failures, not success.
    scene = reset()
    bpy.ops.sdof.setup()
    s = scene.sdof
    radius_node = nodes.find(s.effect_tree, 'Maximum Radius')
    s.effect_tree.nodes.remove(radius_node)
    s.radius = 9
    check('missing radius node is diagnosed on control edit', 'Maximum Radius' in s.last_error)
    before = len(bpy.context.view_layer.aovs), len(bpy.data.materials['Material'].node_tree.nodes)
    check('refresh rejects missing radius node', core.execute_refresh(Reporter(), bpy.context) == {'CANCELLED'} and 'Maximum Radius' in s.last_error)
    check('damaged graph refresh leaves passes and materials unchanged', before == (len(bpy.context.view_layer.aovs), len(bpy.data.materials['Material'].node_tree.nodes)))
    check('health check diagnoses missing control', 'Maximum Radius' in core.health_report(bpy.context))
    scene = reset()
    bpy.ops.sdof.setup()
    s = scene.sdof
    scalar = nodes.find(s.effect_tree, 'Effect Strength').outputs[0]
    scalar.driver_remove('default_value')
    check('health check diagnoses missing driver', 'control driver: strength' in core.health_report(bpy.context))
    scene = reset()
    bpy.ops.sdof.setup()
    s = scene.sdof
    size = nodes.find(s.effect_tree, 'Bilateral').inputs['Size']
    s.effect_tree.links.remove(size.links[0])
    check('refresh rejects deleted internal filter link', core.execute_refresh(Reporter(), bpy.context) == {'CANCELLED'} and 'link' in s.last_error)
    scene = reset()
    bpy.ops.sdof.setup()
    s = scene.sdof
    s.shader_tree.nodes.remove(nodes.find(s.shader_tree, 'Camera Plane Depth'))
    check('refresh rejects deleted shader depth node', core.execute_refresh(Reporter(), bpy.context) == {'CANCELLED'} and 'Camera Plane Depth' in s.last_error)

    scene = reset()
    bpy.ops.sdof.setup()
    s = scene.sdof
    counts = len(s.effect_tree.nodes), len(s.shader_tree.nodes)
    report_before, error_before = s.last_report, s.last_error
    check('healthy setup passes on-demand inspection', core.health_report(bpy.context).startswith('Checks passed'))
    check('health check preserves graph and diagnostic state', counts == (len(s.effect_tree.nodes), len(s.shader_tree.nodes)) and (s.last_report, s.last_error) == (report_before, error_before))
    mat_tree = bpy.data.materials['Material'].node_tree
    guide = next(n for n in mat_tree.nodes if n.get(nodes.ROLE) == 'aov_Guide')
    mat_tree.links.remove(guide.inputs['Color'].links[0])
    check('health check diagnoses broken material AOV links', 'Material needs Refresh' in core.health_report(bpy.context))
    bpy.ops.sdof.refresh()
    check('refresh repairs material AOV links', core.health_report(bpy.context).startswith('Checks passed'))
    into = nodes.find(s.effect_tree, 'Effect Bypass').inputs['On']
    s.effect_tree.links.remove(into.links[0])
    check('health check diagnoses disconnected selected result', 'Effect Bypass' in core.health_report(bpy.context))
    bpy.ops.sdof.refresh()
    check('refresh repairs selected result wiring', core.health_report(bpy.context).startswith('Checks passed'))
    image = bpy.data.images.new('Missing File Brush', width=4, height=4)
    image.source, image.filepath = 'FILE', '//missing_sdof_regression_brush.png'
    s.guide_source, s.brush_image = 'IMAGE', image
    check('health check diagnoses a missing unpacked brush file', 'Brush image file is missing' in core.health_report(bpy.context))
    s.guide_source, s.brush_image = 'PROCEDURAL', None
    point_data = bpy.data.pointclouds.new('Unsupported Points')
    point_object = bpy.data.objects.new('Unsupported Points', point_data)
    scene.collection.objects.link(point_object)
    check('unsupported geometry appears in the material report', any('POINTCLOUD: unsupported geometry' in name for name in core.materials_for(bpy.context)[3]))
    check('health check flags material scan warnings', 'material scan has warnings' in core.health_report(bpy.context))
    bpy.data.objects.remove(point_object, do_unlink=True)
    scene.render.use_compositing = False
    panel = LayoutProbe()
    addon.draw_panel(panel, bpy.context)
    check('scene compositor bypass has an explicit panel notice and action', 'sdof.enable_compositing' in panel.operators and any('compositing is off' in line for line in panel.labels))
    bpy.ops.sdof.refresh()
    check('refresh respects deliberate scene compositor bypass', not scene.render.use_compositing)
    check('health check diagnoses scene-level bypass', 'compositing is disabled' in core.health_report(bpy.context))
    check('explicit enable compositing action works', bpy.ops.sdof.enable_compositing() == {'FINISHED'} and scene.render.use_compositing)
    other = bpy.data.node_groups.new('Other User Compositor', 'CompositorNodeTree')
    scene.compositing_node_group = other
    panel = LayoutProbe()
    addon.draw_panel(panel, bpy.context)
    check('disconnected setup offers restoration instead of build', 'sdof.restore_compositor' in panel.operators and 'sdof.setup' not in panel.operators)
    check('explicit restore retains the alternative compositor', bpy.ops.sdof.restore_compositor() == {'FINISHED'} and scene.compositing_node_group == s.tree and other in bpy.data.node_groups.values())
    output = next(n for n in s.tree.nodes if n.bl_idname == 'NodeGroupOutput')
    s.tree.links.remove(output.inputs[0].links[0])
    check('unwired setup output is detected', not core.output_connected(scene) and 'does not feed' in core.health_report(bpy.context))
    panel = LayoutProbe()
    addon.draw_panel(panel, bpy.context)
    check('unwired setup does not offer a duplicate build', 'sdof.setup' not in panel.operators)

    # Forced failure after clearing copied state restores the entire detach.
    scene = reset()
    bpy.ops.sdof.setup()
    s = scene.sdof
    copied = scene.copy()
    bpy.context.window.scene = copied
    before_tree, token = copied.compositing_node_group, copied.sdof.token
    before_groups = len(bpy.data.node_groups)
    before_aovs = {(a.name, a.type) for a in copied.view_layers[0].aovs}
    original_links = {(l.from_node.name, l.from_socket.name, l.to_node.name, l.to_socket.name) for l in before_tree.links}
    real_clear = core.clear_state

    def fail_clear(scene):
        real_clear(scene)
        raise RuntimeError('Injected failure after clearing state')

    core.clear_state = fail_clear
    try:
        result = core.execute_detach(Reporter(), bpy.context)
    finally:
        core.clear_state = real_clear
    check('late detach failure restores copied compositor and metadata', result == {'CANCELLED'} and copied.compositing_node_group == before_tree and copied.sdof.token == token and copied.sdof.effect_tree == s.effect_tree)
    check('late detach failure restores copied passes and frees staging tree', before_aovs == {(a.name, a.type) for a in copied.view_layers[0].aovs} and len(bpy.data.node_groups) == before_groups)
    check('failed detach leaves original scene intact', scene.sdof.token == token and core.installed(scene) and len(scene.view_layers[0].aovs) == 3)
    check('failed detach preserves shared compositor links', original_links == {(l.from_node.name, l.from_socket.name, l.to_node.name, l.to_socket.name) for l in before_tree.links})
    check('detachment succeeds after a late failure', bpy.ops.sdof.detach() == {'FINISHED'} and not copied.sdof.token and not copied.view_layers[0].aovs)

    # An unexpected late removal must retain a Blender Undo step.
    bpy.context.window.scene = scene
    core.clear_state = fail_clear
    try:
        result = core.execute_remove(Reporter(), bpy.context)
    finally:
        core.clear_state = real_clear
    check('late removal failure retains undo eligibility and diagnosis', result == {'FINISHED'} and scene.sdof.error_source == 'REMOVAL')
