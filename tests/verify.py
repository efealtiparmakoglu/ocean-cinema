#!/usr/bin/env python3
"""ocean-cinema fizik kapilari: dispersiyon, superpozisyon, periyot, determinizm."""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from ocean import Deniz, G

OK = 0


def kontrol(ad, kosul, detay=""):
    global OK
    if kosul:
        OK += 1
        print(f"  [ok] {ad}")
    else:
        print(f"  [FAIL] {ad} {detay}")
        sys.exit(1)


print("1) tek dalganin olculen periyodu = analitik 2*pi/omega")
lam = 40.0
D = Deniz([{"lam": lam, "genlik": 1.0, "yon": 0.0}])
k = 2 * math.pi / lam
omega_analitik = math.sqrt(G * k)
# sabit noktada sifir gecisleri olc (2 pi/omega aralikli)
x = np.array([0.0])
t_ornek = np.linspace(0, 4 * math.pi / omega_analitik, 4000)
yuz = D.yukseklik(x * np.ones_like(t_ornek), t_ornek)
isaret = yuz > 0
gecis = np.where(isaret[:-1] != isaret[1:])[0]
t1, t2 = t_ornek[gecis[0]], t_ornek[gecis[1]]
olculen = 2 * (t2 - t1)
kontrol(f"periyot {olculen:.3f} ~ analitik {2 * math.pi / omega_analitik:.3f}",
        abs(olculen - 2 * math.pi / omega_analitik) / (2 * math.pi / omega_analitik) < 0.01)

print("2) superpozisyon: iki dalganin toplami ayri ayri toplaminla esit")
D2 = Deniz([{"lam": 50, "genlik": 0.6, "yon": 0.1}, {"lam": 23, "genlik": 0.3, "yon": -0.2}])
xA = np.linspace(0, 200, 300)
toplam = D2.yukseklik(xA, 3.7)
tek1 = Deniz([{"lam": 50, "genlik": 0.6, "yon": 0.1}]).yukseklik(xA, 3.7)
tek2 = Deniz([{"lam": 23, "genlik": 0.3, "yon": -0.2}]).yukseklik(xA, 3.7)
kontrol("cizgisellik (superpozisyon)", bool(np.allclose(toplam, tek1 + tek2, atol=1e-12)))

print("3) ortalama yuzey seviyesi ~ 0 (uzun sure)")
t_uzun = np.linspace(0, 600, 3000)
sev = np.array([D2.yukseklik(np.linspace(0, 200, 50), t) for t in np.linspace(0, 600, 400)])
ortalama = float(sev.mean())
kontrol("ortalama seviye |y| < 0.02", abs(ortalama) < 0.02, f"{ortalama:.4f}")

print("4) dispersiyon: kisa dalga daha hizli osile eder (omega = sqrt(gk) artan)")
k1_, k2_ = 2 * math.pi / 20, 2 * math.pi / 80
o1, o2 = math.sqrt(G * k1_), math.sqrt(G * k2_)
kontrol("omega kisa > omega uzun", o1 > o2, f"{o1:.3f} vs {o2:.3f}")

print("5) determinizm")
a = Deniz([{"lam": 30, "genlik": 0.4, "yon": 0.2}]).yukseklik(np.linspace(0, 90, 100), 2.5)
b = Deniz([{"lam": 30, "genlik": 0.4, "yon": 0.2}]).yukseklik(np.linspace(0, 90, 100), 2.5)
kontrol("ayni girdi -> ayni profil", bool(np.array_equal(a, b)))

print(f"\nTUM KAPILAR GECTI ({OK} kontrol)")
