"""Version 5 graph additions: image-relative sizing and usable bloom controls."""
from . import nodes as ng
from .looks import Graph, has

CONTROLS = {'Scale with Resolution': 'scale_with_resolution', 'Reference Width': 'reference_width',
            'Bloom Exposure': 'bloom_exposure', 'Bloom Falloff': 'bloom_falloff'}
NODES = {'Reference Fraction', 'Image Size Scale', 'Resolution Scale', 'Scaled Radius', 'Scaled Defocus', 'Final Effect Enabled'}


def dimensions(g):
    fraction = g.math('Reference Fraction', 'DIVIDE', 1.0, g.value('Reference Width'))
    size = g.node('CompositorNodeRelativeToPixel', 'Image Size Scale')
    if g.inspect:
        if size.data_type != 'FLOAT' or size.reference_dimension != 'X':
            raise RuntimeError('Changed resolution reference. Refresh or restore the generated node.')
    else:
        size.data_type, size.reference_dimension = 'FLOAT', 'X'
    value = next(s for s in size.inputs if s.identifier == 'Float Value')
    if g.inspect:
        if len(value.links) != 1 or value.links[0].from_socket != fraction:
            raise RuntimeError('Changed resolution reference link.')
    else:
        g.journal.wire(g.tree, fraction, value)
    g.into(size, 'Image', ng.find(g.tree, 'Render and Surface Data').outputs['Image'])
    scale = g.switch('Resolution Scale', g.value('Scale with Resolution'), (1, 1, 1, 1), size.outputs['Value'])
    g.math('Scaled Radius', 'MULTIPLY', g.value('Effective Radius'), scale)
    g.math('Scaled Defocus', 'MULTIPLY', g.value('Enabled Defocus'), scale)
    active = g.node('ShaderNodeMath', 'Final Effect Enabled')
    if g.inspect:
        if active.operation != 'MAXIMUM':
            raise RuntimeError('Changed final effect bypass operation.')
    else:
        active.operation = 'MAXIMUM'
    g.into(active, 0, g.value('Enabled Result'))


def shape_bloom(g, luminance, glow):
    exposure = g.math('Bloom Exposure Gain', 'POWER', 2.0, g.value('Bloom Exposure'))
    shape = g.math('Bloom Falloff Shape', 'POWER', luminance, g.value('Bloom Falloff'))
    shaped = g.math('Bloom Shaped Luminance', 'MULTIPLY', shape, exposure)
    ratio = g.math('Bloom Soft Hue Ratio', 'DIVIDE', shaped, g.value('Bloom Safe Luminance'))
    color = g.scale('Bloom Shaped Color', glow, ratio)
    return shaped, color


def upgrade(tree, settings, journal):
    for key, prop in CONTROLS.items():
        if any(n.get(ng.KEY) == key or n.name == key for n in tree.nodes):
            raise RuntimeError('An unversioned update control already exists: ' + key)
        n = ng.feature_node(tree, 'ShaderNodeValue', key, journal)
        n.outputs[0].default_value = getattr(settings, prop)
        journal.driver(n.outputs[0], 'default_value')
        ng.driver(n.outputs[0], 'default_value', settings.id_data, 'sdof.' + prop)
    dimensions(Graph(tree, journal))
    if has(tree, 'Bloom Bypass'):
        g = Graph(tree, journal)
        shaped, color = shape_bloom(g, g.value('Bloom Positive Luminance'), ng.find(tree, 'Bloom Glow').outputs['Glare'])
        journal.wire(tree, shaped, ng.find(tree, 'Bloom Log Input').inputs[0])
        journal.wire(tree, shaped, ng.find(tree, 'Bloom Texture Coverage').inputs[0])
        journal.wire(tree, color, ng.find(tree, 'Bloom Style').inputs['Off'])
        journal.wire(tree, g.value('Effect Enabled'), ng.find(tree, 'Bloom Allowed').inputs[1])
    configure(tree, settings, journal)


def configure(tree, settings, journal):
    radius, defocus = ng.find(tree, 'Scaled Radius').outputs[0], ng.find(tree, 'Scaled Defocus').outputs[0]
    for key, name in (('Bilateral', 'Size'), ('Soft Radius', 0), ('Depth Driven Radius', 1)):
        journal.wire(tree, radius, ng.find(tree, key).inputs[name])
    if has(tree, 'Paint Filter'):
        journal.wire(tree, radius, ng.find(tree, 'Paint Filter').inputs['Size'])
    journal.wire(tree, defocus, ng.find(tree, 'Depth Defocus').inputs['Size'])
    if has(tree, 'Aperture Blur'):
        journal.wire(tree, defocus, ng.find(tree, 'Aperture Blur').inputs['Size'])
    final = ng.find(tree, 'Final Effect Enabled')
    if has(tree, 'Bloom Bypass'):
        journal.wire(tree, ng.find(tree, 'Bloom Has Amount').outputs[0], final.inputs[1])
    else:
        journal.set(final.inputs[1], 'default_value', 0.0)


def validate(tree, settings):
    g = Graph(tree, inspect=True)
    dimensions(g)
    final = ng.find(tree, 'Final Effect Enabled', remember=False)
    if has(tree, 'Bloom Bypass'):
        ng.require_link(tree, ng.find(tree, 'Bloom Has Amount', remember=False), 0, final, 1)
    elif final.inputs[1].is_linked or final.inputs[1].default_value != 0:
        raise RuntimeError('Changed final bloom bypass. Restore its zero input.')

