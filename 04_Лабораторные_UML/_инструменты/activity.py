"""Диаграммы деятельности для StarUML 6 (.mdj) и StarUML 5.0 (.uml) из описания на Python.

Раскладка: вертикальные плавательные дорожки (разделы активности), узлы ставятся в клетку
(дорожка, строка); переходы трассируются ортогонально; подпись перехода «событие [условие]»
ставится рядом с началом перехода. Геометрия считается один раз и пишется в оба формата.

StarUML 6 (сверено с metamodel.json, elements.js, core.js 6.3.3):
  - UMLActivity: nodes / edges / groups (UMLActivityPartition, узлы дорожки — в partition.nodes),
    диаграмма UMLActivityDiagram — в ownedElements деятельности;
  - ссылка на деятельность (SubactivityState) — UMLAction с kind="callBehavior", target и
    subactivity = вызываемая деятельность: подпись «ссылка:Деятельность» и значок-«грабли»;
  - UMLControlFlow: name (триггерное событие) и guard; подпись — EdgeLabelView в середине
    ребра (EP_MIDDLE), смещение задаётся alpha/distance (Coord.getPointAwayLine);
  - lineStyle пишется явно (иначе загрузчик берёт 0 из метамодели).
StarUML 5.0 (UMLModels.pas, UMLFacto.pas): UMLActivityGraph в Behaviors пакета, вершины — в
Top (UMLCompositeState «TOP»), UMLPartition.Contents, UMLTransition с GuardCondition и Triggers.
"""
import math

from staruml_xpd import LINE_H, Obj, text_w, wrap

LANE_HEAD = 24        # высота заголовка дорожки
ROW_GAP = 40          # вертикальный зазор между строками
TOP_PAD = 28          # от заголовка дорожки до первой строки
SIZES = {"initial": (20, 20), "final": (26, 26), "decision": (30, 24)}
RAKE = 15             # ширина значка вызова деятельности справа


def label_text(trigger, guard, effect=""):
    """Подпись перехода по правилу StarUML: «событие [условие] / действие»."""
    t = (trigger + (" " if trigger and guard else "") + (f"[{guard}]" if guard else "")).strip()
    return f"{t} / {effect}".strip() if effect else t


PSEUDO = ("decision", "choice", "junction")      # узлы-ромбы и точки: выход и вход сбоку
BARS = ("fork", "join")   # линейки разветвления и синхронизации параллельных потоков
BAR_H = 6                 # толщина линейки (FORKNODE_MINTHICK в StarUML 6, SYNCHRONIZATION_MINTHICK в 5.0)


def _away_line(p1, p2, alpha, distance):
    """Coord.getPointAwayLine из StarUML."""
    a, b = p1[0] - p2[0], p1[1] - p2[1]
    th = math.atan(abs(b) / (abs(a) + 0.000001))
    if a > 0:
        th = math.pi - th if b > 0 else th + math.pi
    elif b < 0:
        th = 2 * math.pi - th
    return th, (math.floor(distance * math.cos(th + alpha)), math.floor(-distance * math.sin(th + alpha)))


def middle_ref(points):
    """Опорная точка подписи EP_MIDDLE (EdgeParasiticView.arrangeObject)."""
    n = len(points)
    mid = n // 2 - (1 if n % 2 == 0 else 0)
    p1, p2 = points[mid], points[mid + 1]
    if n % 2 == 0:
        p1 = (math.floor((p1[0] + p2[0]) / 2), math.floor((p1[1] + p2[1]) / 2))
    return p1, p2


def label_center(points, alpha, distance):
    p1, p2 = middle_ref(points)
    _, (dx, dy) = _away_line(p1, p2, alpha, distance)
    return p1[0] + dx, p1[1] + dy


def alpha_distance(points, center):
    """alpha и distance, при которых центр подписи окажется в center."""
    p1, p2 = middle_ref(points)
    th, _ = _away_line(p1, p2, 0, 0)
    dx, dy = center[0] - p1[0], center[1] - p1[1]
    return math.atan2(-dy, dx) - th, math.hypot(dx, dy)


