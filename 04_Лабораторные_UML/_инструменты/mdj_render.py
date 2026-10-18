"""Рендер и проверка диаграмм вариантов использования из проекта StarUML 6 (.mdj).

Координаты, размеры и связи берутся из представлений (views) файла .mdj; правила
отрисовки повторяют StarUML 6.3.3 (elements.js): Arial 13 px; у прецедента с точками
расширения — эллипс сверху и отсек со списком точек под ним; имя актора — внизу рамки;
подпись «include» — в 30 px от середины ребра (Coord.getPointAwayLine).

  python -I mdj_render.py <проект.mdj> <папка_вывода> [имя1 имя2 ...]  — SVG по диаграммам (в <папка>/SVG)
  python -I mdj_render.py <проект.mdj> <папка_вывода> [имена ...] --png  — и PNG (в <папка>/PNG, через LibreOffice)
  python -I mdj_render.py --check <проект.mdj>                          — проверка раскладки
  --activity / --statechart — только диаграммы деятельности / автомата (рендер и проверка — act_render.py)
"""
import json
import math
import os
import sys
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from staruml_xpd import LINE_H, EXT_ITEM_H, label_pos, text_w, wrap  # noqa: E402
import act_render  # noqa: E402

FONT = "Arial, Helvetica, sans-serif"
FS = 13


def T(x, y, s, anchor="middle", weight="normal", style="normal", size=FS):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" text-anchor="{anchor}" '
            f'font-weight="{weight}" font-style="{style}" fill="#000">{escape(s)}</text>')


def arrow_open(p_from, p_to, size=12):
    a = math.atan2(p_to[1] - p_from[1], p_to[0] - p_from[0])
    pts = [(p_to[0] - size * math.cos(a - s * math.radians(28)), p_to[1] - size * math.sin(a - s * math.radians(28))) for s in (1, -1)]
    return (f'<path d="M{pts[0][0]:.1f},{pts[0][1]:.1f} L{p_to[0]:.1f},{p_to[1]:.1f} L{pts[1][0]:.1f},{pts[1][1]:.1f}" '
            f'fill="none" stroke="#000" stroke-width="1"/>')


def triangle(p_from, p_to, size=14, half=8):
    a = math.atan2(p_to[1] - p_from[1], p_to[0] - p_from[0])
    bx, by = p_to[0] - size * math.cos(a), p_to[1] - size * math.sin(a)
    nx, ny = -math.sin(a) * half, math.cos(a) * half
    return (f'<polygon points="{p_to[0]:.1f},{p_to[1]:.1f} {bx + nx:.1f},{by + ny:.1f} {bx - nx:.1f},{by - ny:.1f}" '
            f'fill="#fff" stroke="#000" stroke-width="1"/>')


def load(path):
    project = json.load(open(path, encoding="utf-8"))
    ids, diagrams = {}, []

    def index(o):
        if isinstance(o, dict):
            if "_id" in o:
                ids[o["_id"]] = o
            if o.get("_type") in ("UMLUseCaseDiagram", "UMLActivityDiagram", "UMLStatechartDiagram"):
                diagrams.append(o)
            for v in o.values():
                index(v)
        elif isinstance(o, list):
            for x in o:
                index(x)
    index(project)
    return project, ids, diagrams


