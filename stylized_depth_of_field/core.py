"""Scene setup, ownership checks and transactional material maintenance."""
import traceback
import uuid
from contextlib import contextmanager

import bpy
from . import nodes as ng
from .transaction import Journal

TAG, ROLE = ng.TAG, ng.ROLE
_suspended = set()
STATE = ('token', 'tree', 'backup_tree', 'effect_tree', 'shader_tree', 'bound_camera',
         'bound_target', 'bound_bone', 'layer_name', 'original_compositing',
         'paint_depth_added', 'paint_position_added')


def set_error(settings, message, source):
    settings.last_error, settings.error_source = str(message), source


def clear_error(settings, *sources):
    if not sources or settings.error_source in sources or not settings.error_source:
        settings.last_error = settings.error_source = ''


@contextmanager
def suspend(scene):
    key = scene.as_pointer()
    already = key in _suspended
    _suspended.add(key)
    try:
        yield
    finally:
        if not already:
            _suspended.discard(key)


def suspended(scene):
    return scene.as_pointer() in _suspended


def owned(node, token):
    return bool(token) and node.get(TAG) == token


def effect_instance(scene):
    tree, s = scene.compositing_node_group, scene.sdof
    if tree and s.token:
        return next((n for n in tree.nodes if owned(n, s.token) and n.get(ROLE) == 'instance'), None)
    return None


def installed(scene):
    return effect_instance(scene) is not None


def output_status(scene, tree=None):
    """Trace image sockets, respecting simple switches and native mute bypasses.

    Linked switches and opaque user groups are structural connections only;
    they cannot prove that the effect contributes to the rendered image.
    """
    tree = tree or scene.compositing_node_group
    if not tree:
        return 'DISCONNECTED'
    outputs = [n for n in tree.nodes if n.bl_idname == 'NodeGroupOutput']
    output = next((n for n in outputs if n.is_active_output), outputs[0] if outputs else None)
    if not output:
        return 'DISCONNECTED'
    first = next((x for x in output.inputs if x.bl_idname != 'NodeSocketVirtual'), None)
    pending = [(link.from_socket, False) for link in first.links] if first else []
    seen = set()
    uncertain = False
    while pending:
        source, unknown = pending.pop()
        n = source.node
        key = (source.as_pointer(), unknown)
        if key in seen:
            continue
        seen.add(key)
        if n.mute:
            inputs = [link.from_socket for link in n.internal_links if link.to_socket == source]
            pending.extend((link.from_socket, unknown) for x in inputs for link in x.links)
            continue
        if (owned(n, scene.sdof.token) and n.get(ROLE) == 'instance' and
                n.bl_idname == 'CompositorNodeGroup' and n.node_tree == scene.sdof.effect_tree and not n.mute):
            if not unknown:
                return 'CONNECTED'
            uncertain = True
            continue
        inputs = list(n.inputs)
        if n.bl_idname == 'CompositorNodeSwitch':
            switch = n.inputs.get('Switch')
            animation = n.id_data.animation_data
            animated = bool(switch and (ng.binding(switch) or (animation and animation.action)))
            if switch and not switch.is_linked and not animated:
                inputs = [n.inputs['On' if switch.default_value else 'Off']]
            else:
                inputs = [n.inputs['On'], n.inputs['Off']]
                unknown = True
        elif n.bl_idname == 'ShaderNodeMixRGB' and n.blend_type == 'MIX':
            factor = n.inputs[0]
            animation = n.id_data.animation_data
            if not factor.is_linked and not ng.binding(factor) and not (animation and animation.action):
                if factor.default_value <= 0:
                    inputs = [n.inputs[1]]
                elif factor.default_value >= 1:
                    inputs = [n.inputs[2]]
        elif n.bl_idname == 'CompositorNodeGroup':
            unknown = True
            # Trace nested structural reachability as uncertain, without
            # attempting to evaluate arbitrary user-group logic.
            outputs = [item for item in n.node_tree.nodes if item.bl_idname == 'NodeGroupOutput'] if n.node_tree else []
            output = next((item for item in outputs if item.is_active_output), outputs[0] if outputs else None)
            into = next((x for x in output.inputs if x.identifier == source.identifier), None) if output else None
            if into:
                pending.extend((link.from_socket, True) for link in into.links)
        pending.extend((link.from_socket, unknown) for x in inputs for link in x.links)
    return 'UNCERTAIN' if uncertain else 'DISCONNECTED'


def output_connected(scene, tree=None):
    return output_status(scene, tree) != 'DISCONNECTED'