class Node:
    def __init__(self, key, kind, name="", doc="", lane=0, row=0, dx=0, w=None, call=None, cols=(), pad=40):
        self.key, self.kind, self.name, self.doc = key, kind, name, doc
        self.lane, self.row, self.dx, self.w = lane, row, dx, w
        self.call = call          # ключ вызываемой деятельности (ссылка на деятельность)
        self.cols, self.pad = list(cols), pad      # линейка: колонки (дорожка, dx), которые она перекрывает
        self.box = None

    def label(self, acts):
        return f"{self.name}:{acts[self.call].name}" if self.call else self.name

    def size(self, acts):
        if self.kind in SIZES:
            return SIZES[self.kind]
        if self.kind in BARS:
            return 0, BAR_H                   # ширина — по колонкам при раскладке
        w = (self.w or 180) // 2 * 2         # чётная ширина: центр узла — целый пиксель
        # перенос с запасом: StarUML может разбить строку раньше, тогда узел вырастет вниз
        lines = wrap(self.label(acts), w - 26 - (RAKE if self.call else 0))
        return w, max(40, LINE_H * len(lines) + 16)

    # точки привязки
    def c(self):
        x, y, w, h = self.box
        return x + w / 2, y + h / 2

    def side(self, s):
        x, y, w, h = self.box
        return {"top": (x + w / 2, y), "bottom": (x + w / 2, y + h),
                "left": (x, y + h / 2), "right": (x + w, y + h / 2)}[s]


class Flow:
    def __init__(self, a, b, trigger="", guard="", doc="", via=None, pts=None, lab=None, exit=None, enter=None,
                 effect=""):
        self.a, self.b, self.trigger, self.guard, self.doc = a, b, trigger, guard, doc
        self.effect = effect                      # действие на переходе (в диаграммах автомата)
        self.via, self.pts, self.lab, self.exit, self.enter = via, pts, lab, exit, enter
        self.points = None
        self.alpha, self.distance = math.pi / 2, 15
        self.lcenter = None

    @property
    def text(self):
        return label_text(self.trigger, self.guard, self.effect)


