"""Native camera focus where available; older bindings remain a fallback."""
import bpy
from . import nodes as ng

KINDS = {'Active Scene Camera': 'GeometryNodeInputActiveCamera', 'Native Camera Focus': 'GeometryNodeCameraInfo'}


def supported(tree):
    # Geometry node UI poll() rejects compositor trees even though these
    # specific native nodes are supported there in Blender 5.2/5.3.
    return tree.get(ng.GRAPH_VERSION, 1) >= 5 and all(getattr(bpy.types, kind, None) for kind in KINDS.values())


def active(tree):
    into = ng.find(tree, 'Focus Plus Offset', remember=False).inputs[0]
    return len(into.links) == 1 and into.links[0].from_node.get(ng.KEY) == 'Native Camera Focus'


def bind(tree, scene, journal):
    if scene.sdof.focus_mode != 'CAMERA' or not supported(tree):
        return False
    present = any(n.get(ng.KEY) in KINDS for n in tree.nodes)
    if present:
        nodes = ng.resolve(tree, KINDS)
    else:
        nodes = {key: ng.feature_node(tree, kind, key, journal) for key, kind in KINDS.items()}
    journal.wire(tree, nodes['Active Scene Camera'].outputs['Active Camera'], nodes['Native Camera Focus'].inputs['Camera'])
    journal.wire(tree, nodes['Native Camera Focus'].outputs['Focus Distance'], ng.find(tree, 'Focus Plus Offset').inputs[0])
    # Preserve an existing F-curve (including modifiers) for fallback/manual
    # mode, but do not evaluate its now-unneeded object references per frame.
    out = ng.find(tree, 'Focus Distance').outputs[0]
    curve = ng.binding(out)
    if curve:
        journal.driver(out, 'default_value')
        curve.mute = True
    return True


def validate(tree, scene):
    nodes = ng.resolve(tree, KINDS, remember=False)
    ng.require_link(tree, nodes['Active Scene Camera'], 'Active Camera', nodes['Native Camera Focus'], 'Camera')
    ng.require_link(tree, nodes['Native Camera Focus'], 'Focus Distance', ng.find(tree, 'Focus Plus Offset', remember=False), 0)
    if scene.sdof.focus_mode != 'CAMERA':
        return 'Focus source needs syncing.'
    camera = scene.camera
    if not camera or camera.type != 'CAMERA':
        return 'Choose an active scene camera or Manual Distance.'
    target, bone = camera.data.dof.focus_object, camera.data.dof.focus_subtarget
    if target and bone and (target.type != 'ARMATURE' or bone not in target.pose.bones):
        return 'The camera focus bone is missing. Correct the target before syncing.'
    return ''
