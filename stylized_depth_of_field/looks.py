"""Paint controls, optional aperture blur and bloom. Native nodes only."""
from . import nodes as ng

VERSION = 6
CONTROLS = {
    'Paint Sharpness': 'paint_sharpness', 'Paint Colors': 'paint_colors',
    'Paint Pooling': 'paint_pooling', 'Paint Seed': 'paint_seed',
    'Canvas Scale': 'paint_canvas_scale', 'Canvas Amount': 'paint_canvas_amount',
    'Aperture Blades': 'bokeh_blades', 'Aperture Rotation': 'bokeh_rotation',
    'Aperture Roundness': 'bokeh_roundness',
    'Bloom Enabled': 'bloom_enabled', 'Bloom Amount': 'bloom_amount',
    'Bloom Spread': 'bloom_spread', 'Bloom Threshold': 'bloom_threshold',
    'Bloom Steps': 'bloom_steps', 'Bloom Softness': 'bloom_softness',
    'Bloom Breakup': 'bloom_breakup', 'Bloom Texture Scale': 'bloom_texture_scale',
    'Bloom Seed': 'bloom_seed', 'Bloom Tracking': 'bloom_tracking',
}
PAINT_INPUTS = {'Sharpness': 'Paint Sharpness', 'Accidental Colors': 'Paint Colors',
                'Pooling': 'Paint Pooling', 'Seed': 'Paint Seed',
                'Scale': 'Canvas Scale', 'Overlay Texture': 'Canvas Amount'}
STYLES = {'WATERCOLOR': 'Watercolor', 'OIL': 'Oil Paint', 'GEOMETRIC': 'Digital Geometric'}
CANVASES = {'CANVAS': 'Canvas', 'PAPER': 'Paper Rough', 'NONE': 'None'}


class Graph:
    """Build or inspect the same fixed node specification without duplicating it."""
    def __init__(self, tree, journal=None, inspect=False):
        self.tree, self.journal, self.inspect = tree, journal, inspect

    def node(self, kind, key):
        if self.inspect:
            return ng.resolve(self.tree, {key: kind}, remember=False)[key]
        return ng.feature_node(self.tree, kind, key, self.journal)

    def value(self, key):
        return ng.find(self.tree, key, remember=not self.inspect).outputs[0]

    def into(self, node, name, source):
        socket = node.inputs[name]
        if hasattr(source, 'node'):
            if self.inspect:
                if len(socket.links) != 1 or socket.links[0].from_socket != source:
                    raise RuntimeError('Missing or changed generated link into ' + node.label + '. Restore it or rebuild.')
            else:
                self.journal.wire(self.tree, source, socket)
        elif self.inspect:
            value = socket.default_value
            equal = value == source if isinstance(source, (str, bool)) else abs(value-source) < 1e-5 if isinstance(source, (int, float)) else all(abs(a-b) < 1e-5 for a, b in zip(value, source))
            if socket.is_linked or not equal:
                raise RuntimeError('Changed generated setting in ' + node.label + ': ' + socket.name + '. Restore it or rebuild.')
        else:
            self.journal.set(socket, 'default_value', source)

    def math(self, key, operation, a, b=0, clamp=False):
        n = self.node('ShaderNodeMath', key)
        if self.inspect:
            if n.operation != operation or n.use_clamp != clamp:
                raise RuntimeError('Changed generated operation: ' + key + '. Restore it or rebuild.')
        else:
            n.operation, n.use_clamp = operation, clamp
        self.into(n, 0, a)
        if operation not in {'FLOOR', 'FRACT', 'SQRT'}:
            self.into(n, 1, b)
        return n.outputs[0]

    def switch(self, key, enabled, off, on):
        n = self.node('CompositorNodeSwitch', key)
        for name, value in (('Switch', enabled), ('Off', off), ('On', on)):
            self.into(n, name, value)
        return n.outputs[0]

    def scale(self, key, color, amount):
        n = self.node('ShaderNodeVectorMath', key)
        if self.inspect:
            if n.operation != 'SCALE':
                raise RuntimeError('Changed generated operation: ' + key)
        else:
            n.operation = 'SCALE'
        self.into(n, 0, color)
        self.into(n, 'Scale', amount)
        return n.outputs[0]


def has(tree, key):
    return any(n.get(ng.KEY) == key for n in tree.nodes)