class Activity:
    """Деятельность. Без lanes — вызываемая деятельность без собственной диаграммы."""

    def __init__(self, key, name, doc="", diagram=None, diagram_doc="", lanes=(), lane_docs=()):
        self.key, self.name, self.doc = key, name, doc
        self.diagram, self.diagram_doc = diagram, diagram_doc
        self.lanes = list(lanes)                 # [(название, ширина)]
        self.lane_docs = list(lane_docs) or [""] * len(self.lanes)
        self.nodes, self.flows = {}, []
        self.order = []

    # -- построение
    def _add(self, n):
        self.nodes[n.key] = n
        self.order.append(n)
        return n.key

    def initial(self, key, lane, row, doc="", dx=0):
        return self._add(Node(key, "initial", "", doc, lane, row, dx))

    def final(self, key, lane, row, doc="", dx=0):
        return self._add(Node(key, "final", "", doc, lane, row, dx))

    def decision(self, key, lane, row, doc="", dx=0):
        return self._add(Node(key, "decision", "", doc, lane, row, dx))

    def action(self, key, name, lane, row, doc="", dx=0, w=None):
        return self._add(Node(key, "action", name, doc, lane, row, dx, w))

    def call(self, key, ref_name, target, lane, row, doc="", dx=0, w=None):
        return self._add(Node(key, "action", ref_name, doc, lane, row, dx, w, call=target))

    def fork(self, key, row, cols, doc="", pad=40):
        """Линейка разветвления; cols — колонки [(дорожка, dx)] параллельных потоков."""
        return self._add(Node(key, "fork", "", doc, cols[0][0], row, cols=cols, pad=pad))

    def join(self, key, row, cols, doc="", pad=40):
        """Линейка синхронизации: переход дальше — после завершения всех входящих потоков."""
        return self._add(Node(key, "join", "", doc, cols[0][0], row, cols=cols, pad=pad))

    def flow(self, a, b, trigger="", guard="", doc="", **kw):
        f = Flow(a, b, trigger, guard, doc, **kw)
        self.flows.append(f)
        return f

    # -- раскладка
    def layout(self, acts, x0=20, y0=20):
        lane_x, x = [], x0
        for _, w in self.lanes:
            lane_x.append(x)
            x += w
        self.width = x - x0
        sizes = {k: n.size(acts) for k, n in self.nodes.items()}
        rows = sorted({n.row for n in self.nodes.values()})
        row_h = {r: max(sizes[n.key][1] for n in self.nodes.values() if n.row == r) for r in rows}
        y, row_c = y0 + LANE_HEAD + TOP_PAD, {}
        for r in range(rows[-1] + 1):
            h = row_h.get(r, 20)
            row_c[r] = y + h / 2
            y += h + ROW_GAP
        self.height = y - ROW_GAP + TOP_PAD - y0
        self.lane_boxes = [(lane_x[i], y0, w, self.height) for i, (_, w) in enumerate(self.lanes)]
        for n in self.nodes.values():
            w, h = sizes[n.key]
            if n.kind in BARS:                      # горизонтальная линейка поперёк своих колонок
                xs = [lane_x[ln] + self.lanes[ln][1] / 2 + dx for ln, dx in n.cols]
                x0, x1 = round(min(xs) - n.pad), round(max(xs) + n.pad)
                n.box = (x0, round(row_c[n.row] - h / 2), max(x1 - x0, 70), h)
                continue
            cx = lane_x[n.lane] + self.lanes[n.lane][1] / 2 + n.dx
            n.box = (round(cx - w / 2), round(row_c[n.row] - h / 2), w, h)
        for f in self.flows:
            f.points = self._route(f)
            if f.text:
                f.lcenter = self._label_spot(f)
                f.alpha, f.distance = alpha_distance(f.points, f.lcenter)

    def _route(self, f):
        T, H = self.nodes[f.a], self.nodes[f.b]
        tc, hc = T.c(), H.c()
        if f.pts:                                   # явные промежуточные точки (или функция от узлов)
            mids = list(f.pts(self.nodes) if callable(f.pts) else f.pts)
            return [self._proj(T, mids[0], f.exit), *mids, self._proj(H, mids[-1], f.enter)]
        if f.via:                                   # обход сбоку: ("right"|"left", x)
            side, cx = f.via
            p1 = T.side(f.exit or side)
            p2 = H.side(f.enter or side)
            return [p1, (cx, p1[1]), (cx, p2[1]), p2]
        tb, ht = T.box[1] + T.box[3], H.box[1]
        if T.kind in BARS:                          # из линейки — вертикально вниз, над узлом
            return [(hc[0], tb), H.side("top")]
        if H.kind in BARS:                          # в линейку — вертикально вниз из-под узла
            return [T.side("bottom"), (tc[0], ht)]
        if ht > tb and f.exit in ("left", "right") and T.kind not in PSEUDO:   # выход сбоку действия
            s = T.side(f.exit)
            return [s, (hc[0], s[1]), H.side("top")]
        if ht > tb:                                 # голова ниже
            if abs(tc[0] - hc[0]) < 1:
                return [T.side("bottom"), H.side("top")]
            if T.kind in PSEUDO and f.exit != "bottom":
                s = T.side("right" if hc[0] > tc[0] else "left")
                return [s, (hc[0], s[1]), H.side("top")]
            if H.kind in PSEUDO and f.enter != "top":
                s = H.side("left" if tc[0] < hc[0] else "right")
                return [T.side("bottom"), (tc[0], s[1]), s]
            ym = ht - 14 if f.text else (tb + ht) / 2   # над нижним отрезком — место для подписи
            return [T.side("bottom"), (tc[0], ym), (hc[0], ym), H.side("top")]
        if abs(tc[0] - hc[0]) < 1 and hc[1] < tc[1]:   # строго вверх по одной вертикали (цепочка соединений)
            return [T.side("top"), H.side("bottom")]
        if abs(tc[1] - hc[1]) < 1:                  # одна строка
            if hc[0] > tc[0]:
                return [T.side("right"), H.side("left")]
            return [T.side("left"), H.side("right")]
        raise ValueError(f"{self.name}: переход {f.a}->{f.b} вверх без via")

    @staticmethod
    def _proj(n, p, side=None):
        if side:
            return n.side(side)
        x, y, w, h = n.box
        if x <= p[0] <= x + w:
            return (p[0], y if p[1] < y else y + h)
        return (x if p[0] < x else x + w, p[1])

    def _label_spot(self, f):
        if callable(f.lab):
            return f.lab(self.nodes)
        if f.lab and not isinstance(f.lab, str):
            return f.lab
        lw, lh = text_w(f.text) + 6, LINE_H
        pts = f.points
        (x1, y1), (x2, y2) = pts[0], pts[1]
        if len(pts) == 4 and abs(x1 - x2) < 1 and abs(pts[1][1] - pts[2][1]) < 1:   # Z: над средним отрезком
            xa, xb = pts[1][0], pts[2][0]
            d = 1 if xb > xa else -1
            return (self._past_borders(xa + d * 8, lw, d), pts[1][1] - lh / 2 - 3)
        if abs(y1 - y2) < 1:                         # первый отрезок горизонтальный — над ним, у начала
            d = 1 if x2 > x1 else -1
            cx = self._past_borders(x1 + d * 8, lw, d)
            if self._lane_of(cx - lw / 2) is None or self._lane_of(cx + lw / 2) is None:
                cx = self._clamp(x1 + d * (lw / 2 + 8), lw, x1 + d * 4)
            return (cx, y1 - lh / 2 - 3)
        d = 1 if y2 > y1 else -1                     # вертикальный — сбоку, у начала
        right, left = x1 + 6 + lw / 2, x1 - 6 - lw / 2
        lane = self._lane_of(x1)
        fits_right = lane is None or right + lw / 2 <= lane[0] + lane[2] - 4
        fits_left = lane is not None and left - lw / 2 >= lane[0] + 4
        cx = left if f.lab == "left" or (not fits_right and fits_left) else right
        return (cx, y1 + d * (lh / 2 + 6))

    def _lane_of(self, x):
        for lb in self.lane_boxes:
            if lb[0] <= x <= lb[0] + lb[2]:
                return lb
        return None

    def _past_borders(self, start, lw, d):
        """Центр подписи, идущей от start в сторону d; если она легла бы на границу дорожки — за границу."""
        lo, hi = sorted((start, start + d * lw))
        for lb in self.lane_boxes:
            for bx in (lb[0], lb[0] + lb[2]):
                if lo + 1 < bx < hi - 1:
                    start = bx + d * 4
                    lo, hi = sorted((start, start + d * lw))
        return (lo + hi) / 2

    def _clamp(self, cx, lw, ref_x):
        """Сдвигает подпись шириной lw внутрь дорожки, в которой лежит ref_x."""
        lane = self._lane_of(ref_x)
        if lane is None or lw > lane[2] - 8:
            return cx
        return min(max(cx, lane[0] + 4 + lw / 2), lane[0] + lane[2] - 4 - lw / 2)

    def edges_count(self):
        return len(self.flows)


