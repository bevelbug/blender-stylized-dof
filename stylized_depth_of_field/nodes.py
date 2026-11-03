"""Native Blender 5.2 shader/compositor builders. No render-time Python."""
import bpy

TAG = "sdof_owner"
ROLE = "sdof_role"
KEY = "sdof_key"
GRAPH_VERSION = 'sdof_graph_version'
FOCUS_EXPRESSION = "max(0.0001,abs((tx-cx)*nx+(ty-cy)*ny+(tz-cz)*nz)/max(0.0001,sqrt(nx*nx+ny*ny+nz*nz)))"


def node(tree, kind, name, x=0, y=0):
    n = tree.nodes.new(kind)
    n.name = name
    n.label = name
    n[KEY] = name
    n.location = x, y
    return n


def find(tree, key, kind=None, remember=True):
    """Resolve a persistent internal key, with compatibility for v1.1 groups."""
    matches = [n for n in tree.nodes if n.get(KEY) == key]
    if len(matches) > 1:
        raise RuntimeError("Duplicate generated node: " + key + ". Remove the duplicate before updating.")
    n = matches[0] if matches else tree.nodes.get(key)
    if n is None or (kind and n.bl_idname != kind):
        raise RuntimeError("Missing or replaced generated node: " + key + ". Restore it or remove and rebuild the setup.")
    if remember and not matches and tree.is_editable:
        n[KEY] = key
    return n


def resolve(tree, required, remember=True):
    """Index once for multi-node checks; retain the legacy name fallback."""
    indexed = {}
    for n in tree.nodes:
        key = n.get(KEY)
        if key in required:
            indexed.setdefault(key, []).append(n)
    result = {}
    for key, kind in required.items():
        matches = indexed.get(key, [])
        if len(matches) > 1:
            raise RuntimeError('Duplicate generated node: ' + key + '. Remove the duplicate before updating.')
        n = matches[0] if matches else tree.nodes.get(key)
        if n is None or (kind and n.bl_idname != kind):
            raise RuntimeError('Missing or replaced generated node: ' + key + '. Restore it or remove and rebuild the setup.')
        if n.mute:
            raise RuntimeError('Generated node is muted: ' + key + '. Unmute it in the node editor, then refresh.')
        if remember and not matches and tree.is_editable:
            n[KEY] = key
        result[key] = n
    return result


EFFECT_CONTROLS = {
    'Focus Offset': 'focus_offset', 'Sharp Half Width': 'sharp_width',
    'Near Falloff': 'near_falloff', 'Far Falloff': 'far_falloff',
    'Near Enabled': 'near_enabled', 'Far Enabled': 'far_enabled',
    'Maximum Radius': 'radius', 'Effect Strength': 'strength', 'Effect Enabled': 'enabled',
    'Texture Influence': 'texture_influence', 'Depth Edge Protection': 'edge_protection',
    'Boundary Threshold': 'threshold',
}
NEW_CONTROLS = {'Defocus Amount': 'defocus', 'Paint Simplification': 'paint_simplification',
                'Paint Edge Breakup': 'paint_edge_breakup', 'Paint Tracking': 'paint_tracking'}
DEFOCUS_NODES = {'Defocus Amount': 'ShaderNodeValue', 'Paint Simplification': 'ShaderNodeValue',
                 'Paint Edge Breakup': 'ShaderNodeValue', 'Paint Tracking': 'ShaderNodeValue',
                 'Enabled Defocus': 'ShaderNodeMath', 'Use Defocus': 'ShaderNodeMath',
                 'Depth Defocus': 'CompositorNodeBlur', 'Defocus Focus Blend': 'ShaderNodeMixRGB',
                 'Softened Source': 'CompositorNodeSwitch'}
PAINT_NODES = {'Paint Filter': 'CompositorNodeGroup', 'Paint Focus Blend': 'ShaderNodeMixRGB',
               'Active Paint Simplification': 'ShaderNodeMath', 'Active Paint Edge Breakup': 'ShaderNodeMath',
               **{'Paint ' + key + ' Input': 'CompositorNodeSwitch' for key in ('Image', 'Constraints', 'Position', 'Depth')}}
PLACEMENT_CONTROLS = (('Scale', 0, 'tile_u'), ('Scale', 1, 'tile_v'),
                      ('Scale', 2, 'tile_u'), ('Rotation', 2, 'texture_rotation'))


def binding(owner, path='default_value', index=0):
    tree = owner.id_data
    return tree.animation_data.drivers.find(owner.path_from_id(path), index=index) if tree.animation_data else None


def validate_property_driver(owner, scene, prop, index=0):
    fc = binding(owner, index=index)
    d = fc.driver if fc else None
    variables = list(d.variables) if d else []
    if (not d or fc.mute or d.type != 'AVERAGE' or len(variables) != 1 or
            variables[0].type != 'SINGLE_PROP' or variables[0].targets[0].id != scene or
            variables[0].targets[0].data_path != 'sdof.' + prop):
        raise RuntimeError('Missing or changed control driver: ' + prop + '. Restore it or remove and rebuild the setup.')


def validate_controls(tree, scene, shader=False, remember=True, resolved=None):
    """Only control bindings on slider edits; full graph checks are on demand."""
    if shader:
        placement = find(tree, 'Texture Placement', 'ShaderNodeMapping', remember)
        for name, index, prop in PLACEMENT_CONTROLS:
            validate_property_driver(placement.inputs[name], scene, prop, index)
    else:
        controls = {**EFFECT_CONTROLS, **(NEW_CONTROLS if tree.get(GRAPH_VERSION, 1) >= 3 else {})}
        resolved = resolved or resolve(tree, {key: 'ShaderNodeValue' for key in controls}, remember)
        for key, prop in controls.items():
            validate_property_driver(resolved[key].outputs[0], scene, prop)


def require_link(tree, source, output, sink, input_socket):
    out = source.outputs[output] if isinstance(output, int) else socket(source.outputs, output)
    into = sink.inputs[input_socket] if isinstance(input_socket, int) else socket(sink.inputs, input_socket)
    if len(into.links) != 1 or into.links[0].from_socket != out:
        raise RuntimeError('Missing or changed generated link: ' + source.label + ' → ' + sink.label +
                           '. Restore the link or remove and rebuild the setup.')