def geometry(diagram, ids):
    """Список фигур диаграммы: узлы (с рамками для проверки), рёбра, подписи."""
    items = []
    for v in diagram.get("ownedViews", []):
        t = v["_type"]
        m = ids.get(v["model"]["$ref"]) if v.get("model") else None
        it = {"view": v, "type": t, "model": m}
        if "left" in v:
            x, y, w, h = v["left"], v["top"], v["width"], v["height"]
            it["box"] = (x, y, x + w, y + h)
            if t == "UMLUseCaseView":
                n = len(m.get("extensionPoints", []))
                ext_h = 10 + EXT_ITEM_H * n - 2 if n else 0
                it["ell_h"] = h - (5 + ext_h if n else 0)
                it["label"] = m["name"]
            elif t == "UMLActorView":
                nw = text_w(m["name"]) + 4
                cx = x + w / 2
                it["bbox"] = (min(x, cx - nw / 2), y, max(x + w, cx + nw / 2), y + h)
                it["label"] = m["name"]
            elif t in ("UMLNoteView", "UMLTextView", "UMLClassView"):
                it["label"] = (v.get("text") or (m or {}).get("name", ""))[:28].replace("\n", " ")
        elif "points" in v:
            pts = [tuple(float(c) for c in p.split(":")) for p in v["points"].split(";")]
            it["points"] = pts
            if t == "UMLIncludeView":
                lx, ly = label_pos(pts[0], pts[-1], math.pi / 2, 30)
                lw = text_w("«include»") + 4
                it["lbox"] = (lx - lw / 2, ly - 8, lx + lw / 2, ly + 8)
        items.append(it)
    return items