# ---------------------------------------------------------------- StarUML 6 (.mdj)

def _mdj(mod, type_, parent, **fields):
    return mod.node(type_, parent, **fields)


def _pts6(points):
    return ";".join(f"{int(round(x))}:{int(round(y))}" for x, y in points)


def mdj_logical_view(mod, project_obj, acts, doc=""):
    """UMLModel «Logical View» с деятельностями для staruml_mdj.Project."""
    ref = mod.ref
    model = {"_type": "UMLModel", "_id": mod.new_id(), "_parent": ref(project_obj), "name": "Logical View"}
    if doc:
        model["documentation"] = doc
    objs = {}
    for a in acts.values():                         # сначала объекты деятельностей — для ссылок
        o = _mdj(mod, "UMLActivity", model, name=a.name)
        if a.doc:
            o["documentation"] = a.doc
        objs[a.key] = o
    owned = []
    for a in acts.values():
        o = objs[a.key]
        owned.append(o)
        if not a.lanes:
            continue
        parts = []
        for i, (lname, _) in enumerate(a.lanes):
            p = _mdj(mod, "UMLActivityPartition", o, name=lname, nodes=[])
            if a.lane_docs[i]:
                p["documentation"] = a.lane_docs[i]
            parts.append(p)
        nobj = {}
        for n in a.order:
            t = {"initial": "UMLInitialNode", "final": "UMLActivityFinalNode", "decision": "UMLDecisionNode",
                 "fork": "UMLForkNode", "join": "UMLJoinNode", "action": "UMLAction"}[n.kind]
            no = _mdj(mod, t, parts[n.lane], name=n.name)
            if n.doc:
                no["documentation"] = n.doc
            if n.call:
                no.update(kind="callBehavior", target=ref(objs[n.call]), subactivity=ref(objs[n.call]))
            parts[n.lane]["nodes"].append(no)
            nobj[n.key] = no
        edges = []
        for f in a.flows:
            e = _mdj(mod, "UMLControlFlow", o, source=ref(nobj[f.a]), target=ref(nobj[f.b]))
            if f.trigger:
                e["name"] = f.trigger
            if f.guard:
                e["guard"] = f.guard
            if f.doc:
                e["documentation"] = f.doc
            edges.append(e)
        o["groups"] = parts
        o["edges"] = edges
        d = _mdj(mod, "UMLActivityDiagram", o, name=a.diagram)
        d["documentation"] = (a.diagram_doc + "\n\n" if a.diagram_doc else "") + quantitative(a)
        views, nview = [], {}
        for i, (lx, ly, lw, lh) in enumerate(a.lane_boxes):
            views.append(_mdj(mod, "UMLSwimlaneView", d, model=ref(parts[i]), left=lx, top=ly, width=lw,
                              height=lh, isVertical=True))
        for n in a.order:
            x, y, w, h = n.box
            if n.kind == "action":
                v = _mdj(mod, "UMLActionView", d, model=ref(nobj[n.key]), left=x, top=y, width=w, height=h,
                         wordWrap=True)
            else:
                v = _mdj(mod, "UMLControlNodeView", d, model=ref(nobj[n.key]), left=x, top=y, width=w, height=h)
            views.append(v)
            nview[n.key] = v
        for f, e in zip(a.flows, edges):
            v = _mdj(mod, "UMLControlFlowView", d, model=ref(e), head=ref(nview[f.b]), tail=ref(nview[f.a]),
                     lineStyle=0, points=_pts6(f.points))
            labels = []
            for nm, vis, al, ds in (("nameLabel", bool(f.text), f.alpha, f.distance),
                                    ("stereotypeLabel", False, math.pi / 2, 30),
                                    ("propertyLabel", False, -math.pi / 2, 15)):
                lb = _mdj(mod, "EdgeLabelView", v, model=ref(e), visible=vis, alpha=al, distance=ds,
                          hostEdge=ref(v), edgePosition=1)
                labels.append(lb)
                v[nm] = ref(lb)
            v["subViews"] = labels
            views.append(v)
        d["ownedViews"] = views
        o["ownedElements"] = [d]
    model["ownedElements"] = owned
    return model


