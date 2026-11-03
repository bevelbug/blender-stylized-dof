"""Explicit, one-time import of saved v1 settings.

Old storage keys appear only here for compatibility. The old extension must be
disabled before migration; its registered classes are never recreated.
"""
import traceback
import bpy
from bpy.props import PointerProperty
from . import core
from .transaction import Journal

LEGACY_PROPERTY = 'sspd'
LEGACY_TAG, LEGACY_ROLE = 'sspd_owner', 'sspd_role'
_bridge_class = None
CONTROL_NAMES = ('enabled', 'scope', 'method', 'preview', 'radius', 'strength',
                 'focus_mode', 'manual_focus', 'focus_offset', 'sharp_width',
                 'near_enabled', 'far_enabled', 'near_falloff', 'far_falloff',
                 'guide_source', 'brush_image', 'pack_image', 'mapping', 'tile_u',
                 'tile_v', 'texture_rotation', 'texture_influence', 'threshold',
                 'edge_protection')


def register_bridge(settings_class=None):
    """Expose Blender's saved RNA group without loading the old add-on.

    Scene.get() cannot read these pointer groups in Blender 5.2. A matching
    property schema is required to deserialize them after the old add-on is off.
    """
    global _bridge_class
    if LEGACY_PROPERTY in bpy.types.Scene.bl_rna.properties:
        return
    if _bridge_class is None:
        if settings_class is None:
            from . import SDOF_Settings
            settings_class = SDOF_Settings
        definitions = {}
        for name, prop in settings_class.__annotations__.items():
            if name in set(CONTROL_NAMES) | set(core.STATE) | {'last_error', 'last_report'}:
                definitions[name] = prop.function(**{k: v for k, v in prop.keywords.items() if k != 'update'})
        _bridge_class = type('SDOF_LegacySettings', (bpy.types.PropertyGroup,), {'__annotations__': definitions})
        bpy.utils.register_class(_bridge_class)
    setattr(bpy.types.Scene, LEGACY_PROPERTY, PointerProperty(type=_bridge_class))


def unregister_bridge():
    global _bridge_class
    prop = bpy.types.Scene.bl_rna.properties.get(LEGACY_PROPERTY)
    if prop and _bridge_class and prop.fixed_type.identifier == _bridge_class.__name__:
        delattr(bpy.types.Scene, LEGACY_PROPERTY)
    if _bridge_class:
        bpy.utils.unregister_class(_bridge_class)
        _bridge_class = None


def legacy_settings(scene):
    return getattr(scene, LEGACY_PROPERTY, None)


def has_legacy(scene):
    old = legacy_settings(scene)
    return old is not None and bool(old.token)


def action_curves(action):
    if action is None:
        return
    if getattr(action, 'is_action_legacy', False):
        yield from action.fcurves
    else:
        for layer in action.layers:
            for strip in layer.strips:
                for bag in getattr(strip, 'channelbags', ()):
                    yield from bag.fcurves


def remap_path(path):
    prefix = LEGACY_PROPERTY + '.'
    return 'sdof.' + path[len(prefix):] if path.startswith(prefix) else path


def copy_controls(old, settings):
    for name in CONTROL_NAMES:
        # RNA getters decode enum values and saved ID pointer wrappers.
        setattr(settings, name, getattr(old, name))


def retire_legacy(scene, old):
    """Final cleanup after commit; no rollback handles survive into this phase."""
    token = old.token
    other_users = [other for other in bpy.data.scenes if other != scene and
                   has_legacy(other) and legacy_settings(other).token == token]
    materials = [mat for mat in bpy.data.materials if mat.node_tree and
                 any(n.get(LEGACY_TAG) == token for n in mat.node_tree.nodes)]
    if not other_users and any(not mat.is_editable or not mat.node_tree.is_editable for mat in materials):
        raise RuntimeError('An old guide material is read-only. Make it local and finish cleanup again.')
    groups = list(dict.fromkeys(g for g in (old.tree, old.effect_tree, old.shader_tree) if g))
    groups.extend(g for g in bpy.data.node_groups if g.get(LEGACY_TAG) == token and g not in groups)
    if not other_users:
        for mat in materials:
            for node in list(mat.node_tree.nodes):
                if node.get(LEGACY_TAG) == token:
                    mat.node_tree.nodes.remove(node)
    for layer in scene.view_layers:
        for key in ('Guide', 'Depth', 'Coverage'):
            aov = layer.aovs.get('SSPD_' + token + '_' + key)
            if aov:
                layer.aovs.remove(aov)
        layer.update_render_passes()
    for key in core.STATE:
        if key == 'token':
            continue
        prop = old.bl_rna.properties[key]
        if prop.type == 'POINTER':
            setattr(old, key, None)
        elif prop.type == 'STRING':
            setattr(old, key, '')
    if not other_users:
        old.brush_image = None
    for group in groups:
        if group.is_editable and group.users == 0:
            bpy.data.node_groups.remove(group)
    # Retain the marker until every cleanup step succeeds, allowing a retry.
    old.token = ''


