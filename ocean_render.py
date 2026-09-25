#!/usr/bin/env python3
# Blender icinde kosulur: blender --background --python ocean_render.py -- --scene scenes/gunbatimi.json
"""ocean-cinema — Gerstner dalga mesh'ini Blender Cycles ile gercek 3B render eder.

JSON:
{
  "output": "renders/gunbatimi.png",
  "ocean": {
    "size": 40, "segments": 320, "choppiness": 0.8,
    "waves": [
      {"amplitude": 0.14, "wavelength": 8.0, "direction_deg": 30, "steepness": 0.6},
      {"amplitude": 0.08, "wavelength": 4.2, "direction_deg": 55, "steepness": 0.5}
    ]
  },
  "sun": {"elevation_deg": 8, "azimuth_deg": 210, "strength": 3.5},
  "camera": {"position": [x,y,z], "look_at": [x,y,z], "lens": 50},
  "render": {"width": 1600, "height": 900, "samples": 128}
}
"""

import argparse
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

G = 9.81


# ---------------------------------------------------------------- yardimcilar

def temiz():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def kamera_kur(konum, hedef, lens=50):
    cam = bpy.data.cameras.new("Cam")
    cam.lens = lens
    co = bpy.data.objects.new("kamera", cam)
    bpy.context.collection.objects.link(co)
    co.location = konum
    yon = Vector(hedef) - Vector(konum)
    co.rotation_euler = yon.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = co
    print(f"  [kamera] konum={tuple(round(x,2) for x in konum)} "
          f"hedef={tuple(round(x,2) for x in hedef)} lens={lens}")


def gunes_vektoru(el_rad, az_rad):
    """Ufuktan yukselis acisiyla gunes yonu (birim, sahne->gunes)."""
    return Vector((math.cos(el_rad) * math.sin(az_rad),
                   -math.cos(el_rad) * math.cos(az_rad),
                   math.sin(el_rad)))


def govcem_diski(cfg, cam_konum):
    """Gunes/ay diski: SUN lambasiyla ayni aci vektorunde emissive mesh."""
    d = cfg["sun"].get("disk")
    if not d:
        return
    el = math.radians(cfg["sun"]["elevation_deg"])
    az = math.radians(cfg["sun"]["azimuth_deg"])
    dist = d.get("distance", 260)
    merkez = gunes_vektoru(el, az) * dist
    bpy.ops.mesh.primitive_circle_add(vertices=96, radius=d.get("radius", 2.5),
                                      fill_type="NGON", location=merkez)
    disk = bpy.context.active_object
    disk.name = "govdem_diski"
    yon = Vector(cam_konum) - merkez
    disk.rotation_euler = yon.to_track_quat("Z", "Y").to_euler()

    m = bpy.data.materials.new("DiskMat")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    renk = list(d.get("color", (1.0, 0.6, 0.3)))
    if len(renk) == 3:
        renk.append(1.0)
    em.inputs["Color"].default_value = renk
    em.inputs["Strength"].default_value = d.get("strength", 40.0)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    disk.data.materials.append(m)


# ---------------------------------------------------------------- Gerstner mesh

def okyanus_mesh(cfg):
    """Buyuk grid olustur, Gerstner formuluyle yer degistir."""
    oc = cfg["ocean"]
    size = oc.get("size", 40)
    seg = oc.get("segments", 320)
    dalgalar = oc.get("waves", [])
    chop = oc.get("choppiness", 0.8)
    t = oc.get("time", 0.0)

    bpy.ops.mesh.primitive_grid_add(x_subdivisions=seg, y_subdivisions=seg, size=size)
    obj = bpy.context.active_object
    obj.name = "okyanus"
    mesh = obj.data

    verts = np.array([v.co[:] for v in mesh.vertices])
    px = np.zeros(len(verts))
    py = np.zeros(len(verts))
    pz = np.zeros(len(verts))

    for w in dalgalar:
        lam = w["wavelength"]
        k = 2 * math.pi / lam
        omega = math.sqrt(G * k)
        steep = w.get("steepness", 0.5) / (k * max(1, len(dalgalar)))
        dir_rad = math.radians(w["direction_deg"])
        dx, dz = math.cos(dir_rad), math.sin(dir_rad)
        faz = k * (dx * verts[:, 0] + dz * verts[:, 1]) - omega * t
        cos_f = np.cos(faz)
        px += steep * dz * cos_f * lam / (2 * math.pi)
        py += steep * dx * cos_f * lam / (2 * math.pi)
        pz += w["amplitude"] * np.sin(faz)

    verts[:, 0] += px * chop
    verts[:, 1] += py * chop
    verts[:, 2] += pz

    for i, v in enumerate(mesh.vertices):
        v.co = verts[i]
    mesh.update()
    for poly in mesh.polygons:
        poly.use_smooth = True
    return obj


# ---------------------------------------------------------------- materyal

def okyanus_materyali(cfg):
    m = bpy.data.materials.new("Okyanus")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.004, 0.025, 0.07, 1)
    bsdf.inputs["Roughness"].default_value = 0.055
    bsdf.inputs["IOR"].default_value = 1.33

    # noise bump
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 18.0
    noise.inputs["Detail"].default_value = 12.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    # hafif subsurface
    if "Subsurface Weight" in bsdf.inputs:
        bsdf.inputs["Subsurface Weight"].default_value = 0.08
        bsdf.inputs["Subsurface Radius"].default_value = (0.3, 0.6, 1.2)
    return m


# ---------------------------------------------------------------- sahne kurulum