def quantitative(a):
    kinds = [n.kind for n in a.nodes.values()]
    calls = sum(1 for n in a.nodes.values() if n.call)
    bars = (f"узлов разветвления (Fork) — {kinds.count('fork')}; узлов синхронизации (Join) — "
            f"{kinds.count('join')}; " if "fork" in kinds else "")
    return (f"Количественная характеристика диаграммы: разделов активности (дорожек) — {len(a.lanes)}; "
            f"состояний действия — {kinds.count('action') - calls}; ссылок на деятельности — {calls}; "
            f"узлов решения — {kinds.count('decision')}; {bars}начальных состояний — {kinds.count('initial')}; "
            f"конечных состояний — {kinds.count('final')}; переходов — {len(a.flows)}.")


# ---------------------------------------------------------------- StarUML 5.0 (.uml)

def _pts5(points):
    return ";".join(f"{int(round(x))},{int(round(y))}" for x, y in points)


# в StarUML 5.0 разветвление и синхронизация — один вид псевдосостояния (линейка), ориентация — по размерам вида
XPD_PSEUDO = {"initial": "pkInitial", "decision": "pkDecision", "choice": "pkChoice", "junction": "pkJunction",
              "fork": "pkSynchronization", "join": "pkSynchronization"}


def xpd_logical_view(project_obj, acts, doc="", extra_behaviors=(), extra_owned=None):
    """UMLModel «Logical View» с UMLActivityGraph для staruml_xpd.Project."""
    model = Obj("UMLModel")
    model.attr("Name", "Logical View")
    if doc:
        model.attr("Documentation", doc)
    model.ref("Namespace", project_obj)
    graphs = {a.key: Obj("UMLActivityGraph") for a in acts.values()}
    sub_refs = {k: [] for k in acts}                 # вызывающие ссылки на деятельность
    built, diagram_views = [], {}
    for a in acts.values():
        g = graphs[a.key]
        g.attr("Name", a.name)
        if a.doc:
            g.attr("Documentation", a.doc)
        g.ref("Context", model)
        top = Obj("UMLCompositeState")
        top.attr("Name", "TOP").ref("StateMachine", g)
        vert, views, n_views, out, inc = {}, {}, {}, {}, {}
        parts = [Obj("UMLPartition") for _ in a.lanes]
        lane_content = [[] for _ in a.lanes]
        for n in a.order:
            t = {"initial": "UMLPseudostate", "decision": "UMLPseudostate", "fork": "UMLPseudostate",
                 "join": "UMLPseudostate", "final": "UMLFinalState",
                 "action": "UMLSubactivityState" if n.call else "UMLActionState"}[n.kind]
            vert[n.key] = Obj(t)
            out[n.key], inc[n.key] = [], []
            lane_content[n.lane].append(vert[n.key])
            if n.call:
                sub_refs[n.call].append(vert[n.key])
        trans = [Obj("UMLTransition") for _ in a.flows]
        for f, t in zip(a.flows, trans):
            out[f.a].append(t)
            inc[f.b].append(t)
        owned_views = diagram_views.setdefault(a.key, [])
        if a.lanes:
            for i, (lx, ly, lw, lh) in enumerate(a.lane_boxes):
                v = Obj("UMLSwimlaneView")
                v.attr("Left", int(lx)).attr("Top", int(ly)).attr("Width", int(lw)).attr("Height", int(lh))
                v.ref("Model", parts[i])
                v.child("NameLabel", Obj("LabelView")).attr("Text", a.lanes[i][0])
                owned_views.append(v)
                n_views[("lane", i)] = v
            for n in a.order:
                x, y, w, h = n.box
                if n.kind == "action":
                    v = Obj("UMLSubactivityStateView" if n.call else "UMLActionStateView")
                else:
                    v = Obj("UMLFinalStateView" if n.kind == "final" else "UMLPseudostateView")
                v.attr("Left", int(x)).attr("Top", int(y)).attr("Width", int(w)).attr("Height", int(h))
                v.ref("Model", vert[n.key])
                if n.kind == "action":
                    v.attr("WordWrap", True)
                    nc = v.child("NameCompartment", Obj("UMLNameCompartmentView"))
                    nc.child("NameLabel", Obj("LabelView")).attr("Text", n.name)
                    nc.child("StereotypeLabel", Obj("LabelView")).attr("Visible", False)
                    nc.child("PropertyLabel", Obj("LabelView")).attr("Visible", False)
                    if n.call:
                        v.child("IncludeLabel", Obj("LabelView")).attr("Text", "include / " + acts[n.call].name)
                owned_views.append(v)
                views[n.key] = v
            for f, t in zip(a.flows, trans):
                v = Obj("UMLTransitionView")
                v.attr("LineStyle", "lsRectilinear", "LineStyleKind")
                v.attr("Points", _pts5(f.points), "Points")
                v.ref("Model", t).ref("Head", views[f.b]).ref("Tail", views[f.a])
                nl = v.child("NameLabel", Obj("EdgeLabelView"))
                if not f.text:
                    nl.attr("Visible", False)
                nl.attr("Alpha", float(f.alpha)).attr("Distance", float(f.distance))
                if f.text:
                    nl.attr("Text", f.text)
                nl.ref("Model", t)
                sl = v.child("StereotypeLabel", Obj("EdgeLabelView"))
                sl.attr("Visible", False).attr("Alpha", math.pi / 2).attr("Distance", 30.0).ref("Model", t)
                pl = v.child("PropertyLabel", Obj("EdgeLabelView"))
                pl.attr("Visible", False).attr("Alpha", -math.pi / 2).attr("Distance", 15.0)
                owned_views.append(v)
                n_views[id(t)] = (v, nl, sl)
        # вершины
        subs = []
        for n in a.order:
            o = vert[n.key]
            if n.kind == "action":
                o.attr("Name", n.name)
            if n.doc:
                o.attr("Documentation", n.doc)
            if n.kind in XPD_PSEUDO:
                o.attr("PseudostateKind", XPD_PSEUDO[n.kind], "UMLPseudostateKind")
            if n.call:
                o.ref("Submachine", graphs[n.call])
            o.ref("ContainerState", top)
            if n.key in views:
                o.refs("Views", [views[n.key]])
            o.refs("OwnerPartitions", [parts[n.lane]])
            o.refs("Outgoings", out[n.key])
            o.refs("Incomings", inc[n.key])
            subs.append(o)
        top.children("Subvertices", subs)
        g.child("Top", top)
        for f, t in zip(a.flows, trans):
            if f.guard:
                t.attr("GuardCondition", f.guard)
            if f.doc:
                t.attr("Documentation", f.doc)
            t.ref("StateMachine", g).ref("Source", vert[f.a]).ref("Target", vert[f.b])
            if id(t) in n_views:
                v, nl, sl = n_views[id(t)]
                t.refs("Views", [v, nl, sl])
            if f.trigger:
                ev = Obj("UMLCallEvent")
                ev.attr("Name", f.trigger).ref("Transition", t)
                t.children("Triggers", [ev])
        g.children("Transitions", trans)
        for i, p in enumerate(parts):
            p.attr("Name", a.lanes[i][0])
            if a.lane_docs[i]:
                p.attr("Documentation", a.lane_docs[i])
            p.ref("ActivityGraph", g)
            p.refs("Views", [n_views[("lane", i)]])
            p.refs("Contents", lane_content[i])
        g.children("Partitions", parts)
        built.append(a)
    for a in built:                                  # обратные ссылки и диаграммы
        g = graphs[a.key]
        g.refs("SubmachineStates", sub_refs[a.key])
        if a.lanes:
            d = Obj("UMLActivityDiagram")
            d.attr("Name", a.diagram)
            d.attr("Documentation", (a.diagram_doc + "\n\n" if a.diagram_doc else "") + quantitative(a))
            d.ref("DiagramOwner", g)
            dv = d.child("DiagramView", Obj("UMLActivityDiagramView"))
            dv.ref("Diagram", d)
            dv.children("OwnedViews", diagram_views[a.key])
            g.children("OwnedDiagrams", [d])
    if extra_owned:                                  # пакеты следующих работ (ЛР3: «Автоматы»)
        model.children("OwnedElements", extra_owned(model))
    extra = extra_behaviors(model) if callable(extra_behaviors) else extra_behaviors
    model.children("Behaviors", [graphs[a.key] for a in acts.values()] + list(extra))
    return model

