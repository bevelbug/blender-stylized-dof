"""Native focus, output sizing and broad stepped bloom regressions.

Blender --background --factory-startup --python-exit-code 1 --threads 8
--python this_file -- --work-dir PATH [--previous-blend V2_BLEND]
"""
import argparse
import json
from pathlib import Path
import sys
import time
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
import numpy as np
from stylized_depth_of_field import core, nodes, focus
from stylized_depth_of_field.transaction import Journal
import stylized_depth_of_field as addon

parser=argparse.ArgumentParser()
parser.add_argument('--work-dir',type=Path,required=True)
parser.add_argument('--previous-blend',type=Path)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
out=args.work_dir.resolve();out.mkdir(parents=True,exist_ok=True)
checks=[];metrics={};timings={}
def check(name,ok):
    assert ok,name
    checks.append(name);print('PASS',name,flush=True)

def render(name,field=None,scalar=False,png=False):
    scene=bpy.context.scene
    journal=Journal()
    if field is not None:
        tree=scene.sdof.effect_tree
        journal.wire(tree,field,nodes.find(tree,'Result').inputs['Image'])
    scene.render.image_settings.file_format='OPEN_EXR'
    scene.render.image_settings.color_mode='RGBA';scene.render.image_settings.color_depth='32'
    scene.render.filepath=str(out/(name+'.exr'))
    try:
        start=time.perf_counter();bpy.ops.render.render(write_still=True)
        timings[name]=time.perf_counter()-start
        im=bpy.data.images.load(scene.render.filepath,check_existing=False)
        if scalar:
            data=float(im.pixels[0])
        else:
            data=np.empty(len(im.pixels),np.float32);im.pixels.foreach_get(data)
            data=data.reshape(im.size[1],im.size[0],4)
        bpy.data.images.remove(im)
        if png:
            scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_depth='8'
            bpy.data.images['Render Result'].save_render(str(out/(name+'.png')),scene=scene)
        check('finite render: '+name,bool(np.isfinite(data).all()))
        return data
    finally:
        journal.rollback()

def focus_value(name):
    tree=bpy.context.scene.sdof.effect_tree
    field=nodes.find(tree,'Focus Plus Offset').inputs[0].links[0].from_socket
    return render(name,field,scalar=True)

addon.register()
scene=bpy.context.scene;scene.render.engine='CYCLES'
check('fresh setup',bpy.ops.sdof.setup()=={'FINISHED'})
s=scene.sdof;tree=s.effect_tree
scene.render.engine='BLENDER_WORKBENCH'
scene.render.compositor_device='CPU'
scene.render.resolution_x,scene.render.resolution_y,scene.render.resolution_percentage=64,32,100
check('native camera path selected',focus.active(tree) and not nodes.focus_status(tree,scene))
cam=scene.camera;cam.location=(0,0,0);cam.rotation_euler=(0,0,0);cam.data.dof.use_dof=False
for frame,distance in ((1,4),(2,10)):
    cam.data.dof.focus_distance=distance;cam.data.dof.keyframe_insert(data_path='focus_distance',frame=frame)
    cam.data.lens=35 if frame==1 else 70;cam.data.keyframe_insert(data_path='lens',frame=frame)
for frame in (2,1,2):
    scene.frame_set(frame)
    check('camera focus/lens keys frame '+str(frame),abs(focus_value('focus_key_'+str(len(checks)))-{1:4,2:10}[frame])<1e-4)
target=bpy.data.objects.new('Native Focus Target',None);scene.collection.objects.link(target)
target.location=(6,2,-8);cam.data.dof.focus_object=target
check('target replacement follows without Sync',abs(focus_value('off_axis')-8)<1e-4 and not nodes.focus_status(tree,scene))
cam.rotation_euler=(.15,.25,.2);cam.scale=(2,.5,1.5)
bpy.context.view_layer.update()
expected=abs((target.matrix_world.translation-cam.matrix_world.translation).dot(cam.matrix_world.col[2].xyz.normalized()))
check('rotated scaled camera target projection',abs(focus_value('rotated_scaled')-expected)<1e-4)
arm=bpy.data.armatures.new('Focus Arm');rig=bpy.data.objects.new('Focus Rig',arm);scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active=rig;rig.select_set(True)
bpy.ops.object.mode_set(mode='EDIT');bone=arm.edit_bones.new('Focus');bone.head=(0,0,-12);bone.tail=(0,1,-12)
bpy.ops.object.mode_set(mode='OBJECT')
cam.location=(0,0,0);cam.rotation_euler=(0,0,0);cam.scale=(1,1,1)
cam.data.dof.focus_object=rig;cam.data.dof.focus_subtarget='Focus'
for frame,z in ((1,0),(2,3)):
    rig.pose.bones['Focus'].location.z=z;rig.pose.bones['Focus'].keyframe_insert(data_path='location',frame=frame)
