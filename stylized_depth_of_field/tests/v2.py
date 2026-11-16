"""Cycles renders, native keyframes, recovery and motion regressions for v2.

Run with --background --factory-startup --python-exit-code 1 --threads 8
--python this_file -- --work-dir PATH. Uses disposable scenes only.
"""
import argparse
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
import numpy as np
import stylized_depth_of_field as addon
from stylized_depth_of_field import core, looks, nodes
nodes.camera_focus.supported = lambda tree: False  # Fallback regressions; native path is in v21.py.
from stylized_depth_of_field.transaction import Journal

parser = argparse.ArgumentParser()
parser.add_argument('--work-dir', type=Path, required=True)
parser.add_argument('--previous-blend', type=Path, help='Optional real v1.3 setup for late upgrade rollback')
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
out = args.work_dir.resolve()
out.mkdir(parents=True, exist_ok=True)
checks, timings, metrics = [], {}, {}


def check(name, condition):
    assert condition, name
    checks.append(name)
    print('PASS', name, flush=True)


def render(name, png=False):
    scene = bpy.context.scene
    scene.render.image_settings.file_format = 'OPEN_EXR'
    scene.render.image_settings.color_depth = '32'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.filepath = str(out / (name + '.exr'))
    started = time.perf_counter()
    bpy.ops.render.render(write_still=True)
    timings[name] = time.perf_counter() - started
    image = bpy.data.images.load(scene.render.filepath, check_existing=False)
    data = np.empty(len(image.pixels), dtype=np.float32)
    image.pixels.foreach_get(data)
    data = data.reshape(image.size[1], image.size[0], 4)
    bpy.data.images.remove(image)
    if png:
        scene.render.image_settings.file_format = 'PNG'
        scene.render.image_settings.color_depth = '8'
        bpy.data.images['Render Result'].save_render(str(out / (name + '.png')), scene=scene)
    check('finite Cycles output: ' + name, np.isfinite(data).all())
    return data


def delta(a, b):
    return float(np.abs(a[:, :, :3] - b[:, :, :3]).mean())


addon.register()
scene = bpy.context.scene
for obj in list(scene.objects):
    if obj.type != 'CAMERA':
        bpy.data.objects.remove(obj, do_unlink=True)
cam = scene.camera
cam.location, cam.rotation_euler = (0, 0, 0), (0, 0, 0)
cam.data.type, cam.data.ortho_scale = 'ORTHO', 8
cam.data.dof.focus_distance, cam.data.dof.use_dof = 10, False
scene.render.engine, scene.cycles.device, scene.cycles.samples = 'CYCLES', 'CPU', 8
scene.render.compositor_device = 'CPU'
scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 384, 192, 100
scene.render.film_transparent = True
scene.world.color = (0.015, 0.015, 0.015)
mat = bpy.data.materials.new('Cycles Brush Test')
mat.use_nodes = True
tree = mat.node_tree
tree.nodes.clear()
uv, checker = tree.nodes.new('ShaderNodeTexCoord'), tree.nodes.new('ShaderNodeTexChecker')
checker.inputs['Scale'].default_value = 20
checker.inputs['Color1'].default_value, checker.inputs['Color2'].default_value = (0.035, 0.15, 0.28, 1), (0.65, 0.28, 0.06, 1)
emission, output = tree.nodes.new('ShaderNodeEmission'), tree.nodes.new('ShaderNodeOutputMaterial')
tree.links.new(uv.outputs['UV'], checker.inputs['Vector'])
tree.links.new(checker.outputs['Color'], emission.inputs['Color'])
tree.links.new(emission.outputs[0], output.inputs[0])
for x, depth in ((-2.5, 4), (0, 10), (2.5, 18)):
    bpy.ops.mesh.primitive_plane_add(size=2, location=(x, 0, -depth))
    bpy.context.object.data.materials.append(mat)
glow_mat = bpy.data.materials.new('Warm HDR Light')
glow_mat.use_nodes = True
g = glow_mat.node_tree
g.nodes.clear()
emission, output = g.nodes.new('ShaderNodeEmission'), g.nodes.new('ShaderNodeOutputMaterial')
emission.inputs['Color'].default_value, emission.inputs['Strength'].default_value = (1, 0.3, 0.04, 1), 12
g.links.new(emission.outputs[0], output.inputs[0])
for x in (-2.5, 0, 2.5):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=0.08, location=(x, 1.1, -8))
    bpy.context.object.data.materials.append(glow_mat)