def health_report(context):
    """Explicit diagnostic scan. No handlers, repairs or saved state changes."""
    scene, s = context.scene, context.scene.sdof
    if not s.token:
        return 'Build a setup first.'
    if foreign_setup(scene):
        return 'This scene shares another scene\'s setup. Detach it before editing.'
    issues = []
    for title, check in (
            ('Surface guide', lambda: ng.validate_shader(s.shader_tree, remember=False, settings=s)),
            ('Guide controls', lambda: ng.validate_controls(s.shader_tree, scene, shader=True, remember=False)),
            ('Effect', lambda: ng.validate_effect(s.effect_tree, s, remember=False, configured=True))):
        try:
            check()
        except (ReferenceError, RuntimeError, AttributeError, TypeError, KeyError) as exc:
            issues.append(title + ': ' + str(exc))
    focus = ng.focus_status(s.effect_tree, scene)
    if focus:
        issues.append(focus)
    if not scene.render.use_compositing:
        issues.append('Scene compositing is disabled. Use Enable Compositing to include the effect in renders.')
    routing = output_status(scene)
    if routing == 'DISCONNECTED':
        issues.append('The effect does not feed the active compositor output. Restore the configured compositor or its output links.')
    elif routing == 'UNCERTAIN':
        issues.append('The effect is routed through a linked/animated switch or a user group. Check the final render; its contribution cannot be confirmed here.')
    if scene.render.engine not in {'CYCLES', 'BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'}:
        issues.append('Choose Cycles or Eevee to render the required surface data.')
    layer = context.view_layer
    try:
        layer = configured_layer(scene, remember=False)
        for key, name in aov_names(s.token).items():
            aov = layer.aovs.get(name)
            if not aov or not aov.is_valid or aov.type != ('COLOR' if key == 'Guide' else 'VALUE'):
                issues.append('Missing or conflicting ' + key + ' pass. Refresh Materials, then rerender.')
        renders = [n for n in s.tree.nodes if owned(n, s.token) and n.get(ROLE) == 'render_data']
        instances = [n for n in s.tree.nodes if owned(n, s.token) and n.get(ROLE) == 'instance']
        if len(instances) != 1 or instances[0].node_tree != s.effect_tree:
            issues.append('The configured compositor effect was removed or replaced.')
        else:
            for key, name in aov_names(s.token).items():
                source = ng.socket(renders[0].outputs, name)
                links = instances[0].inputs[key + ' AOV'].links
                if len(links) != 1 or links[0].from_socket != source:
                    issues.append('Missing or changed ' + key + ' compositor pass link. Refresh Materials.')
            if s.method == 'PAINT' and s.paint_tracking:
                for flag, output, into in (('use_pass_z', 'Depth', 'Paint Depth'), ('use_pass_position', 'Position', 'Position')):
                    links = instances[0].inputs[into].links
                    source = renders[0].outputs.get(output)
                    if not getattr(layer, flag) or not source or len(links) != 1 or links[0].from_socket != source:
                        issues.append('Paint tracking needs its ' + output + ' pass. Refresh Materials, then render again.')
    except (ReferenceError, RuntimeError, AttributeError, TypeError, KeyError) as exc:
        issues.append(str(exc))
    mats, missing, no_uv, skipped = materials_for(context, layer)
    issues.extend(render_scan_warnings(context, layer))
    if missing or skipped or (no_uv and s.mapping == 'UV'):
        issues.append('The material scan has warnings; see the details below.')
    for mat in mats:
        roles = {}
        duplicate = False
        for n in mat.node_tree.nodes:
            if owned(n, s.token):
                role = n.get(ROLE)
                duplicate |= role in roles
                roles[role] = n
                if n.mute:
                    issues.append('Muted surface-data node in material ' + mat.name + ': ' + n.name + '. Unmute it, then refresh.')
        group = roles.get('material_group')
        valid = bool(group and group.bl_idname == 'ShaderNodeGroup' and group.node_tree == s.shader_tree and not duplicate)
        for key, name in aov_names(s.token).items():
            n = roles.get('aov_' + key)
            if not n or n.bl_idname != 'ShaderNodeOutputAOV' or getattr(n, 'aov_name', n.name) != name:
                valid = False
                continue
            links = n.inputs['Color' if key == 'Guide' else 'Value'].links
            if not group or len(links) != 1 or links[0].from_socket != group.outputs.get(key):
                valid = False
        if not valid:
            issues.append('Material needs Refresh: ' + mat.name)
    if s.guide_source == 'IMAGE' and not s.brush_image:
        issues.append('No brush image selected; Starter Patches are being used.')
    if s.brush_image and s.guide_source == 'IMAGE' and s.brush_image.source == 'FILE' and not s.brush_image.packed_file:
        import os
        path = bpy.path.abspath(s.brush_image.filepath, library=s.brush_image.library)
        if not os.path.isfile(path):
            issues.append('Brush image file is missing. Reload it or use Starter Patches.')
    summary = 'Checks passed for the current setup.' if not issues else 'Setup needs attention:\n' + '\n'.join(dict.fromkeys(issues))
    details = report_text(mats, missing, no_uv, skipped).replace('Materials connected:', 'Materials found in current scope:', 1)
    return summary + '\n\n' + details + '\nMaterial scan uses the current frame and configured view layer. Rerender after repairs.'


