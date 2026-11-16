# Stylized Depth of Field

A Blender add-on by bevelbug.

I made this for shots where I wanted the background to fall away into paint and still keep the subject sharp. It follows your camera's focus, so you can pull focus through a shot the same way you normally would.

<!--
Optional screenshots. Add the files under docs/screenshots/ and remove the comment markers when they're ready. The first image works best as the same frame with the effect off and on.
![Same shot with the effect off and with Paint Filter on](docs/screenshots/before-after.png)
![The Stylized DOF panel open in Blender](docs/screenshots/panel.png)
-->

## Install

You'll need **Blender 5.2 or newer** and a scene using **Cycles or Eevee**. Tested on Blender 5.2 and 5.3 on Windows.

Grab `Stylized_Depth_of_Field_v2.1.1.zip` from **Releases** (skip GitHub's automatic source ZIP). In Blender, go to **Edit → Preferences → Add-ons**, open the menu in the top right, and choose **Install from Disk**. Leave the ZIP zipped.

## First render

1. Set the scene camera's focus distance or pick a focus object. You can leave the camera's own Depth of Field off.
2. Press **N** in the 3D View or Compositor, open **Stylized DOF**, and click **Build Setup**.
3. Render with **F12**. If the wrong part of the shot is getting painted, try **Preview → Focus Mask**. Black stays sharp. Switch back to **Final Effect** before saving your render.

**Bilateral** follows a brush pattern on the surface. **Kuwahara** works from the image itself and is good for smoothing detail into larger shapes. **Paint Filter** adds more obvious brushwork. Try it with a stroke size around **16 px** and **4–8 px of Defocus** for a softer background.

Paint Filter can be slow on CPU at higher resolutions. If your setup supports it, try **Advanced → Compositor → GPU**. Changing a surface guide or turning on Position Tracking needs a fresh render. Tracking uses world position, so strokes can still slide on moving or deforming objects.

## What's in v2

**New in 2.1.1:** Protect Sharp Edges reduces the blurred duplicate outline that Defocus could leave around a sharp subject. It starts on and appears below Defocus. Turn it off to return to the earlier filtering behavior.

Paint Filter now exposes **Watercolor, Oil Paint, and Digital Geometric** styles, with brush sharpness, color variation, pigment pooling, and canvas controls. They live in the Brush and Canvas sections so the main panel stays short.

**Defocus Shape** adds round and polygonal bokeh. Raise Defocus above zero to see it. **Bloom** adds either a soft glow or stepped washes around bright areas. Use Preview Bloom Only to see its bands; Band Density and Edge Softness control their definition. Only the glow gets stepped; the rest of your image keeps its shading.

Older setups upgrade when you reopen them, keeping existing controls and animation. New resolution scaling starts off; neutral Glow Exposure and Falloff preserve ordinary 2.0 looks. Save a copy before upgrading a production shot; files saved with the new edge-protection setup need 2.1.1 or newer to edit it.

## Making bloom easier to push

In 2.1, **Glow Exposure** boosts faint glow before the stepping happens, and **Falloff** lets you lift its outer tail. Try Spread 0.4, Glow Exposure +3, Falloff 0.75, Amount 0.25 and Band Density 2. Use **Preview Bloom Only** while adjusting, then switch back to Final Effect. Raise Highlight Threshold if too much of the scene starts glowing.

Bloom now stays available with painterly Strength or Radius zero. The main Enable Effect checkbox still bypasses everything. Original alpha is preserved, so a transparent background can hide the halo in your final composite.

For switching between 1080p and 4K, try **Advanced → Scale with Resolution**, with Reference Width 1920. Native camera information also follows focus changes automatically where supported. Existing look controls and animation are kept when upgrading.

## Notes

The [full guide](GUIDE.md) covers the controls, upgrading older files, and what to check if the effect isn't showing up. If you hit a bug, open an issue with your Blender version, render engine, and the method you were using. A screenshot or a small example file helps.

The add-on is [GPL-3.0-or-later](LICENSE). The bundled Paint Filter is by Pau Homs and comes from Blender's Online Essentials library under CC0. See the [asset credit](THIRD_PARTY_NOTICES.md).
