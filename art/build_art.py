"""Draw the report's page banners as SVG, then render them to PNG with headless Edge.

Original flat illustrations: no photographs, real people, logos or text.
Run this only when the art changes. The PNGs are committed.
"""
import subprocess
import tempfile
from pathlib import Path

ART = Path(__file__).resolve().parent
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

PAPER, INK, TEAL, SOFT = "#FBF6EE", "#1F2933", "#0F4C5C", "#BFD7DA"
TERRA, GOLD, SKY, LEAF = "#C8553D", "#E3A857", "#DCEBEA", "#5E8C61"
SKIN = ["#8D5B3E", "#B9805A", "#D9A77C"]
GROUND = 172


def rect(x, y, w, h, fill, rx=0):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" rx="{rx}"/>'


def circle(x, y, r, fill):
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}"/>'


def poly(points, fill):
    return f'<polygon points="{points}" fill="{fill}"/>'


def path(d, fill):
    return f'<path d="{d}" fill="{fill}"/>'


def person(x, kind="shirt", top=TEAL, bottom=INK, skin=1, scale=1.0, flip=False):
    """A faceless standing figure, feet on the ground line, about 46 px tall at scale 1."""
    s = SKIN[skin]
    parts = []
    if kind == "kurung":  # long tunic and skirt, tudung
        parts += [path("M-6,-30 L-10,0 L10,0 L6,-30 Z", bottom), path("M-7,-32 L-9,-13 L9,-13 L7,-32 Z", top),
                  circle(0, -38, 5.5, s), path("M-7,-37 Q-7,-46 0,-46 Q7,-46 7,-37 L8,-28 Q0,-24 -8,-28 Z", TERRA if top != TERRA else GOLD),
                  circle(0, -38, 3.6, s)]
    elif kind == "melayu":  # baju melayu, songkok
        parts += [rect(-5, -14, 4.5, 14, bottom), rect(0.5, -14, 4.5, 14, bottom), rect(-7, -32, 14, 20, top, 2),
                  rect(-7.5, -18, 15, 7, GOLD, 1), circle(0, -38, 5.5, s), rect(-5.5, -46, 11, 6, INK, 1)]
    elif kind == "dress":  # hair tied back, dress
        parts += [path("M-5,-32 L-9,0 L9,0 L5,-32 Z", top), circle(0, -38, 5.5, s),
                  path("M-6,-38 Q-6,-45 0,-45 Q6,-45 6,-38 Q2,-42 -6,-38 Z", INK), circle(-6, -41, 2.5, INK)]
    else:  # shirt and trousers
        parts += [rect(-5, -15, 4.5, 15, bottom), rect(0.5, -15, 4.5, 15, bottom), rect(-7, -32, 14, 18, top, 3),
                  circle(0, -38, 5.5, s), path("M-5.5,-39 Q-5,-45 0,-45 Q5,-45 5.5,-39 Q0,-42 -5.5,-39 Z", INK)]
    flip_part = "scale(-1,1)" if flip else ""
    return f'<g transform="translate({x},{GROUND}) {flip_part} scale({scale})">{"".join(parts)}</g>'


def child(x, top=GOLD, skin=1):
    return person(x, "shirt", top, INK, skin, 0.62)


def cane(x):
    return rect(x, GROUND - 22, 1.8, 22, INK)


def basket(x, y):
    return (path(f"M{x - 8},{y} L{x - 6},{y + 10} L{x + 6},{y + 10} L{x + 8},{y} Z", GOLD)
            + circle(x - 3, y - 1, 3, LEAF) + circle(x + 3, y - 1, 3, TERRA))


def palm(x, height=70, ground=GROUND):
    top = ground - height
    fronds = "".join(
        path(f"M{x},{top} Q{x + dx * .5},{top - lift} {x + dx},{top + drop} Q{x + dx * .5},{top - lift + 8} {x},{top} Z", LEAF)
        for dx, lift, drop in [(-34, 14, 12), (-26, 24, -2), (-8, 26, -18), (12, 26, -16), (28, 22, -2), (34, 12, 14)])
    trunk = path(f"M{x - 2},{ground} Q{x - 6},{ground - height / 2} {x - 1},{top} L{x + 2},{top} Q{x - 1},{ground - height / 2} {x + 3},{ground} Z", INK)
    return trunk + fronds + circle(x - 1, top + 3, 2.5, TERRA) + circle(x + 3, top + 4, 2.5, TERRA)