def foreign_setup(scene):
    s = scene.sdof
    return any(g and g.get('owner_scene') != scene for g in (s.effect_tree, s.shader_tree))


def check_owner(scene):
    if not scene.is_editable:
        raise RuntimeError('This scene is read-only. Make it local before editing the setup.')
    s = scene.sdof
    if foreign_setup(scene):
        raise RuntimeError('This is a shared scene copy. Use Detach Shared Setup, then build its own setup.')
    if s.token:
        for other in bpy.data.scenes:
            if other != scene and other.sdof.token == s.token:
                raise RuntimeError('Another scene shares this setup. Detach its shared setup before editing or removing this one.')
    for group in (s.tree, s.effect_tree, s.shader_tree):
        if group and not group.is_editable:
            raise RuntimeError('A setup node group is read-only. Make it local first.')


def aov_names(token):
    return {key: 'SDOF_' + token + '_' + key for key in ('Guide', 'Depth', 'Coverage')}


def materials_for(context, layer=None):
    """Scan once per setup/refresh, including evaluated geometry and instances."""
    s = context.scene.sdof
    layer = layer or context.view_layer
    layer.update()
    depsgraph = context.evaluated_depsgraph_get() if layer == context.view_layer else layer.depsgraph
    objects = [obj for obj in layer.objects if obj and (s.scope == 'SCENE' or obj.select_get(view_layer=layer))]
    scoped = {obj.as_pointer() for obj in objects}
    entries = [(obj, obj.evaluated_get(depsgraph)) for obj in objects]
    for instance in depsgraph.object_instances:
        if not instance.is_instance:
            continue
        parent = instance.parent.original if instance.parent else None
        if s.scope == 'SCENE' or (parent and parent.as_pointer() in scoped):
            entries.append((instance.object.original, instance.object))
    materials, missing, no_uv, skipped, seen = {}, set(), set(), set(), set()
    def add_material(mat):
        mat = mat.original
        if not mat.is_editable or not getattr(mat, 'use_nodes', True) or not mat.node_tree or not mat.node_tree.is_editable:
            skipped.add(mat.name)
        else:
            materials[mat.as_pointer()] = mat

    if layer.material_override:
        add_material(layer.material_override)
    for obj, evaluated in entries:
        key = (obj.as_pointer(), evaluated.data.as_pointer() if evaluated.data else 0)
        if key in seen:
            continue
        seen.add(key)
        if evaluated.type not in {'MESH', 'CURVE', 'CURVES', 'SURFACE', 'FONT', 'META'}:
            if evaluated.type in {'VOLUME', 'POINTCLOUD', 'GREASEPENCIL'}:
                skipped.add(obj.name + ' (' + evaluated.type + ': unsupported geometry)')
            continue
        if evaluated.type == 'MESH' and not evaluated.data.uv_layers:
            no_uv.add(obj.name)
        candidates = [slot.material for slot in obj.material_slots]
        # Set Material and converted geometry can add render materials without
        # changing original slots. Never attach branches to evaluated IDs.
        candidates.extend(getattr(evaluated.data, 'materials', ()))
        if not layer.material_override and (not candidates or any(mat is None for mat in candidates)):
            missing.add(obj.name)
        for mat in candidates:
            if not mat:
                continue
            add_material(mat)
    return list(materials.values()), sorted(missing), sorted(no_uv), sorted(skipped)


def render_scan_warnings(context, layer):
    """Warn about render-only geometry without evaluating an expensive render graph."""
    objects = (obj for obj in layer.objects if obj and (
        context.scene.sdof.scope == 'SCENE' or obj.select_get(view_layer=layer)))
    changed = [obj.name for obj in objects if any(
        mod.type == 'NODES' and mod.show_render != mod.show_viewport for mod in obj.modifiers)]
    if not changed:
        return []
    return ['Geometry Nodes render/viewport visibility differs: ' + ', '.join(changed) +
            '. The current-frame material scan may miss render materials. Enable the modifier in the viewport before Refresh, or add its render materials to the original slots.']