def execute(operator, context):
    scene, s = context.scene, context.scene.sdof
    journal, copied_actions = Journal(), []
    committed = False
    previous = {p.identifier: getattr(s, p.identifier) for p in s.bl_rna.properties if p.identifier != 'rna_type'}
    try:
        register_bridge()
        prop = bpy.types.Scene.bl_rna.properties.get(LEGACY_PROPERTY)
        if prop and (not _bridge_class or prop.fixed_type.identifier != _bridge_class.__name__):
            raise RuntimeError('Disable the old add-on in Preferences before migrating. Both add-ons must not edit the same setup.')
        if not has_legacy(scene):
            raise RuntimeError('No saved v1 setup was found in this scene.')
        old = legacy_settings(scene)
        if s.token:
            core.check_owner(scene)
            if not core.installed(scene) or not s.effect_tree or not s.shader_tree:
                raise RuntimeError('Restore the updated setup before finishing its old data cleanup.')
            committed = True
            retire_legacy(scene, old)
            core.clear_error(s, 'CLEANUP', 'MIGRATION')
            operator.report({'INFO'}, 'Older setup cleanup finished.')
            return {'FINISHED'}
        token = old.token
        effect, shader, old_tree = old.effect_tree, old.shader_tree, old.tree
        if not effect or not shader or not old_tree or not effect.get('owner_scene'):
            raise RuntimeError('The saved setup is missing a generated node group or its owner.')
        if scene.compositing_node_group != old_tree:
            raise RuntimeError('The old compositor is disconnected. Reconnect it before migration.')
        renders = [n for n in old_tree.nodes if n.get(LEGACY_TAG) == token and n.get(LEGACY_ROLE) == 'render_data']
        if len(renders) != 1 or renders[0].scene not in (scene, effect.get('owner_scene')):
            raise RuntimeError('The saved Render Layers node is missing or points to another scene.')
        layer = scene.view_layers.get(renders[0].layer)
        if layer is None:
            raise RuntimeError('The old view layer is missing. Restore it before migration.')
        materials = [mat for mat in bpy.data.materials if mat.node_tree and
                     any(n.get(LEGACY_TAG) == token for n in mat.node_tree.nodes)]
        if any(not mat.is_editable or not mat.node_tree.is_editable for mat in materials):
            raise RuntimeError('An old guide material is read-only. Make it local before migration.')
        restore_state = (old.backup_tree, old.original_compositing)
        # Cosmetic renaming must never attempt to edit a linked asset.
        image = old.brush_image
        if image and image.is_editable and image.name.startswith('SS Guide'):
            journal.set(image, 'name', 'Brush Guide • ' + image.name.split('•')[-1].strip())
        # Stage private actions so actions shared by other IDs remain untouched.
        animation = scene.animation_data

        def stage_action(owner):
            original = owner.action
            if original and any(remap_path(f.data_path) != f.data_path for f in action_curves(original)):
                action = original.copy()
                copied_actions.append(action)
                for curve in action_curves(action):
                    curve.data_path = remap_path(curve.data_path)
                slot_handle = owner.action_slot_handle

                def restore(owner=owner, original=original, slot_handle=slot_handle):
                    owner.action = original
                    owner.action_slot_handle = slot_handle

                journal.undo.append(restore)
                owner.action = action
                owner.action_slot_handle = slot_handle

        with core.suspend(scene):
            copy_controls(old, s)
        if animation:
            stage_action(animation)
            for track in animation.nla_tracks:
                for strip in track.strips:
                    if strip.type == 'CLIP':
                        stage_action(strip)
            for curve in animation.drivers:
                journal.set(curve, 'data_path', remap_path(curve.data_path))
        collections = (bpy.data.scenes, bpy.data.objects, bpy.data.node_groups, bpy.data.materials,
                       bpy.data.cameras, [m.node_tree for m in bpy.data.materials if m.node_tree])
        for collection in collections:
            for block in collection:
                # These groups retain their old bindings until retired. New
                # generated groups already receive correct native drivers.
                if block in (effect, shader, old_tree) or block.get(LEGACY_TAG) == token:
                    continue
                data = block.animation_data
                if not data or not block.is_editable:
                    continue
                for curve in data.drivers:
                    for var in curve.driver.variables:
                        if var.type == 'SINGLE_PROP':
                            for target in var.targets:
                                if target.id == scene:
                                    journal.set(target, 'data_path', remap_path(target.data_path))
        core.build(context, legacy=(token, LEGACY_TAG, LEGACY_ROLE), layer=layer,
                   materials=materials, restore_state=restore_state)
        # Clear every reversible handle before deleting any legacy resources.
        journal.commit()
        committed = True
        retire_legacy(scene, old)
        core.clear_error(s, 'MIGRATION', 'CLEANUP')
        s.last_report += '\nSaved settings and scene animation migrated. Rerender for the renamed AOVs.'
        operator.report({'INFO'}, 'Saved setup migrated. Rerender, then save the updated blend file.')
        return {'FINISHED'}
    except Exception as exc:
        if committed:
            core.set_error(s, 'Updated setup is ready, but older data cleanup needs attention: ' + str(exc), 'CLEANUP')
            operator.report({'WARNING'}, s.last_error + ' Use Finish Cleanup to retry.')
            return {'FINISHED'}
        journal.rollback()
        # build() is transactional. Before it commits, restore all new controls.
        with core.suspend(scene):
            for name, value in previous.items():
                setattr(s, name, value)
        for action in copied_actions:
            if action.users == 0:
                bpy.data.actions.remove(action)
        core.set_error(s, exc, 'MIGRATION')
        traceback.print_exc()
        operator.report({'ERROR'}, 'Migration rolled back: ' + str(exc))
        return {'CANCELLED'}