def rumah(x):
    """Rumah kampung: raised on posts, steep attap roof, verandah, steps."""
    y = GROUND
    posts = "".join(rect(x + d, y - 30, 3.5, 30, INK) for d in (6, 34, 62, 90))
    body = rect(x, y - 62, 100, 32, GOLD) + rect(x - 4, y - 32, 108, 3.5, INK)
    slats = "".join(rect(x + 2 + i * 8, y - 62, 1, 32, "#CF9445") for i in range(13))
    windows = "".join(rect(x + d, y - 54, 12, 16, TEAL) + rect(x + d + 5.5, y - 54, 1, 16, SOFT) for d in (10, 78))
    door = rect(x + 44, y - 58, 14, 26, INK)
    roof = poly(f"{x - 12},{y - 62} {x + 50},{y - 104} {x + 112},{y - 62}", TERRA)
    gable = poly(f"{x + 30},{y - 76} {x + 50},{y - 90} {x + 70},{y - 76}", PAPER)
    steps = "".join(rect(x + 112 + i * 5, y - 24 + i * 8, 5, 3, INK) for i in range(3))
    stairs = poly(f"{x + 104},{y - 30} {x + 110},{y - 30} {x + 134},{y} {x + 128},{y}", INK)
    return posts + body + slats + windows + door + roof + gable + stairs + steps


def shophouse(x, wall, trim, width=64, height=112):
    y = GROUND
    arch = lambda ax: path(f"M{ax},{y} V{y - 26} A10,10 0 0 1 {ax + 20},{y - 26} V{y} Z", INK)
    uppers = "".join(rect(x + d, y - height + 18, 12, 24, TEAL, 6) + rect(x + d + 5.5, y - height + 18, 1, 24, SOFT)
                     for d in (10, 42))
    return (rect(x, y - height, width, height, wall) + rect(x - 2, y - height - 4, width + 4, 6, trim)
            + uppers + rect(x, y - 56, width, 5, trim) + arch(x + 6) + arch(x + 36)
            + poly(f"{x + 14},{y - height - 4} {x + width / 2},{y - height - 16} {x + width - 14},{y - height - 4}", trim))


