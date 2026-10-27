"""Рендер и проверка диаграмм классов StarUML 6 (.mdj); вызывается из mdj_render.py.

Правила отрисовки — по elements.js StarUML 6.3.3: класс — прямоугольник с отсеками имени («стереотип»,
имя полужирным, у абстрактного — курсивом), атрибутов и операций (строки «+имя: тип», «+Имя(п: т): р»);
пакет — папка с вкладкой; ассоциация — сплошная линия (ромб у «целого»: пустой — агрегация,
закрашенный — композиция; стрелка — навигация), зависимость — штриховая со стрелкой и «стереотипом»,
обобщение — сплошная с пустым треугольником, реализация — штриховая с пустым треугольником.
Подписи — по alpha/distance относительно хвоста, головы или середины ребра (EdgeParasiticView).
"""
import math
from xml.sax.saxutils import escape

from act_render import _cross, _overlap, _seg_box
from activity import _away_line, middle_ref
from classdiagram import BOLD_K, FONT_K, GAP, PAD
from staruml_xpd import LINE_H, text_w

FONT = "Arial, Helvetica, sans-serif"
VIS = {"public": "+", "private": "-", "protected": "#", "package": "~"}


def _t(x, y, s, anchor="middle", weight="normal", style="normal"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="13" text-anchor="{anchor}" '
            f'font-weight="{weight}" font-style="{style}" fill="#000">{escape(s)}</text>')


def _pts(v):
    return [tuple(float(c) for c in p.split(":")) for p in v["points"].split(";")]


def _ref(ids, o, key):
    r = o.get(key)
    return ids.get(r["$ref"]) if isinstance(r, dict) and "$ref" in r else None


def attr_text(a):
    t = VIS.get(a.get("visibility", "public"), "+") + a["name"]
    if a.get("type"):
        t += f": {a['type']}"
    if a.get("defaultValue"):
        t += f" = {a['defaultValue']}"
    return t


def op_text(o):
    ps = [p for p in o.get("parameters", []) if p.get("direction") != "return"]
    ret = [p for p in o.get("parameters", []) if p.get("direction") == "return"]
    s = ", ".join(f"{p['name']}: {p['type']}" if p.get("type") else p["name"] for p in ps)
    t = VIS.get(o.get("visibility", "public"), "+") + f"{o['name']}({s})"
    if ret and ret[0].get("type"):
        t += f": {ret[0]['type']}"
    return t


def label_point(points, pos, alpha, distance):
    if pos == 0:
        p1, p2 = points[-1], points[-2]
    elif pos == 2:
        p1, p2 = points[0], points[1]
    else:
        p1, p2 = middle_ref(points)
    _, (dx, dy) = _away_line(p1, p2, alpha, distance)
    return p1[0] + dx, p1[1] + dy


def geometry(diagram, ids):
    items = []
    for v in diagram.get("ownedViews", []):
        t = v["_type"]
        m = _ref(ids, v, "model")
        it = {"view": v, "type": t, "model": m}
        if "left" in v:
            x, y, w, h = v["left"], v["top"], v["width"], v["height"]
            it["box"] = (x, y, x + w, y + h)
            it["label"] = m.get("name", "") if m else ""
            if t in ("UMLClassView", "UMLInterfaceView"):
                it["stereo"] = "interface" if m["_type"] == "UMLInterface" else m.get("stereotype", "")
                it["abstract"] = m.get("isAbstract", False)
                full = not v.get("suppressAttributes")
                it["attrs"] = [attr_text(a) for a in m.get("attributes", [])] if full else None
                it["ops"] = [op_text(o) for o in m.get("operations", [])] if full and not v.get("suppressOperations") else None
        elif "points" in v:
            pts = _pts(v)
            it["points"] = pts
            labels = []
            for sv in v.get("subViews", []):
                if not sv.get("visible", True):
                    continue
                lm = _ref(ids, sv, "model")
                name = next((k for k, r in v.items() if isinstance(r, dict) and r.get("$ref") == sv["_id"]), "")
                if name in ("nameLabel",):
                    txt = m.get("name", "")
                elif name == "stereotypeLabel":
                    txt = f"«{m['stereotype']}»" if m.get("stereotype") else ""
                elif name.endswith("MultiplicityLabel"):
                    txt = (lm or {}).get("multiplicity", "")
                elif name.endswith("RoleNameLabel"):
                    txt = (lm or {}).get("name", "")
                else:
                    txt = ""
                if not txt:
                    continue
                cx, cy = label_point(pts, sv.get("edgePosition", 1), sv.get("alpha", 0), sv.get("distance", 0))
                lw = text_w(txt) + 6
                labels.append((txt, (cx - lw / 2, cy - LINE_H / 2, cx + lw / 2, cy + LINE_H / 2)))
            it["labels"] = labels
        items.append(it)
    return items