lamp = bpy.context.object
check('fresh setup succeeds', bpy.ops.sdof.setup() == {'FINISHED'})
s = scene.sdof
check('v2 uses no per-frame handlers', not any(h.__module__.startswith('stylized_depth_of_field') for collection in (bpy.app.handlers.frame_change_pre, bpy.app.handlers.frame_change_post, bpy.app.handlers.render_pre, bpy.app.handlers.render_post) for h in collection))
check('new controls all have tooltips', all(s.bl_rna.properties[p].description for p in looks.CONTROLS.values()))
check('optional effects stay unbuilt by default', not looks.has(s.effect_tree, 'Aperture Blur') and not looks.has(s.effect_tree, 'Bloom Bypass'))
s.enabled = False
original = render('original', True)
s.enabled, s.radius, s.method = True, 14, 'PAINT'
styles = {}
for style in ('WATERCOLOR', 'OIL', 'GEOMETRIC'):
    s.paint_style = style
    check('style updates without errors: ' + style, not s.last_error)
    styles[style] = render('style_' + style.lower(), True)
    nodes.validate_effect(s.effect_tree, s, configured=True)
check('brush styles visibly differ', all(delta(styles[a], styles[b]) > 0.001 for a, b in (('WATERCOLOR', 'OIL'), ('OIL', 'GEOMETRIC'))))
s.paint_style = 'WATERCOLOR'
for prop, value in (('paint_sharpness', 0.95), ('paint_colors', 0.7), ('paint_pooling', 0.7),
                    ('paint_seed', 7), ('paint_canvas_scale', 7), ('paint_canvas_amount', 0.65)):
    old = getattr(s, prop)
    setattr(s, prop, value)
    pixels = render(prop)
    difference = delta(styles['WATERCOLOR'], pixels)
    metrics[prop + '_mean_delta'] = difference
    check('Paint control visibly affects render: ' + prop, difference > 0.00001)
    setattr(s, prop, old)
canvas = {}
for mode in ('CANVAS', 'PAPER', 'NONE'):
    s.paint_canvas = mode
    canvas[mode] = render('canvas_' + mode.lower())
check('canvas choices affect actual output', delta(canvas['CANVAS'], canvas['PAPER']) > 0.0001 and delta(canvas['NONE'], canvas['PAPER']) > 0.0001)
s.paint_canvas = 'CANVAS'
s.method, s.radius, s.defocus = 'KUWAHARA', 1, 14
bokehs = {}
for shape in ('GAUSSIAN', 'ROUND', 'POLYGON'):
    s.bokeh_shape, s.bokeh_blades, s.bokeh_roundness = shape, 3, 0
    bokehs[shape] = render('bokeh_' + shape.lower(), True)
    check('bokeh keeps alpha: ' + shape, np.abs(bokehs[shape][:, :, 3] - original[:, :, 3]).max() < 0.0001)
check('aperture shapes visibly differ', delta(bokehs['ROUND'], bokehs['POLYGON']) > 0.0001)
s.bokeh_rotation = 0.7
rotated = render('bokeh_rotated')
check('aperture rotation changes output', delta(rotated, bokehs['POLYGON']) > 0.0001)
s.bokeh_roundness = 1
rounded = render('bokeh_rounded')
check('roundness approaches circular bokeh', delta(rounded, bokehs['ROUND']) < 0.0001)
s.bokeh_shape, s.defocus, s.method, s.radius = 'GAUSSIAN', 0, 'PAINT', 14
no_bloom = render('bloom_off')
s.bloom_enabled, s.bloom_amount, s.bloom_spread, s.bloom_threshold = True, 0.8, 0.15, 0.5
blooms = {}
for style in ('SOFT', 'STEPPED'):
    s.bloom_style = style
    blooms[style] = render('bloom_' + style.lower(), True)
    check('bloom preserves alpha: ' + style, np.abs(blooms[style][:, :, 3] - no_bloom[:, :, 3]).max() < 0.0001)
    check('bloom adds visible light: ' + style, delta(blooms[style], no_bloom) > 0.002)
check('stepping affects glow output', delta(blooms['SOFT'], blooms['STEPPED']) > 0.0001)
for prop, value in (('bloom_steps', 2), ('bloom_softness', 0.1), ('bloom_breakup', 0.95), ('bloom_spread', 0.05), ('bloom_threshold', 10)):
    old = getattr(s, prop)
    setattr(s, prop, value)
    pixels = render(prop)
    check('bloom control affects output: ' + prop, delta(pixels, blooms['STEPPED']) > 0.00001)
    setattr(s, prop, old)