def validate_shader(tree, remember=True, settings=None):
    required = {
        "Your Brush Image": "ShaderNodeTexImage",
        "Surface Coordinates": "ShaderNodeTexCoord",
        "Texture Placement": "ShaderNodeMapping",
        "Starter Painted Patches": "ShaderNodeTexVoronoi",
        "AOV Data": "NodeGroupOutput",
        "Camera Plane Depth": "ShaderNodeCameraData",
        "Irregular Patch Edges": "ShaderNodeTexNoise",
        "Small Edge Variation": "ShaderNodeVectorMath",
        "Perturbed Coordinates": "ShaderNodeVectorMath",
    }
    resolved = resolve(tree, required, remember)
    socket(resolved["AOV Data"].inputs, "Guide")
    for source, out, sink, into in (
            ('Texture Placement', 0, 'Your Brush Image', 'Vector'),
            ('Texture Placement', 0, 'Irregular Patch Edges', 'Vector'),
            ('Irregular Patch Edges', 'Color', 'Small Edge Variation', 0),
            ('Texture Placement', 0, 'Perturbed Coordinates', 0),
            ('Small Edge Variation', 0, 'Perturbed Coordinates', 1),
            ('Perturbed Coordinates', 0, 'Starter Painted Patches', 'Vector'),
            ('Camera Plane Depth', 'View Z Depth', 'AOV Data', 'Depth')):
        require_link(tree, resolved[source], out, resolved[sink], into)
    coverage = socket(resolved['AOV Data'].inputs, 'Coverage')
    if coverage.is_linked or coverage.default_value != 1:
        raise RuntimeError('Generated surface coverage was changed. Restore it to 1 or rebuild the setup.')
    if settings is not None:
        require_link(tree, resolved['Surface Coordinates'], 'UV' if settings.mapping == 'UV' else 'Generated',
                     resolved['Texture Placement'], 'Vector')
        source = 'Your Brush Image' if settings.guide_source == 'IMAGE' and settings.brush_image else 'Starter Painted Patches'
        require_link(tree, resolved[source], 'Color', resolved['AOV Data'], 'Guide')
        if resolved['Your Brush Image'].image != settings.brush_image:
            raise RuntimeError('Brush image binding differs from the panel. Refresh Materials to apply it.')
    return resolved


