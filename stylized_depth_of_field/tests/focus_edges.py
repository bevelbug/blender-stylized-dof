"""Render high-contrast moving silhouettes with native CPU/GPU compositors."""
import argparse
import json
from pathlib import Path
import sys
import time
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
import numpy as np
import stylized_depth_of_field as addon
from stylized_depth_of_field import nodes as ng
from stylized_depth_of_field.transaction import Journal

p = argparse.ArgumentParser()
p.add_argument('--work-dir', required=True, type=Path)
p.add_argument('--previous-blend', type=Path)
a = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
out = a.work_dir.resolve(); out.mkdir(parents=True, exist_ok=True)
checks, metrics, timings = [], {}, {}
def check(name, condition):
    assert condition, name
    checks.append(name); print('PASS', name, flush=True)

addon.register()
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
check('setup', bpy.ops.sdof.setup() == {'FINISHED'})
s = scene.sdof
scene.render.engine = 'BLENDER_WORKBENCH'
scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 256, 128, 100
scene.render.compositor_device = 'CPU'
s.focus_mode = 'MANUAL'; s.manual_focus = 5; s.sharp_width = .25
s.far_falloff = s.near_falloff = 2
s.radius = 6; s.defocus = 12; s.bloom_enabled = False
s.strength = 1; s.bokeh_shape = 'GAUSSIAN'; s.method = 'KUWAHARA'
tree = s.tree
effect = next(n for n in tree.nodes if getattr(n, 'node_tree', None) == s.effect_tree)
original = np.zeros((128,256,4),np.float32)
original[:,:,:3] = (.03,.08,.3); original[:,:,3] = 1
original[26:102,88:168,:3] = (4,.1,.03)
depth = np.full_like(original,20);depth[:,:,3] = 1;depth[26:102,88:168,:3] = 5
def image(name, values):
    im = bpy.data.images.new(name,256,128,float_buffer=True,alpha=True)
    im.pixels.foreach_set(values.ravel());im.update()
    n=tree.nodes.new('CompositorNodeImage');n.image=im
    return im,n
color, color_node = image('HDR red subject',original)
z, z_node = image('Planar depth',depth)
tree.links.new(color_node.outputs[0],effect.inputs['Image'])
tree.links.new(z_node.outputs[0],effect.inputs['Depth AOV'])
for key in ('Coverage AOV','Guide AOV'):
    for link in list(effect.inputs[key].links):tree.links.remove(link)
effect.inputs['Coverage AOV'].default_value = 1
effect.inputs['Guide AOV'].default_value = (1,1,1,1)

def render(name):
    scene.render.image_settings.file_format='OPEN_EXR'
    scene.render.image_settings.color_mode='RGBA';scene.render.image_settings.color_depth='32'
    scene.render.filepath=str(out/(name+'.exr'))
    start=time.perf_counter();bpy.ops.render.render(write_still=True);timings[name]=time.perf_counter()-start
    im=bpy.data.images.load(scene.render.filepath,check_existing=False)
    values=np.empty(len(im.pixels),np.float32);im.pixels.foreach_get(values)
    values=values.reshape(128,256,4);bpy.data.images.remove(im)
    check('finite '+name,np.isfinite(values).all())
    return values

halo_region=np.zeros((128,256),bool);halo_region[38:90,75:88]=True;halo_region[38:90,168:181]=True
sharp_region=np.zeros_like(halo_region);sharp_region[30:98,92:164]=True
for method in ('BILATERAL','KUWAHARA','PAINT'):
    s.method=method
    for shape in ('GAUSSIAN','ROUND','POLYGON'):
        s.bokeh_shape=shape
        s.protect_focus_edges=False;before=render(method+'_'+shape+'_before')
        s.protect_focus_edges=True;after=render(method+'_'+shape+'_after')
        old=float(np.maximum(before[:,:,0][halo_region]-.03,0).mean())
        new=float(np.maximum(after[:,:,0][halo_region]-.03,0).mean())
        metrics[method+'_'+shape]={'red_halo_before':old,'red_halo_after':new}
        check('halo reduced '+method+' '+shape,new < max(.002,old*.15))
        check('sharp subject preserved '+method+' '+shape,np.abs(after[sharp_region]-original[sharp_region]).max()<1e-5)
        check('original alpha '+method+' '+shape,np.abs(after[:,:,3]-original[:,:,3]).max()<1e-5)
    s.defocus=0
    s.protect_focus_edges=False;old=render(method+'_zero_off')
    s.protect_focus_edges=True;new=render(method+'_zero_on')
    check('zero Defocus unchanged '+method,np.abs(new-old).max()<1e-5)
    s.defocus=12

