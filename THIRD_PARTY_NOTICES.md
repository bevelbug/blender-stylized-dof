# Paint Filter asset

The bundled `paint_filter.blend` contains the **Paint Filter** node group and its
required helper groups from Blender's Online Essentials library for Blender 5.2.

- Author: **Pau Homs**
- Asset metadata copyright: Blender Foundation
- License: **CC0 1.0 Universal — Public Domain**
- Source project: https://projects.blender.org/blender/blender-assets
- Official asset file: https://cdn.extensions.blender.org/asset-libraries/essentials/nodes/compositing_nodes_essentials_online.blend
- CC0 dedication: https://creativecommons.org/publicdomain/zero/1.0/legalcode

Pinned October 31, 2026. The source file's SHA-256 matches Blender's local
official asset listing: `7446825ab2e5e58085a19846e37d95057c3fe4ef4418ba02e490a99c5c9bbf06`.
The bundled subset is compressed with Blender's library writer and has SHA-256
`97475b42e9e9588e8566eb9664a089d04694b24a1f44786c67aa9cef4ad3ed45`.
Only Paint Filter and its dependencies are included, with their original
author/license metadata. The source was verified through Blender's asset
listing; it is not downloaded at add-on registration or render time.

The add-on appends the group locally when Paint Filter is first selected.
Referenced groups are saved in the user's blend file. Existing user groups with
the same name are not adopted or overwritten. Unused groups imported by this
add-on are released on rollback/removal; user references are retained.

The Python add-on code is licensed under GPL-3.0-or-later; see `LICENSE`.