def add_controls(tree, settings, journal):
    for key, prop in CONTROLS.items():
        if any(n.get(ng.KEY) == key or n.name == key for n in tree.nodes):
            raise RuntimeError('An unversioned v2 control already exists: ' + key)
        n = ng.feature_node(tree, 'ShaderNodeValue', key, journal)
        n.outputs[0].default_value = getattr(settings, prop)
        journal.driver(n.outputs[0], 'default_value')
        ng.driver(n.outputs[0], 'default_value', settings.id_data, 'sdof.' + prop)


def paint_menu(instance, identifier):
    # Two asset inputs are both named Texture. Stable interface identifiers
    # distinguish brush style from canvas style.
    socket = next((s for s in instance.inputs if s.identifier == identifier), None)
    if socket is None:
        raise RuntimeError('Missing Paint Filter style input. Restore the bundled group or rebuild the setup.')
    return socket


def configure_paint(tree, settings, journal):
    if not has(tree, 'Paint Filter'):
        return
    instance = ng.find(tree, 'Paint Filter')
    for name, key in PAINT_INPUTS.items():
        journal.wire(tree, ng.find(tree, key).outputs[0], instance.inputs[name])
    journal.set(paint_menu(instance, 'Socket_7'), 'default_value', STYLES[settings.paint_style])
    journal.set(paint_menu(instance, 'Socket_18'), 'default_value', CANVASES[settings.paint_canvas])


def aperture(g):
    image = g.node('CompositorNodeBokehImage', 'Aperture Image')
    g.into(image, 'Flaps', g.value('Aperture Blades'))
    g.into(image, 'Angle', g.value('Aperture Rotation'))
    g.into(image, 'Catadioptric Size', 0.0)
    g.into(image, 'Color Shift', 0.0)
    blur = g.node('CompositorNodeBokehBlur', 'Aperture Blur')
    source = (g.value('Protected Defocus Source') if g.tree.get(ng.GRAPH_VERSION, 1) >= 6
              else ng.find(g.tree, 'Render and Surface Data').outputs['Image'])
    # Constants while inactive keep the optional convolution off the full image.
    gated = g.switch('Aperture Input', g.value('Use Defocus'), (0, 0, 0, 1), source)
    g.into(blur, 'Image', gated)
    g.into(blur, 'Bokeh', image.outputs[0])
    g.into(blur, 'Size', g.value('Scaled Defocus' if g.tree.get(ng.GRAPH_VERSION, 1) >= 5 else 'Enabled Defocus'))
    g.into(blur, 'Mask', 1.0)
    g.into(blur, 'Extend Bounds', False)