def render(diagram, ids):
    items = geometry(diagram, ids)
    back, nodes, edges, front = [], [], [], []
    ext = [1e9, 1e9, -1e9, -1e9]

    def grow(b):
        ext[0], ext[1], ext[2], ext[3] = min(ext[0], b[0]), min(ext[1], b[1]), max(ext[2], b[2]), max(ext[3], b[3])

    for it in items:
        v, t, m = it["view"], it["type"], it["model"]
        if "box" in it:
            x0, y0, x1, y1 = it["box"]
            w, h = x1 - x0, y1 - y0
            grow(it.get("bbox", it["box"]))
        if t == "UMLUseCaseSubjectView":
            back.append(f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" fill="#fff" stroke="#000"/>')
            back.append(T(x0 + w / 2, y0 + 20, m["name"], weight="bold"))
        elif t == "UMLUseCaseView":
            eh = it["ell_h"]
            cx, cy = x0 + w / 2, y0 + eh / 2
            nodes.append(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{w / 2:.1f}" ry="{eh / 2:.1f}" fill="#fff" stroke="#000"/>')
            lines = wrap(m["name"], w / math.sqrt(2) - 10)
            ny = cy - (len(lines) - 1) * LINE_H / 2 + 4
            for i, s in enumerate(lines):
                nodes.append(T(cx, ny + i * LINE_H, s))
            eps = m.get("extensionPoints", [])
            if eps:
                top = y0 + eh + 5
                nodes.append(f'<line x1="{x0}" y1="{top}" x2="{x1}" y2="{top}" stroke="#000"/>')
                for i, e in enumerate(eps):
                    nodes.append(T(x0 + 5, top + 5 + 12 + i * EXT_ITEM_H, e["name"], anchor="start"))
        elif t == "UMLActorView":
            cx = x0 + w / 2
            fh = h - LINE_H - 4
            hr = min(w * 0.22, fh * 0.13)
            hy = y0 + hr + 1
            st = 'stroke="#000" stroke-width="1.2" fill="none"'
            nodes += [f'<circle cx="{cx:.1f}" cy="{hy:.1f}" r="{hr:.1f}" fill="#fff" stroke="#000" stroke-width="1.2"/>',
                      f'<line x1="{cx:.1f}" y1="{hy + hr:.1f}" x2="{cx:.1f}" y2="{y0 + fh * 0.66:.1f}" {st}/>',
                      f'<line x1="{x0:.1f}" y1="{y0 + fh * 0.38:.1f}" x2="{x1:.1f}" y2="{y0 + fh * 0.38:.1f}" {st}/>',
                      f'<line x1="{cx:.1f}" y1="{y0 + fh * 0.66:.1f}" x2="{x0 + 3:.1f}" y2="{y0 + fh:.1f}" {st}/>',
                      f'<line x1="{cx:.1f}" y1="{y0 + fh * 0.66:.1f}" x2="{x1 - 3:.1f}" y2="{y0 + fh:.1f}" {st}/>',
                      T(cx, y1 - 4, m["name"])]
        elif t == "UMLClassView":
            nodes.append(f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" fill="#fff" stroke="#000"/>')
            if m.get("stereotype"):
                nodes += [T(x0 + w / 2, y0 + 18, f"«{m['stereotype']}»"), T(x0 + w / 2, y0 + 35, m["name"], weight="bold")]
            else:
                nodes.append(T(x0 + w / 2, y0 + h / 2 + 4, m["name"], weight="bold"))
        elif t == "UMLNoteView":
            f = 10
            front.append(f'<path d="M{x0},{y0} H{x1 - f} L{x1},{y0 + f} V{y1} H{x0} Z" fill="#fff" stroke="#000"/>')
            front.append(f'<path d="M{x1 - f},{y0} V{y0 + f} H{x1}" fill="none" stroke="#000"/>')
            for i, s in enumerate(wrap(v.get("text", ""), w - 12)):
                front.append(T(x0 + 6, y0 + 17 + i * LINE_H, s, anchor="start"))
        elif t == "UMLTextView":
            lines = wrap(v.get("text", ""), w - 6)
            if v.get("vertAlign", 3) == 5:
                ty = y0 + h / 2 - (len(lines) - 1) * LINE_H / 2 + 4
            else:
                ty = y0 + 14
            for i, s in enumerate(lines):
                if v.get("horzAlign", 0) == 2:
                    front.append(T(x0 + w / 2, ty + i * LINE_H, s))
                else:
                    front.append(T(x0 + 3, ty + i * LINE_H, s, anchor="start"))
        elif "points" in it:
            pts = it["points"]
            for p in pts:
                grow((p[0], p[1], p[0], p[1]))
            dash = ' stroke-dasharray="6 4"' if t in ("UMLIncludeView", "UMLExtendView") else (
                ' stroke-dasharray="2 3"' if t == "UMLNoteLinkView" else "")
            d = " L".join(f"{p[0]:.1f},{p[1]:.1f}" for p in pts)
            edges.append(f'<path d="M{d}" fill="none" stroke="#000"{dash}/>')
            if t in ("UMLIncludeView", "UMLExtendView"):
                edges.append(arrow_open(pts[-2], pts[-1]))
            elif t == "UMLGeneralizationView":
                edges.append(triangle(pts[-2], pts[-1]))
            elif t == "UMLAssociationView":
                if m["end2"].get("navigable") == "navigable":
                    edges.append(arrow_open(pts[-2], pts[-1]))
            if "lbox" in it:
                lb = it["lbox"]
                front.append(T((lb[0] + lb[2]) / 2, lb[3] - 4, "«include»"))
                grow(lb)
    mg = 20
    x0, y0, W, H = ext[0] - mg, ext[1] - mg, ext[2] - ext[0] + 2 * mg, ext[3] - ext[1] + 2 * mg
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" viewBox="{x0:.0f} {y0:.0f} {W:.0f} {H:.0f}">\n'
            f'<rect x="{x0:.0f}" y="{y0:.0f}" width="{W:.0f}" height="{H:.0f}" fill="#fff"/>\n'
            + "\n".join(back + nodes + edges + front) + "\n</svg>\n")


# ---------------------------------------------------------------- проверка раскладки

def _boxes_overlap(a, b, pad=3):
    return not (a[2] <= b[0] + pad or b[2] <= a[0] + pad or a[3] <= b[1] + pad or b[3] <= a[1] + pad)


def _seg_hits_box(p, q, b, shrink=4):
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


def check(diagram, ids):
    items = geometry(diagram, ids)
    solids = []      # (имя, рамка, view_id)
    for it in items:
        if "box" in it and it["type"] != "UMLUseCaseSubjectView":
            solids.append((f'{it["type"][3:]}:{it.get("label", "")}', it.get("bbox", it["box"]), it["view"]["_id"]))
        if "lbox" in it:
            solids.append(("include-подпись", it["lbox"], it["view"]["_id"] + "#l"))
    problems = []
    for i, (na, ba, _) in enumerate(solids):
        for nb, bb, _ in solids[i + 1:]:
            if _boxes_overlap(ba, bb):
                problems.append(f"наложение: {na} ✕ {nb}")
    by_view = {it["view"]["_id"]: it for it in items}
    for it in items:
        if "points" not in it:
            continue
        v = it["view"]
        ends = {v.get("head", {}).get("$ref"), v.get("tail", {}).get("$ref")}
        pts = it["points"]
        for na, ba, vid in solids:
            if vid in ends or vid == v["_id"] + "#l":
                continue
            if any(_seg_hits_box(pts[k], pts[k + 1], ba) for k in range(len(pts) - 1)):
                head = by_view.get(v.get("head", {}).get("$ref"), {}).get("label", "?")
                tail = by_view.get(v.get("tail", {}).get("$ref"), {}).get("label", "?")
                problems.append(f"линия {it['type'][3:-4]} [{tail} → {head}] проходит через {na}")
    return problems


def _pick(diagrams, kind):
    return [d for d in diagrams if d["_type"] == kind] if kind else diagrams


BEHAVIOR = ("UMLActivityDiagram", "UMLStatechartDiagram")    # рисуются и проверяются act_render.py


def main():
    only_act = ("UMLActivityDiagram" if "--activity" in sys.argv else
                "UMLStatechartDiagram" if "--statechart" in sys.argv else None)
    sys.argv = [a for a in sys.argv if a not in ("--activity", "--statechart")]
    if sys.argv[1] == "--check":
        project, ids, diagrams = load(sys.argv[2])
        total = 0
        for dg in _pick(diagrams, only_act):
            pr = (act_render.check if dg["_type"] in BEHAVIOR else check)(dg, ids)
            total += len(pr)
            print(f"{dg['name'][:64]:64} проблем: {len(pr)}")
            for p in pr:
                print("    " + p)
        print("ИТОГО проблем:", total)
        return
    png = "--png" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--png"]
    src, out = args[0], args[1]
    names = args[2:]
    project, ids, diagrams = load(src)
    svg_dir = os.path.join(out, "SVG")                # SVG и PNG — в отдельных подпапках
    os.makedirs(svg_dir, exist_ok=True)
    for i, dg in enumerate(_pick(diagrams, only_act)):
        name = names[i] if i < len(names) else f"D{i + 1}"
        with open(os.path.join(svg_dir, name + ".svg"), "w", encoding="utf-8") as f:
            f.write((act_render.render if dg["_type"] in BEHAVIOR else render)(dg, ids))
        print(name + ".svg —", dg["name"])
    if png:
        to_png(svg_dir, os.path.join(out, "PNG"))


def to_png(folder, png_dir):
    """SVG -> PNG через LibreOffice; SVG временно увеличивается вдвое (LibreOffice ограничивает ширину 2048 px)."""
    import glob
    import re
    import shutil
    import subprocess
    import tempfile
    soffice = shutil.which("soffice") or r"C:\Program Files\LibreOffice\program\soffice.exe"
    with tempfile.TemporaryDirectory() as tmp:
        for f in glob.glob(os.path.join(folder, "*.svg")):
            s = open(f, encoding="utf-8").read()
            s = re.sub(r'width="(\d+)" height="(\d+)"', lambda m: f'width="{2 * int(m[1])}" height="{2 * int(m[2])}"', s, count=1)
            open(os.path.join(tmp, os.path.basename(f)), "w", encoding="utf-8").write(s)
        svgs = sorted(glob.glob(os.path.join(tmp, "*.svg")))
        subprocess.run([soffice, "--headless", "--convert-to", "png", "--outdir", tmp, *svgs], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.makedirs(png_dir, exist_ok=True)
        for f in glob.glob(os.path.join(tmp, "*.png")):
            shutil.copy(f, png_dir)
            print(os.path.basename(f))


if __name__ == "__main__":
    main()
