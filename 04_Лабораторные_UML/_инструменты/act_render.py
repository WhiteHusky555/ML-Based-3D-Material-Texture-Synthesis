"""Рендер и проверка диаграмм деятельности StarUML 6 (.mdj); вызывается из mdj_render.py.

Правила отрисовки — по elements.js StarUML 6.3.3: действие — скруглённый прямоугольник
(радиус 10), у вызова деятельности справа значок-«грабли» (15 px); начальное состояние —
закрашенный круг, конечное — круг с точкой, решение — ромб; дорожка — рамка с заголовком;
подпись перехода «событие [условие]» — по alpha/distance от середины ребра (EP_MIDDLE).
"""
import math
from xml.sax.saxutils import escape

from activity import RAKE, label_center, label_text
from staruml_xpd import LINE_H, text_w, wrap

FONT = "Arial, Helvetica, sans-serif"


def _t(x, y, s, anchor="middle", weight="normal"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="13" text-anchor="{anchor}" '
            f'font-weight="{weight}" fill="#000">{escape(s)}</text>')


def _pts(v):
    return [tuple(float(c) for c in p.split(":")) for p in v["points"].split(";")]


def geometry(diagram, ids):
    items = []
    for v in diagram.get("ownedViews", []):
        t = v["_type"]
        m = ids.get(v["model"]["$ref"]) if v.get("model") else None
        it = {"view": v, "type": t, "model": m}
        if "left" in v:
            x, y, w, h = v["left"], v["top"], v["width"], v["height"]
            it["box"] = (x, y, x + w, y + h)
            if t == "UMLActionView":
                sub = ids.get(m.get("subactivity", {}).get("$ref", "")) if m.get("subactivity") else None
                it["label"] = f"{m['name']}:{sub['name']}" if sub else m["name"]
                it["call"] = sub is not None
            elif t == "UMLControlNodeView":
                it["kind"] = m["_type"]
                it["label"] = m["_type"][3:]
            elif t == "UMLSwimlaneView":
                it["label"] = m["name"]
            elif t == "UMLStateView":
                sub = ids.get(m.get("submachine", {}).get("$ref", "")) if m.get("submachine") else None
                it["label"] = f"{m['name']}: {sub['name']}" if sub else m["name"]
                it["sub"] = sub is not None
                it["items"] = ([f"entry/{b['name']}" for b in m.get("entryActivities", [])]
                               + [f"do/{b['name']}" for b in m.get("doActivities", [])]
                               + [f"exit/{b['name']}" for b in m.get("exitActivities", [])])
            elif t in ("UMLPseudostateView", "UMLFinalStateView"):
                it["kind"] = m.get("kind", "final") if t == "UMLPseudostateView" else "final"
                it["label"] = it["kind"]
            elif t == "UMLNoteView":
                it["label"] = v.get("text", "")[:28]
        elif "points" in v:
            pts = _pts(v)
            it["points"] = pts
            if t == "UMLTransitionView":
                text = label_text(", ".join(e["name"] for e in m.get("triggers", [])), m.get("guard", ""),
                                  ", ".join(e["name"] for e in m.get("effects", [])))
            else:
                text = label_text(m.get("name", ""), m.get("guard", ""))
            nl = ids.get(v.get("nameLabel", {}).get("$ref", ""))
            if text and nl and nl.get("visible", True):
                cx, cy = label_center(pts, nl["alpha"], nl["distance"])
                lw = text_w(text) + 6
                it["text"] = text
                it["lbox"] = (cx - lw / 2, cy - LINE_H / 2, cx + lw / 2, cy + LINE_H / 2)
        items.append(it)
    return items


def _arrow(p_from, p_to, size=10):
    a = math.atan2(p_to[1] - p_from[1], p_to[0] - p_from[0])
    pts = [(p_to[0] - size * math.cos(a - s * math.radians(30)), p_to[1] - size * math.sin(a - s * math.radians(30)))
           for s in (1, -1)]
    return (f'<path d="M{pts[0][0]:.1f},{pts[0][1]:.1f} L{p_to[0]:.1f},{p_to[1]:.1f} L{pts[1][0]:.1f},{pts[1][1]:.1f}" '
            f'fill="none" stroke="#000"/>')


