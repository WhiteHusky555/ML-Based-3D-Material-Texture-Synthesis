"""Рендер и проверка диаграмм последовательности StarUML 6 (.mdj); вызывается из mdj_render.py.

Правила отрисовки — по elements.js StarUML 6.3.3: шапка линии жизни — прямоугольник высотой 40 со
«стереотипом» и именем «имя: Тип» (у актора — значок и имя под ним), линия — штриховая; активация — белый
прямоугольник шириной 14; синхронный вызов — сплошная линия с закрашенной стрелкой, асинхронный — сплошная с
открытой, ответ и «create» — штриховые с открытой; подпись «N : Операция(параметры)» (showType = false — без
типов), у «create» — ещё «create» над подписью; комбинированный фрагмент — рамка с пятиугольником оператора,
условия операндов «[…]» в 20 px от левого и 15 px от верхнего края операнда, разделители — штриховые.
"""
import math
from xml.sax.saxutils import escape

from act_render import _cross, _overlap, _seg_box
from class_render import label_point
from staruml_xpd import LINE_H, text_w

FONT = "Arial, Helvetica, sans-serif"
FONT_K = 1.07


def _t(x, y, s, anchor="middle", weight="normal"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="13" text-anchor="{anchor}" '
            f'font-weight="{weight}" fill="#000">{escape(s)}</text>')


def _ref(ids, o, key):
    r = o.get(key)
    return ids.get(r["$ref"]) if isinstance(r, dict) and "$ref" in r else None


def _pts(v):
    return [tuple(float(c) for c in p.split(":")) for p in v["points"].split(";")]


def _tw(s):
    return text_w(s) * FONT_K


def geometry(diagram, ids):
    inter = ids[diagram["_parent"]["$ref"]]
    order = [m["_id"] for m in inter.get("messages", [])]
    lls, msgs, frags = {}, [], []
    for v in diagram.get("ownedViews", []):
        t = v["_type"]
        if t == "UMLSeqLifelineView":
            lf = _ref(ids, v, "model")
            role = _ref(ids, lf, "represent")
            typ = _ref(ids, role, "type") if role else None
            lp = _ref(ids, v, "linePart")
            actor = v.get("stereotypeDisplay") == "icon" and typ and typ["_type"] == "UMLActor"
            hh = 40 + (26 if actor else 0)
            lls[lp["_id"]] = {
                "box": (v["left"], v["top"], v["left"] + v["width"], v["top"] + 40),
                "head": (v["left"], v["top"], v["left"] + v["width"], v["top"] + hh),
                "stereo": lf.get("stereotype", ""), "name": f"{lf.get('name', '')}: {typ['name'] if typ else ''}",
                "actor": actor, "x": lp["left"], "y1": lp["top"], "y2": lp["top"] + lp["height"],
                "lifeline": lf["_id"]}
        elif t == "UMLSeqMessageView":
            m = _ref(ids, v, "model")
            pts = _pts(v)
            no = order.index(m["_id"]) + 1
            sort = m.get("messageSort", "synchCall")
            if sort in ("synchCall", "asynchCall"):
                op = _ref(ids, m, "signature")
                if "arguments" in m:
                    args = m["arguments"]
                else:
                    args = ", ".join(p["name"] for p in op.get("parameters", []) if p.get("direction") != "return")
                text = f"{no} : {op['name']}({args})"
            else:
                text = f"{no} : {m.get('name', '')}"
            labels = []
            for nm in ("nameLabel", "stereotypeLabel"):
                lb = _ref(ids, v, nm)
                if not lb or not lb.get("visible", True):
                    continue
                txt = text if nm == "nameLabel" else "«create»"
                cx, cy = label_point(pts, lb.get("edgePosition", 1), lb.get("alpha", 0), lb.get("distance", 0))
                lw = _tw(txt) + 6
                labels.append((txt, (cx - lw / 2, cy - LINE_H / 2, cx + lw / 2, cy + LINE_H / 2)))
            act = _ref(ids, v, "activation")
            ab = None
            if act and act.get("visible", True):
                ab = (act["left"], act["top"], act["left"] + act["width"], act["top"] + act["height"])
            msgs.append({"points": pts, "sort": sort, "labels": labels, "act": ab, "no": no,
                         "tail": _ref(ids, v, "tail")["_id"], "head": _ref(ids, v, "head")["_id"]})
        elif t == "UMLCombinedFragmentView":
            f = _ref(ids, v, "model")
            box = (v["left"], v["top"], v["left"] + v["width"], v["top"] + v["height"])
            oc = _ref(ids, v, "operandCompartment")
            ops = []
            for i, ov in enumerate(oc.get("subViews", []) if oc else []):
                om = _ref(ids, ov, "model")
                g = om.get("guard", "")
                gtxt = f"[{g}]" if g else ""
                gl = None
                if gtxt:
                    x0, y0 = ov["left"] + 20, ov["top"] + 15
                    gl = (gtxt, (x0, y0, x0 + _tw(gtxt) + 4, y0 + LINE_H))
                ops.append({"top": ov["top"], "first": i == 0, "guard": gl})
            kind = f.get("interactionOperator", "")
            kw = _tw(kind) * 1.12 + 4
            hdr = (box[0], box[1], box[0] + 5 + kw + 5 + 13, box[1] + 26)
            frags.append({"box": box, "kind": kind, "ops": ops, "hdr": hdr})
    return lls, msgs, frags


