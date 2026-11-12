"""Рендер и проверка диаграмм коммуникации StarUML 6 (.mdj); вызывается из mdj_render.py.

Правила отрисовки — по elements.js StarUML 6.3.3: объект — прямоугольник со «стереотипом» и именем «имя: Тип»
(у актора — значок и имя под ним); связь — сплошная ломаная; сообщение (UMLCommMessageView) — стрелка длиной
40 px вдоль среднего участка связи, центр — в alpha / distance от его середины; синхронный вызов — закрашенный
наконечник, асинхронный и «create» — открытый, ответ — штриховая с открытым; подпись «N : Операция(параметры)»
(NodeLabelView) — в alpha / distance от центра стрелки, у «create» — ещё «create».
"""
import math

from act_render import _cross, _overlap, _seg_box
from class_render import label_point
from seq_render import _actor, _head, _pts, _ref, _t, _tw
from staruml_xpd import LINE_H


def geometry(diagram, ids):
    inter = ids[diagram["_parent"]["$ref"]]
    order = [m["_id"] for m in inter.get("messages", [])]
    nodes, links, msgs = {}, {}, []
    for v in diagram.get("ownedViews", []):
        t = v["_type"]
        if t == "UMLCommLifelineView":
            lf = _ref(ids, v, "model")
            role = _ref(ids, lf, "represent")
            typ = _ref(ids, role, "type") if role else None
            nodes[v["_id"]] = {
                "box": (v["left"], v["top"], v["left"] + v["width"], v["top"] + v["height"]),
                "stereo": lf.get("stereotype", ""), "name": f"{lf.get('name', '')}: {typ['name'] if typ else ''}",
                "actor": v.get("stereotypeDisplay") == "icon" and typ and typ["_type"] == "UMLActor",
                "lifeline": lf["_id"]}
        elif t == "UMLConnectorView":
            links[v["_id"]] = {"points": _pts(v), "tail": v["tail"]["$ref"], "head": v["head"]["$ref"]}
    for v in diagram.get("ownedViews", []):
        if v["_type"] != "UMLCommMessageView":
            continue
        m = _ref(ids, v, "model")
        ln = links[v["hostEdge"]["$ref"]]
        pts = ln["points"]
        cx, cy = label_point(pts, 1, v.get("alpha", 0), v.get("distance", 0))
        mid = len(pts) // 2 - (1 if len(pts) % 2 == 0 else 0)
        (x1, y1), (x2, y2) = pts[mid], pts[mid + 1]
        d = math.hypot(x2 - x1, y2 - y1)
        ux, uy = (x2 - x1) / d, (y2 - y1) / d
        if m["source"]["$ref"] != nodes[ln["tail"]]["lifeline"]:        # обратное сообщение
            ux, uy = -ux, -uy
        tail, head = (cx - 20 * ux, cy - 20 * uy), (cx + 20 * ux, cy + 20 * uy)
        no = order.index(m["_id"]) + 1
        sort = m.get("messageSort", "synchCall")
        if sort in ("synchCall", "asynchCall"):
            op = _ref(ids, m, "signature")
            args = m["arguments"] if "arguments" in m else ", ".join(
                p["name"] for p in op.get("parameters", []) if p.get("direction") != "return")
            text = f"{no} : {op['name']}({args})"
        else:
            text = f"{no} : {m.get('name', '')}"
        labels = []
        for nm in ("nameLabel", "stereotypeLabel"):
            lb = _ref(ids, v, nm)
            if not lb or not lb.get("visible", True):
                continue
            txt = text if nm == "nameLabel" else "«create»"
            lx = cx + lb.get("distance", 0) * math.cos(lb.get("alpha", 0))
            ly = cy - lb.get("distance", 0) * math.sin(lb.get("alpha", 0))
            lw = _tw(txt) + 6
            labels.append((txt, (lx - lw / 2, ly - LINE_H / 2, lx + lw / 2, ly + LINE_H / 2)))
        box = (min(tail[0], head[0]) - 5 * abs(uy), min(tail[1], head[1]) - 5 * abs(ux),
               max(tail[0], head[0]) + 5 * abs(uy), max(tail[1], head[1]) + 5 * abs(ux))
        msgs.append({"no": no, "sort": sort, "tail": tail, "head": head, "labels": labels, "box": box,
                     "link": v["hostEdge"]["$ref"]})
    return nodes, links, msgs