def render(diagram, ids):
    items = geometry(diagram, ids)
    back, nodes, edges, front = [], [], [], []
    ext = [1e9, 1e9, -1e9, -1e9]

    def grow(b):
        ext[0], ext[1], ext[2], ext[3] = min(ext[0], b[0]), min(ext[1], b[1]), max(ext[2], b[2]), max(ext[3], b[3])

    for it in items:
        t = it["type"]
        if "box" in it:
            x0, y0, x1, y1 = it["box"]
            w, h = x1 - x0, y1 - y0
            grow(it["box"])
        if t == "UMLSwimlaneView":
            back.append(f'<rect x="{x0}" y="{y0}" width="{w}" height="24" fill="#fff" stroke="#000" stroke-width="2"/>')
            back.append(f'<path d="M{x0},{y1} V{y0} H{x1} V{y1}" fill="none" stroke="#000" stroke-width="2"/>')
            back.append(_t(x0 + w / 2, y0 + 17, it["label"], weight="bold"))
        elif t == "UMLActionView":
            nodes.append(f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" rx="10" ry="10" fill="#fff" stroke="#000"/>')
            tw = w - (RAKE if it["call"] else 0)
            lines = wrap(it["label"], tw - 26)          # тот же запас, что при раскладке (activity.py)
            ty = y0 + h / 2 - (len(lines) - 1) * LINE_H / 2 + 4
            for i, s in enumerate(lines):
                nodes.append(_t(x0 + tw / 2, ty + i * LINE_H, s))
            if it["call"]:                           # значок вызова деятельности («грабли»)
                rx, ry = x1 - 12, y1 - 12
                nodes.append(f'<path d="M{rx + 4},{ry} V{ry + 8} M{rx},{ry + 8} V{ry + 4} H{rx + 8} V{ry + 8}" '
                             f'fill="none" stroke="#000"/>')
        elif t == "UMLControlNodeView":
            k = it["kind"]
            cx, cy = x0 + w / 2, y0 + h / 2
            if k == "UMLInitialNode":
                nodes.append(f'<circle cx="{cx}" cy="{cy}" r="{w / 2}" fill="#000"/>')
            elif k == "UMLActivityFinalNode":
                nodes.append(f'<circle cx="{cx}" cy="{cy}" r="{w / 2}" fill="#fff" stroke="#000"/>')
                nodes.append(f'<circle cx="{cx}" cy="{cy}" r="{w / 2 - 5}" fill="#000"/>')
            else:
                nodes.append(f'<polygon points="{x0},{cy} {cx},{y0} {x1},{cy} {cx},{y1}" fill="#fff" stroke="#000"/>')
        elif t == "UMLStateView":
            nodes.append(f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" rx="10" ry="10" fill="#fff" stroke="#000"/>')
            nodes.append(_t(x0 + w / 2, y0 + 18, it["label"]))
            if it["items"]:
                ly = y0 + LINE_H + 10
                nodes.append(f'<line x1="{x0}" y1="{ly}" x2="{x1}" y2="{ly}" stroke="#000"/>')
                for i, s_ in enumerate(it["items"]):
                    nodes.append(_t(x0 + 8, ly + 17 + i * LINE_H, s_, anchor="start"))
            if it["sub"]:                            # значок ссылочного состояния (как в StarUML 6)
                nodes.append(f'<ellipse cx="{x1 - 23}" cy="{y1 - 13}" rx="3" ry="3" fill="none" stroke="#000"/>'
                             f'<line x1="{x1 - 20}" y1="{y1 - 13}" x2="{x1 - 14}" y2="{y1 - 13}" stroke="#000"/>'
                             f'<ellipse cx="{x1 - 11}" cy="{y1 - 13}" rx="3" ry="3" fill="none" stroke="#000"/>')
        elif t in ("UMLPseudostateView", "UMLFinalStateView"):
            k = it["kind"]
            cx, cy = x0 + w / 2, y0 + h / 2
            if k in ("initial", "junction"):
                nodes.append(f'<circle cx="{cx}" cy="{cy}" r="{w / 2}" fill="#000"/>')
            elif k == "final":
                nodes.append(f'<circle cx="{cx}" cy="{cy}" r="{w / 2}" fill="#fff" stroke="#000"/>')
                nodes.append(f'<circle cx="{cx}" cy="{cy}" r="{w / 2 - 5}" fill="#000"/>')
            else:
                nodes.append(f'<polygon points="{x0},{cy} {cx},{y0} {x1},{cy} {cx},{y1}" fill="#fff" stroke="#000"/>')
        elif t == "UMLNoteView":
            f = 10
            front.append(f'<path d="M{x0},{y0} H{x1 - f} L{x1},{y0 + f} V{y1} H{x0} Z" fill="#fff" stroke="#000"/>')
            for i, s in enumerate(wrap(it["view"].get("text", ""), w - 12)):
                front.append(_t(x0 + 6, y0 + 17 + i * LINE_H, s, anchor="start"))
        elif "points" in it:
            pts = it["points"]
            for p in pts:
                grow((p[0], p[1], p[0], p[1]))
            d = " L".join(f"{p[0]:.1f},{p[1]:.1f}" for p in pts)
            edges.append(f'<path d="M{d}" fill="none" stroke="#000"/>')
            edges.append(_arrow(pts[-2], pts[-1]))
            if "lbox" in it:
                lb = it["lbox"]
                front.append(f'<rect x="{lb[0]:.1f}" y="{lb[1]:.1f}" width="{lb[2] - lb[0]:.1f}" height="{LINE_H}" '
                             f'fill="#fff" fill-opacity="0.85"/>')
                front.append(_t((lb[0] + lb[2]) / 2, lb[3] - 4, it["text"]))
                grow(lb)
    mg = 20
    x0, y0, W, H = ext[0] - mg, ext[1] - mg, ext[2] - ext[0] + 2 * mg, ext[3] - ext[1] + 2 * mg
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" viewBox="{x0:.0f} {y0:.0f} {W:.0f} {H:.0f}">\n'
            f'<rect x="{x0:.0f}" y="{y0:.0f}" width="{W:.0f}" height="{H:.0f}" fill="#fff"/>\n'
            + "\n".join(back + nodes + edges + front) + "\n</svg>\n")


# ---------------------------------------------------------------- проверка

def _overlap(a, b, pad=2):
    return not (a[2] <= b[0] + pad or b[2] <= a[0] + pad or a[3] <= b[1] + pad or b[3] <= a[1] + pad)


def _seg_box(p, q, b, shrink=3):
    x0, y0, x1, y1 = b[0] + shrink, b[1] + shrink, b[2] - shrink, b[3] - shrink
    if x0 >= x1 or y0 >= y1:
        return False
    t0, t1 = 0.0, 1.0
    dx, dy = q[0] - p[0], q[1] - p[1]
    for pp, qq in ((-dx, p[0] - x0), (dx, x1 - p[0]), (-dy, p[1] - y0), (dy, y1 - p[1])):
        if pp == 0:
            if qq < 0:
                return False
        else:
            r = qq / pp
            if pp < 0:
                t0 = max(t0, r)
            else:
                t1 = min(t1, r)
            if t0 > t1:
                return False
    return True


def _cross(p1, p2, q1, q2):
    """Пересечение двух ортогональных отрезков во внутренних точках (касание концами не считается)."""
    if p1[1] == p2[1] and q1[0] == q2[0]:
        h, v = (p1, p2), (q1, q2)
    elif p1[0] == p2[0] and q1[1] == q2[1]:
        h, v = (q1, q2), (p1, p2)
    else:
        return False
    hx0, hx1 = sorted((h[0][0], h[1][0]))
    vy0, vy1 = sorted((v[0][1], v[1][1]))
    x, y = v[0][0], h[0][1]
    return hx0 + 1 < x < hx1 - 1 and vy0 + 1 < y < vy1 - 1


def check(diagram, ids):
    items = geometry(diagram, ids)
    lanes = [it for it in items if it["type"] == "UMLSwimlaneView"]
    solids = [(f'{it["type"][3:-4]}:{it.get("label", "")[:30]}', it["box"], it["view"]["_id"])
              for it in items if "box" in it and it["type"] != "UMLSwimlaneView"]
    labels = [(f'подпись [{it["text"][:30]}]', it["lbox"], it["view"]["_id"]) for it in items if "lbox" in it]
    problems = []
    allb = solids + labels
    for i, (na, ba, _) in enumerate(allb):
        for nb, bb, _ in allb[i + 1:]:
            if _overlap(ba, bb):
                problems.append(f"наложение: {na} ✕ {nb}")
    for it in items:                                 # состояние: название и деятельности помещаются
        if it["type"] == "UMLStateView":
            x0, y0, x1, y1 = it["box"]
            need_h = LINE_H + 10 + ((LINE_H * len(it["items"]) + 10) if it["items"] else 0) + (16 if it["sub"] else 0)
            if any(text_w(t) * 1.06 + 16 > x1 - x0 for t in [it["label"]] + it["items"]) or need_h > y1 - y0:
                problems.append(f'текст не помещается в состояние: {it["label"][:40]}')
    for it in items:                                 # название помещается в узел (реальный шрифт ~6 % шире оценки)
        if it["type"] == "UMLActionView":
            x0, y0, x1, y1 = it["box"]
            avail = x1 - x0 - 10 - (RAKE if it["call"] else 0)
            lines = wrap(it["label"], avail - 16)
            if any(text_w(t) * 1.06 > avail for t in lines) or LINE_H * len(lines) + 8 > y1 - y0:
                problems.append(f'текст не помещается в узел: {it["label"][:40]}')
    borders = sorted({l["box"][0] for l in lanes} | {l["box"][2] for l in lanes})
    for na, ba, _ in labels:                         # подпись не лежит на границе дорожек
        if any(ba[0] + 1 < x < ba[2] - 1 for x in borders):
            problems.append(f"{na} пересекает границу дорожки")
    for na, ba, _ in solids:                         # узел целиком в своей дорожке
        if lanes and not any(l["box"][0] <= ba[0] and ba[2] <= l["box"][2] for l in lanes):
            problems.append(f"узел выходит за дорожку: {na}")
    by_view = {it["view"]["_id"]: it for it in items}
    flows = [it for it in items if "points" in it]
    for it in flows:
        v = it["view"]
        ends = {v["head"]["$ref"], v["tail"]["$ref"]}
        pts = it["points"]
        name = f'[{by_view[v["tail"]["$ref"]].get("label", "?")[:20]} → {by_view[v["head"]["$ref"]].get("label", "?")[:20]}]'
        for na, ba, vid in solids:
            if vid not in ends and any(_seg_box(pts[k], pts[k + 1], ba) for k in range(len(pts) - 1)):
                problems.append(f"линия {name} проходит через {na}")
        for na, ba, vid in labels:
            shrink = 1 if vid == v["_id"] else 0
            if any(_seg_box(pts[k], pts[k + 1], ba, shrink) for k in range(len(pts) - 1)):
                problems.append(f"линия {name} задевает {na}")
    for it in flows:                                # переходы — только горизонтальные и вертикальные отрезки
        pts = it["points"]
        if any(p[0] != q[0] and p[1] != q[1] for p, q in zip(pts, pts[1:])):
            problems.append(f'косой отрезок перехода: {pts}')
    for i, a in enumerate(flows):
        for b in flows[i + 1:]:
            pa, pb = a["points"], b["points"]
            if any(_cross(pa[k], pa[k + 1], pb[j], pb[j + 1]) for k in range(len(pa) - 1) for j in range(len(pb) - 1)):
                ta = by_view[a["view"]["tail"]["$ref"]].get("label", "?")[:18]
                tb = by_view[b["view"]["tail"]["$ref"]].get("label", "?")[:18]
                problems.append(f"пересечение линий: от «{ta}» и от «{tb}»")
    return problems