def validate_effect(tree, settings, remember=True, configured=False):
    version = tree.get(GRAPH_VERSION, 1)
    if version > 3:
        raise RuntimeError('This effect was saved by a newer add-on. Update the add-on before editing it.')
    kinds = {"Mix Painterly Result": "ShaderNodeMixRGB", "Effect Bypass": "CompositorNodeSwitch",
             "Enabled Result": "ShaderNodeMath", "Effect Enabled": "ShaderNodeValue", "Focus Distance": "ShaderNodeValue"}
    kinds.update({key: 'ShaderNodeValue' for key in EFFECT_CONTROLS})
    kinds.update({key: 'ShaderNodeMath' for key in (
        'Geometry Coverage', 'Safe Coverage', 'Unpremultiply Depth', 'Bounded Depth',
        'Focus Plus Offset', 'Positive Focus Distance', 'Focus Mask', 'Covered Focus Mask',
        'Depth Driven Radius', 'Positive Radius', 'Positive Strength', 'Enabled Radius',
        'Effect Blend', 'Has Blur Radius', 'Active Effect Blend', 'Unpremultiply Guide',
        'Brush Boundary Guide', 'Depth Boundary Guide', 'Background Boundary Guide',
        'Soft Radius', 'Near Blur Blend', 'Far Blur Blend')})
    for label in ('Near', 'Far'):
        kinds.update({label + ' ' + suffix: 'ShaderNodeMath' for suffix in
                      ('Distance', 'Outside Sharp Zone', 'Safe Falloff', 'Linear Mask',
                       'Squared', 'Smooth Tail', 'Smooth Mask', 'Mask')})
    kinds.update({'Render and Surface Data': 'NodeGroupInput', 'Result': 'NodeGroupOutput',
                  'Brush Luminance': 'CompositorNodeRGBToBW', 'Bilateral Determinator': 'CompositorNodeCombineColor',
                  'Bilateral': 'CompositorNodeBilateralblur', 'Bilateral Soft': 'CompositorNodeBilateralblur',
                  'Kuwahara': 'CompositorNodeKuwahara', 'Original Alpha': 'CompositorNodeSeparateColor',
                  'Preserve Original Alpha': 'CompositorNodeSetAlpha'})
    kinds.update({key: 'ShaderNodeMixRGB' for key in ('Bilateral Near Level', 'Bilateral Focus Levels', 'Bilateral Fast Level')})
    if version >= 2:
        kinds['Effective Radius'] = 'ShaderNodeMath'
    if version >= 3:
        kinds.update(DEFOCUS_NODES)
    has_paint = any(n.get(KEY) == 'Paint Filter' for n in tree.nodes)
    if has_paint or (configured and settings.method == 'PAINT'):
        kinds.update(PAINT_NODES)
    resolved = resolve(tree, kinds, remember)
    validate_controls(tree, settings.id_data, remember=remember, resolved=resolved)
    preview = {"FOCUS": "Covered Focus Mask", "GUIDE": "Render and Surface Data", "RESULT": "Preserve Original Alpha"}[settings.preview]
    for name in ("On", "Off", "Switch"):
        socket(resolved["Effect Bypass"].inputs, name)
    if settings.preview == "GUIDE":
        socket(resolved[preview].outputs, "Guide AOV")
    # Every fixed generated input must remain connected. Configuration links
    # (method, preview and enable source) are reapplied by update_effect.
    for key, n in resolved.items():
        if n.bl_idname == 'ShaderNodeValue':
            continue
        linked_inputs = {
            'NodeGroupOutput': (0,), 'ShaderNodeMixRGB': (0, 1, 2),
            'CompositorNodeRGBToBW': (0,), 'CompositorNodeSeparateColor': (0,),
            'CompositorNodeCombineColor': (0, 1, 2), 'CompositorNodeSetAlpha': (0, 1),
        }.get(n.bl_idname, ())
        if n.bl_idname == 'ShaderNodeMath':
            constants = {'Geometry Coverage', 'Safe Coverage', 'Bounded Depth', 'Positive Focus Distance',
                         'Positive Radius', 'Positive Strength', 'Has Blur Radius', 'Background Boundary Guide',
                         'Soft Radius', 'Near Blur Blend', 'Far Blur Blend', 'Near Safe Falloff', 'Far Safe Falloff', 'Use Defocus'}
            linked_inputs = (1,) if key.endswith('Smooth Tail') else ((0,) if key in constants else (0, 1))
        for i in linked_inputs:
            if (key, i) != ('Mix Painterly Result', 2) and not n.inputs[i].is_linked:
                raise RuntimeError('Missing generated link into ' + key + '. Restore it or rebuild the setup.')
        if n.bl_idname in {'CompositorNodeBilateralblur', 'CompositorNodeKuwahara'}:
            for name in (('Image', 'Size', 'Determinator', 'Threshold') if n.bl_idname == 'CompositorNodeBilateralblur' else ('Image', 'Size')):
                if not socket(n.inputs, name).is_linked:
                    raise RuntimeError('Missing generated link into ' + key + ': ' + name + '. Restore it or rebuild the setup.')
    radius_source = 'Effective Radius' if version >= 2 else 'Maximum Radius'
    if version >= 2:
        require_link(tree, resolved['Maximum Radius'], 0, resolved['Effective Radius'], 0)
        require_link(tree, resolved['Enabled Result'], 0, resolved['Effective Radius'], 1)
        if resolved['Effective Radius'].operation != 'MULTIPLY':
            raise RuntimeError('Effective Radius operation was changed. Restore Multiply or rebuild the setup.')
    for source, out, sink, into in (
            (radius_source, 0, 'Bilateral', 'Size'), (radius_source, 0, 'Soft Radius', 0),
            (radius_source, 0, 'Depth Driven Radius', 1), ('Maximum Radius', 0, 'Positive Radius', 0),
            ('Boundary Threshold', 0, 'Bilateral', 'Threshold'), ('Boundary Threshold', 0, 'Bilateral Soft', 'Threshold'),
            ('Soft Radius', 0, 'Bilateral Soft', 'Size'), ('Depth Driven Radius', 0, 'Kuwahara', 'Size'),
            ('Effect Strength', 0, 'Effect Blend', 1), ('Effect Strength', 0, 'Positive Strength', 0),
            ('Focus Distance', 0, 'Focus Plus Offset', 0), ('Focus Offset', 0, 'Focus Plus Offset', 1),
            ('Effect Enabled', 0, 'Enabled Radius', 0), ('Positive Radius', 0, 'Enabled Radius', 1),
            ('Enabled Radius', 0, 'Enabled Result', 0), ('Positive Strength', 0, 'Enabled Result', 1),
            ('Effect Bypass', 0, 'Result', 'Image'),
            ('Render and Surface Data', 'Image', 'Effect Bypass', 'Off'),
            ('Original Alpha', 'Alpha', 'Preserve Original Alpha', 'Alpha')):
        require_link(tree, resolved[source], out, resolved[sink], into)
    for label in ('Near', 'Far'):
        for source, sink, into in (('Sharp Half Width', label + ' Outside Sharp Zone', 1),
                                   (label + ' Falloff', label + ' Safe Falloff', 0),
                                   (label + ' Enabled', label + ' Mask', 1)):
            require_link(tree, resolved[source], 0, resolved[sink], into)
    if version >= 3:
        for source, out, sink, into in (
                ('Defocus Amount', 0, 'Enabled Defocus', 0), ('Enabled Result', 0, 'Enabled Defocus', 1),
                ('Enabled Defocus', 0, 'Depth Defocus', 'Size'),
                ('Render and Surface Data', 'Image', 'Depth Defocus', 'Image'),
                ('Covered Focus Mask', 0, 'Defocus Focus Blend', 0),
                ('Render and Surface Data', 'Image', 'Defocus Focus Blend', 1),
                ('Depth Defocus', 0, 'Defocus Focus Blend', 2),
                ('Enabled Defocus', 0, 'Use Defocus', 0), ('Use Defocus', 0, 'Softened Source', 'Switch'),
                ('Render and Surface Data', 'Image', 'Softened Source', 'Off'),
                ('Defocus Focus Blend', 0, 'Softened Source', 'On')):
            require_link(tree, resolved[source], out, resolved[sink], into)
        for key in ('Bilateral', 'Bilateral Soft', 'Kuwahara'):
            require_link(tree, resolved['Softened Source'], 0, resolved[key], 'Image')
    if has_paint:
        from . import paint
        paint.validate(resolved['Paint Filter'])
        for source, out, sink, into in (
                ('Effective Radius', 0, 'Paint Filter', 'Size'),
                ('Paint Simplification', 0, 'Active Paint Simplification', 0),
                ('Enabled Result', 0, 'Active Paint Simplification', 1),
                ('Active Paint Simplification', 0, 'Paint Filter', 'Simplification'),
                ('Paint Edge Breakup', 0, 'Active Paint Edge Breakup', 0),
                ('Enabled Result', 0, 'Active Paint Edge Breakup', 1),
                ('Active Paint Edge Breakup', 0, 'Paint Filter', 'Edge Breakup'),
                ('Paint Tracking', 0, 'Paint Filter', 'Use Tracking'),
                ('Covered Focus Mask', 0, 'Paint Focus Blend', 0),
                ('Render and Surface Data', 'Image', 'Paint Focus Blend', 1),
                ('Paint Filter', 'Image', 'Paint Focus Blend', 2)):
            require_link(tree, resolved[source], out, resolved[sink], into)
        for key, source, out in (('Image', 'Softened Source', 0), ('Constraints', 'Depth Boundary Guide', 0),
                                 ('Depth', 'Render and Surface Data', 'Paint Depth'),
                                 ('Position', 'Render and Surface Data', 'Position')):
            gate = resolved['Paint ' + key + ' Input']
            require_link(tree, resolved[source], out, gate, 'On')
            require_link(tree, resolved['Enabled Result'], 0, gate, 'Switch')
            require_link(tree, gate, 0, resolved['Paint Filter'], key)
            if gate.inputs['Off'].is_linked:
                raise RuntimeError('The Paint bypass input was changed. Restore its unlinked constant or rebuild the setup.')
    if configured:
        bilateral = 'Bilateral Focus Levels' if settings.quality == 'BALANCED' else 'Bilateral Fast Level'
        chosen = bilateral if settings.method == 'BILATERAL' else ('Paint Focus Blend' if settings.method == 'PAINT' else 'Kuwahara')
        require_link(tree, resolved[chosen], 0, resolved['Mix Painterly Result'], 2)
        require_link(tree, resolved[preview], 'Guide AOV' if settings.preview == 'GUIDE' else 0, resolved['Effect Bypass'], 'On')
        require_link(tree, resolved['Enabled Result' if settings.preview == 'RESULT' else 'Effect Enabled'],
                     0, resolved['Effect Bypass'], 'Switch')
    return resolved