def render(diagram, ids):
    nodes, links, msgs = geometry(diagram, ids)
    W = max([n["box"][2] for n in nodes.values()] + [lb[1][2] for m in msgs for lb in m["labels"]] +
            [p[0] for ln in links.values() for p in ln["points"]]) + 30
    H = max([n["box"][3] for n in nodes.values()] + [p[1] for ln in links.values() for p in ln["points"]]) + 30
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" viewBox="0 0 {W:.0f} {H:.0f}">',
           f'<rect width="{W:.0f}" height="{H:.0f}" fill="#fff"/>']
    for ln in links.values():
        d = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(ln["points"]))
        out.append(f'<path d="{d}" fill="none" stroke="#000"/>')
    for n in nodes.values():
        x1, y1, x2, y2 = n["box"]
        cx = (x1 + x2) / 2
        if n["actor"]:
            out.append(f'<rect x="{x1:.1f}" y="{y1:.1f}" width="{x2 - x1:.1f}" height="{y2 - y1:.1f}" fill="#fff"/>')
            out.append(_actor(cx, y1))
            out.append(_t(cx, y1 + 40 + 17, n["name"]))
        else:
            out.append(f'<rect x="{x1:.1f}" y="{y1:.1f}" width="{x2 - x1:.1f}" height="{y2 - y1:.1f}" fill="#fff" '
                       f'stroke="#000"/>')
            if n["stereo"]:
                out.append(_t(cx, y1 + 16, f"«{n['stereo']}»"))
                out.append(_t(cx, y1 + 33, n["name"]))
            else:
                out.append(_t(cx, y1 + 25, n["name"]))
    for m in msgs:
        (tx, ty), (hx, hy) = m["tail"], m["head"]
        dash = ' stroke-dasharray="3,3"' if m["sort"] == "reply" else ""
        out.append(f'<line x1="{tx:.1f}" y1="{ty:.1f}" x2="{hx:.1f}" y2="{hy:.1f}" stroke="#000"{dash}/>')
        out.append(_head(m["sort"], m["tail"], m["head"]))
        for txt, (bx1, by1, bx2, by2) in m["labels"]:
            out.append(_t((bx1 + bx2) / 2, (by1 + by2) / 2 + 5, txt))
    out.append("</svg>")
    return "\n".join(out)


def check(diagram, ids):
    nodes, links, msgs = geometry(diagram, ids)
    pr = []
    boxes = [(t, b) for m in msgs for t, b in m["labels"]] + [(f"стрелка {m['no']}", m["box"]) for m in msgs]
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if _overlap(boxes[i][1], boxes[j][1], 1):
                pr.append(f"наложение: [{boxes[i][0][:30]}] ✕ [{boxes[j][0][:30]}]")
    segs = [(p, q) for ln in links.values() for p, q in zip(ln["points"], ln["points"][1:])]
    for t, b in boxes:
        if min(b[0], b[1]) < 0:
            pr.append(f"[{t[:30]}] выходит за край диаграммы")
        for n in nodes.values():
            if _overlap(b, n["box"], 1):
                pr.append(f"[{t[:30]}] на объекте {n['name']}")
        if any(_seg_box(p, q, b, 1) for p, q in segs):
            pr.append(f"связь проходит через [{t[:30]}]")
    ns = list(nodes.values())
    for i, a in enumerate(ns):
        for b in ns[i + 1:]:
            if _overlap(a["box"], b["box"], 0):
                pr.append(f"объекты {a['name']} и {b['name']} наложены")
    for ln in links.values():
        for vid, n in nodes.items():
            for k, (p, q) in enumerate(zip(ln["points"], ln["points"][1:])):
                own = vid in (ln["tail"], ln["head"]) and k in (0, len(ln["points"]) - 2)
                if not own and _seg_box(p, q, n["box"], 2):
                    pr.append(f"связь проходит через объект {n['name']}")
    ls = list(links.values())
    for i, a in enumerate(ls):
        for b in ls[i + 1:]:
            if any(_cross(p1, p2, q1, q2) for p1, p2 in zip(a["points"], a["points"][1:])
                   for q1, q2 in zip(b["points"], b["points"][1:])):
                pr.append("связи пересекаются")
    return sorted(set(pr))
