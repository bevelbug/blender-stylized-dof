"""Native enable/timer and real Undo checks in an isolated Blender event loop."""
import sys
import json
import traceback
from pathlib import Path
sys.dont_write_bytecode = True
import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--work-dir', type=Path, required=True)
parser.add_argument('--previous-blend', type=Path, help='Optional older setup to open before native enabling')
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
out_dir = args.work_dir.resolve()
out_dir.mkdir(parents=True, exist_ok=True)
(out_dir / 'event_loop_error.txt').unlink(missing_ok=True)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
import addon_utils

if args.previous_blend:
    bpy.ops.wm.open_mainfile(filepath=str(args.previous_blend.resolve()))
errors, passed = [], []
addon = addon_utils.enable('stylized_depth_of_field', default_set=False, handle_error=errors.append)
assert addon and not errors
assert bpy.app.timers.is_registered(addon._initialize_once)
old_count = len(bpy.context.scene.sdof.effect_tree.nodes) if args.previous_blend else 0
old_version = bpy.context.scene.sdof.effect_tree.get(addon.ng.GRAPH_VERSION, 1) if args.previous_blend else 5
phase = 0
material_names = []


def check(name, condition):
    assert condition, name
    passed.append(name)
    print('PASS', name, flush=True)


def step():
    global phase
    try:
        window = bpy.context.window
        area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
        region = next(r for r in area.regions if r.type == 'WINDOW')
        with bpy.context.temp_override(window=window, area=area, region=region):
            scene = bpy.context.scene
            if phase == 0:
                check('one-shot initialization ran and stopped', not bpy.app.timers.is_registered(addon._initialize_once))
                if args.previous_blend:
                    tree = scene.sdof.effect_tree
                    added = (1 if old_version < 2 else 0) + (len(addon.ng.DEFOCUS_NODES) if old_version < 3 else 0) + (len(addon.ng.looks.CONTROLS) if old_version < 4 else 0)
                    if old_version < 5:
                        added += len(addon.ng.refinements.CONTROLS) + len(addon.ng.refinements.NODES)
                        if addon.ng.camera_focus.active(tree):
                            added += 2
                        if addon.ng.looks.has(tree, 'Bloom Bypass'):
                            added += 5
                    if old_version < 6:
                        added += len(addon.ng.edges.NODES)
                    check('deferred enable upgrades an already open older setup', tree.get(addon.ng.GRAPH_VERSION) == addon.ng.looks.VERSION and len(tree.nodes) == old_count + added)
                    check('deferred upgrade retains a healthy saved setup', addon.core.health_report(bpy.context).startswith('Checks passed'))
                    bpy.ops.sdof.remove()
                    # The upgrade fixture may have keyed look controls. Start
                    # the independent Undo scenario without those scene keys.
                    scene.animation_data_clear()
                scene.render.engine = 'CYCLES'
                bpy.ops.ed.undo_push(message='Disposable initial scene')
                bpy.ops.sdof.setup()
                check('native event-loop setup', addon.core.installed(scene))
                scene.sdof.method, scene.sdof.paint_tracking, scene.sdof.defocus = 'PAINT', True, 4
                check('native event-loop Paint tracking prepares passes', not scene.sdof.last_error and scene.view_layers[0].use_pass_z and scene.view_layers[0].use_pass_position)
                scene.sdof.bloom_enabled, scene.sdof.bloom_tracking = True, True
                scene.sdof.bokeh_shape = 'POLYGON'
                check('native event-loop v2 effects build cleanly', not scene.sdof.last_error and addon.ng.looks.has(scene.sdof.effect_tree, 'Bloom Bypass') and addon.ng.looks.has(scene.sdof.effect_tree, 'Aperture Blur'))
                material_names[:] = [m.name for m in bpy.data.materials if m.node_tree and any(
                    addon.core.owned(n, scene.sdof.token) for n in m.node_tree.nodes)]
            elif phase == 1:
                bpy.ops.ed.undo_push(message='Final effect preview')
                bpy.ops.sdof.preview_bloom()
                bpy.ops.ed.undo_push(message='Bloom only preview')
                bpy.ops.ed.undo()
                check('bloom preview Undo restores final output', bpy.context.scene.sdof.preview == 'RESULT')
                bpy.ops.ed.redo()
                check('bloom preview Redo restores isolated glow', bpy.context.scene.sdof.preview == 'BLOOM')
                bpy.ops.sdof.preview_bloom()
                check('bloom preview button returns to final output', bpy.context.scene.sdof.preview == 'RESULT')
                scene = bpy.context.scene
                scene.render.use_compositing = False
                bpy.ops.ed.undo_push(message='Compositing disabled')
                bpy.ops.sdof.enable_compositing()
                bpy.ops.ed.undo_push(message='Enabled compositing')
            elif phase == 2:
                bpy.ops.ed.undo()
                check('Enable Compositing Undo restores bypass', not bpy.context.scene.render.use_compositing)
                bpy.ops.ed.redo()
                check('Enable Compositing Redo restores enabled state', bpy.context.scene.render.use_compositing)
                scene = bpy.context.scene
                other = bpy.data.node_groups.new('Disposable Alternative', 'CompositorNodeTree')
                scene.compositing_node_group = other
                bpy.ops.ed.undo_push(message='Alternative compositor')
                bpy.ops.sdof.restore_compositor()
                bpy.ops.ed.undo_push(message='Restored compositor')
            elif phase == 3:
                bpy.ops.ed.undo()
                check('Restore Compositor Undo retains alternative', bpy.context.scene.compositing_node_group.name == 'Disposable Alternative')
                bpy.ops.ed.redo()
                check('Restore Compositor Redo uses configured graph', addon.core.installed(bpy.context.scene))
                scene = bpy.context.scene
                copy = scene.copy()
                copy.name = 'Disposable Copy'
                window.scene = copy
                bpy.ops.ed.undo_push(message='Shared scene copy')
                bpy.ops.sdof.detach()
                bpy.ops.ed.undo_push(message='Detached scene')
                check('native detach clears copied state', not copy.sdof.token)
            elif phase == 4:
                bpy.ops.ed.undo()
                copied = bpy.data.scenes['Disposable Copy']
                check('Detach Undo restores copied metadata and AOVs', bool(copied.sdof.token) and len(copied.view_layers[0].aovs) == 3)
                bpy.ops.ed.redo()
                copied = bpy.data.scenes['Disposable Copy']
                check('Detach Redo removes copied state and AOVs', not copied.sdof.token and not copied.view_layers[0].aovs)
                original = next(s for s in bpy.data.scenes if s.sdof.token)
                window.scene = original
                bpy.ops.ed.undo_push(message='Configured original')
                real_clear = addon.core.clear_state

                def fail_clear(scene):
                    real_clear(scene)
                    raise RuntimeError('Injected late removal failure for Undo verification')

                addon.core.clear_state = fail_clear
                try:
                    bpy.ops.sdof.remove()
                finally:
                    addon.core.clear_state = real_clear
                bpy.ops.ed.undo_push(message='Interrupted removal')
                check('unexpected removal failure reports recovery', bpy.context.scene.sdof.error_source == 'REMOVAL')
            elif phase == 5:
                bpy.ops.ed.undo()
                scene = bpy.context.scene
                check('late removal Undo restores working setup', addon.core.installed(scene) and len(scene.view_layers[0].aovs) == 3)
                check('late removal Undo restores material branches', bool(material_names) and all(len([
                    n for n in bpy.data.materials[name].node_tree.nodes if addon.core.owned(n, scene.sdof.token)]) == 4 for name in material_names))
                check('late removal Undo restores healthy controls', addon.core.health_report(bpy.context).startswith('Checks passed'))
                check('late removal Undo restores Paint tracking and softness', scene.sdof.method == 'PAINT' and scene.sdof.defocus == 4 and scene.view_layers[0].use_pass_position)
                bpy.ops.sdof.remove()
                bpy.ops.ed.undo_push(message='Removed tracked Paint setup')
            elif phase == 6:
                bpy.ops.ed.undo()
                scene = bpy.context.scene
                check('complete removal Undo restores bundled Paint graph', addon.core.installed(scene) and addon.core.health_report(bpy.context).startswith('Checks passed'))
                check('complete removal Undo restores v2 controls and graphs', scene.sdof.bloom_enabled and scene.sdof.bokeh_shape == 'POLYGON' and addon.ng.looks.has(scene.sdof.effect_tree, 'Bloom Bypass') and addon.ng.looks.has(scene.sdof.effect_tree, 'Aperture Blur'))
                check('complete removal Undo restores native tracking passes', scene.view_layers[0].use_pass_z and scene.view_layers[0].use_pass_position)
                bpy.ops.ed.redo()
                check('complete removal Redo clears tracking and owned assets', not bpy.context.scene.sdof.token and not bpy.context.view_layer.use_pass_position and not any(g.get('sdof_paint_asset') for g in bpy.data.node_groups))
                addon_utils.disable('stylized_depth_of_field', default_set=False, handle_error=errors.append)
                check('event-loop disable leaves no schema or timer', not errors and not hasattr(bpy.types.Scene, 'sdof') and not bpy.app.timers.is_registered(addon._initialize_once))
                (out_dir / 'event_loop_results.json').write_text(json.dumps({'passed': len(passed), 'checks': passed}, indent=2))
                print('EVENT_LOOP_CHECKS_PASSED', flush=True)
                bpy.ops.wm.quit_blender()
                return None
        phase += 1
        return 0.15
    except Exception:
        traceback.print_exc()
        (out_dir / 'event_loop_error.txt').write_text(traceback.format_exc())
        bpy.ops.wm.quit_blender()
        return None


bpy.app.timers.register(step, first_interval=0.25)