def upgrade_effect(tree, settings, journal=None):
    """Upgrade intact older graphs in place, retaining controls and animation."""
    if tree.get(GRAPH_VERSION, 1) >= 3:
        return
    from .transaction import Journal
    own_journal = journal is None
    journal = journal or Journal()
    try:
        # Configuration may already have changed to Paint before an older
        # graph's first update. Validate its old structure without requiring it.
        old = validate_effect(tree, settings, remember=False)
        if tree.get(GRAPH_VERSION, 1) < 2:
            if any(n.get(KEY) == 'Effective Radius' or n.name == 'Effective Radius' for n in tree.nodes):
                raise RuntimeError('An unversioned Effective Radius node already exists. Restore the original graph before upgrading.')
            effective = feature_node(tree, 'ShaderNodeMath', 'Effective Radius', journal)
            effective.operation = 'MULTIPLY'
            x, y = old['Maximum Radius'].location
            effective.location = (x + 240, y - 210)
            journal.wire(tree, old['Maximum Radius'].outputs[0], effective.inputs[0])
            journal.wire(tree, old['Enabled Result'].outputs[0], effective.inputs[1])
            for key, into in (('Bilateral', 'Size'), ('Soft Radius', 0), ('Depth Driven Radius', 1)):
                journal.wire(tree, effective.outputs[0], old[key].inputs[into])
            journal.property(tree, GRAPH_VERSION, 2)
        add_defocus(tree, settings, journal)
        journal.property(tree, GRAPH_VERSION, 3)
        validate_effect(tree, settings, remember=False)
        tree.update_tag()
        if own_journal:
            journal.commit()
    except Exception:
        if own_journal:
            journal.rollback()
        raise


def feature_node(tree, kind, name, journal):
    n = node(tree, kind, name)
    journal.created_node(tree, n)
    return n


def feature_math(tree, name, operation, a, b, journal):
    n = feature_node(tree, 'ShaderNodeMath', name, journal)
    n.operation = operation
    for index, value in enumerate((a, b)):
        if isinstance(value, (float, int)):
            n.inputs[index].default_value = value
        else:
            journal.wire(tree, value, n.inputs[index])
    return n.outputs[0]


def add_defocus(tree, settings, journal):
    if any(n.get(KEY) in DEFOCUS_NODES or n.name in DEFOCUS_NODES for n in tree.nodes):
        raise RuntimeError('Unversioned Defocus nodes already exist. Restore the original generated group before upgrading.')
    for key, prop in NEW_CONTROLS.items():
        n = feature_node(tree, 'ShaderNodeValue', key, journal)
        n.outputs[0].default_value = getattr(settings, prop)
        journal.driver(n.outputs[0], 'default_value')
        driver(n.outputs[0], 'default_value', settings.id_data, 'sdof.' + prop)
    inp = find(tree, 'Render and Surface Data')
    for name, kind in (('Paint Depth', 'NodeSocketFloat'), ('Position', 'NodeSocketVector')):
        item = interface(tree, name, 'INPUT', kind)
        journal.undo.append(lambda item=item: tree.interface.remove(item))
    active = feature_math(tree, 'Enabled Defocus', 'MULTIPLY', find(tree, 'Defocus Amount').outputs[0],
                          find(tree, 'Enabled Result').outputs[0], journal)
    use_defocus = feature_math(tree, 'Use Defocus', 'GREATER_THAN', active, 0.0, journal)
    blur = feature_node(tree, 'CompositorNodeBlur', 'Depth Defocus', journal)
    journal.wire(tree, inp.outputs['Image'], blur.inputs['Image'])
    journal.wire(tree, active, blur.inputs['Size'])
    blend = feature_node(tree, 'ShaderNodeMixRGB', 'Defocus Focus Blend', journal)
    journal.wire(tree, find(tree, 'Covered Focus Mask').outputs[0], blend.inputs[0])
    journal.wire(tree, inp.outputs['Image'], blend.inputs[1])
    journal.wire(tree, blur.outputs[0], blend.inputs[2])
    source = feature_node(tree, 'CompositorNodeSwitch', 'Softened Source', journal)
    journal.wire(tree, inp.outputs['Image'], source.inputs['Off'])
    journal.wire(tree, blend.outputs[0], source.inputs['On'])
    journal.wire(tree, use_defocus, source.inputs['Switch'])
    for key in ('Bilateral', 'Bilateral Soft', 'Kuwahara'):
        journal.wire(tree, source.outputs[0], find(tree, key).inputs['Image'])