def sahne_kur(cfg):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for dv in prefs.devices:
            dv.use = True
        sc.cycles.device = "GPU"
    except Exception as e:
        print("  [uyari] GPU:", e)
    sc.cycles.samples = cfg["render"].get("samples", 128)
    sc.cycles.use_denoising = True
    sc.render.resolution_x = cfg["render"].get("width", 1600)
    sc.render.resolution_y = cfg["render"].get("height", 900)
    sc.view_settings.view_transform = "Filmic"
    sc.view_settings.exposure = cfg["render"].get("exposure", 0.0)
    look = cfg["render"].get("look")
    if look:
        try:
            sc.view_settings.look = look
        except Exception as e:
            print(f"  [uyari] look '{look}': {e}")

    # dunya: Hosek-Wilkie gokyuzu
    dunya = bpy.data.worlds.new("Gokyuzu")
    sc.world = dunya
    dunya.use_nodes = True
    nt = dunya.node_tree
    nt.nodes.clear()
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "HOSEK_WILKIE"
    sun_elev = math.radians(cfg["sun"]["elevation_deg"])
    sun_azim = math.radians(cfg["sun"]["azimuth_deg"])
    sky.sun_elevation = sun_elev
    sky.sun_rotation = sun_azim
    skycfg = cfg.get("sky", {})
    for attr, key, varsayilan in (("turbidity", "turbidity", 2.2),
                                  ("dust_density", "dust", 1.0)):
        try:
            setattr(sky, attr, skycfg.get(key, varsayilan))
        except Exception as e:
            print(f"  [uyari] sky.{attr}: {e}")
    sky.sun_rotation = sun_azim + math.radians(skycfg.get("az_offset", 0))
    bg_node = nt.nodes.new("ShaderNodeBackground")
    bg_node.inputs["Strength"].default_value = cfg["sky"].get("strength", 1.0)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(sky.outputs["Color"], bg_node.inputs["Color"])
    nt.links.new(bg_node.outputs["Background"], out.inputs["Surface"])

    # gunes isigi
    sun_data = bpy.data.lights.new("gunes", "SUN")
    sun_data.energy = cfg["sun"].get("strength", 3.5)
    sun_data.angle = math.radians(1.2)
    sun_data.color = tuple(cfg["sun"].get("color", (1.0, 0.9, 0.75)))
    sun_obj = bpy.data.objects.new("gunes_isigi", sun_data)
    bpy.context.collection.objects.link(sun_obj)
    sun_obj.rotation_euler = gunes_vektoru(sun_elev, sun_azim).to_track_quat("Z", "Y").to_euler()

    return sc


# ---------------------------------------------------------------- okyanus

def okyanus(cfg):
    """Gerstner mesh'i olusturur, materyal atar."""
    oc = cfg["ocean"]
    size = oc.get("size", 40)
    seg = oc.get("segments", 320)
    dalgalar = oc.get("waves", [])
    chop = oc.get("choppiness", 0.8)
    t = oc.get("time", 0.0)

    bpy.ops.mesh.primitive_grid_add(x_subdivisions=seg, y_subdivisions=seg, size=size)
    obj = bpy.context.active_object
    obj.name = "okyanus"
    mesh = obj.data

    verts = np.array([v.co[:] for v in mesh.vertices])
    px = np.zeros(len(verts))
    py = np.zeros(len(verts))
    pz = np.zeros(len(verts))

    for w in dalgalar:
        lam = w["wavelength"]
        k = 2 * math.pi / lam
        omega = math.sqrt(G * k)
        steep = w.get("steepness", 0.5) / (k * max(1, len(dalgalar)))
        dir_rad = math.radians(w["direction_deg"])
        dx, dz = math.cos(dir_rad), math.sin(dir_rad)
        faz = k * (dx * verts[:, 0] + dz * verts[:, 1]) - omega * t
        cos_f = np.cos(faz)
        px += steep * dz * cos_f * lam / (2 * math.pi)
        py += steep * dx * cos_f * lam / (2 * math.pi)
        pz += w["amplitude"] * np.sin(faz)

    verts[:, 0] += px * chop
    verts[:, 1] += py * chop
    verts[:, 2] += pz

    mesh.vertices.foreach_set("co", verts.ravel())
    for poly in mesh.polygons:
        poly.use_smooth = True

    # okyanus materyali
    m = bpy.data.materials.new("Okyanus")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    renk = oc.get("color", (0.004, 0.025, 0.07))
    bsdf.inputs["Base Color"].default_value = (renk[0], renk[1], renk[2], 1)
    bsdf.inputs["Roughness"].default_value = oc.get("roughness", 0.055)
    bsdf.inputs["IOR"].default_value = 1.33
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 18.0
    noise.inputs["Detail"].default_value = 12.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    if "Subsurface Weight" in bsdf.inputs:
        bsdf.inputs["Subsurface Weight"].default_value = 0.08
        bsdf.inputs["Subsurface Radius"].default_value = (0.3, 0.6, 1.2)
    obj.data.materials.append(m)
    return obj


# ---------------------------------------------------------------- ana

def main():
    ayirici = ["--"]
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", required=True)
    a = ap.parse_args(args)

    cfg = json.load(open(a.scene, encoding="utf-8"))
    if os.environ.get("HIZLI") == "1":
        cfg["render"] = {**cfg.get("render", {}), "width": 800, "height": 450,
                         "samples": 40}
        cfg["output"] = "/tmp/onizleme_" + os.path.basename(a.scene).replace(".json", ".png")
        print("  [HIZLI] onizleme modu: 800x450 / 40 sample ->", cfg["output"])
    temiz()

    sc = sahne_kur(cfg)
    okyanus(cfg)

    cam = cfg["camera"]
    kamera_kur(cam["position"], cam["look_at"], cam.get("lens", 50))
    govcem_diski(cfg, cam["position"])

    out = cfg["output"]
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    sc.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print(f"== BİTTİ -> {out}")


if __name__ == "__main__":
    main()