def _head(sort, p_from, p_to):
    a = math.atan2(p_to[1] - p_from[1], p_to[0] - p_from[0])
    if sort == "synchCall":
        q = [(p_to[0] - 12 * math.cos(a + s * math.radians(25)), p_to[1] - 12 * math.sin(a + s * math.radians(25)))
             for s in (1, -1)]
        return (f'<polygon points="{p_to[0]:.1f},{p_to[1]:.1f} {q[0][0]:.1f},{q[0][1]:.1f} {q[1][0]:.1f},{q[1][1]:.1f}" '
                f'fill="#000" stroke="#000"/>')
    q = [(p_to[0] - 12 * math.cos(a + s * math.radians(28)), p_to[1] - 12 * math.sin(a + s * math.radians(28)))
         for s in (1, -1)]
    return (f'<path d="M{q[0][0]:.1f},{q[0][1]:.1f} L{p_to[0]:.1f},{p_to[1]:.1f} L{q[1][0]:.1f},{q[1][1]:.1f}" '
            f'fill="none" stroke="#000"/>')


def _actor(cx, top):
    """Значок актора в области 40 px (UMLActorView.drawIcon, пропорции StarUML)."""
    h = 38
    w = h * 0.55
    head_r = h / 7
    hy = top + 1 + head_r
    body = (hy + head_r, hy + head_r + h * 0.33)
    arms = hy + head_r + h * 0.1
    legs = top + 1 + h
    return (f'<circle cx="{cx:.1f}" cy="{hy:.1f}" r="{head_r:.1f}" fill="#fff" stroke="#000"/>'
            f'<line x1="{cx:.1f}" y1="{body[0]:.1f}" x2="{cx:.1f}" y2="{body[1]:.1f}" stroke="#000"/>'
            f'<line x1="{cx - w / 2:.1f}" y1="{arms:.1f}" x2="{cx + w / 2:.1f}" y2="{arms:.1f}" stroke="#000"/>'
            f'<line x1="{cx:.1f}" y1="{body[1]:.1f}" x2="{cx - w / 2:.1f}" y2="{legs:.1f}" stroke="#000"/>'
            f'<line x1="{cx:.1f}" y1="{body[1]:.1f}" x2="{cx + w / 2:.1f}" y2="{legs:.1f}" stroke="#000"/>')