def add_paint(tree, settings, journal):
    if any(n.get(KEY) == 'Paint Filter' for n in tree.nodes):
        return
    from . import paint
    group = paint.load(journal)
    n = feature_node(tree, 'CompositorNodeGroup', 'Paint Filter', journal)
    n.node_tree = group
    paint.validate(n)
    for key in ('Simplification', 'Edge Breakup'):
        value = feature_math(tree, 'Active Paint ' + key, 'MULTIPLY', find(tree, 'Paint ' + key).outputs[0],
                             find(tree, 'Enabled Result').outputs[0], journal)
        journal.wire(tree, value, n.inputs[key])
    for key, source in (('Size', 'Effective Radius'), ('Use Tracking', 'Paint Tracking')):
        journal.wire(tree, find(tree, source).outputs[0], n.inputs[key])
    inp = find(tree, 'Render and Surface Data')
    # Radius zero alone does not skip the asset's procedural textures. Feeding
    # constants while bypassed gives those operations a single-pixel domain.
    for key, source in (('Image', find(tree, 'Softened Source').outputs[0]),
                        ('Constraints', find(tree, 'Depth Boundary Guide').outputs[0]),
                        ('Position', inp.outputs['Position']), ('Depth', inp.outputs['Paint Depth'])):
        gate = feature_node(tree, 'CompositorNodeSwitch', 'Paint ' + key + ' Input', journal)
        gate.inputs['Off'].default_value = (0, 0, 0, 1)
        journal.wire(tree, source, gate.inputs['On'])
        journal.wire(tree, find(tree, 'Enabled Result').outputs[0], gate.inputs['Switch'])
        journal.wire(tree, gate.outputs[0], n.inputs[key])
    blend = feature_node(tree, 'ShaderNodeMixRGB', 'Paint Focus Blend', journal)
    journal.wire(tree, find(tree, 'Covered Focus Mask').outputs[0], blend.inputs[0])
    journal.wire(tree, inp.outputs['Image'], blend.inputs[1])
    journal.wire(tree, n.outputs['Image'], blend.inputs[2])


def socket(collection, *names):
    for name in names:
        s = collection.get(name)
        if s is not None:
            return s
    # Identifier lookup survives sockets whose visible names differ.
    for s in collection:
        if s.identifier in names:
            return s
    raise RuntimeError('Missing socket: ' + ' / '.join(names) +
                       '. Restore the original node or interface, or remove and rebuild the setup.')


def wire(tree, out, into):
    if len(into.links) == 1 and into.links[0].from_socket == out:
        return
    tree.links.new(out, into)


def scalar(tree, name, value, scene=None, prop=None):
    n = node(tree, "ShaderNodeValue", name)
    n.outputs[0].default_value = getattr(scene.sdof, prop) if prop else value
    if prop:
        driver(n.outputs[0], "default_value", scene, "sdof." + prop)
    return n.outputs[0]


def driver(owner, path, target, target_path, index=None):
    fc = owner.driver_add(path) if index is None else owner.driver_add(path, index)
    d = fc.driver
    d.type = "AVERAGE"
    for old_var in list(d.variables):
        d.variables.remove(old_var)
    v = d.variables.new()
    v.name = "value"
    v.type = "SINGLE_PROP"
    v.targets[0].id_type = target.id_type
    v.targets[0].id = target
    v.targets[0].data_path = target_path
    return d


def math(tree, op, a, b=None, name=None, clamp=False):
    n = node(tree, "ShaderNodeMath", name or op.title())
    n.operation = op
    n.use_clamp = clamp
    for i, value in enumerate((a, b)):
        if value is None:
            continue
        if isinstance(value, (int, float)):
            n.inputs[i].default_value = value
        else:
            wire(tree, value, n.inputs[i])
    return n.outputs[0]


def mix(tree, factor, a, b, name):
    n = node(tree, "ShaderNodeMixRGB", name)
    n.blend_type = "MIX"
    n.use_clamp = False
    wire(tree, factor, n.inputs[0])
    wire(tree, a, n.inputs[1])
    wire(tree, b, n.inputs[2])
    return n.outputs[0]


def interface(tree, name, direction, kind, default=None):
    s = tree.interface.new_socket(name=name, in_out=direction, socket_type=kind)
    if default is not None:
        s.default_value = default
    return s


def tidy(tree):
    # Assign readable topological columns, retaining meaningful node names.
    levels = {}
    visiting = set()
    parents_by_name = {n.name: [] for n in tree.nodes}
    for link in tree.links:
        parents_by_name[link.to_node.name].append(link.from_node)
    def level(n):
        if n.name in levels:
            return levels[n.name]
        if n.name in visiting:
            return 0
        visiting.add(n.name)
        parents = parents_by_name[n.name]
        value = 0 if not parents else 1 + max(level(p) for p in parents)
        visiting.remove(n.name)
        levels[n.name] = value
        return value
    rows = {}
    for n in tree.nodes:
        c = level(n)
        r = rows.get(c, 0)
        n.location = (c * 240, -r * 210)
        n.width = 200
        rows[c] = r + 1