def tower(x, width, height, wall, window, cap=None):
    y = GROUND
    rows = "".join(rect(x + 7 + c * (width - 14) / 4, y - height + 12 + r * 14, (width - 14) / 4 - 4, 7, window)
                   for r in range((height - 24) // 14) for c in range(4))
    top = "" if cap is None else rect(x + width / 2 - 1, y - height - 18, 2, 18, cap) + rect(x + width * .2, y - height - 5, width * .6, 5, cap)
    return rect(x, y - height, width, height, wall) + rows + top


def backdrop(clouds=((760, 34), (1040, 26))):
    cloud = lambda x, y: "".join(circle(x + dx, y + dy, r, PAPER) for dx, dy, r in
                                 [(0, 6, 10), (14, 0, 14), (32, 4, 11), (46, 8, 8)]) + rect(x - 8, y + 8, 62, 8, PAPER, 4)
    return (rect(0, 0, 1280, 200, SKY) + circle(640, 40, 24, "#F2D9A8")
            + path("M0,172 Q130,132 290,158 T620,150 T900,172 Z", "#CFE1DF")
            + "".join(cloud(x, y) for x, y in clouds)
            + rect(0, GROUND, 1280, 28, PAPER) + rect(0, GROUND, 1280, 3, SOFT))


def hero_pressure():
    return "".join([
        backdrop(), palm(642, 92), rumah(660), palm(820, 74),
        shophouse(846, SOFT, TEAL), shophouse(914, PAPER, TERRA, height=120), shophouse(982, SOFT, TEAL),
        tower(1064, 58, 136, TEAL, PAPER, GOLD), tower(1126, 70, 158, INK, GOLD), tower(1200, 62, 124, SOFT, TEAL, TERRA),
        person(800, "kurung", TEAL, SOFT, 1), child(816, GOLD, 1),
        person(884, "melayu", SOFT, INK, 0), basket(896, 150),
        person(958, "dress", TERRA, INK, 2), person(1036, "kurung", LEAF, INK, 0), cane(1048),
        person(1110, "shirt", GOLD, TEAL, 1, flip=True), person(1250, "shirt", TERRA, INK, 2),
    ])


def stall(x):
    y = GROUND
    posts = "".join(rect(x + d, y - 96, 4, 96, INK) for d in (4, 212))
    stripes = "".join(poly(f"{x - 8 + i * 28},{y - 96} {x + 20 + i * 28},{y - 96} {x + 20 + i * 28},{y - 72} {x - 8 + i * 28},{y - 72}",
                           TERRA if i % 2 == 0 else PAPER) for i in range(8))
    scallops = "".join(circle(x + 6 + i * 28, y - 72, 14, TERRA if i % 2 == 0 else PAPER) for i in range(8))
    table = rect(x - 4, y - 36, 224, 6, INK) + rect(x, y - 30, 216, 30, TEAL)
    crates = "".join(rect(x + d, y - 54, 44, 18, GOLD, 1) + rect(x + d, y - 46, 44, 2, "#CF9445") for d in (10, 62, 114, 166))
    veg = "".join(circle(x + d, y - 58, 6, LEAF) for d in (20, 32, 44))
    tomato = "".join(circle(x + d, y - 58, 5.5, TERRA) for d in (72, 84, 96))
    eggs = "".join(circle(x + d, y - 57, 4, PAPER) for d in (122, 131, 140, 149))
    fish = "".join(path(f"M{x + d},{y - 58} q10,-7 18,0 l6,-4 v8 l-6,-4 q-8,7 -18,0 Z", SOFT) for d in (172, 182))
    sacks = "".join(path(f"M{x + d},{y} C{x + d - 6},{y - 22} {x + d + 2},{y - 30} {x + d + 13},{y - 30} C{x + d + 24},{y - 30} {x + d + 32},{y - 22} {x + d + 26},{y} Z", PAPER)
                    + rect(x + d + 8, y - 33, 10, 4, TERRA, 1) for d in (-40,))
    return scallops + stripes + rect(x - 8, y - 100, 224, 5, INK) + posts + table + crates + veg + tomato + eggs + fish + sacks


def scale_beam():
    pivot_x, y = 1120, 42
    left, right = 1012, 1228
    left_y, right_y = 74, 50  # the side with the money sits higher than the side with the basket
    pan = lambda x, top: (poly(f"{x - 1},{top} {x + 1},{top} {x - 36},{top + 62} {x - 38},{top + 62}", INK)
                          + poly(f"{x - 1},{top} {x + 1},{top} {x + 38},{top + 62} {x + 36},{top + 62}", INK)
                          + path(f"M{x - 46},{top + 62} Q{x},{top + 80} {x + 46},{top + 62} Z", TEAL))
    goods = (path(f"M{left - 30},{left_y + 62} L{left - 24},{left_y + 28} L{left + 24},{left_y + 28} L{left + 30},{left_y + 62} Z", GOLD)
             + circle(left - 12, left_y + 26, 8, LEAF) + circle(left + 2, left_y + 22, 8, TERRA) + circle(left + 14, left_y + 26, 7, LEAF))
    notes = "".join(rect(right - 28, right_y + 54 - i * 7, 56, 6, LEAF, 1) + rect(right - 14, right_y + 55 - i * 7, 28, 4, PAPER) for i in range(4))
    beam = poly(f"{left},{left_y - 2} {right},{right_y - 2} {right},{right_y + 2} {left},{left_y + 2}", TEAL)
    stand = rect(pivot_x - 3, y + 16, 6, GROUND - y - 26, INK) + poly(f"{pivot_x - 34},{GROUND} {pivot_x},{GROUND - 18} {pivot_x + 34},{GROUND}", INK)
    return stand + pan(left, left_y) + pan(right, right_y) + goods + notes + beam + circle(pivot_x, 60, 9, GOLD)


def hero_drivers():
    return "".join([
        backdrop(((690, 22),)), palm(622, 84), stall(690),
        person(788, "melayu", SOFT, INK, 0, 1.0), person(936, "kurung", GOLD, TEAL, 1), basket(950, 150),
        child(916, TERRA, 1), scale_beam(),
    ])


def terrace(x):
    y = GROUND
    return "".join([
        rect(x, y - 92, 150, 92, PAPER), poly(f"{x - 10},{y - 92} {x + 75},{y - 132} {x + 160},{y - 92}", TERRA),
        rect(x + 10, y - 80, 30, 24, TEAL), rect(x + 110, y - 80, 30, 24, TEAL),
        rect(x + 24, y - 80, 2, 24, SOFT), rect(x + 124, y - 80, 2, 24, SOFT),
        rect(x - 4, y - 50, 158, 5, INK), rect(x + 64, y - 40, 22, 40, INK),
        rect(x + 12, y - 36, 34, 20, SOFT), rect(x + 104, y - 36, 34, 20, SOFT),
    ])


def flats(x):
    y = GROUND
    width, height = 330, 148
    balconies = "".join(rect(x + 14 + c * 62, y - height + 14 + r * 34, 48, 20, PAPER if (r + c) % 3 else GOLD, 1)
                        + rect(x + 14 + c * 62, y - height + 30 + r * 34, 48, 4, TEAL)
                        for r in range(4) for c in range(5))
    return rect(x, y - height, width, height, SOFT) + rect(x - 4, y - height - 6, width + 8, 6, TEAL) + balconies


def hero_budgets():
    people = [
        person(690, "shirt", TERRA, INK, 2),
        person(748, "melayu", TEAL, INK, 0), person(768, "kurung", GOLD, SOFT, 1),
        person(836, "shirt", SOFT, TEAL, 1), person(856, "dress", TERRA, INK, 2), child(876, GOLD, 2), child(890, LEAF, 2),
        person(956, "melayu", LEAF, INK, 0), cane(968), person(986, "kurung", SOFT, TEAL, 0), cane(998),
        person(1062, "kurung", TERRA, INK, 1), child(1080, GOLD, 1),
        person(1140, "shirt", GOLD, INK, 1, flip=True), child(1158, TERRA, 1), child(1172, LEAF, 1),
    ]
    return "".join([backdrop(((660, 20),)), terrace(630), flats(830), palm(1224, 100), *people])


def hero_growth():
    y = GROUND
    terraces = "".join(path(f"M{620 + i * 12},{y - i * 13} Q{700 + i * 8},{y - 10 - i * 13} {800 - i * 8},{y - i * 13} L{800 - i * 8},{y - i * 13 - 9} Q{700 + i * 8},{y - 18 - i * 13} {620 + i * 12},{y - i * 13 - 9} Z",
                            LEAF if i % 2 else GOLD) for i in range(6))
    palms = "".join(palm(820 + i * 34, 40 + (i % 2) * 8) for i in range(5))
    posts = "".join(rect(1002 + i * 24, y - 24, 3, 24, INK) for i in range(8))
    longhouse = (posts + rect(996, y - 26, 186, 4, INK) + rect(1002, y - 54, 174, 28, GOLD)
                 + "".join(rect(1012 + i * 30, y - 48, 12, 14, TEAL) for i in range(6))
                 + poly(f"{988},{y - 54} {1012},{y - 84} {1166},{y - 84} {1190},{y - 54}", TEAL))
    sea = rect(1190, y - 6, 90, 34, TEAL) + rect(1205, y + 8, 30, 2, SOFT) + rect(1240, y + 16, 26, 2, SOFT)
    boat = (path(f"M1208,{y - 12} L1262,{y - 12} Q1256,{y - 2} 1216,{y - 2} Z", TERRA) + rect(1232, y - 50, 2, 38, INK)
            + poly(f"1234,{y - 48} 1234,{y - 16} 1258,{y - 16}", PAPER))
    hills = (path("M600,172 Q700,70 830,126 Q960,54 1110,108 Q1200,76 1280,104 L1280,172 Z", SOFT)
             + path("M640,172 Q760,110 900,142 Q1030,96 1190,136 L1280,120 L1280,172 Z", "#8DB39A"))
    return "".join([backdrop(((720, 20), (1120, 18))), hills, terraces, palms, longhouse, sea, boat,
                    person(800, "shirt", TERRA, INK, 0, .8)])


def svg(body):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 200" width="1280" height="200">{body}</svg>'


def render(name):
    source = ART / f"{name}.svg"
    target = ART / f"{name}.png"
    page = f'<!doctype html><html><body style="margin:0">{source.read_text(encoding="utf-8")}</body></html>'
    with tempfile.TemporaryDirectory() as folder:
        html = Path(folder) / "page.html"
        html.write_text(page, encoding="utf-8")
        subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
                        "--window-size=1280,200", f"--screenshot={target}", f"--user-data-dir={folder}\\edge", html.as_uri()],
                       check=True, capture_output=True, timeout=60)


def main():
    scenes = {"hero_pressure": hero_pressure, "hero_drivers": hero_drivers,
              "hero_budgets": hero_budgets, "hero_growth": hero_growth}
    for name, scene in scenes.items():
        (ART / f"{name}.svg").write_text(svg(scene()), encoding="utf-8")
        render(name)
        print(f"[OK] {name}.png")


if __name__ == "__main__":
    main()