def _class_need(it):
    texts = [(f"«{it['stereo']}»", 1.0)] if it["stereo"] else []
    texts.append((it["label"], BOLD_K))
    h = PAD + (LINE_H + GAP if it["stereo"] else GAP) + LINE_H + PAD
    if it["attrs"] is not None:
        comps = [c for c in (it["attrs"], it["ops"]) if c is not None]
        texts += [(s, 1.0) for c in comps for s in c]
        for n in map(len, comps):
            h += PAD + n * LINE_H + max(n - 1, 0) * GAP + PAD if n else 2 * PAD
    w = max(text_w(t) * k * FONT_K for t, k in texts) + 2 * PAD
    return w, h


def _head(kind, p_from, p_to):
    """Окончание ребра у точки p_to: open — стрелка, tri — пустой треугольник, dia / fdia — ромб."""
    a = math.atan2(p_to[1] - p_from[1], p_to[0] - p_from[0])
    ca, sa = math.cos(a), math.sin(a)
    if kind == "open":
        pts = [(p_to[0] - 12 * math.cos(a - s * math.radians(28)), p_to[1] - 12 * math.sin(a - s * math.radians(28)))
               for s in (1, -1)]
        return (f'<path d="M{pts[0][0]:.1f},{pts[0][1]:.1f} L{p_to[0]:.1f},{p_to[1]:.1f} '
                f'L{pts[1][0]:.1f},{pts[1][1]:.1f}" fill="none" stroke="#000"/>')
    if kind == "tri":
        b = (p_to[0] - 14 * ca, p_to[1] - 14 * sa)
        q1 = (b[0] - 8 * sa, b[1] + 8 * ca)
        q2 = (b[0] + 8 * sa, b[1] - 8 * ca)
        return (f'<polygon points="{p_to[0]:.1f},{p_to[1]:.1f} {q1[0]:.1f},{q1[1]:.1f} {q2[0]:.1f},{q2[1]:.1f}" '
                f'fill="#fff" stroke="#000"/>')
    m = (p_to[0] - 10 * ca, p_to[1] - 10 * sa)
    e = (p_to[0] - 20 * ca, p_to[1] - 20 * sa)
    q1 = (m[0] - 6 * sa, m[1] + 6 * ca)
    q2 = (m[0] + 6 * sa, m[1] - 6 * ca)
    fill = "#000" if kind == "fdia" else "#fff"
    return (f'<polygon points="{p_to[0]:.1f},{p_to[1]:.1f} {q1[0]:.1f},{q1[1]:.1f} {e[0]:.1f},{e[1]:.1f} '
            f'{q2[0]:.1f},{q2[1]:.1f}" fill="{fill}" stroke="#000"/>')


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
            w = x1 - x0
            grow(it["box"])
        if t == "UMLPackageView":
            tw = min(max(text_w(it["label"]) * BOLD_K + 24, 90), w - 20)
            back.append(f'<rect x="{x0}" y="{y0}" width="{tw:.0f}" height="22" fill="#fff" stroke="#000"/>')
            back.append(f'<rect x="{x0}" y="{y0 + 22}" width="{w}" height="{y1 - y0 - 22}" fill="#fff" stroke="#000"/>')
            back.append(_t(x0 + 10, y0 + 16, it["label"], anchor="start", weight="bold"))
        elif t in ("UMLClassView", "UMLInterfaceView"):
            nodes.append(f'<rect x="{x0}" y="{y0}" width="{w}" height="{y1 - y0}" fill="#fff" stroke="#000"/>')
            y = y0 + PAD
            cx = x0 + w / 2
            if it["stereo"]:
                nodes.append(_t(cx, y + 12, f"«{it['stereo']}»"))
                y += LINE_H + GAP
            else:
                y += GAP
            nodes.append(_t(cx, y + 12, it["label"], weight="bold", style="italic" if it["abstract"] else "normal"))
            y += LINE_H + PAD
            if it["attrs"] is not None:
                for lines in (c for c in (it["attrs"], it["ops"]) if c is not None):
                    nodes.append(f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" stroke="#000"/>')
                    yy = y + PAD
                    for s in lines:
                        nodes.append(_t(x0 + PAD + 2, yy + 12, s, anchor="start"))
                        yy += LINE_H + GAP
                    y += PAD + len(lines) * LINE_H + max(len(lines) - 1, 0) * GAP + PAD if lines else 2 * PAD
        elif "points" in it:
            pts = it["points"]
            for p in pts:
                grow((p[0], p[1], p[0], p[1]))
            d = " L".join(f"{p[0]:.1f},{p[1]:.1f}" for p in pts)
            dashed = t in ("UMLDependencyView", "UMLInterfaceRealizationView")
            edges.append(f'<path d="M{d}" fill="none" stroke="#000"' + (' stroke-dasharray="6 4"' if dashed else "")
                         + "/>")
            m = it["model"]
            if t == "UMLAssociationView":
                e1, e2 = m["end1"], m["end2"]
                if e2.get("navigable") == "navigable":
                    edges.append(_head("open", pts[-2], pts[-1]))
                agg = e1.get("aggregation", "none")
                if agg in ("shared", "composite"):
                    edges.append(_head("fdia" if agg == "composite" else "dia", pts[1], pts[0]))
            elif t == "UMLDependencyView":
                edges.append(_head("open", pts[-2], pts[-1]))
            else:
                edges.append(_head("tri", pts[-2], pts[-1]))
            for txt, lb in it["labels"]:
                front.append(f'<rect x="{lb[0]:.1f}" y="{lb[1]:.1f}" width="{lb[2] - lb[0]:.1f}" height="{LINE_H}" '
                             f'fill="#fff" fill-opacity="0.85"/>')
                front.append(_t((lb[0] + lb[2]) / 2, lb[3] - 4, txt))
                grow(lb)
    mg = 20
    x0, y0, W, H = ext[0] - mg, ext[1] - mg, ext[2] - ext[0] + 2 * mg, ext[3] - ext[1] + 2 * mg
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" viewBox="{x0:.0f} {y0:.0f} {W:.0f} {H:.0f}">\n'
            f'<rect x="{x0:.0f}" y="{y0:.0f}" width="{W:.0f}" height="{H:.0f}" fill="#fff"/>\n'
            + "\n".join(back + nodes + edges + front) + "\n</svg>\n")