def build_shader(scene, token):
    s = scene.sdof
    tree = bpy.data.node_groups.new("Stylized Surface Guide • " + scene.name, "ShaderNodeTree")
    tree[TAG] = token
    tree[ROLE] = "shader"
    try:
        for name, kind in (("Guide", "NodeSocketColor"), ("Depth", "NodeSocketFloat"),
                           ("Coverage", "NodeSocketFloat")):
            interface(tree, name, "OUTPUT", kind)
        out = node(tree, "NodeGroupOutput", "AOV Data")
        tex = node(tree, "ShaderNodeTexCoord", "Surface Coordinates")
        mapping = node(tree, "ShaderNodeMapping", "Texture Placement")
        mapping.vector_type = "POINT"
        driver(mapping.inputs["Scale"], "default_value", scene, "sdof.tile_u", 0)
        driver(mapping.inputs["Scale"], "default_value", scene, "sdof.tile_v", 1)
        driver(mapping.inputs["Scale"], "default_value", scene, "sdof.tile_u", 2)
        driver(mapping.inputs["Rotation"], "default_value", scene, "sdof.texture_rotation", 2)
        image = node(tree, "ShaderNodeTexImage", "Your Brush Image")
        image.extension = "REPEAT"
        image.interpolation = "Linear"
        image.projection_blend = 0.25
        wire(tree, mapping.outputs[0], image.inputs["Vector"])
        noise = node(tree, "ShaderNodeTexNoise", "Irregular Patch Edges")
        noise.inputs["Scale"].default_value = 6.0
        noise.inputs["Detail"].default_value = 2.0
        wire(tree, mapping.outputs[0], noise.inputs["Vector"])
        perturb = node(tree, "ShaderNodeVectorMath", "Small Edge Variation")
        perturb.operation = "SCALE"
        perturb.inputs["Scale"].default_value = 0.035
        wire(tree, noise.outputs["Color"], perturb.inputs[0])
        add = node(tree, "ShaderNodeVectorMath", "Perturbed Coordinates")
        add.operation = "ADD"
        wire(tree, mapping.outputs[0], add.inputs[0])
        wire(tree, perturb.outputs[0], add.inputs[1])
        cells = node(tree, "ShaderNodeTexVoronoi", "Starter Painted Patches")
        cells.voronoi_dimensions = "3D"
        cells.feature = "F1"
        cells.distance = "EUCLIDEAN"
        cells.inputs["Scale"].default_value = 18.0
        wire(tree, add.outputs[0], cells.inputs["Vector"])
        camera = node(tree, "ShaderNodeCameraData", "Camera Plane Depth")
        wire(tree, camera.outputs["View Z Depth"], out.inputs["Depth"])
        out.inputs["Coverage"].default_value = 1.0
        update_shader(tree, s)
        tidy(tree)
        return tree
    except Exception:
        bpy.data.node_groups.remove(tree)
        raise


def update_shader(tree, settings, journal=None):
    n = validate_shader(tree)
    validate_controls(tree, settings.id_data, shader=True)
    image = n["Your Brush Image"]
    coords = "UV" if settings.mapping == "UV" else "Generated"
    source = image if settings.guide_source == "IMAGE" and settings.brush_image else n["Starter Painted Patches"]
    placement = socket(n["Texture Placement"].inputs, "Vector")
    coordinates = socket(n["Surface Coordinates"].outputs, coords)
    guide = socket(n["AOV Data"].inputs, "Guide")
    color = socket(source.outputs, "Color")
    if journal:
        journal.set(image, "image", settings.brush_image)
        journal.set(image, "projection", "FLAT" if settings.mapping == "UV" else "BOX")
        journal.wire(tree, coordinates, placement)
        journal.wire(tree, color, guide)
    else:
        image.image = settings.brush_image
        image.projection = "FLAT" if settings.mapping == "UV" else "BOX"
        wire(tree, coordinates, placement)
        wire(tree, color, guide)


def focus_status(tree, scene):
    """Read-only check, including pointers Blender cleared after target deletion."""
    s = scene.sdof
    try:
        out = find(tree, 'Focus Distance', 'ShaderNodeValue', remember=False).outputs[0]
        fc = binding(out)
        if not fc or fc.mute or not fc.driver.is_valid:
            return 'Focus binding needs syncing.'
        d = fc.driver
        if s.focus_mode == 'MANUAL':
            validate_property_driver(out, scene, 'manual_focus')
            return ''
        cam = scene.camera
        if not cam or cam.type != 'CAMERA':
            return 'Choose an active scene camera or Manual Distance.'
        target = cam.data.dof.focus_object
        bone = cam.data.dof.focus_subtarget if target else ''
        if bone and (target.type != 'ARMATURE' or bone not in target.pose.bones):
            return 'The camera focus bone is missing. Correct the target before syncing.'
        if (s.bound_camera, s.bound_target, s.bound_bone) != (cam, target, bone):
            return 'Focus source changed. Sync to apply it.'
        variables = {v.name: v for v in d.variables}
        if not target:
            v = next(iter(d.variables), None)
            if (d.type != 'AVERAGE' or len(d.variables) != 1 or not v or v.type != 'SINGLE_PROP' or
                    v.targets[0].id != cam.data or v.targets[0].data_path != 'dof.focus_distance'):
                return 'Focus binding needs syncing.'
        else:
            if d.type != 'SCRIPTED' or d.expression != FOCUS_EXPRESSION or len(variables) != 9:
                return 'Focus binding needs syncing.'
            for prefix, obj, subtarget in (('c', cam, ''), ('t', target, bone)):
                for axis in 'XYZ':
                    v = variables.get(prefix + axis.lower())
                    if (not v or v.type != 'TRANSFORMS' or v.targets[0].id != obj or
                            v.targets[0].bone_target != subtarget or v.targets[0].transform_type != 'LOC_' + axis or
                            v.targets[0].transform_space != 'WORLD_SPACE'):
                        return 'Focus binding needs syncing.'
            for i, axis in enumerate('xyz'):
                v = variables.get('n' + axis)
                if not v or v.type != 'SINGLE_PROP' or v.targets[0].id != cam or v.targets[0].data_path != 'matrix_world[2][%d]' % i:
                    return 'Focus binding needs syncing.'
        return ''
    except (ReferenceError, RuntimeError, AttributeError, TypeError):
        return 'Focus binding needs syncing.'