def ensure_aovs(layer, token, journal):
    names = aov_names(token)
    # Validate all existing passes before making the first edit.
    for key, name in names.items():
        aov = layer.aovs.get(name)
        expected = 'COLOR' if key == 'Guide' else 'VALUE'
        if aov and aov.type != expected:
            raise RuntimeError('AOV type conflict: ' + name)
    for key, name in names.items():
        aov = layer.aovs.get(name)
        if aov is None:
            aov = layer.aovs.add()
            journal.created_aov(layer, aov)
            aov.name = name
            aov.type = 'COLOR' if key == 'Guide' else 'VALUE'
        if not aov.is_valid:
            raise RuntimeError('Invalid or conflicting AOV: ' + name)
    layer.update_render_passes()


def attach_material(mat, group, token, journal):
    tree = mat.node_tree
    by_role = {}
    for n in tree.nodes:
        if owned(n, token):
            if n.mute:
                raise RuntimeError('Muted surface-data node in material ' + mat.name + ': ' + n.name + '. Unmute it, then refresh.')
            role = n.get(ROLE)
            if role in by_role:
                raise RuntimeError('Duplicate setup nodes in material ' + mat.name + '. Remove the duplicate or undo the manual edit.')
            by_role[role] = n
    instance = by_role.get('material_group')
    if instance and (instance.bl_idname != 'ShaderNodeGroup' or instance.node_tree != group):
        raise RuntimeError('The guide group was replaced in material ' + mat.name + '. Restore it before refreshing.')
    if instance is None:
        instance = tree.nodes.new('ShaderNodeGroup')
        journal.created_node(tree, instance)
        instance.node_tree = group
        instance.name = 'Stylized Surface Guide'
        instance.label = 'Surface Guide • AOV only'
        instance[TAG], instance[ROLE] = token, 'material_group'
        instance.location = (-200, min((n.location.y for n in tree.nodes if n != instance), default=0) - 350)
        instance.width = 230
    for i, (key, name) in enumerate(aov_names(token).items()):
        aov_node = by_role.get('aov_' + key)
        if aov_node and aov_node.bl_idname != 'ShaderNodeOutputAOV':
            raise RuntimeError('The ' + key + ' AOV node was replaced in material ' + mat.name)
        if aov_node is None:
            aov_node = tree.nodes.new('ShaderNodeOutputAOV')
            journal.created_node(tree, aov_node)
            aov_node[TAG], aov_node[ROLE] = token, 'aov_' + key
            aov_node.label = 'Surface Guide • ' + key
            aov_node.location = (instance.location.x + 300, instance.location.y - i * 160)
        journal.set(aov_node, 'name', name)
        if hasattr(aov_node, 'aov_name'):
            journal.set(aov_node, 'aov_name', name)
        journal.wire(tree, instance.outputs[key], aov_node.inputs['Color' if key == 'Guide' else 'Value'])


def bypass(tree, token, tag=TAG, role_key=ROLE, effect=None):
    """Remove an effect from a private tree, preserving downstream edits."""
    for node in list(tree.nodes):
        if ((node.get(tag) == token and node.get(role_key) == 'instance') or
                (effect and node.bl_idname == 'CompositorNodeGroup' and node.node_tree == effect)):
            source = node.inputs['Image'].links[0].from_socket if node.inputs['Image'].is_linked else None
            sinks = [link.to_socket for link in tree.links if link.from_node == node]
            if source:
                for sink in sinks:
                    ng.wire(tree, source, sink)
            else:
                # Preserve an unlinked constant image too.
                value = tuple(node.inputs['Image'].default_value)
                for sink in sinks:
                    if hasattr(sink, 'default_value'):
                        sink.default_value = value
            tree.nodes.remove(node)
    for node in list(tree.nodes):
        if node.get(tag) == token and node.get(role_key) == 'render_data':
            if any(s.is_linked for s in node.outputs):
                del node[tag]
                del node[role_key]
                node.name, node.label = 'Render Layers', ''
            else:
                tree.nodes.remove(node)


def retarget_scene_sources(tree, owner, scene, token, tag=TAG, role_key=ROLE):
    for n in tree.nodes:
        if n.bl_idname != 'CompositorNodeRLayers':
            continue
        if (n.get(tag) == token and n.get(role_key) == 'render_data') or (owner and n.scene == owner):
            layer = scene.view_layers.get(n.layer)
            if layer is None and len(scene.view_layers) == 1:
                layer = scene.view_layers[0]
            if layer is None:
                raise RuntimeError('The copied scene has no matching view layer. Restore its layer before updating the setup.')
            n.scene, n.layer = scene, layer.name