def _inside(a, b):
    return b[0] <= a[0] and b[1] <= a[1] and a[2] <= b[2] and a[3] <= b[3]


def check(diagram, ids):
    items = geometry(diagram, ids)
    pkgs = [it for it in items if it["type"] == "UMLPackageView"]
    classes = [it for it in items if it["type"] in ("UMLClassView", "UMLInterfaceView")]
    flows = [it for it in items if "points" in it]
    problems = []
    for it in classes:                                  # размер вмещает текст
        need_w, need_h = _class_need(it)
        x0, y0, x1, y1 = it["box"]
        if need_w > x1 - x0 or need_h > y1 - y0 + 0.5:
            problems.append(f"текст не помещается в класс {it['label']}: нужно {need_w:.0f}×{need_h:.0f}, "
                            f"есть {x1 - x0}×{y1 - y0}")
    solids = [(f"класс {it['label']}", it["box"], it["view"]["_id"]) for it in classes]
    labels = [(f"подпись [{txt}]", lb, it["view"]["_id"]) for it in flows for txt, lb in it["labels"]]
    allb = solids + labels
    for i, (na, ba, _) in enumerate(allb):
        for nb, bb, _ in allb[i + 1:]:
            if _overlap(ba, bb):
                problems.append(f"наложение: {na} ✕ {nb}")
    for p in pkgs:                                      # класс либо внутри пакета, либо вне его
        for na, ba, _ in solids:
            if _overlap(ba, p["box"]) and not _inside(ba, (p["box"][0], p["box"][1] + 22, p["box"][2], p["box"][3])):
                problems.append(f"{na} пересекает границу пакета {p['label']}")
    by_view = {it["view"]["_id"]: it for it in items}
    for it in flows:
        v = it["view"]
        ends = {v["head"]["$ref"], v["tail"]["$ref"]}
        pts = it["points"]
        name = f'[{by_view[v["tail"]["$ref"]]["label"][:22]} → {by_view[v["head"]["$ref"]]["label"][:22]}]'
        for na, ba, vid in solids:
            if vid not in ends and any(_seg_box(pts[k], pts[k + 1], ba) for k in range(len(pts) - 1)):
                problems.append(f"линия {name} проходит через {na}")
        for na, ba, vid in labels:
            shrink = 1 if vid == v["_id"] else 0
            if any(_seg_box(pts[k], pts[k + 1], ba, shrink) for k in range(len(pts) - 1)):
                problems.append(f"линия {name} задевает {na}")
        if any(p[0] != q[0] and p[1] != q[1] for p, q in zip(pts, pts[1:])):
            problems.append(f"косой отрезок {name}: {pts}")
        for k, (end, idx) in enumerate(((v["tail"]["$ref"], 0), (v["head"]["$ref"], -1))):
            b = by_view[end]["box"]
            p = pts[idx]
            on = (abs(p[0] - b[0]) < 1.5 or abs(p[0] - b[2]) < 1.5) and b[1] - 1 <= p[1] <= b[3] + 1 or \
                 (abs(p[1] - b[1]) < 1.5 or abs(p[1] - b[3]) < 1.5) and b[0] - 1 <= p[0] <= b[2] + 1
            if not on:
                problems.append(f"конец линии {name} не на границе класса: {p}")
    for i, a in enumerate(flows):
        for b in flows[i + 1:]:
            pa, pb = a["points"], b["points"]
            # обобщения/реализации к одному родителю рисуются деревом с общим участком (UML shared target style)
            if a["type"] == b["type"] in ("UMLGeneralizationView", "UMLInterfaceRealizationView") and \
                    a["view"]["head"]["$ref"] == b["view"]["head"]["$ref"] and pa[-1] == pb[-1]:
                continue
            if any(_cross(pa[k], pa[k + 1], pb[j], pb[j + 1]) for k in range(len(pa) - 1) for j in range(len(pb) - 1)):
                ta = by_view[a["view"]["tail"]["$ref"]]["label"][:18]
                tb = by_view[b["view"]["tail"]["$ref"]]["label"][:18]
                problems.append(f"пересечение линий: от «{ta}» и от «{tb}»")
            # совпадающие участки (линии идут друг по другу)
            for k in range(len(pa) - 1):
                for j in range(len(pb) - 1):
                    (p1, p2), (q1, q2) = (pa[k], pa[k + 1]), (pb[j], pb[j + 1])
                    if p1[0] == p2[0] == q1[0] == q2[0]:
                        lo = max(min(p1[1], p2[1]), min(q1[1], q2[1]))
                        hi = min(max(p1[1], p2[1]), max(q1[1], q2[1]))
                        if hi - lo > 2:
                            problems.append(f"линии идут друг по другу (вертикаль x={p1[0]})")
                    elif p1[1] == p2[1] == q1[1] == q2[1]:
                        lo = max(min(p1[0], p2[0]), min(q1[0], q2[0]))
                        hi = min(max(p1[0], p2[0]), max(q1[0], q2[0]))
                        if hi - lo > 2:
                            problems.append(f"линии идут друг по другу (горизонталь y={p1[1]})")
    return problems
