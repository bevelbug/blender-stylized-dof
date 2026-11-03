# Stylized Depth of Field

A Blender add-on by bevelbug.

I made this for shots where I wanted the background to fall away into paint and still keep the subject sharp. It follows your camera's focus, so you can pull focus through a shot the same way you normally would.

<!--
Optional screenshots. Add the files under docs/screenshots/ and remove the comment markers when they're ready. The first image works best as the same frame with the effect off and on.
![Same shot with the effect off and with Paint Filter on](docs/screenshots/before-after.png)
![The Stylized DOF panel open in Blender](docs/screenshots/panel.png)
-->

## Install

You'll need **Blender 5.2 or newer** and a scene using **Cycles or Eevee**. I've tested this on Blender 5.2 on Windows.

Grab `Stylized_Depth_of_Field_v1.3.0.zip` from **Releases** (skip GitHub's automatic source ZIP). In Blender, go to **Edit → Preferences → Add-ons**, open the menu in the top right, and choose **Install from Disk**. Leave the ZIP zipped.

## First render

1. Set the scene camera's focus distance or pick a focus object. You can leave the camera's own Depth of Field off.
2. Press **N** in the 3D View or Compositor, open **Stylized DOF**, and click **Build Setup**.
3. Render with **F12**. If the wrong part of the shot is getting painted, try **Preview → Focus Mask**. Black stays sharp. Switch back to **Final Effect** before saving your render.

**Bilateral** follows a brush pattern on the surface. **Kuwahara** works from the image itself and is good for smoothing detail into larger shapes. **Paint Filter** adds more obvious brushwork. Try it with a stroke size around **16 px** and **4–8 px of Defocus** for a softer background.

Paint Filter can be slow on CPU at higher resolutions. If your setup supports it, try **Advanced → Compositor → GPU**. Changing a surface guide or turning on Position Tracking needs a fresh render. Tracking uses world position, so strokes can still slide on moving or deforming objects.

## Notes

The [full guide](GUIDE.md) covers the controls, upgrading older files, and what to check if the effect isn't showing up. If you hit a bug, open an issue with your Blender version, render engine, and the method you were using. A screenshot or a small example file helps.

The add-on is [GPL-3.0-or-later](LICENSE). The bundled Paint Filter is by Pau Homs and comes from Blender's Online Essentials library under CC0. See the [asset credit](THIRD_PARTY_NOTICES.md).