def bloom(g):
    v = g.value
    refined = g.tree.get(ng.GRAPH_VERSION, 1) >= 5
    active = g.math('Bloom Allowed', 'MULTIPLY', v('Bloom Enabled'), v('Effect Enabled' if refined else 'Enabled Result'))
    amount = g.math('Bloom Active Amount', 'MULTIPLY', active, v('Bloom Amount'))
    active = g.math('Bloom Has Amount', 'GREATER_THAN', amount, 0.0)
    source = v('Mix Painterly Result')
    image = g.switch('Bloom Input', active, (0, 0, 0, 1), source)
    glare = g.node('CompositorNodeGlare', 'Bloom Glow')
    for name, value in (('Image', image), ('Type', 'Bloom'), ('Quality', 'High'),
                        ('Threshold', v('Bloom Threshold')), ('Smoothness', 0.25),
                        ('Clamp', False), ('Strength', 1.0), ('Saturation', 1.0),
                        ('Tint', (1, 1, 1, 1)), ('Size', v('Bloom Spread'))):
        g.into(glare, name, value)
    glow = glare.outputs['Glare']
    gray = g.node('CompositorNodeRGBToBW', 'Bloom Luminance')
    g.into(gray, 0, glow)
    lum = g.math('Bloom Positive Luminance', 'MAXIMUM', gray.outputs[0], 0.0)
    soft_color = glow
    if refined:
        from . import refinements
        safe = g.math('Bloom Safe Luminance', 'MAXIMUM', lum, 0.000001)
        lum, soft_color = refinements.shape_bloom(g, lum, glow)
    # Logarithmic levels retain HDR energy and preserve hue by scaling RGB
    # together. Smoothstep boundaries reduce threshold popping during motion.
    log = g.math('Bloom Log Input', 'ADD', lum, 1.0)
    log = g.math('Bloom Log Luminance', 'LOGARITHM', log, 2.0)
    steps = g.math('Bloom Band Position', 'MULTIPLY', log, v('Bloom Steps'))
    coords = g.node('CompositorNodeImageCoordinates', 'Bloom Image Coordinates')
    g.into(coords, 'Image', image)
    position = ng.find(g.tree, 'Render and Surface Data').outputs['Position']
    position = g.switch('Bloom Position Input', active, (0, 0, 0, 1), position)
    fallback = g.node('ShaderNodeMixRGB', 'Bloom Surface Coordinates')
    g.into(fallback, 0, v('Geometry Coverage'))
    g.into(fallback, 1, coords.outputs['Uniform'])
    g.into(fallback, 2, position)
    mapping = g.switch('Bloom Coordinate Mode', v('Bloom Tracking'), coords.outputs['Uniform'], fallback.outputs[0])
    noise = g.node('ShaderNodeTexNoise', 'Bloom Brush Texture')
    if g.inspect:
        if noise.noise_dimensions != '4D':
            raise RuntimeError('Changed Bloom Brush Texture dimensions.')
    else:
        noise.noise_dimensions = '4D'
    for name, value in (('Vector', mapping), ('W', v('Bloom Seed')), ('Scale', v('Bloom Texture Scale')),
                        ('Detail', 2.0), ('Roughness', 0.6)):
        g.into(noise, name, value)
    has_texture = g.math('Bloom Uses Texture', 'GREATER_THAN', v('Bloom Breakup'), 0.0)
    texture = g.switch('Bloom Texture Bypass', has_texture, (0.5, 0.5, 0.5, 1), noise.outputs['Factor'])
    offset = g.math('Bloom Centered Texture', 'SUBTRACT', texture, 0.5)
    offset = g.math('Bloom Texture Amount', 'MULTIPLY', offset, v('Bloom Breakup'))
    coverage = g.math('Bloom Texture Coverage', 'MULTIPLY', lum, 32.0, clamp=True)
    offset = g.math('Bloom Covered Texture', 'MULTIPLY', offset, coverage)
    stepped = g.math('Bloom Perturbed Bands', 'ADD', steps, offset)
    stepped = g.math('Bloom Nonnegative Bands', 'MAXIMUM', stepped, 0.0)
    whole = g.math('Bloom Whole Band', 'FLOOR', stepped)
    fraction = g.math('Bloom Band Fraction', 'FRACT', stepped)
    softness = g.math('Bloom Safe Softness', 'MAXIMUM', v('Bloom Softness'), 0.02)
    start = g.math('Bloom Transition Start', 'SUBTRACT', 1.0, softness)
    start = g.math('Bloom Half Transition', 'MULTIPLY', start, 0.5)
    t = g.math('Bloom Transition Offset', 'SUBTRACT', fraction, start)
    t = g.math('Bloom Transition', 'DIVIDE', t, softness, clamp=True)
    square = g.math('Bloom Transition Squared', 'MULTIPLY', t, t)
    twice = g.math('Bloom Transition Twice', 'MULTIPLY', t, 2.0)
    tail = g.math('Bloom Transition Tail', 'SUBTRACT', 3.0, twice)
    smooth = g.math('Bloom Smooth Transition', 'MULTIPLY', square, tail)
    level = g.math('Bloom Smoothed Bands', 'ADD', whole, smooth)
    level = g.math('Bloom Band Exposure', 'DIVIDE', level, v('Bloom Steps'))
    level = g.math('Bloom HDR Bands', 'POWER', 2.0, level)
    level = g.math('Bloom Band Luminance', 'SUBTRACT', level, 1.0)
    if not refined:
        safe = g.math('Bloom Safe Luminance', 'MAXIMUM', lum, 0.000001)
    ratio = g.math('Bloom Hue Preserving Ratio', 'DIVIDE', level, safe)
    painted = g.scale('Bloom Stepped Color', glow, ratio)
    # Style selects a branch; Soft mode does not evaluate the band texture.
    selected = g.node('CompositorNodeSwitch', 'Bloom Style')
    g.into(selected, 'Off', soft_color)
    g.into(selected, 'On', painted)
    scaled = g.scale('Bloom Strength', selected.outputs[0], amount)
    add = g.node('ShaderNodeMixRGB', 'Bloom Composite')
    if g.inspect:
        if add.blend_type != 'ADD' or add.use_clamp:
            raise RuntimeError('Changed Bloom Composite operation.')
    else:
        add.blend_type, add.use_clamp = 'ADD', False
    g.into(add, 0, 1.0)
    g.into(add, 1, source)
    g.into(add, 2, scaled)
    g.switch('Bloom Bypass', active, source, add.outputs[0])