for device in ('CPU', 'GPU'):
    scene.render.compositor_device = device
    s.bloom_enabled = False
    device_no_bloom = render('bloom_off_' + device)
    s.bloom_enabled = True
    s.strength = 0
    bloom_only = render('bloom_only_' + device)
    s.strength = 1
    for prop, value, reference in (('bloom_enabled', False, device_no_bloom), ('bloom_amount', 0, device_no_bloom),
                                   ('enabled', False, original), ('strength', 0, bloom_only), ('radius', 0, bloom_only)):
        old = getattr(s, prop)
        setattr(s, prop, value)
        pixels = render('bypass_' + device + '_' + prop)
        check('exact bypass on ' + device + ': ' + prop, np.abs(pixels - reference).max() < 0.002)
        setattr(s, prop, old)
    pixels = render('bloom_active_' + device)
    metrics['CPU_GPU_' + device + '_mean_delta'] = delta(pixels, blooms['STEPPED'])
    check('CPU/GPU bloom agreement: ' + device, delta(pixels, blooms['STEPPED']) < 0.005)
scene.render.compositor_device = 'CPU'
s.paint_tracking, s.bloom_tracking = True, True
check('shared tracking passes enabled once', bpy.context.view_layer.use_pass_position and bpy.context.view_layer.use_pass_z)
s.method = 'BILATERAL'
check('bloom keeps Position and releases unused Depth after leaving Paint', bpy.context.view_layer.use_pass_position and not bpy.context.view_layer.use_pass_z)
s.bloom_style = 'SOFT'
check('soft bloom releases unused tracking passes', not bpy.context.view_layer.use_pass_position and not bpy.context.view_layer.use_pass_z)
s.bloom_style, s.method = 'STEPPED', 'PAINT'
check('tracked bloom and Paint pass diagnostics', core.health_report(bpy.context).startswith('Checks passed'))

# Simultaneous camera translation, focal length/focus, a moving light and
# keyframed native effect controls. Revisiting frames must not depend on history.
cam.data.type = 'PERSP'
s.bokeh_shape = 'ROUND'
for frame, focus, lens, amount, sharpness in ((1, 10, 38, 0.4, 0.4), (2, 4, 40, 0.7, 0.8), (3, 18, 42, 0.4, 0.4)):
    cam.location.x = (frame - 1) * 0.06
    cam.keyframe_insert(data_path='location', frame=frame)
    cam.data.lens = lens
    cam.data.keyframe_insert(data_path='lens', frame=frame)
    cam.data.dof.focus_distance = focus
    cam.data.dof.keyframe_insert(data_path='focus_distance', frame=frame)
    lamp.location.x = 2.5 + (frame - 1) * 0.025
    lamp.keyframe_insert(data_path='location', frame=frame)
    s.bloom_amount, s.paint_sharpness, s.defocus = amount, sharpness, 10
    for prop in ('bloom_amount', 'paint_sharpness', 'defocus'):
        s.keyframe_insert(data_path=prop, frame=frame)
for device in ('CPU', 'GPU'):
    scene.render.compositor_device = device
    visited = {}
    for frame in (1, 2, 3, 2, 1):
        scene.frame_set(frame)
        pixels = render('animation_%s_%d_%d' % (device, frame, len(timings)), png=True)
        check('camera focus keys evaluate on ' + device + ' frame ' + str(frame), abs(nodes.find(s.effect_tree, 'Focus Distance').outputs[0].default_value - {1: 10, 2: 4, 3: 18}[frame]) < 0.0001)
        check('effect keys evaluate on ' + device + ' frame ' + str(frame), abs(nodes.find(s.effect_tree, 'Bloom Amount').outputs[0].default_value - {1: .4, 2: .7, 3: .4}[frame]) < 0.0001)
        if frame in visited:
            difference = float(np.abs(pixels - visited[frame]).max())
            metrics['frame_repeat_' + device + '_' + str(frame)] = difference
            check('frame-order-independent output: ' + device + ' frame ' + str(frame), difference < 0.00001)
        visited[frame] = pixels
    check('animation actually changes', delta(visited[1], visited[3]) > 0.001)
scene.render.compositor_device = 'CPU'
scene.frame_set(2)
before = render('before_reopen')
blend = out / 'v2_tracked_animation.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(blend))
bpy.ops.wm.open_mainfile(filepath=str(blend))
scene, s = bpy.context.scene, bpy.context.scene.sdof
after = render('after_reopen')
check('v2 saved file renders identically after reopening', np.abs(before-after).max() < 0.00001)
check('reopened v2 diagnostics pass', core.health_report(bpy.context).startswith('Checks passed'))
counts = len(s.effect_tree.nodes), len(bpy.data.node_groups)
for _ in range(3):
    for shape in ('GAUSSIAN', 'POLYGON', 'ROUND'):
        s.bokeh_shape = shape
    for style in ('SOFT', 'STEPPED'):
        s.bloom_style = style
    bpy.ops.sdof.refresh()
check('repeated mode changes do not grow nodes or assets', counts == (len(s.effect_tree.nodes), len(bpy.data.node_groups)))

