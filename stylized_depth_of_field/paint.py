"""Pinned, local CC0 Paint Filter asset. No downloads at runtime."""
from pathlib import Path

import bpy

ASSET_TAG = 'sdof_paint_asset'
ASSET_VERSION = 'essentials-5.2-2026-10-31'


def cleanup_unused():
    # Helpers can reference each other. Never remove a group still used by a
    # scene or by user nodes, even after the add-on setup has been removed.
    while True:
        unused = [g for g in bpy.data.node_groups if g.get(ASSET_TAG) == ASSET_VERSION and g.users == 0]
        if not unused:
            break
        for group in unused:
            bpy.data.node_groups.remove(group)


def load(journal):
    for group in bpy.data.node_groups:
        if group.get(ASSET_TAG) == ASSET_VERSION and group.get('sdof_paint_root'):
            return group
    path = Path(__file__).resolve().parent / 'assets' / 'paint_filter.blend'
    if not path.is_file():
        raise RuntimeError('The bundled Paint Filter is missing. Reinstall the complete add-on ZIP.')
    before = {g.as_pointer() for g in bpy.data.node_groups}
    try:
        with bpy.data.libraries.load(str(path), link=False) as (source, target):
            if 'Paint Filter' not in source.node_groups:
                raise RuntimeError('The bundled Paint Filter could not be read. Reinstall the add-on.')
            target.node_groups = ['Paint Filter']
        group = target.node_groups[0]
    finally:
        created = [g for g in bpy.data.node_groups if g.as_pointer() not in before]
        for item in created:
            item[ASSET_TAG] = ASSET_VERSION
            item.use_fake_user = False
        journal.undo.append(cleanup_unused)
    group['sdof_paint_root'] = True
    group.name = 'Stylized DOF • Paint Filter'
    return group


def validate(instance):
    group = instance.node_tree
    if not group or group.get(ASSET_TAG) != ASSET_VERSION or not group.get('sdof_paint_root'):
        raise RuntimeError('The generated Paint Filter was replaced. Restore it or remove and rebuild the setup.')
    for name in ('Image', 'Size', 'Simplification', 'Edge Breakup', 'Constraints', 'Use Tracking', 'Depth', 'Position',
                 'Sharpness', 'Accidental Colors', 'Pooling', 'Seed', 'Scale', 'Overlay Texture'):
        if instance.inputs.get(name) is None:
            raise RuntimeError('Missing Paint Filter input: ' + name + '. Reinstall the add-on and restore its generated group.')