def bind_focus(tree, scene, journal=None):
    s = scene.sdof
    out = find(tree, "Focus Distance", "ShaderNodeValue").outputs[0]
    cam = scene.camera
    target, bone = None, ""
    # Validate before removing the last working binding.
    if s.focus_mode == "CAMERA":
        if not cam or cam.type != "CAMERA":
            raise RuntimeError("Set an active scene camera, or choose Manual focus.")
        target = cam.data.dof.focus_object
        bone = getattr(cam.data.dof, "focus_subtarget", "") if target else ""
        if bone and (target.type != "ARMATURE" or bone not in target.pose.bones):
            raise RuntimeError("The camera focus bone does not exist on its target. Correct it before syncing.")
    if journal:
        journal.driver(out, 'default_value')
        for key in ('bound_camera', 'bound_target', 'bound_bone'):
            old = getattr(s, key)
            journal.undo.append(lambda key=key, old=old: setattr(s, key, old))
    # Reuse the F-curve so syncing keeps its modifiers and supports rollback.
    out.driver_add('default_value').mute = False
    if s.focus_mode == "MANUAL":
        driver(out, "default_value", scene, "sdof.manual_focus")
        s.bound_camera = s.bound_target = None
        s.bound_bone = ""
        return
    s.bound_camera = cam
    if not target:
        driver(out, "default_value", cam.data, "dof.focus_distance")
        s.bound_target = None
        s.bound_bone = ""
        return
    # Project target onto camera forward axis, matching a planar focus distance.
    # Transform variables include parented and constrained world transforms.
    d = out.driver_add("default_value").driver
    d.type = "SCRIPTED"
    for old_var in list(d.variables):
        d.variables.remove(old_var)
    for prefix, obj, subtarget in (("c", cam, ""), ("t", target, bone)):
        for axis in "XYZ":
            v = d.variables.new()
            v.name = prefix + axis.lower()
            v.type = "TRANSFORMS"
            v.targets[0].id = obj
            v.targets[0].transform_type = "LOC_" + axis
            v.targets[0].transform_space = "WORLD_SPACE"
            v.targets[0].bone_target = subtarget
    for i, axis in enumerate("xyz"):
        v = d.variables.new()
        v.name = "n" + axis
        v.type = "SINGLE_PROP"
        v.targets[0].id = cam
        # RNA paths index matrix columns, while mathutils uses row indexing.
        # Reading [i][2] here silently projects onto the third row after rotation.
        v.targets[0].data_path = "matrix_world[2][%d]" % i
    d.expression = FOCUS_EXPRESSION
    s.bound_target = target
    s.bound_bone = bone


def build_effect(scene, token):
    tree = bpy.data.node_groups.new("Stylized Depth of Field • " + scene.name, "CompositorNodeTree")
    tree[TAG] = token
    tree[ROLE] = "effect"
    try:
        for name, kind in (("Image", "NodeSocketColor"), ("Guide AOV", "NodeSocketColor"),
                           ("Depth AOV", "NodeSocketFloat"), ("Coverage AOV", "NodeSocketFloat")):
            interface(tree, name, "INPUT", kind)
        interface(tree, "Image", "OUTPUT", "NodeSocketColor")
        inp = node(tree, "NodeGroupInput", "Render and Surface Data")
        out = node(tree, "NodeGroupOutput", "Result")
        cov = math(tree, "MULTIPLY", inp.outputs["Coverage AOV"], 1.0, "Geometry Coverage", True)
        safe_cov = math(tree, "MAXIMUM", cov, 0.0001, "Safe Coverage")
        z = math(tree, "DIVIDE", inp.outputs["Depth AOV"], safe_cov, "Unpremultiply Depth")
        z = math(tree, "MINIMUM", z, 1000000.0, "Bounded Depth")
        focus = scalar(tree, "Focus Distance", 10)
        offset = scalar(tree, "Focus Offset", 0, scene, "focus_offset")
        focus = math(tree, "ADD", focus, offset, "Focus Plus Offset")
        focus = math(tree, "MAXIMUM", focus, 0.0001, "Positive Focus Distance")
        width = scalar(tree, "Sharp Half Width", 0.25, scene, "sharp_width")
        masks = []
        for near in (True, False):
            label = "Near" if near else "Far"
            delta = math(tree, "SUBTRACT", focus if near else z, z if near else focus, label + " Distance")
            delta = math(tree, "SUBTRACT", delta, width, label + " Outside Sharp Zone")
            fall = scalar(tree, label + " Falloff", 3, scene, "near_falloff" if near else "far_falloff")
            safe_fall = math(tree, "MAXIMUM", fall, 0.001, label + " Safe Falloff")
            t = math(tree, "DIVIDE", delta, safe_fall, label + " Linear Mask", True)
            # smoothstep: t*t*(3-2*t)
            sq = math(tree, "MULTIPLY", t, t, label + " Squared")
            tail = math(tree, "SUBTRACT", 3, math(tree, "MULTIPLY", 2, t), label + " Smooth Tail")
            smooth = math(tree, "MULTIPLY", sq, tail, label + " Smooth Mask")
            enabled = scalar(tree, label + " Enabled", 1, scene, "near_enabled" if near else "far_enabled")
            masks.append(math(tree, "MULTIPLY", smooth, enabled, label + " Mask"))
        mask = math(tree, "MAXIMUM", *masks, name="Focus Mask")
        mask = math(tree, "MULTIPLY", mask, cov, "Covered Focus Mask")
        max_radius = scalar(tree, "Maximum Radius", 5, scene, "radius")
        radius = math(tree, "MULTIPLY", mask, max_radius, "Depth Driven Radius")
        strength = scalar(tree, "Effect Strength", 1, scene, "strength")
        enabled = scalar(tree, "Effect Enabled", 1, scene, "enabled")
        positive_radius = math(tree, "GREATER_THAN", max_radius, 0.0, "Positive Radius")
        positive_strength = math(tree, "GREATER_THAN", strength, 0.0, "Positive Strength")
        active = math(tree, "MULTIPLY", enabled, positive_radius, "Enabled Radius")
        active = math(tree, "MULTIPLY", active, positive_strength, "Enabled Result")
        effective_radius = math(tree, "MULTIPLY", max_radius, active, "Effective Radius")
        wire(tree, effective_radius, radius.node.inputs[1])
        blend = math(tree, "MULTIPLY", cov, strength, "Effect Blend", True)
        has_radius = math(tree, "GREATER_THAN", radius, 0.0, "Has Blur Radius")
        blend = math(tree, "MULTIPLY", blend, has_radius, "Active Effect Blend")
        gray = node(tree, "CompositorNodeRGBToBW", "Brush Luminance")
        wire(tree, inp.outputs["Guide AOV"], gray.inputs[0])
        guide = math(tree, "DIVIDE", gray.outputs[0], safe_cov, "Unpremultiply Guide")
        contrast = scalar(tree, "Texture Influence", 1, scene, "texture_influence")
        guide = math(tree, "MULTIPLY", guide, contrast, "Brush Boundary Guide")
        protect = scalar(tree, "Depth Edge Protection", 1, scene, "edge_protection")
        depth_guide = math(tree, "MULTIPLY", z, protect, "Depth Boundary Guide")
        coverage_guide = math(tree, "MULTIPLY", cov, 100, "Background Boundary Guide")
        combine = node(tree, "CompositorNodeCombineColor", "Bilateral Determinator")
        combine.mode = "RGB"
        wire(tree, guide, combine.inputs[0])
        wire(tree, depth_guide, combine.inputs[1])
        wire(tree, coverage_guide, combine.inputs[2])
        bi = node(tree, "CompositorNodeBilateralblur", "Bilateral")
        wire(tree, inp.outputs["Image"], socket(bi.inputs, "Image"))
        wire(tree, combine.outputs[0], socket(bi.inputs, "Determinator"))
        wire(tree, effective_radius, socket(bi.inputs, "Size"))
        threshold = scalar(tree, "Boundary Threshold", 0.12, scene, "threshold")
        wire(tree, threshold, socket(bi.inputs, "Threshold"))
        soft = node(tree, "CompositorNodeBilateralblur", "Bilateral Soft")
        wire(tree, inp.outputs["Image"], soft.inputs["Image"])
        wire(tree, combine.outputs[0], soft.inputs["Determinator"])
        wire(tree, threshold, soft.inputs["Threshold"])
        half_radius = math(tree, "MULTIPLY", effective_radius, 0.5, "Soft Radius")
        wire(tree, half_radius, soft.inputs["Size"])
        # Bilateral Size is a single-value input in 5.2. Blend two fixed
        # radius levels with the focus mask instead of sending it an image.
        low = math(tree, "MULTIPLY", mask, 2.0, "Near Blur Blend", True)
        high = math(tree, "SUBTRACT", math(tree, "MULTIPLY", mask, 2.0), 1.0, "Far Blur Blend", True)
        stage = mix(tree, low, inp.outputs["Image"], soft.outputs[0], "Bilateral Near Level")
        bilateral_result = mix(tree, high, stage, bi.outputs[0], "Bilateral Focus Levels")
        mix(tree, mask, inp.outputs["Image"], bi.outputs[0], "Bilateral Fast Level")
        kw = node(tree, "CompositorNodeKuwahara", "Kuwahara")
        socket(kw.inputs, "Variation", "Type").default_value = "Anisotropic"
        wire(tree, inp.outputs["Image"], socket(kw.inputs, "Image"))
        wire(tree, radius, socket(kw.inputs, "Size"))
        result = mix(tree, blend, inp.outputs["Image"], bilateral_result, "Mix Painterly Result")
        # Preserve the incoming compositor alpha rather than spreading alpha.
        sep = node(tree, "CompositorNodeSeparateColor", "Original Alpha")
        sep.mode = "RGB"
        wire(tree, inp.outputs["Image"], sep.inputs[0])
        alpha = node(tree, "CompositorNodeSetAlpha", "Preserve Original Alpha")
        if hasattr(alpha, "mode"):
            alpha.mode = "REPLACE_ALPHA"
        elif alpha.inputs.get("Type"):
            alpha.inputs["Type"].default_value = "Replace Alpha"
        wire(tree, result, socket(alpha.inputs, "Image"))
        wire(tree, socket(sep.outputs, "Alpha"), socket(alpha.inputs, "Alpha"))
        bypass = node(tree, "CompositorNodeSwitch", "Effect Bypass")
        wire(tree, inp.outputs["Image"], bypass.inputs["Off"])
        wire(tree, bypass.outputs[0], out.inputs["Image"])
        tree[GRAPH_VERSION] = 2
        bind_focus(tree, scene)
        update_effect(tree, scene.sdof)
        tidy(tree)
        return tree
    except Exception:
        bpy.data.node_groups.remove(tree)
        raise