def render(diagram, ids):
    lls, msgs, frags = geometry(diagram, ids)
    W = max([l["box"][2] for l in lls.values()] + [f["box"][2] for f in frags] +
            [lb[1][2] for m in msgs for lb in m["labels"]]) + 30
    H = max([l["y2"] for l in lls.values()] + [f["box"][3] for f in frags]) + 30
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" viewBox="0 0 {W:.0f} {H:.0f}">',
           f'<rect width="{W:.0f}" height="{H:.0f}" fill="#fff"/>']
    for l in lls.values():
        out.append(f'<line x1="{l["x"]:.1f}" y1="{l["y1"]:.1f}" x2="{l["x"]:.1f}" y2="{l["y2"]:.1f}" stroke="#000" '
                   f'stroke-dasharray="3,3"/>')
    for l in lls.values():
        x1, y1, x2, y2 = l["box"]
        cx = (x1 + x2) / 2
        if l["actor"]:
            out.append(_actor(cx, y1))
            out.append(_t(cx, y1 + 40 + 17, l["name"]))
        else:
            out.append(f'<rect x="{x1:.1f}" y="{y1:.1f}" width="{x2 - x1:.1f}" height="{y2 - y1:.1f}" fill="#fff" '
                       f'stroke="#000"/>')
            if l["stereo"]:
                out.append(_t(cx, y1 + 16, f"«{l['stereo']}»"))
                out.append(_t(cx, y1 + 33, l["name"]))
            else:
                out.append(_t(cx, y1 + 25, l["name"]))
    for m in msgs:
        if m["act"]:
            x1, y1, x2, y2 = m["act"]
            out.append(f'<rect x="{x1:.1f}" y="{y1:.1f}" width="{x2 - x1:.1f}" height="{y2 - y1:.1f}" fill="#fff" '
                       f'stroke="#000"/>')
    for f in frags:
        x1, y1, x2, y2 = f["box"]
        hx2, hy2 = f["hdr"][2], f["hdr"][3]
        h = hy2 - y1
        out.append(f'<rect x="{x1:.1f}" y="{y1:.1f}" width="{x2 - x1:.1f}" height="{y2 - y1:.1f}" fill="none" '
                   f'stroke="#000"/>')
        out.append(f'<polygon points="{x1:.1f},{y1:.1f} {x1:.1f},{hy2:.1f} {hx2 - h / 2:.1f},{hy2:.1f} '
                   f'{hx2:.1f},{y1 + h / 2:.1f} {hx2:.1f},{y1:.1f}" fill="#fff" stroke="#000"/>')
        out.append(_t(x1 + 5, y1 + 18, f["kind"], anchor="start", weight="bold"))
        for op in f["ops"]:
            if not op["first"]:
                out.append(f'<line x1="{x1:.1f}" y1="{op["top"]:.1f}" x2="{x2 - 1:.1f}" y2="{op["top"]:.1f}" '
                           f'stroke="#000" stroke-dasharray="10,3"/>')
            if op["guard"]:
                txt, (gx, gy, _, _) = op["guard"]
                out.append(_t(gx, gy + 12, txt, anchor="start"))
    for m in msgs:
        pts = m["points"]
        dash = ' stroke-dasharray="5,3"' if m["sort"] in ("reply", "createMessage") else ""
        d = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))
        out.append(f'<path d="{d}" fill="none" stroke="#000"{dash}/>')
        out.append(_head(m["sort"], pts[-2], pts[-1]))
        for txt, (bx1, by1, bx2, by2) in m["labels"]:
            out.append(_t((bx1 + bx2) / 2, (by1 + by2) / 2 + 5, txt))
    out.append("</svg>")
    return "\n".join(out)