for frame in (2,1,2):
    scene.frame_set(frame);bpy.context.view_layer.update()
    expected=abs((rig.matrix_world@rig.pose.bones['Focus'].matrix).translation.z)
    check('native focus bone key frame '+str(frame),abs(focus_value('bone_'+str(len(checks)))-expected)<1e-4)
cam.data.dof.focus_subtarget='Missing'
check('missing focus bone still diagnosed','bone is missing' in nodes.focus_status(tree,scene))
cam.data.dof.focus_subtarget='Focus'
other=bpy.data.objects.new('Replacement Camera',bpy.data.cameras.new('Replacement Camera'))
scene.collection.objects.link(other);scene.camera=other;other.data.dof.focus_distance=6.5
check('active camera replacement needs no Sync',abs(focus_value('new_camera')-6.5)<1e-4 and not nodes.focus_status(tree,scene))
bpy.data.objects.remove(cam,do_unlink=True)
check('deleting the previous camera does not break native focus',abs(focus_value('deleted_old_camera')-6.5)<1e-4)
real_support=focus.supported;focus.supported=lambda tree:False
try:
    nodes.bind_focus(tree,scene)
    check('driver fallback remains functional',not focus.active(tree) and abs(focus_value('fallback')-6.5)<1e-4)
finally:focus.supported=real_support
nodes.bind_focus(tree,scene)
check('native path can be restored',focus.active(tree))
s.focus_mode='MANUAL';s.manual_focus=11
check('manual focus remains functional',abs(focus_value('manual')-11)<1e-4)
s.focus_mode='CAMERA'
s.scale_with_resolution=True;s.radius=8;s.defocus=6
for width,height,percentage,factor in ((1920,1080,100,1),(3840,2160,100,2),(3840,2160,50,1)):
    scene.render.resolution_x,scene.render.resolution_y,scene.render.resolution_percentage=width,height,percentage
    check('actual input width scaling '+str((width,percentage)),abs(render('scale_'+str(width)+'_'+str(percentage),nodes.find(tree,'Scaled Radius').outputs[0],scalar=True)-8*factor)<1e-4)
    check('defocus uses same resolution factor '+str((width,percentage)),abs(render('defocus_'+str(width)+'_'+str(percentage),nodes.find(tree,'Scaled Defocus').outputs[0],scalar=True)-6*factor)<1e-4)
s.scale_with_resolution=False
check('pixel mode preserves original size at 4K',abs(render('pixel_mode',nodes.find(tree,'Scaled Radius').outputs[0],scalar=True)-8)<1e-4)

# A fixed fractional-size HDR disk gives matching scene-linear input at 1080p
# and 4K. Empty Workbench is only a carrier for actual native compositing.
for obj in list(scene.objects):
    if obj!=scene.camera:bpy.data.objects.remove(obj,do_unlink=True)