def make_compositor(scene, layer, effect, token, legacy=None):
    old = scene.compositing_node_group
    tree = old.copy() if old else bpy.data.node_groups.new('Stylized DOF Compositor', 'CompositorNodeTree')
    tree.name = 'Stylized DOF Compositor • ' + scene.name
    tree[TAG], tree[ROLE] = token, 'compositor'
    tree['owner_scene'] = scene
    try:
        if legacy:
            render = next((n for n in tree.nodes if n.get(legacy[1]) == legacy[0] and n.get(legacy[2]) == 'render_data'), None)
            retarget_scene_sources(tree, render.scene if render else None, scene, *legacy)
            bypass(tree, *legacy)
        outputs = [n for n in tree.nodes if n.bl_idname == 'NodeGroupOutput']
        output = next((n for n in outputs if n.is_active_output), outputs[0] if outputs else None)
        if output is None:
            sockets = [x for x in tree.interface.items_tree if x.item_type == 'SOCKET' and x.in_out == 'OUTPUT']
            if not sockets:
                ng.interface(tree, 'Image', 'OUTPUT', 'NodeSocketColor')
            output = ng.node(tree, 'NodeGroupOutput', 'Image Output', 750, 200)
        first = next((s for s in output.inputs if s.bl_idname != 'NodeSocketVirtual'), None)
        if first is None or first.type != 'RGBA':
            raise RuntimeError("The compositor's first output must be a Color socket.")
        render = ng.node(tree, 'CompositorNodeRLayers', 'Stylized DOF AOVs', output.location.x - 700, output.location.y - 350)
        render.scene, render.layer = scene, layer.name
        render[TAG], render[ROLE] = token, 'render_data'
        source = first.links[0].from_socket if first.is_linked else (None if old and outputs else render.outputs['Image'])
        instance = ng.node(tree, 'CompositorNodeGroup', 'Stylized Depth of Field', output.location.x - 330, output.location.y)
        instance.node_tree, instance.width = effect, 260
        instance[TAG], instance[ROLE] = token, 'instance'
        viewers = [l.to_socket for l in tree.links if l.from_socket == source and l.to_node.bl_idname == 'CompositorNodeViewer']
        if source:
            ng.wire(tree, source, instance.inputs['Image'])
        else:
            instance.inputs['Image'].default_value = tuple(first.default_value)
        for key, name in aov_names(token).items():
            ng.wire(tree, ng.socket(render.outputs, name), instance.inputs[key + ' AOV'])
        ng.wire(tree, instance.outputs['Image'], first)
        for sink in viewers:
            ng.wire(tree, instance.outputs['Image'], sink)
        return tree
    except Exception:
        bpy.data.node_groups.remove(tree)
        raise


def configured_layer(scene, journal=None, remember=True):
    s = scene.sdof
    renders = [n for n in s.tree.nodes if owned(n, s.token) and n.get(ROLE) == 'render_data'] if s.tree else []
    if len(renders) != 1 or renders[0].scene != scene:
        raise RuntimeError('The setup Render Layers node was removed or replaced. Restore it before refreshing.')
    if renders[0].mute:
        raise RuntimeError('The setup Render Layers node is muted. Unmute it, then refresh.')
    # Follow renamed view layers through Blender's native Render Layers reference.
    layer = scene.view_layers.get(renders[0].layer)
    if layer is None:
        raise RuntimeError('The configured view layer was removed. Remove and rebuild the setup.')
    if remember:
        if journal:
            journal.set(s, 'layer_name', layer.name)
        else:
            s.layer_name = layer.name
    return layer


def sync_paint_tracking(scene, journal, release=False):
    """Use native passes only for optional Paint tracking; preserve user users."""
    s = scene.sdof
    wanted = not release and s.method == 'PAINT' and s.paint_tracking
    if not wanted and not (s.paint_depth_added or s.paint_position_added):
        return
    layer = configured_layer(scene, journal) if wanted else scene.view_layers.get(s.layer_name)
    if layer is None:
        return
    sources = [(tree, n) for tree in bpy.data.node_groups if tree.bl_idname == 'CompositorNodeTree' and (tree.users or tree == s.tree)
               for n in tree.nodes if n.bl_idname == 'CompositorNodeRLayers' and
               n.scene in (None, scene) and n.layer == layer.name]
    for flag, marker, output, into in (
            ('use_pass_z', 'paint_depth_added', 'Depth', 'Paint Depth'),
            ('use_pass_position', 'paint_position_added', 'Position', 'Position')):
        if wanted and not getattr(layer, flag):
            journal.render_pass(layer, flag, True, sources)
            journal.set(s, marker, True)
        elif not wanted and getattr(s, marker):
            external = any(not (owned(link.to_node, s.token) and link.to_node.get(ROLE) == 'instance' and
                               link.to_socket.name == into) for tree, n in sources
                           for out in n.outputs if out.name == output for link in out.links)
            if not external:
                journal.render_pass(layer, flag, False, sources)
            journal.set(s, marker, False)
    if wanted:
        render = next(n for n in s.tree.nodes if owned(n, s.token) and n.get(ROLE) == 'render_data')
        instance = next(n for n in s.tree.nodes if owned(n, s.token) and n.get(ROLE) == 'instance')
        for output, into in (('Depth', 'Paint Depth'), ('Position', 'Position')):
            journal.wire(s.tree, ng.socket(render.outputs, output), instance.inputs[into])