# Deliberately break generated links, then verify diagnostics and native rollback.
tree = s.effect_tree
glare = nodes.find(tree, 'Bloom Glow')
link = glare.inputs['Image'].links[0]
source = link.from_socket
tree.links.remove(link)
check('broken bloom graph is diagnosed', 'Bloom Glow' in core.health_report(bpy.context))
tree.links.new(source, glare.inputs['Image'])
check('removal releases shared passes', bpy.ops.sdof.remove() == {'FINISHED'} and not bpy.context.view_layer.use_pass_position)
s.bloom_enabled = False
s.bokeh_shape = 'GAUSSIAN'
check('fresh rebuild after removal', bpy.ops.sdof.setup() == {'FINISHED'})
counts = len(s.effect_tree.nodes), len(s.effect_tree.links), len(s.effect_tree.animation_data.drivers)
real_node = nodes.feature_node
def fail_late(*a, **kw):
    result = real_node(*a, **kw)
    if a[2] == 'Bloom Bypass':
        raise RuntimeError('Injected final bloom build failure')
    return result
nodes.feature_node = fail_late
try:
    s.bloom_enabled = True
finally:
    nodes.feature_node = real_node
check('failed bloom build leaves no nodes links or drivers', counts == (len(s.effect_tree.nodes), len(s.effect_tree.links), len(s.effect_tree.animation_data.drivers)) and 'Injected' in s.last_error)
check('failed bloom build retries cleanly', bpy.ops.sdof.refresh() == {'FINISHED'} and not s.last_error)
counts = len(s.effect_tree.nodes), len(s.effect_tree.links), len(s.effect_tree.animation_data.drivers)
def fail_aperture(*a, **kw):
    result = real_node(*a, **kw)
    if a[2] == 'Aperture Input':
        raise RuntimeError('Injected aperture build failure')
    return result
nodes.feature_node = fail_aperture
try:
    s.bokeh_shape = 'POLYGON'
finally:
    nodes.feature_node = real_node
check('failed aperture build restores the old graph', counts == (len(s.effect_tree.nodes), len(s.effect_tree.links), len(s.effect_tree.animation_data.drivers)) and not looks.has(s.effect_tree, 'Aperture Blur'))
check('failed aperture build retries cleanly', bpy.ops.sdof.refresh() == {'FINISHED'} and not s.last_error)
bpy.ops.sdof.remove()
if args.previous_blend:
    bpy.app.handlers.load_post.remove(addon._load_post)
    try:
        bpy.ops.wm.open_mainfile(filepath=str(args.previous_blend.resolve()))
    finally:
        bpy.app.handlers.load_post.append(addon._load_post)
    scene, s = bpy.context.scene, bpy.context.scene.sdof
    tree = s.effect_tree
    check('upgrade fixture is genuinely v1.3 graph', tree.get(nodes.GRAPH_VERSION) == 3)
    before = len(tree.nodes), len(tree.links), len(tree.animation_data.drivers), len(tree.interface.items_tree)
    links = {(l.from_node.name, l.from_socket.identifier, l.to_node.name, l.to_socket.identifier) for l in tree.links}
    old_driver = nodes.binding(nodes.find(tree, 'Maximum Radius').outputs[0]).as_pointer()
    configure = looks.configure
    def fail_upgrade(*a, **kw):
        configure(*a, **kw)
        raise RuntimeError('Injected final v2 upgrade failure')
    looks.configure = fail_upgrade
    try:
        try:
            nodes.upgrade_effect(tree, s)
        except RuntimeError:
            pass
    finally:
        looks.configure = configure
    check('late v2 upgrade rolls back nodes drivers interfaces and schema', before == (len(tree.nodes), len(tree.links), len(tree.animation_data.drivers), len(tree.interface.items_tree)) and tree.get(nodes.GRAPH_VERSION) == 3)
    check('late v2 upgrade restores every original link', links == {(l.from_node.name, l.from_socket.identifier, l.to_node.name, l.to_socket.identifier) for l in tree.links})
    nodes.upgrade_effect(tree, s)
    check('v2 upgrade retry preserves existing control curve identity', tree.get(nodes.GRAPH_VERSION) == looks.VERSION and nodes.binding(nodes.find(tree, 'Maximum Radius').outputs[0]).as_pointer() == old_driver)
    check('upgraded v1.3 keeps new effects opt-in', not s.bloom_enabled and s.bokeh_shape == 'GAUSSIAN')
    render('v1_3_0_upgraded')
    check('upgraded v1.3 removes cleanly', bpy.ops.sdof.remove() == {'FINISHED'})
addon.unregister()
report = {'version': '2.0.0', 'blender': bpy.app.version_string, 'passed': len(checks), 'checks': checks, 'metrics': metrics, 'render_seconds': timings}
(out / 'v2_results.json').write_text(json.dumps(report, indent=2))
print('V2_CHECKS_PASSED', len(checks), flush=True)