s.method='KUWAHARA';s.bokeh_shape='GAUSSIAN'
cpu=render('cpu_reference')
scene.render.compositor_device='GPU'
gpu=render('gpu_reference')
check('CPU/GPU agree',np.abs(cpu-gpu).mean()<.002)
metrics['cpu_gpu_mean_difference']=float(np.abs(cpu-gpu).mean())
for offset in (-5,0,5,0):
    color.pixels.foreach_set(np.roll(original,offset,axis=1).ravel());color.update()
    z.pixels.foreach_set(np.roll(depth,offset,axis=1).ravel());z.update()
    pixels=render('motion_'+str(len(checks)))
    mask=np.roll(sharp_region,offset,axis=1)
    check('moving sharp subject retained '+str(offset),np.abs(pixels[mask]-np.roll(original,offset,axis=1)[mask]).max()<1e-5)
    if offset==0:check('motion returns deterministically',np.abs(gpu-pixels).max()<1e-5)

# Subpixel coverage, curved edges, a narrow sharp stem, HDR and varied alpha.
y,x=np.mgrid[:128,:256]
coverage=np.clip(28.5-np.sqrt((x-125.25)**2+(y-63.5)**2),0,1)
coverage[:,124:127]=1
aa=original.copy();aa[:,:,:3]=(.03,.08,.3)
aa[:,:,:3]=aa[:,:,:3]*(1-coverage[:,:,None])+np.array((4,.1,.03))*coverage[:,:,None]
aa[:,:,3]=np.linspace(.2,1,256)[None,:]
aa_depth=depth.copy();aa_depth[:,:,:3]=20-15*coverage[:,:,None]
color.pixels.foreach_set(aa.ravel());color.update()
z.pixels.foreach_set(aa_depth.ravel());z.update()
outside=(coverage==0)&((x>80)&(x<175))
for amount in (8,32,64):
    s.defocus=amount
    s.protect_focus_edges=False;before=render('aa_before_'+str(amount))
    s.protect_focus_edges=True;after=render('aa_after_'+str(amount))
    old=float(np.maximum(before[:,:,0][outside]-.03,0).mean())
    new=float(np.maximum(after[:,:,0][outside]-.03,0).mean())
    metrics['aa_'+str(amount)]={'before':old,'after':new}
    check('curved and thin silhouette halo reduced '+str(amount),new<max(.002,old*.15))
    check('varied alpha preserved '+str(amount),np.abs(after[:,:,3]-aa[:,:,3]).max()<1e-5)
    check('thin sharp stem preserved '+str(amount),np.abs(after[coverage==1]-aa[coverage==1]).max()<1e-5)

# Empty masks must not create NaNs, darken a fully blurred image or lose a sharp one.
for distance in (5,20):
    flat=depth.copy();flat[:,:,:3]=distance
    z.pixels.foreach_set(flat.ravel());z.update()
    s.protect_focus_edges=False;before=render('uniform_before_'+str(distance))
    s.protect_focus_edges=True;after=render('uniform_after_'+str(distance))
    check('uniform focus mask unchanged '+str(distance),np.abs(before-after).max()<1e-5)
color.pixels.foreach_set(original.ravel());color.update()
z.pixels.foreach_set(depth.ravel());z.update();s.defocus=12

color.pack();z.pack()
path=out/'focus_edge_fixture.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(path))
before=render('saved_before')
bpy.ops.wm.open_mainfile(filepath=str(path));scene=bpy.context.scene;s=scene.sdof
after=render('saved_after')
check('save reopen matches',np.abs(before-after).max()<1e-5)
check('schema 6 after reopen',s.effect_tree.get(ng.GRAPH_VERSION)==6)
ng.validate_effect(s.effect_tree,s,configured=True)
check('configured graph validates',True)

if a.previous_blend:
    bpy.app.handlers.load_post.remove(addon._load_post)
    bpy.ops.wm.open_mainfile(filepath=str(a.previous_blend.resolve()))
    bpy.app.handlers.load_post.append(addon._load_post)
    scene=bpy.context.scene;s=scene.sdof;tree=s.effect_tree
    check('real v2.1 graph',tree.get(ng.GRAPH_VERSION)==5)
    before_snapshot=(len(tree.nodes),len(tree.links),len(tree.animation_data.drivers))
    j=Journal();ng.upgrade_effect(tree,s,j);j.rollback()
    check('upgrade rollback restores old graph',before_snapshot==(len(tree.nodes),len(tree.links),len(tree.animation_data.drivers)) and tree.get(ng.GRAPH_VERSION)==5)
    ng.upgrade_effect(tree,s)
    check('old setup upgrades',tree.get(ng.GRAPH_VERSION)==6)
    ng.validate_effect(tree,s,configured=True)
    check('upgraded graph validates',True)
report={'blender':bpy.app.version_string,'version':'2.1.1','passed':len(checks),'checks':checks,'metrics':metrics,'render_seconds':timings}
(out/'focus-edge-report.json').write_text(json.dumps(report,indent=2))
print('FOCUS_EDGES_PASS',len(checks),flush=True)
