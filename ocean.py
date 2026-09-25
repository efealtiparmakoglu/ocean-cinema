#!/usr/bin/env python3
"""
ocean-cinema — Gerstner dalga denizi (sifirdan, NumPy).

Derin su dispersiyonu: omega = sqrt(g * k),  k = 2*pi/lambda
Yuzey: coklu Gerstner dalgasinin toplami; tepeciklerde kopuk.

    python3 ocean.py --scene scenes/ay.json
"""

import argparse
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import zlib

import numpy as np

G = 9.81


# ---------------------------------------------------------------- png

def png_yaz(path, img):
    img = np.clip(img, 0, 255).astype(np.uint8)
    h, w, _ = img.shape
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += img[y].tobytes()

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                + chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b""))


# ---------------------------------------------------------------- deniz

class Deniz:
    """Coklu Gerstner dalgasi. Her dalga: yon (radyan), lam (dalgaboyu), genlik."""

    def __init__(self, dalgalar):
        self.k = np.array([2 * math.pi / d["lam"] for d in dalgalar])
        self.omega = np.sqrt(G * self.k)                  # derin su dispersiyonu
        self.dir = np.array([[math.cos(d["yon"]), math.sin(d["yon"])]
                             for d in dalgalar])
        self.amp = np.array([d["genlik"] for d in dalgalar])
        self.sayi = len(dalgalar)

    def yukseklik(self, x, t):
        """x boyunca yuzey yuksekligi profili (1D, yan gorunum)."""
        x = np.atleast_1d(np.asarray(x, float))
        yuz = np.zeros(x.shape[0])
        for i in range(self.sayi):
            faz = self.k[i] * (x * self.dir[i, 0]) - self.omega[i] * t
            yuz += self.amp[i] * np.sin(faz)
        return yuz

    def egim(self, x, t):
        """Yuzey egimi (dy/dx) — gemi yatisi icin."""
        x = np.atleast_1d(np.asarray(x, float))
        eg = np.zeros(x.shape[0])
        for i in range(self.sayi):
            faz = self.k[i] * (x * self.dir[i, 0]) - self.omega[i] * t
            eg += self.amp[i] * self.k[i] * self.dir[i, 0] * np.cos(faz)
        return eg


def gorece_baskin(deniz, x, t):
    """Tepe noktalarinda kopuk: yukseklik + egim buyukse kopuk yogun."""
    yuz = deniz.yukseklik(x, t)
    eg = np.abs(deniz.egim(x, t))
    esik = yuz.max() * 0.55
    return (yuz > esik) & (eg > deniz.k.mean() * deniz.amp.mean() * 0.45)


# ---------------------------------------------------------------- cizim

def sahne_ciz(D, t, cfg, W, H):
    p = cfg["palette"]
    # gokyuzu tam yukseklige degrade (deniz ustune cizilecek)
    ufuk = int(H * 0.44)
    img = np.zeros((H, W, 3))
    ust, alt = np.array(p["sky_top"]), np.array(p["sky_bottom"])
    for y in range(H):
        f = min(1.0, y / max(1, ufuk - 1))
        img[y] = ust * (1 - f) + alt * f
    # gunes/ay diski + glitter yolu
    gx, gy = int(W * p["cekcik_x"]), int(ufuk * 0.35)
    r = int(W * p.get("cekcik_r", 0.035))
    yy, xx = np.mgrid[0:H, 0:W]
    disk = (xx - gx) ** 2 + (yy - gy) ** 2 < r ** 2
    img[disk] = np.array(p["cekcik_renk"])
    # glitter: disk altinda denize dusen titrek sutun
    sutun = (np.abs(xx - gx) < int(W * 0.045)) & (yy > gy) & (yy < ufuk + 40)
    titre = (np.sin(yy * 0.7 + t * 6) * 0.5 + 0.5) * \
            (np.abs(xx - gx) / max(1, int(W * 0.045)))
    img[sutun] += p.get("glitter", 140) * (1 - titre[sutun])[:, None] * 0.5

    # deniz: yuzey profilinden dolgu
    yuz = D.yukseklik(np.linspace(0, W - 1, W), t) * cfg["amplitud_olcek"]
    olcek_px = cfg.get("amplitud_px", 22)
    yuzey_y = ufuk + 30 + yuz * olcek_px
    deniz_ust = np.array(p["sea_top"])
    deniz_alt = np.array(p["sea_bottom"])
    for x in range(W):
        y0 = int(yuzey_y[x])
        derinlik_f = np.linspace(0, 1, max(1, H - y0))[:, None]
        img[y0:H, x] = deniz_ust * (1 - derinlik_f) + deniz_alt * derinlik_f
    # dalga yuzey cizgisi
    for x in range(W):
        y0 = int(yuzey_y[x])
        if 0 <= y0 < H:
            img[y0] = np.array(p["yuzey_cizgi"])

    # kopuk tepeler
    kopuk = gorece_baskin(D, np.linspace(0, W - 1, W), t)
    for x in np.where(kopuk)[0]:
        y0 = int(yuzey_y[x])
        if 0 <= y0 < H - 2:
            img[y0:y0 + 2, x] = p.get("kopuk_renk", (245, 245, 245))
    return img


# ---------------------------------------------------------------- ana

def kos(cfg):
    sim = cfg["sim"]
    D = Deniz(sim["dalgalar"])
    W, H = sim.get("width", 960), sim.get("height", 540)
    fps = sim.get("fps", 20)
    adet = sim.get("frames", 160)
    out = cfg["output"]
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    tmp = out + ".frames"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    for f in range(adet):
        img = sahne_ciz(D, f / fps, cfg, W, H)
        png_yaz(f"{tmp}/f{f:05d}.png", img)
        if f % 40 == 0:
            print(f"  kare {f}/{adet}")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps),
                    "-i", f"{tmp}/f%05d.png",
                    "-vf", "palettegen=max_colors=256:stats_mode=diff", f"{tmp}/pal.png"],
                   check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps),
                    "-i", f"{tmp}/f%05d.png", "-i", f"{tmp}/pal.png",
                    "-lavfi", "paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle",
                    "-loop", "0", out], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"== BİTTİ -> {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", required=True)
    a = ap.parse_args()
    cfg = json.load(open(a.scene, encoding="utf-8")) if (json := __import__("json")) else None
    kos(cfg)