def report_text(mats, missing, no_uv, skipped):
    lines = ['Materials connected: %d' % len(mats)]
    if missing:
        lines.append('Missing or empty material slots: ' + ', '.join(missing))
    if no_uv:
        lines.append('No UV map (guide flat in UV mode): ' + ', '.join(no_uv))
    if skipped:
        lines.append('Skipped materials or unsupported geometry: ' + ', '.join(skipped))
    return '\n'.join(lines)


def build(context, legacy=None, layer=None, materials=None, restore_state=None):
    scene, s = context.scene, context.scene.sdof
    ng.check_capabilities()
    check_owner(scene)
    if scene.render.engine not in {'CYCLES', 'BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'}:
        raise RuntimeError('Choose Cycles or Eevee to render shader AOVs.')
    if s.token or s.effect_tree or s.shader_tree:
        raise RuntimeError('A setup already exists. Remove it before building another.')
    layer = layer or context.view_layer
    mats, missing, no_uv, skipped = materials_for(context, layer)
    scan_warnings = render_scan_warnings(context, layer)
    if materials is not None:
        mats = materials
    if not mats:
        raise RuntimeError('No editable node materials found. Assign a material or change the material scope.')
    journal, groups = Journal(), []
    token = uuid.uuid4().hex[:16]
    old_tree, old_compositing = scene.compositing_node_group, scene.render.use_compositing
    previous = {key: getattr(s, key) for key in STATE}
    try:
        with suspend(scene):
            shader = ng.build_shader(scene, token)
            groups.append(shader)
            shader['owner_scene'] = scene
            effect = ng.build_effect(scene, token)
            groups.append(effect)
            effect['owner_scene'] = scene
            ensure_aovs(layer, token, journal)
            for mat in mats:
                attach_material(mat, shader, token, journal)
            tree = make_compositor(scene, layer, effect, token, legacy)
            groups.append(tree)
            s.token = token
            s.tree, s.backup_tree = tree, restore_state[0] if restore_state else old_tree
            s.effect_tree, s.shader_tree = effect, shader
            s.layer_name = layer.name
            s.original_compositing = restore_state[1] if restore_state else old_compositing
            scene.compositing_node_group = tree
            scene.render.use_compositing = True
            effect_instance(scene).mute = False
            sync_paint_tracking(scene, journal)
        context.view_layer.update()
        clear_error(s)
        s.last_report = '\n'.join([report_text(mats, missing, no_uv, skipped)] + scan_warnings)
        journal.commit()
        return mats, bool(missing or (no_uv and s.mapping == 'UV') or skipped or scan_warnings)
    except Exception:
        with suspend(scene):
            scene.compositing_node_group = old_tree
            scene.render.use_compositing = old_compositing
            for key, value in previous.items():
                setattr(s, key, value)
        failures = journal.rollback()
        layer.update_render_passes()
        for group in reversed(groups):
            if group.users == 0:
                bpy.data.node_groups.remove(group)
        from . import paint
        paint.cleanup_unused()
        if failures:
            print('Stylized DOF rollback warnings:', failures)
        raise


def execute_setup(operator, context):
    if installed(context.scene):
        operator.report({'INFO'}, 'Already set up. Use Add / Refresh Materials for new objects.')
        return {'FINISHED'}
    try:
        from .migration import has_legacy
        if has_legacy(context.scene):
            raise RuntimeError('Use Migrate Saved Setup to preserve the existing setup first.')
        mats, warning = build(context)
        operator.report({'WARNING'} if warning else {'INFO'}, 'Ready: %d materials. Render again to create AOVs.%s' %
                        (len(mats), ' See Setup Report.' if warning else ''))
        return {'FINISHED'}
    except Exception as exc:
        set_error(context.scene.sdof, exc, 'SETUP')
        traceback.print_exc()
        operator.report({'ERROR'}, 'Setup rolled back: ' + str(exc))
        return {'CANCELLED'}