inst=core.effect_instance(scene);parent=s.tree
input_node=parent.nodes.new('CompositorNodeImage')
parent.links.new(input_node.outputs['Image'],inst.inputs['Image'])
s.method,s.radius,s.defocus='KUWAHARA',0,0
s.bloom_enabled=True;s.bloom_spread=.6;s.bloom_amount=.35;s.bloom_threshold=1
s.bloom_steps,s.bloom_softness,s.bloom_breakup=2,.3,0
s.preview='BLOOM';scene.render.compositor_device='GPU'
for width,height in ((1920,1080),(3840,2160)):
    scene.render.resolution_x,scene.render.resolution_y,scene.render.resolution_percentage=width,height,100
    y,x=np.ogrid[:height,:width]
    disk=((x-width//2)**2+(y-height//2)**2)<(height*.015)**2
    data=np.ones((height,width,4),np.float32);data[:,:,:3]=0
    data[disk,:3]=(12,3.6,.6)
    image=bpy.data.images.new('HDR input '+str(width),width=width,height=height,float_buffer=True)
    image.colorspace_settings.name='Non-Color';image.pixels.foreach_set(data.reshape(-1));image.update()
    input_node.image=image;del data,disk
    s.bloom_exposure,s.bloom_falloff=0,1
    dim=render('bloom_dim_'+str(width))
    s.bloom_exposure,s.bloom_falloff=4,.7
    broad=render('bloom_broad_'+str(width),png=True)
    dim_area=int((dim[:,:,:3].max(axis=2)>1e-6).sum())
    area=int((broad[:,:,:3].max(axis=2)>1e-6).sum())
    metrics['halo_'+str(width)]={'dim_pixels':dim_area,'broad_pixels':area,'fraction':area/(width*height)}
    check('broad glow reaches farther '+str(width),area>dim_area*1.5)
    check('bloom works with painterly radius zero '+str(width),broad[:,:,:3].max()>.1)
    s.bloom_steps=6
    different=render('band_density_'+str(width))
    check('bands visibly adjustable '+str(width),np.abs(different-broad).mean()>.0005)
    s.bloom_steps=2
    s.bloom_softness=.9
    soft=render('band_softness_'+str(width))
    check('band edge softness visibly adjustable '+str(width),np.abs(soft-broad).mean()>.0001)
    s.bloom_softness=.3
    s.bloom_spread,s.bloom_exposure,s.bloom_falloff,s.bloom_amount=1,16,.15,32
    pushed=render('pushed_limits_'+str(width))
    check('full spread and maximum gain remain usable '+str(width),pushed[:,:,:3].max()>broad[:,:,:3].max())
    s.bloom_spread,s.bloom_exposure,s.bloom_falloff,s.bloom_amount=.6,4,.7,.35
    if width==1920:
        reference=broad.copy()
        for frame,ev,gamma in ((1,1,1),(2,4,.7)):
            s.bloom_exposure,s.bloom_falloff=ev,gamma
            s.keyframe_insert(data_path='bloom_exposure',frame=frame);s.keyframe_insert(data_path='bloom_falloff',frame=frame)
        visited={}
        for frame in (2,1,2):
            scene.frame_set(frame);pixels=render('bloom_key_'+str(len(checks)))
            if frame in visited:check('bloom exposure/falloff keys repeat exactly',np.abs(pixels-visited[frame]).max()<1e-5)
            visited[frame]=pixels
        check('bloom keys actually change image',np.abs(visited[1]-visited[2]).mean()>.001)
        scene.animation_data_clear();s.bloom_exposure,s.bloom_falloff=4,.7
        scene.render.compositor_device='CPU'
        cpu=render('broad_cpu')
        check('CPU/GPU broad glow agree',np.abs(cpu-reference).mean()<.005)
        scene.render.compositor_device='GPU'
    s.preview='RESULT'
    result=render('final_glow_only_'+str(width))
    check('final output keeps original alpha '+str(width),np.abs(result[:,:,3]-1).max()<1e-5)
    s.strength=0
    zero_strength=render('zero_paint_strength_'+str(width))
    check('zero paint strength does not hide bloom '+str(width),np.abs(result-zero_strength).max()<1e-5)
    s.enabled=False
    bypass=render('bloom_disabled_'+str(width))
    original=np.array(image.pixels[:],np.float32).reshape(height,width,4)
    check('global disable bypasses bloom '+str(width),np.abs(bypass-original).max()<1e-5)
    s.enabled=True;s.strength=1;s.preview='BLOOM'
    if width==3840:
        image.pack();bpy.ops.wm.save_as_mainfile(filepath=str(out/'broad_bloom_portable.blend'))
        before=render('before_reopen')
        bpy.ops.wm.open_mainfile(filepath=str(out/'broad_bloom_portable.blend'))
        scene,s=bpy.context.scene,bpy.context.scene.sdof;tree=s.effect_tree
        after=render('after_reopen')
        check('new controls and preview survive reopen',np.abs(before-after).max()<1e-5 and s.preview=='BLOOM' and s.bloom_exposure==4)

if args.previous_blend:
    bpy.app.handlers.load_post.remove(addon._load_post)
    try:bpy.ops.wm.open_mainfile(filepath=str(args.previous_blend.resolve()))
    finally:bpy.app.handlers.load_post.append(addon._load_post)
    scene,s=bpy.context.scene,bpy.context.scene.sdof;tree=s.effect_tree
    # This comparison isolates the v2.1 neutral bloom controls. Edge protection
    # deliberately changes Defocus boundaries and has its own render suite.
    s.protect_focus_edges=False
    check('upgrade fixture is real v2 graph',tree.get(nodes.GRAPH_VERSION)==4)
    before=render('v2_before_upgrade')
    snapshot=(len(tree.nodes),len(tree.links),len(tree.animation_data.drivers),nodes.binding(nodes.find(tree,'Focus Distance').outputs[0]).mute)
    real_node=nodes.feature_node
    def fail_native(*a,**kw):
        n=real_node(*a,**kw)
        if a[2]=='Native Camera Focus':raise RuntimeError('Injected native binding build failure')
        return n
    nodes.feature_node=fail_native
    try:
        try:nodes.upgrade_effect(tree,s)
        except RuntimeError:pass
    finally:nodes.feature_node=real_node
    check('late upgrade failure restores nodes links curves and mute',snapshot==(len(tree.nodes),len(tree.links),len(tree.animation_data.drivers),nodes.binding(nodes.find(tree,'Focus Distance').outputs[0]).mute) and tree.get(nodes.GRAPH_VERSION)==4)
    nodes.upgrade_effect(tree,s)
    check('upgrade retries with native focus',tree.get(nodes.GRAPH_VERSION)==nodes.looks.VERSION and focus.active(tree))
    after=render('v2_after_upgrade')
    check('normal v2 bloom look preserved at neutral new controls',np.abs(before-after).max()<1e-4)
    check('upgraded setup health passes',core.health_report(bpy.context).startswith('Checks passed'))
    bpy.ops.sdof.remove()
report={'blender':bpy.app.version_string,'version':'2.1.1','passed':len(checks),'checks':checks,'metrics':metrics,'render_seconds':timings}
(out/'results.json').write_text(json.dumps(report,indent=2))
addon.unregister()
print('V21_CHECKS_PASSED',len(checks),flush=True)
