"""Small reversible journal for material/AOV edits during construction."""


class Journal:
    def __init__(self):
        self.undo = []

    def created_node(self, tree, node):
        self.undo.append(lambda: tree.nodes.remove(node))

    def created_aov(self, layer, aov):
        self.undo.append(lambda: layer.aovs.remove(aov))

    def render_pass(self, layer, name, value, sources):
        """Native pass sockets may be recreated; restore links by identifiers."""
        old = getattr(layer, name)
        if old == value:
            return
        links = [(tree, link.from_node, link.from_socket.name, link.to_node,
                  link.to_socket.identifier) for tree, node in sources for out in node.outputs for link in out.links]
        def restore():
            setattr(layer, name, old)
            layer.update_render_passes()
            for tree, source, output, sink, identifier in links:
                into = next((s for s in sink.inputs if s.identifier == identifier), None)
                out = source.outputs.get(output)
                if out and into and not any(link.from_socket == out for link in into.links):
                    tree.links.new(out, into)
        self.undo.append(restore)
        setattr(layer, name, value)
        layer.update_render_passes()

    def set(self, owner, name, value):
        old = getattr(owner, name)
        if old != value:
            self.undo.append(lambda: setattr(owner, name, old))
            setattr(owner, name, value)

    def property(self, owner, key, value):
        existed, old = key in owner, owner.get(key)
        def restore():
            if existed:
                owner[key] = old
            elif key in owner:
                del owner[key]
        self.undo.append(restore)
        owner[key] = value

    def wire(self, tree, source, sink):
        previous = [link.from_socket for link in sink.links]
        if previous == [source]:
            return

        def restore():
            for link in list(sink.links):
                tree.links.remove(link)
            for old_source in previous:
                tree.links.new(old_source, sink)

        self.undo.append(restore)
        tree.links.new(source, sink)

    def driver(self, owner, path):
        """Snapshot a binding without deleting its F-curve or user modifiers."""
        tree = owner.id_data
        full_path = owner.path_from_id(path)
        fc = tree.animation_data.drivers.find(full_path) if tree.animation_data else None
        if fc is None:
            self.undo.append(lambda: owner.driver_remove(path))
            return
        d = fc.driver
        values = (d.type, d.expression, d.use_self, fc.mute)
        fields = ('id_type', 'id', 'data_path', 'bone_target', 'transform_type',
                  'transform_space', 'rotation_mode', 'use_fallback_value', 'fallback_value')
        variables = [(v.name, v.type, [{key: getattr(t, key) for key in fields}
                                     for t in v.targets]) for v in d.variables]

        def restore():
            current = owner.driver_add(path)
            binding = current.driver
            for v in list(binding.variables):
                binding.variables.remove(v)
            binding.type, binding.expression, binding.use_self, current.mute = values
            for name, kind, targets in variables:
                v = binding.variables.new()
                v.name, v.type = name, kind
                for target, saved in zip(v.targets, targets):
                    for key, value in saved.items():
                        setattr(target, key, value)

        self.undo.append(restore)

    def removed_aov(self, layer, aov):
        # Deleted RNA handles cannot be used by a rollback closure.
        name, kind = aov.name, aov.type

        def restore():
            restored = layer.aovs.get(name) or layer.aovs.add()
            restored.name, restored.type = name, kind

        self.undo.append(restore)
        layer.aovs.remove(aov)

    def rollback(self):
        failures = []
        for action in reversed(self.undo):
            try:
                action()
            except (ReferenceError, RuntimeError, TypeError, AttributeError, KeyError) as exc:
                failures.append(str(exc))
        self.undo.clear()
        return failures

    def commit(self):
        self.undo.clear()
