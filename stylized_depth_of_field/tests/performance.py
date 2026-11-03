"""Warm compositor timing; not a production-scene benchmark.

Blender --background --factory-startup --threads 8 --python this_file --
    --work-dir PATH [--device CPU|GPU] [--width 3840] [--height 2160]
Uses Blender's bundled NumPy, never personal preferences or project files.
"""
import argparse
import json
from pathlib import Path
import statistics
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
import numpy as np
import stylized_depth_of_field as addon
from stylized_depth_of_field import core

parser = argparse.ArgumentParser()
parser.add_argument('--work-dir', type=Path, required=True)
parser.add_argument('--device', choices=('CPU', 'GPU'), default='CPU')
parser.add_argument('--width', type=int, default=3840)
parser.add_argument('--height', type=int, default=2160)
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
args.work_dir.mkdir(parents=True, exist_ok=True)
report = {'blender': bpy.app.version_string, 'build': bpy.app.build_hash.decode(),
          'device': args.device, 'size': [args.width, args.height],
          'carrier': 'Empty Workbench scene, deterministic full-frame compositor inputs',
          'samples_per_case': 3, 'cases': []}
addon.register()
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.sdof.focus_mode, scene.sdof.manual_focus = 'MANUAL', 1
assert bpy.ops.sdof.setup() == {'FINISHED'}
s, tree = scene.sdof, scene.sdof.tree
scene.render.compositor_device = args.device
scene.render.resolution_x, scene.render.resolution_y = args.width, args.height
scene.render.resolution_percentage = 100
scene.render.engine = 'BLENDER_WORKBENCH'
for obj in list(scene.objects):
    if obj.type != 'CAMERA':
        bpy.data.objects.remove(obj, do_unlink=True)
yy, xx = np.ogrid[:args.height, :args.width]
data = np.ones((args.height, args.width, 4), dtype=np.float32)
checker = ((xx // 7 + yy // 7) % 2).astype(np.float32)
data[:, :, 0], data[:, :, 1], data[:, :, 2] = .05 + checker * .8, .15 + (1 - checker) * .45, .1 + checker * .2
instance = core.effect_instance(scene)
for name, keys in (('Image', ('Image', 'Guide AOV')), ('Depth', ('Depth AOV',))):
    image = bpy.data.images.new('Benchmark ' + name, width=args.width, height=args.height, float_buffer=True)
    image.colorspace_settings.name = 'Non-Color'
    if name == 'Depth':
        data[:, :, :3] = (6 + np.arange(args.width, dtype=np.float32) / args.width * 8)[None, :, None]
    image.pixels.foreach_set(data.reshape(-1))
    image.update()
    source = tree.nodes.new('CompositorNodeImage')
    source.image = image
    for key in keys:
        tree.links.new(source.outputs['Image'], instance.inputs[key])
    if name == 'Depth':
        tree.links.new(source.outputs['Alpha'], instance.inputs['Coverage AOV'])
del data, checker
s.radius, s.threshold, s.edge_protection = 8, 2, .1
frame = 0


def execute():
    global frame
    frame += 1
    scene.frame_set(frame)
    s.effect_tree.update_tag()
    bpy.context.view_layer.update()
    started = time.perf_counter()
    bpy.ops.render.render(write_still=False)
    return time.perf_counter() - started


for method in ('BILATERAL', 'KUWAHARA', 'PAINT'):
    s.method = method
    assert not s.last_error, s.last_error
    for state, enabled, strength, softness in (
            ('active', True, 1, 0), ('defocus_8px', True, 1, 8),
            ('disabled', False, 1, 8), ('zero_strength', True, 0, 8)):
        s.enabled, s.strength, s.defocus = enabled, strength, softness
        execute()
        times = [execute() for _ in range(3)]
        case = {'method': method, 'state': state, 'radius': s.radius, 'defocus': softness,
                'seconds': times, 'median_seconds': statistics.median(times)}
        report['cases'].append(case)
        (args.work_dir / 'performance.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print('BENCHMARK', method, state, round(case['median_seconds'], 4), flush=True)
addon.unregister()
print('PERFORMANCE_COMPLETE', flush=True)