def execute_refresh(operator, context):
    scene, s = context.scene, context.scene.sdof
    journal = Journal()
    layer = None
    component = 'MATERIALS'
    try:
        check_owner(scene)
        if not s.shader_tree or not s.effect_tree or not s.token:
            raise RuntimeError('Build the setup first.')
        component = 'GUIDE'
        ng.update_shader(s.shader_tree, s, journal)
        component = 'EFFECT'
        ng.update_effect(s.effect_tree, s, journal)
        component = 'MATERIALS'
        active = effect_instance(scene)
        if active:
            if active.node_tree != s.effect_tree:
                raise RuntimeError('The active compositor effect was replaced. Restore it before refreshing.')
            journal.set(s, 'tree', scene.compositing_node_group)
        layer = configured_layer(scene, journal)
        mats, missing, no_uv, skipped = materials_for(context, layer)
        scan_warnings = render_scan_warnings(context, layer)
        ensure_aovs(layer, s.token, journal)
        for mat in mats:
            attach_material(mat, s.shader_tree, s.token, journal)
        # Recreating a deleted pass also recreates its Render Layers socket.
        # Restore those links transactionally, including disconnected setups.
        renders = [n for n in s.tree.nodes if owned(n, s.token) and n.get(ROLE) == 'render_data']
        instances = [n for n in s.tree.nodes if owned(n, s.token) and n.get(ROLE) == 'instance']
        if len(instances) != 1 or instances[0].node_tree != s.effect_tree:
            raise RuntimeError('The compositor effect was removed or replaced. Restore it before refreshing.')
        if instances[0].mute:
            raise RuntimeError('The compositor effect is muted. Unmute it, then refresh.')
        for key, name in aov_names(s.token).items():
            journal.wire(s.tree, ng.socket(renders[0].outputs, name), instances[0].inputs[key + ' AOV'])
        sync_paint_tracking(scene, journal)
        component = 'FOCUS'
        ng.bind_focus(s.effect_tree, scene, journal)
        journal.set(s, 'last_report', '\n'.join([report_text(mats, missing, no_uv, skipped)] + scan_warnings))
        s.shader_tree.update_tag()
        s.effect_tree.update_tag()
        scene.update_tag()
        context.view_layer.update()
        clear_error(s, 'MATERIALS', 'GUIDE', 'EFFECT', 'FOCUS')
        journal.commit()
        warning = bool(missing or skipped or (no_uv and s.mapping == 'UV') or scan_warnings)
        operator.report({'WARNING'} if warning else {'INFO'}, 'Updated %d materials. Rerender to refresh the AOVs.%s' % (len(mats), ' See Setup Report.' if warning else ''))
        return {'FINISHED'}
    except Exception as exc:
        journal.rollback()
        if layer:
            layer.update_render_passes()
        set_error(s, exc, component)
        operator.report({'ERROR'}, 'Refresh rolled back: ' + str(exc))
        return {'CANCELLED'}


def clear_state(scene):
    s = scene.sdof
    with suspend(scene):
        for key in ('shader_tree', 'effect_tree', 'tree', 'backup_tree', 'bound_camera', 'bound_target'):
            setattr(s, key, None)
        s.token = s.layer_name = s.bound_bone = s.last_report = ''
        s.paint_depth_added = s.paint_position_added = False
        clear_error(s)


def execute_detach(operator, context):
    scene, s = context.scene, context.scene.sdof
    if not scene.is_editable or not foreign_setup(scene):
        operator.report({'ERROR'}, 'Only an editable shared scene copy can be detached.')
        return {'CANCELLED'}
    journal, tree = Journal(), None
    original = scene.compositing_node_group
    previous = {key: getattr(s, key) for key in (*STATE, 'last_report', 'last_error', 'error_source')}
    try:
        if original:
            tree = original.copy()
            try:
                owner = next((g.get('owner_scene') for g in (s.effect_tree, s.shader_tree, s.tree)
                              if g and g.get('owner_scene')), None)
                retarget_scene_sources(tree, owner, scene, s.token)
                bypass(tree, s.token)
            except Exception:
                bpy.data.node_groups.remove(tree)
                tree = None
                raise
            journal.set(scene, 'compositing_node_group', tree)
            tree.name = 'Compositor • ' + scene.name
            for key in (TAG, ROLE, 'owner_scene'):
                if key in tree:
                    del tree[key]
        for layer in scene.view_layers:
            for name in aov_names(s.token).values():
                aov = layer.aovs.get(name)
                if aov:
                    journal.removed_aov(layer, aov)
            layer.update_render_passes()
        journal.set(scene.render, 'use_compositing', s.original_compositing)
        sync_paint_tracking(scene, journal, release=True)
        clear_state(scene)
        context.view_layer.update()
        journal.commit()
        operator.report({'INFO'}, 'Shared setup detached from this scene. Build its own setup now.')
        return {'FINISHED'}
    except Exception as exc:
        failures = journal.rollback()
        with suspend(scene):
            for key, value in previous.items():
                setattr(s, key, value)
        for layer in scene.view_layers:
            layer.update_render_passes()
        if tree and tree.users == 0:
            bpy.data.node_groups.remove(tree)
        if failures:
            print('Stylized DOF detach rollback warnings:', failures)
        operator.report({'ERROR'}, 'Detach rolled back: ' + str(exc))
        return {'CANCELLED'}