def update_effect(tree, settings, journal=None):
    if journal is None:
        from .transaction import Journal
        journal = Journal()
        try:
            update_effect(tree, settings, journal)
            journal.commit()
        except Exception:
            journal.rollback()
            raise
        return
    upgrade_effect(tree, settings, journal)
    if settings.method == 'PAINT':
        add_paint(tree, settings, journal)
    n = validate_effect(tree, settings)
    connect = journal.wire if journal else wire
    bilateral = "Bilateral Focus Levels" if settings.quality == "BALANCED" else "Bilateral Fast Level"
    chosen = n[bilateral] if settings.method == "BILATERAL" else n['Paint Focus Blend' if settings.method == 'PAINT' else 'Kuwahara']
    connect(tree, chosen.outputs[0], n["Mix Painterly Result"].inputs[2])
    if settings.preview == "FOCUS":
        result = n["Covered Focus Mask"].outputs[0]
    elif settings.preview == "GUIDE":
        result = n["Render and Surface Data"].outputs["Guide AOV"]
    else:
        result = n["Preserve Original Alpha"].outputs[0]
    connect(tree, result, n["Effect Bypass"].inputs["On"])
    switch = n["Enabled Result"] if settings.preview == "RESULT" else n["Effect Enabled"]
    connect(tree, switch.outputs[0], n["Effect Bypass"].inputs["Switch"])


def check_capabilities():
    """Check the actual APIs rather than rejecting every later Blender version."""
    if bpy.app.version < (5, 2, 0):
        raise RuntimeError("Stylized Depth of Field requires Blender 5.2 or newer.")
    if "compositing_node_group" not in bpy.types.Scene.bl_rna.properties:
        raise RuntimeError("This Blender build has no compatible scene compositor API.")
    for kind in ("CompositorNodeBilateralblur", "CompositorNodeKuwahara", "CompositorNodeBlur", "ShaderNodeOutputAOV"):
        if getattr(bpy.types, kind, None) is None:
            raise RuntimeError("This Blender build is missing a required node: " + kind)
