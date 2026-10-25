"""Combined pipeline flowchart: OBB branch (A) and PlanetScope branch (B).
Sized for a full text width (6.3 in) so fonts print at their stated size.
Outputs fig_flowchart.pdf (vector) and fig_flowchart.png (600 dpi)."""
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

W, H = 6.3, 4.0
plt.rcParams.update({"font.family": "DejaVu Sans"})

STY = {
    "A":    dict(ec="#3B6A9E", fc="#E8EEF6", tc="#2C5282"),
    "B":    dict(ec="#B85C1E", fc="#FCEBDD", tc="#9C4A12"),
    "data": dict(ec="#6B6B6B", fc="#F1F1F1", tc="#444444"),
    "eval": dict(ec="#5B3E96", fc="#ECE6F5", tc="#4A2F80"),
}
LANE = {"A": "#F5F8FC", "B": "#FDF7F2"}

BW, BH = 1.04, 0.80          # box size (in)
X0, GAP = 0.40, 0.12         # first column left edge, gap between columns
cx = [X0 + BW / 2 + i * (BW + GAP) for i in range(5)]
YA, YB1, YB2 = 3.12, 1.95, 0.60

fig = plt.figure(figsize=(W, H))
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")


def lane(y0, y1, key, label):
    ax.add_patch(FancyBboxPatch((0.06, y0), W - 0.12, y1 - y0, boxstyle="round,pad=0,rounding_size=0.06",
                                fc=LANE[key], ec=STY[key]["ec"], lw=0.6, ls=(0, (4, 2)), zorder=0))
    ax.text(0.2, (y0 + y1) / 2, label, rotation=90, ha="center", va="center",
            fontsize=7.2, fontweight="bold", color=STY[key]["tc"])


def box(col, y, key, title, lines, h=BH):
    x = cx[col] - BW / 2
    s = STY[key]
    ax.add_patch(FancyBboxPatch((x, y - h / 2), BW, h, boxstyle="round,pad=0,rounding_size=0.05",
                                fc=s["fc"], ec=s["ec"], lw=0.9, zorder=2))
    ax.text(cx[col], y + h / 2 - 0.09, title, ha="center", va="top", fontsize=6.6,
            fontweight="bold", color=s["tc"], zorder=3)
    ax.text(cx[col], y + h / 2 - 0.26, "\n".join(lines), ha="center", va="top", fontsize=5.9,
            color="#222222", linespacing=1.25, zorder=3)
    return dict(l=x, r=x + BW, t=y + h / 2, b=y - h / 2, x=cx[col], y=y)


def arrow(p, q, dashed=False, rad=0.0, colour="#404040"):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=7, lw=0.8, color=colour,
                                 ls=(0, (3, 2)) if dashed else "-", shrinkA=0, shrinkB=0,
                                 connectionstyle=f"arc3,rad={rad}", zorder=4))


# ---------- lanes --------------------------------------------------------
lane(2.56, 3.93, "A", "A  OBB deep learning\n(0.3–0.5 m)")
lane(0.08, 2.48, "B", "B  PlanetScope anomaly\ndetection (3 m)")

# ---------- branch A -----------------------------------------------------
a0 = box(0, YA, "data", "DOTA v1.5", ["aerial benchmark", "ship class only", "43,738 ships"])
a1 = box(1, YA, "A", "Tiling", ["512 px tiles,", "256 px stride", "50 % of ship images"])
a2 = box(2, YA, "A", "YOLO11s-OBB", ["DOTA-pretrained", "fine-tuned 10 epochs", "Tesla T4 GPU"])
a3 = box(3, YA, "A", "Maxar transfer test", ["WorldView-2/3, Jan 2022", "300 m crops, native res.", "confidence ≥ 0.10"])
a4 = box(4, YA, "eval", "OBB evaluation", ["DOTA test tiles", "precision, recall, mAP", "Maxar: qualitative"])

for p, q in [(a0, a1), (a1, a2), (a2, a3), (a3, a4)]:
    arrow((p["r"], p["y"]), (q["l"], q["y"]))
arrow((a2["x"] + 0.15, a2["t"]), (a4["x"] - 0.15, a4["t"]), rad=-0.22)
ax.text((a2["x"] + a4["x"]) / 2, a2["t"] + 0.08, "DOTA test tiles", ha="center", va="bottom",
        fontsize=5.6, style="italic", color="#404040")

# ---------- branch B, row 1 ----------------------------------------------
b0 = box(0, YB1, "data", "PlanetScope", ["4-band SR + UDM2", "29 scenes → 27 acq.", "Orders API → GEE"])
b1 = box(1, YB1, "B", "Masking", ["UDM2 cloud, shadow,", "haze + 30 m buffer", "water ∩ analysis zone"])
b2 = box(2, YB1, "B", "Background model", ["25th percentile of", "25 clear acquisitions", "noise = IQR / 1.349"])
b3 = box(3, YB1, "B", "Anomaly score", ["NIR anomaly ÷ noise", "scene-normalised", "peaks ≥ 6 → candidates"])
b4 = box(4, YB1, "eval", "Test evaluation", ["3 held-out acquisitions", "1:1 match within 6 m", "recall, precision, 95 % CI"])

for p, q in [(b0, b1), (b1, b2), (b2, b3)]:
    arrow((p["r"], p["y"]), (q["l"], q["y"]))

# ---------- branch B, row 2 ----------------------------------------------
c0 = box(0, YB2, "data", "WorldCover + zone", ["ESA water mask +20 m", "harbour, shore, open", "zones (QGIS)"])
c1 = box(1, YB2, "data", "Maxar Open Data", ["0.31 m, Jan 2022", "visual reference", "when labelling"])
c2 = box(2, YB2, "B", "Manual labels", ["vessel, uncertain,", "wake, false positive", "test scenes blind"])
c3 = box(3, YB2, "B", "Random forest", ["15 features, 500 trees", "CV grouped by scene", "kept if p ≥ 0.40"])
c4 = box(4, YB2, "eval", "Detection map", ["classifier applied to", "all acquisitions", "detections / 100 m cell"])

arrow((c0["x"] + 0.25, c0["t"]), (b1["l"] + 0.2, b1["b"]))                 # zone -> masking
arrow((c1["r"], c1["y"]), (c2["l"], c2["y"]), dashed=True)                   # Maxar -> labels
arrow((b3["l"] + 0.2, b3["b"]), (c2["r"] - 0.2, c2["t"]))                    # candidates -> labels
arrow((b3["x"], b3["b"]), (c3["x"], c3["t"]))                                # candidates -> RF features
arrow((c2["r"], c2["y"]), (c3["l"], c3["y"]))                                # labels -> RF
arrow((c3["r"], c3["y"]), (c4["l"], c4["y"]))                                # RF -> map
arrow((c3["r"] - 0.12, c3["t"]), (b4["l"] + 0.15, b4["b"]))    # RF -> evaluation
ax.text(b3["x"] + 0.05, (b3["b"] + c3["t"]) / 2, "features", ha="left", va="center",
        fontsize=5.6, style="italic", color="#404040")
ax.text((b3["l"] + 0.2 + c2["r"] - 0.2) / 2 - 0.12, (b3["b"] + c2["t"]) / 2 + 0.02, "to label",
        ha="right", va="center", fontsize=5.6, style="italic", color="#404040")

fig.savefig("fig_flowchart.pdf")
fig.savefig("fig_flowchart.png", dpi=600)
print("saved")