def compositor_trees(root):
    """Walk group references only during removal, never during rendering."""
    pending, seen = [root] if root else [], set()
    while pending:
        tree = pending.pop()
        if tree in seen:
            continue
        seen.add(tree)
        yield tree
        pending.extend(n.node_tree for n in tree.nodes if n.bl_idname == 'CompositorNodeGroup' and n.node_tree)


def execute_remove(operator, context):
    scene, s = context.scene, context.scene.sdof
    mutated = False
    try:
        check_owner(scene)
        if not s.token:
            return {'FINISHED'}
        token, shader, effect = s.token, s.shader_tree, s.effect_tree
        trees = [tree for tree in bpy.data.node_groups if tree.bl_idname == 'CompositorNodeTree' and
                 (tree == s.tree or any((owned(n, token) and n.get(ROLE) in {'instance', 'render_data'}) or
                   (effect and n.bl_idname == 'CompositorNodeGroup' and n.node_tree == effect) for n in tree.nodes))]
        for tree in trees:
            if not tree.is_editable:
                raise RuntimeError('A compositor using this setup is read-only. Make it local before removal.')
        for other in bpy.data.scenes:
            if other != scene and any(tree in trees for tree in compositor_trees(other.compositing_node_group)):
                raise RuntimeError('Another scene uses a compositor from this setup. Detach or replace its compositor before removal.')
        # Complete all predictable checks before deleting a node.
        material_trees = []
        for mat in bpy.data.materials:
            if mat.node_tree and any(owned(n, token) for n in mat.node_tree.nodes):
                if not mat.is_editable or not mat.node_tree.is_editable:
                    raise RuntimeError('Material ' + mat.name + ' is read-only. Make it local before removal.')
                material_trees.append(mat.node_tree)
        # Validate every bypass privately before mutating retained user trees.
        for tree in trees:
            probe = tree.copy()
            try:
                bypass(probe, token, effect=effect)
            finally:
                bpy.data.node_groups.remove(probe)
        mutated = True
        pass_journal = Journal()
        try:
            sync_paint_tracking(scene, pass_journal, release=True)
            pass_journal.commit()
        except Exception:
            pass_journal.rollback()
            raise
        if any(tree in trees for tree in compositor_trees(scene.compositing_node_group)):
            scene.render.use_compositing = s.original_compositing
        for tree in trees:
            bypass(tree, token, effect=effect)
            if tree.get(TAG) == token:
                for key in (TAG, ROLE, 'owner_scene'):
                    if key in tree:
                        del tree[key]
        for tree in material_trees:
            for n in list(tree.nodes):
                if owned(n, token):
                    tree.nodes.remove(n)
        for layer in scene.view_layers:
            for name in aov_names(token).values():
                aov = layer.aovs.get(name)
                if aov:
                    layer.aovs.remove(aov)
            layer.update_render_passes()
        clear_state(scene)
        # The detached original setup tree can safely become an orphan; keep
        # user-created references intact and delete only unused owned groups.
        for group in dict.fromkeys((*trees, effect, shader)):
            if group and group.users == 0:
                bpy.data.node_groups.remove(group)
        from . import paint
        paint.cleanup_unused()
        operator.report({'INFO'}, 'Setup removed. Material surfaces and compositor edits retained.')
        return {'FINISHED'}
    except Exception as exc:
        traceback.print_exc()
        set_error(s, exc, 'REMOVAL')
        # FINISHED retains the operator's Undo step after an unexpected late
        # failure. CANCELLED would discard it despite already changed data.
        operator.report({'WARNING'} if mutated else {'ERROR'}, 'Removal could not finish: ' + str(exc) +
                        ('. Use Undo to restore the setup.' if mutated else '. No setup data was removed.'))
        return {'FINISHED'} if mutated else {'CANCELLED'}