def check(diagram, ids):
    lls, msgs, frags = geometry(diagram, ids)
    pr = []
    texts = [(t, b, f"сообщение {m['no']}") for m in msgs for t, b in m["labels"]]
    texts += [(op["guard"][0], op["guard"][1], "условие") for f in frags for op in f["ops"] if op["guard"]]
    texts += [(f["kind"], f["hdr"], "оператор фрагмента") for f in frags]
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            if _overlap(texts[i][1], texts[j][1], 1):
                pr.append(f"наложение подписей: [{texts[i][0][:30]}] ✕ [{texts[j][0][:30]}]")
    acts = [m["act"] for m in msgs if m["act"]]
    for t, b, who in texts:
        for l in lls.values():                   # над пунктиром линии жизни подпись проходить может ([5], рис. 5.3)
            if _overlap(b, l["head"], 1):
                pr.append(f"подпись [{t[:30]}] на шапке {l['name']}")
        for a in acts:
            if _overlap(b, a, 0):
                pr.append(f"подпись [{t[:30]}] на активации")
        for m in msgs:
            if any(b is lb for _, lb in m["labels"]):
                continue
            pts = m["points"]
            for p, q in zip(pts, pts[1:]):
                if _seg_box(p, q, b, 1):
                    pr.append(f"линия сообщения {m['no']} задевает подпись [{t[:30]}]")
        for f in frags:
            x1, y1, x2, y2 = f["box"]
            for (p, q) in (((x1, y1), (x1, y2)), ((x2, y1), (x2, y2)), ((x1, y1), (x2, y1)), ((x1, y2), (x2, y2))):
                if _seg_box(p, q, b, 1) and b is not f["hdr"]:
                    pr.append(f"рамка фрагмента {f['kind']} задевает подпись [{t[:30]}]")
            for op in f["ops"]:
                if not op["first"] and _seg_box((x1, op["top"]), (x2, op["top"]), b, 1):
                    pr.append(f"разделитель операндов задевает подпись [{t[:30]}]")
    for m in msgs:
        pts = m["points"]
        for l in lls.values():
            if m["sort"] == "createMessage" and m["head"] == next(k for k, v in lls.items() if v is l):
                continue
            for p, q in zip(pts, pts[1:]):
                if _seg_box(p, q, l["head"], 2):
                    pr.append(f"сообщение {m['no']} проходит через шапку {l['name']}")
        if len(pts) == 2 and abs(pts[1][0] - pts[0][0]) < 20:
            pr.append(f"сообщение {m['no']} слишком короткое")
    for f in frags:
        x1, y1, x2, y2 = f["box"]
        segs = [((x1, y1), (x1, y2)), ((x2, y1), (x2, y2)), ((x1, y1), (x2, y1)), ((x1, y2), (x2, y2))]
        segs += [((x1, op["top"]), (x2, op["top"])) for op in f["ops"] if not op["first"]]
        for l in lls.values():
            if any(_seg_box(p, q, l["head"], 2) for p, q in segs):
                pr.append(f"рамка фрагмента {f['kind']} проходит через шапку {l['name']}")
        for a in acts:                       # активация, начатая внутри рамки, не выходит за низ и разделители
            if y1 < a[1] < y2 and any(_seg_box(p, q, a, 0) for p, q in segs[3:] if p[1] > a[1]):
                pr.append(f"активация ({int(a[0])}, {int(a[1])}) пересекает низ рамки {f['kind']} или разделитель")
        for g in frags:
            if f is not g and _overlap(f["box"], g["box"], 0):
                inside = (g["box"][0] < f["box"][0] and f["box"][2] < g["box"][2] and g["box"][1] < f["box"][1]
                          and f["box"][3] < g["box"][3])
                contains = (f["box"][0] < g["box"][0] and g["box"][2] < f["box"][2] and f["box"][1] < g["box"][1]
                            and g["box"][3] < f["box"][3])
                if not inside and not contains:
                    pr.append(f"фрагменты {f['kind']} и {g['kind']} пересекаются")
    return sorted(set(pr))
