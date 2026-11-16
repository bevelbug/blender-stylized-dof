"""Extend defocused surroundings behind sharp silhouettes before filtering."""
from . import nodes as ng
from .looks import Graph, has

CONTROLS = {'Protect Focus Edges': 'protect_focus_edges'}
NODES = {'Protect Focus Edges', 'Focus Edge Protection Active', 'Sharp Surface Mask', 'Sharp Edge Coverage',
         'Defocused Surface Mask', 'Isolate Defocused Surfaces', 'Defocus Edge Reach', 'Painterly Edge Reach',
         'Filter Edge Reach', 'Padded Edge Reach', 'Extend Defocused Surfaces', 'Protected Defocus Source'}


def specification(g):
    v = g.value
    active = g.math('Focus Edge Protection Active', 'MULTIPLY', v('Use Defocus'), v('Protect Focus Edges'))
    sharp = g.math('Sharp Surface Mask', 'LESS_THAN', v('Covered Focus Mask'), 0.001)
    border = g.node('CompositorNodeDilateErode', 'Sharp Edge Coverage')
    g.into(border, 'Mask', sharp)
    # Remove mixed edge pixels as well as fully sharp ones from the blur source.
    g.into(border, 'Size', 2)
    g.into(border, 'Type', 'Steps')
    keep = g.math('Defocused Surface Mask', 'SUBTRACT', 1.0, border.outputs[0])
    cut = g.node('CompositorNodeSetAlpha', 'Isolate Defocused Surfaces')
    original = ng.find(g.tree, 'Render and Surface Data').outputs['Image']
    g.into(cut, 'Image', original)
    g.into(cut, 'Alpha', keep)
    # Temporary alpha is solely an inpaint mask. Original transparency is
    # restored downstream; treating it as a hole here would alter glass/alpha.
    g.into(cut, 'Type', 'Replace Alpha')
    # Fill a sufficient border for the following blur and painterly footprint.
    # Deep interiors may remain empty: the final focus blend restores them.
    blur_reach = g.math('Defocus Edge Reach', 'MULTIPLY', v('Scaled Defocus'), 3.0)
    paint_reach = g.math('Painterly Edge Reach', 'MULTIPLY', v('Scaled Radius'), 4.0)
    reach = g.math('Filter Edge Reach', 'ADD', blur_reach, paint_reach)
    reach = g.math('Padded Edge Reach', 'ADD', reach, 8.0)
    fill = g.node('CompositorNodeInpaint', 'Extend Defocused Surfaces')
    g.into(fill, 'Image', cut.outputs[0])
    g.into(fill, 'Size', reach)
    return g.switch('Protected Defocus Source', active, original, fill.outputs[0])


def upgrade(tree, settings, journal):
    if any(n.get(ng.KEY) == 'Protect Focus Edges' or n.name == 'Protect Focus Edges' for n in tree.nodes):
        raise RuntimeError('Unversioned focus-edge nodes already exist. Restore or rebuild the generated setup.')
    n = ng.feature_node(tree, 'ShaderNodeValue', 'Protect Focus Edges', journal)
    n.outputs[0].default_value = settings.protect_focus_edges
    journal.driver(n.outputs[0], 'default_value')
    ng.driver(n.outputs[0], 'default_value', settings.id_data, 'sdof.protect_focus_edges')
    specification(Graph(tree, journal))
    configure(tree, journal)


def configure(tree, journal):
    source = ng.find(tree, 'Protected Defocus Source').outputs[0]
    # Do not restore the sharp subject before painting: it would be spread again.
    # The existing final blend still uses the untouched original image.
    journal.wire(tree, source, ng.find(tree, 'Depth Defocus').inputs['Image'])
    journal.wire(tree, source, ng.find(tree, 'Defocus Focus Blend').inputs[1])
    if has(tree, 'Aperture Input'):
        journal.wire(tree, source, ng.find(tree, 'Aperture Input').inputs['On'])


def validate(tree):
    source = specification(Graph(tree, inspect=True))
    for sink, socket in (('Depth Defocus', 'Image'), ('Defocus Focus Blend', 1)):
        ng.require_link(tree, source.node, 0, ng.find(tree, sink, remember=False), socket)