def configure(tree, settings, journal):
    configure_paint(tree, settings, journal)
    if settings.bokeh_shape != 'GAUSSIAN' and not has(tree, 'Aperture Blur'):
        aperture(Graph(tree, journal))
    if has(tree, 'Aperture Blur'):
        image = ng.find(tree, 'Aperture Image')
        if settings.bokeh_shape == 'POLYGON':
            journal.wire(tree, ng.find(tree, 'Aperture Roundness').outputs[0], image.inputs['Roundness'])
        else:
            into = image.inputs['Roundness']
            for link in list(into.links):
                # A structural change must be reversible too.
                old = link.from_socket
                journal.undo.append(lambda into=into, old=old: ng.wire(tree, old, into))
                tree.links.remove(link)
            journal.set(into, 'default_value', 1.0)
    chosen = 'Depth Defocus' if settings.bokeh_shape == 'GAUSSIAN' else 'Aperture Blur'
    journal.wire(tree, ng.find(tree, chosen).outputs[0], ng.find(tree, 'Defocus Focus Blend').inputs[2])
    if (settings.bloom_enabled or settings.preview == 'BLOOM') and not has(tree, 'Bloom Bypass'):
        bloom(Graph(tree, journal))
    if has(tree, 'Bloom Bypass'):
        journal.set(ng.find(tree, 'Bloom Style').inputs['Switch'], 'default_value', settings.bloom_style == 'STEPPED')
        source = ng.find(tree, 'Bloom Bypass').outputs[0]
    else:
        source = ng.find(tree, 'Mix Painterly Result').outputs[0]
    journal.wire(tree, source, ng.find(tree, 'Preserve Original Alpha').inputs['Image'])


def validate(tree, settings, configured=False):
    if has(tree, 'Paint Filter'):
        n = ng.find(tree, 'Paint Filter', remember=False)
        for name, key in PAINT_INPUTS.items():
            ng.require_link(tree, ng.find(tree, key, remember=False), 0, n, name)
        if any(paint_menu(n, key).is_linked for key in ('Socket_7', 'Socket_18')):
            raise RuntimeError('Paint style selectors must be unlinked. Restore them or rebuild the setup.')
        if configured and (paint_menu(n, 'Socket_7').default_value != STYLES[settings.paint_style] or
                           paint_menu(n, 'Socket_18').default_value != CANVASES[settings.paint_canvas]):
            raise RuntimeError('Paint styles differ from the panel. Refresh Materials to apply them.')
    if has(tree, 'Aperture Blur'):
        aperture(Graph(tree, inspect=True))
        if configured:
            n = ng.find(tree, 'Aperture Image', remember=False)
            if settings.bokeh_shape == 'POLYGON':
                ng.require_link(tree, ng.find(tree, 'Aperture Roundness', remember=False), 0, n, 'Roundness')
            elif n.inputs['Roundness'].is_linked or n.inputs['Roundness'].default_value != 1:
                raise RuntimeError('Round aperture differs from the panel. Refresh Materials.')
    if has(tree, 'Bloom Bypass'):
        bloom(Graph(tree, inspect=True))
        switch = ng.find(tree, 'Bloom Style', remember=False).inputs['Switch']
        if switch.is_linked or (configured and switch.default_value != (settings.bloom_style == 'STEPPED')):
            raise RuntimeError('Bloom style differs from the panel. Refresh Materials.')
    source = 'Bloom Bypass' if has(tree, 'Bloom Bypass') else 'Mix Painterly Result'
    ng.require_link(tree, ng.find(tree, source, remember=False), 0, ng.find(tree, 'Preserve Original Alpha', remember=False), 'Image')
    if configured:
        source = 'Depth Defocus' if settings.bokeh_shape == 'GAUSSIAN' else 'Aperture Blur'
        ng.require_link(tree, ng.find(tree, source, remember=False), 0, ng.find(tree, 'Defocus Focus Blend', remember=False), 2)
