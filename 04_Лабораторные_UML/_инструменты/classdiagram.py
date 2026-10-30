"""Диаграммы классов для StarUML 6 (.mdj) и StarUML 5.0 (.uml) из описания на Python.

Модель: пакеты, классы (стереотипы entity / boundary / control / enumeration), интерфейсы, атрибуты и
операции с видимостью и типами, отношения: ассоциация (агрегация, композиция, кратности, навигация),
зависимость со стереотипом («call», «use», «instantiate», «create»), обобщение, реализация интерфейса.
Геометрия считается один раз и пишется в оба формата.

StarUML 6 (metamodel.json, elements.js 6.3.3):
  - UMLClass / UMLInterface: attributes (UMLAttribute: visibility, type), operations (UMLOperation:
    parameters — UMLParameter, у результата direction = "return"), stereotype — строка;
  - строки отсеков: атрибут «+имя: тип», операция «+Имя(п: тип): результат» (getString);
  - размеры вида: отсек = 5 + строки по 16 px через 2 px + 5; имя со стереотипом — 5 + 16 + 2 + 16 + 5;
    вид не уменьшается до минимума, но и не меньше его — поэтому размеры считаются по содержимому с запасом;
  - UMLAssociation: end1 = tail, end2 = head; aggregation на конце «целого» рисует ромб у этого конца;
    navigable = "navigable" — стрелка навигации; подписи концов — EP_TAIL / EP_HEAD (alpha, distance);
  - UMLDependency (source = клиент, target = поставщик), UMLGeneralization (source = потомок),
    UMLInterfaceRealization (source = реализующий класс, target = интерфейс); lineStyle пишется явно.
StarUML 5.0 (UMLModels.pas, UMLViews.pas, Samples/*.uml): UMLClass / UMLInterface с Attributes
(TypeExpression, Visibility = vk*) и Operations (Parameters, DirectionKind = pdkReturn), стереотип —
StereotypeProfile + StereotypeName; UMLAssociation.Connections[0..1] (Participant, Aggregation = ak*,
Multiplicity, IsNavigable); UMLDependency и UMLRealization (Client / Supplier), UMLGeneralization (Child /
Parent); у классов обратные ссылки #Associations, #Generalizations / #Specializations, #ClientDependencies /
#SupplierDependencies.
"""
import math
import re

from activity import _away_line, alpha_distance
from staruml_xpd import LINE_H, Obj, text_w

PAD, GAP = 5, 2                    # COMPARTMENT_*_PADDING и COMPARTMENT_ITEM_INTERVAL StarUML
FONT_K = 1.07                      # реальный шрифт немного шире оценки text_w
BOLD_K = 1.12
VIS6 = {"+": "public", "-": "private", "#": "protected", "~": "package"}
VIS5 = {"+": "vkPublic", "-": "vkPrivate", "#": "vkProtected", "~": "vkPackage"}
AGG5 = {"none": "akNone", "shared": "akAggregate", "composite": "akComposite"}
STEREO_TEXT = {"entity": "entity", "boundary": "boundary", "control": "control", "enumeration": "enumeration"}


def _split_params(s):
    """Разбить «a: int, b: dict[str, int]» по запятым верхнего уровня."""
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch in "[(":
            depth += 1
        elif ch in "])":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


class Attr:
    """«-имя: тип» (+ необязательно « = значение» и « {readOnly}» — неизменяемый атрибут)."""

    def __init__(self, spec, doc=""):
        self.read_only = spec.endswith("{readOnly}")
        spec = spec.removesuffix("{readOnly}").rstrip()
        m = re.match(r"^([+\-#~])\s*([^:=]+?)\s*(?::\s*([^=]+?))?\s*(?:=\s*(.+))?$", spec)
        if not m:
            raise ValueError(f"атрибут: {spec}")
        self.vis, self.name, self.type, self.default = m.group(1), m.group(2), m.group(3) or "", m.group(4) or ""
        self.doc = doc

    def text(self):
        t = f"{self.vis}{self.name}"
        if self.type:
            t += f": {self.type}"
        if self.default:
            t += f" = {self.default}"
        if self.read_only:
            t += " {readOnly}"
        return t


class Op:
    """«+Имя(п: тип, …): результат»."""

    def __init__(self, spec, doc="", abstract=False):
        m = re.match(r"^([+\-#~])\s*([^(]+?)\s*\((.*)\)\s*(?::\s*(.+))?$", spec)
        if not m:
            raise ValueError(f"операция: {spec}")
        self.vis, self.name, self.ret = m.group(1), m.group(2), (m.group(4) or "").strip()
        self.params = []
        for p in _split_params(m.group(3)):
            n, _, t = p.partition(":")
            self.params.append((n.strip(), t.strip()))
        self.doc, self.abstract = doc, abstract

    def text(self):
        ps = ", ".join(f"{n}: {t}" if t else n for n, t in self.params)
        return f"{self.vis}{self.name}({ps})" + (f": {self.ret}" if self.ret else "")


class Cls:
    def __init__(self, key, name, stereo, doc="", attrs=(), ops=(), abstract=False, interface=False):
        self.key, self.name, self.stereo, self.doc = key, name, stereo, doc
        self.attrs = [a if isinstance(a, Attr) else Attr(*a) for a in attrs]
        self.ops = [o if isinstance(o, Op) else Op(*o) for o in ops]
        self.abstract, self.interface = abstract, interface
        self.pkg = None

    @property
    def no_ops(self):
        """У класса без операций (перечисление, объект-значение, событие) отсек операций скрыт."""
        return not self.ops and not self.interface

    def stereo_text(self):
        return "interface" if self.interface else self.stereo

    @staticmethod
    def comp_h(n):
        return PAD + n * LINE_H + max(n - 1, 0) * GAP + PAD if n else 2 * PAD

    def size(self, mode="full"):
        """mode: full — все отсеки; name — только имя (отсеки атрибутов и операций скрыты)."""
        st = self.stereo_text()
        texts = [(f"«{st}»", 1.0)] if st else []
        texts.append((self.name, BOLD_K))
        h = PAD + (LINE_H + GAP if st else GAP) + LINE_H + PAD
        if mode == "full":
            texts += [(a.text(), 1.0) for a in self.attrs] + [(o.text(), 1.0) for o in self.ops]
            h += self.comp_h(len(self.attrs)) + (0 if self.no_ops else self.comp_h(len(self.ops)))
        w = max(math.ceil(text_w(t) * k * FONT_K) for t, k in texts) + 2 * PAD + 12
        return (max(w, 90) + 1) // 2 * 2, h


class Rel:
    def __init__(self, kind, a, b, doc="", name="", stereo="", mult_a="", mult_b="", agg_a="none",
                 nav_b=False, role_a="", role_b=""):
        self.kind, self.a, self.b, self.doc = kind, a, b, doc
        self.name, self.stereo = name, stereo
        self.mult_a, self.mult_b, self.agg_a, self.nav_b = mult_a, mult_b, agg_a, nav_b
        self.role_a, self.role_b = role_a, role_b
        self.key = f"{kind}:{a}->{b}:{stereo or name}"
        self.obj6 = None

    def kind_ru(self):
        if self.kind == "assoc":
            return {"composite": "композиция", "shared": "агрегация"}.get(self.agg_a, "ассоциация")
        return {"dep": "зависимость", "gen": "обобщение", "real": "реализация"}[self.kind]


class EdgeSpec:
    def __init__(self, rel, pts=None, exit=None, enter=None, dx=0, dy=0, lab=None, vfirst=False,
                 mult_a_at=None, mult_b_at=None):
        self.rel, self.pts, self.exit, self.enter = rel, pts, exit, enter
        self.dx, self.dy, self.lab, self.vfirst = dx, dy, lab, vfirst
        self.mult_a_at, self.mult_b_at = mult_a_at, mult_b_at
        self.points = None
        self.labels = {}             # имя подписи -> (центр, alpha, distance, edgePosition, текст)


class CDiagram:
    def __init__(self, model, key, name, doc="", kind="detail"):
        self.model, self.key, self.name, self.doc, self.kind = model, key, name, doc, kind
        self.nodes = {}              # ключ класса -> [x, y, mode]
        self.order = []
        self.pkg_boxes = []          # (ключ пакета, x, y, w, h)
        self.edges = []
        self.boxes = {}

    def place(self, key, x, y, mode="full", w=None):
        """w — ширина больше минимальной (чтобы к классу подходило несколько линий)."""
        self.nodes[key] = [x, y, mode, w]
        self.order.append(key)
        return self

    def column(self, x, y, keys, gap=36, mode="full"):
        """Классы друг под другом начиная с y; возвращает нижнюю границу."""
        for k in keys:
            self.place(k, x, y, mode)
            y += self.model.cls[k].size(mode)[1] + gap
        return y - gap

    def row(self, x, y, keys, gap=40, mode="full"):
        for k in keys:
            self.place(k, x, y, mode)
            x += self.model.cls[k].size(mode)[0] + gap
        return x - gap

    def package(self, pkg_key, x, y, w, h):
        self.pkg_boxes.append((pkg_key, x, y, w, h))

    def edge(self, rel_key, **kw):
        self.edges.append(EdgeSpec(self.model.rel[rel_key], **kw))
        return self

    # ---------------------------------------------------------------- раскладка
    def layout(self):
        for k in self.order:
            x, y, mode, w0 = self.nodes[k]
            w, h = self.model.cls[k].size(mode)
            self.boxes[k] = (int(x), int(y), max(w, w0 or 0), h)
        for e in self.edges:
            e.points = self._route(e)
            self._labels(e)

    @staticmethod
    def _side(b, s, off=0):
        x, y, w, h = b
        return {"top": (x + w / 2 + off, y), "bottom": (x + w / 2 + off, y + h),
                "left": (x, y + h / 2 + off), "right": (x + w, y + h / 2 + off)}[s]

    @staticmethod
    def _proj(b, p, side=None):
        x, y, w, h = b
        if side == "top":
            return (p[0], y)
        if side == "bottom":
            return (p[0], y + h)
        if side == "left":
            return (x, p[1])
        if side == "right":
            return (x + w, p[1])
        if x <= p[0] <= x + w:
            return (p[0], y if p[1] < y else y + h)
        return (x if p[0] < x else x + w, p[1])

    def _route(self, e):
        A, B = self.boxes[e.rel.a], self.boxes[e.rel.b]
        if e.pts:
            mids = list(e.pts(self.boxes) if callable(e.pts) else e.pts)
            return [self._proj(A, mids[0], e.exit), *mids, self._proj(B, mids[-1], e.enter)]
        ax, ay, aw, ah = A
        bx, by, bw, bh = B
        lo, hi = max(ax, bx), min(ax + aw, bx + bw)
        if hi - lo >= 24 and not e.vfirst:                       # общий диапазон по x — вертикаль
            x = round(min(max((lo + hi) / 2 + e.dx, lo + 8), hi - 8))
            return [(x, ay + ah), (x, by)] if ay + ah <= by else [(x, ay), (x, by + bh)]
        lo, hi = max(ay, by), min(ay + ah, by + bh)
        if hi - lo >= 20 and not e.vfirst:                       # общий диапазон по y — горизонталь
            y = round(min(max((lo + hi) / 2 + e.dy, lo + 8), hi - 8))
            return [(ax + aw, y), (bx, y)] if ax + aw <= bx else [(ax, y), (bx + bw, y)]
        acx, acy, bcx, bcy = ax + aw / 2, ay + ah / 2, bx + bw / 2, by + bh / 2
        if e.vfirst:                                             # вертикально из A, затем горизонтально в B
            x = round(acx + e.dx)
            y = round(bcy + e.dy)
            p1 = (x, ay + ah) if bcy > acy else (x, ay)
            p2 = (bx, y) if bcx > acx else (bx + bw, y)
            return [p1, (x, y), p2]
        y = round(acy + e.dy)                                    # горизонтально из A, затем вертикально в B
        x = round(bcx + e.dx)
        p1 = (ax + aw, y) if bcx > acx else (ax, y)
        p2 = (x, by) if bcy > acy else (x, by + bh)
        return [p1, (x, y), p2]

    # ---------------------------------------------------------------- подписи
    @staticmethod
    def _end_ad(p1, p2, center):
        th, _ = _away_line(p1, p2, 0, 0)
        dx, dy = center[0] - p1[0], center[1] - p1[1]
        return math.atan2(-dy, dx) - th, math.hypot(dx, dy)

    def _end_label(self, pts, at_head, text, override, diamond=False):
        p1, p2 = (pts[-1], pts[-2]) if at_head else (pts[0], pts[1])
        vx, vy = p2[0] - p1[0], p2[1] - p1[1]
        n = math.hypot(vx, vy) or 1
        ux, uy = vx / n, vy / n
        lw = text_w(text) + 6
        if override is not None:
            c = override(p1, ux, uy, lw) if callable(override) else override
        elif abs(uy) > 0.5:                                        # вертикальный конец — справа от линии
            c = (p1[0] + lw / 2 + (9 if diamond else 5), p1[1] + uy * (LINE_H / 2 + 6))
        else:                                                      # горизонтальный конец — над линией (за ромбом)
            c = (p1[0] + ux * (lw / 2 + (22 if diamond else 8)), p1[1] - (LINE_H / 2 + 3))
        a, d = self._end_ad(p1, p2, c)
        return c, a, d

    def _mid_label(self, e, text):
        pts = e.points
        lw = text_w(text) + 6
        if e.lab is not None and not isinstance(e.lab, str):
            c = e.lab(self.boxes, pts) if callable(e.lab) else e.lab
        else:
            k = max(range(len(pts) - 1), key=lambda i: abs(pts[i + 1][0] - pts[i][0]) + abs(pts[i + 1][1] - pts[i][1]))
            (x1, y1), (x2, y2) = pts[k], pts[k + 1]
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            if abs(y1 - y2) < 1:                                   # горизонтальный — над линией
                c = (mx, my + (LINE_H / 2 + 3 if e.lab == "below" else -(LINE_H / 2 + 3)))
            else:                                                  # вертикальный — сбоку
                c = (mx - 6 - lw / 2, my) if e.lab == "left" else (mx + 6 + lw / 2, my)
        a, d = alpha_distance(pts, c)
        return c, a, d

    def _labels(self, e):
        r, pts = e.rel, e.points
        if r.kind == "assoc":
            if r.name:
                e.labels["name"] = (*self._mid_label(e, r.name), 1, r.name)
            if r.mult_a:
                e.labels["tailMultiplicity"] = (*self._end_label(pts, False, r.mult_a, e.mult_a_at, r.agg_a != "none"), 2, r.mult_a)
            if r.mult_b:
                e.labels["headMultiplicity"] = (*self._end_label(pts, True, r.mult_b, e.mult_b_at), 0, r.mult_b)
        elif r.kind == "dep" and r.stereo:
            t = f"«{r.stereo}»"
            e.labels["stereotype"] = (*self._mid_label(e, t), 1, t)


class ClassModel:
    def __init__(self):
        self.pkgs = {}               # ключ -> [имя, описание, [ключи классов]]
        self.cls, self.rel = {}, {}
        self.cls_order, self.rel_order = [], []
        self.diagrams = []

    def package(self, key, name, doc=""):
        self.pkgs[key] = [name, doc, []]
        return key

    def add(self, pkg, key, name, stereo, doc="", attrs=(), ops=(), abstract=False, interface=False):
        c = Cls(key, name, stereo, doc, attrs, ops, abstract, interface)
        c.pkg = pkg
        self.cls[key] = c
        self.cls_order.append(c)
        self.pkgs[pkg][2].append(key)
        return key

    def relation(self, kind, a, b, doc="", **kw):
        r = Rel(kind, a, b, doc, **kw)
        if r.key in self.rel:
            raise ValueError(f"повтор отношения {r.key}")
        self.rel[r.key] = r
        self.rel_order.append(r)
        return r.key

    def assoc(self, a, b, doc="", **kw):
        return self.relation("assoc", a, b, doc, **kw)

    def dep(self, client, supplier, stereo, doc=""):
        return self.relation("dep", client, supplier, doc, stereo=stereo)

    def gen(self, child, parent, doc=""):
        return self.relation("gen", child, parent, doc)

    def real(self, impl, iface, doc=""):
        return self.relation("real", impl, iface, doc)

    def diagram(self, key, name, doc="", kind="detail"):
        d = CDiagram(self, key, name, doc, kind)
        self.diagrams.append(d)
        return d

    def layout(self):
        for d in self.diagrams:
            d.layout()


def quantitative(d):
    ks = [d.model.cls[k] for k in d.order]
    rels = [e.rel for e in d.edges]
    cnt = lambda f: sum(1 for r in rels if f(r))  # noqa: E731
    parts = [f"пакетов — {len(d.pkg_boxes)}"] if d.pkg_boxes else []
    parts.append(f"классов — {sum(1 for c in ks if not c.interface)}")
    if any(c.interface for c in ks):
        parts.append(f"интерфейсов — {sum(1 for c in ks if c.interface)}")
    if d.kind == "detail":
        parts.append(f"атрибутов — {sum(len(c.attrs) for c in ks)}; операций — {sum(len(c.ops) for c in ks)}")
    if rels:
        parts.append(f"ассоциаций — {cnt(lambda r: r.kind == 'assoc' and r.agg_a == 'none')}; агрегаций — "
                     f"{cnt(lambda r: r.kind == 'assoc' and r.agg_a == 'shared')}; композиций — "
                     f"{cnt(lambda r: r.kind == 'assoc' and r.agg_a == 'composite')}; зависимостей — "
                     f"{cnt(lambda r: r.kind == 'dep')}; обобщений — {cnt(lambda r: r.kind == 'gen')}; реализаций — "
                     f"{cnt(lambda r: r.kind == 'real')}")
    return "Количественная характеристика диаграммы: " + "; ".join(parts) + "."


# ---------------------------------------------------------------- StarUML 6 (.mdj)

def _pts6(points):
    return ";".join(f"{int(round(x))}:{int(round(y))}" for x, y in points)


def mdj_package(mod, parent, model, container_name, container_doc):
    """UMLPackage «container_name» с пакетами классов и диаграммами (ownedElements parent)."""
    node, ref = mod.node, mod.ref
    top = node("UMLPackage", parent, name=container_name, documentation=container_doc)
    pkg_obj, cls_obj = {}, {}
    owned = []
    for pk, (pname, pdoc, keys) in model.pkgs.items():
        p = node("UMLPackage", top, name=pname)
        if pdoc:
            p["documentation"] = pdoc
        pkg_obj[pk] = p
        items = []
        for k in keys:
            c = model.cls[k]
            o = node("UMLInterface" if c.interface else "UMLClass", p, name=c.name)
            if c.doc:
                o["documentation"] = c.doc
            st = c.stereo_text() if not c.interface else ""
            if st:
                o["stereotype"] = st
            if c.abstract:
                o["isAbstract"] = True
            if c.attrs:
                o["attributes"] = []
                for a in c.attrs:
                    ao = node("UMLAttribute", o, name=a.name, visibility=VIS6[a.vis])
                    if a.type:
                        ao["type"] = a.type
                    if a.default:
                        ao["defaultValue"] = a.default
                    if a.read_only:
                        ao["isReadOnly"] = True
                    if a.doc:
                        ao["documentation"] = a.doc
                    o["attributes"].append(ao)
            if c.ops:
                o["operations"] = []
                for op in c.ops:
                    oo = node("UMLOperation", o, name=op.name, visibility=VIS6[op.vis])
                    if op.abstract:
                        oo["isAbstract"] = True
                    if op.doc:
                        oo["documentation"] = op.doc
                    params = [node("UMLParameter", oo, name=n, type=t) if t else node("UMLParameter", oo, name=n)
                              for n, t in op.params]
                    if op.ret:
                        params.append(node("UMLParameter", oo, name="", type=op.ret, direction="return"))
                    if params:
                        oo["parameters"] = params
                    o["operations"].append(oo)
            cls_obj[k] = o
            items.append(o)
        p["ownedElements"] = items
        owned.append(p)
    for r in model.rel_order:                                   # отношения — у элемента-источника
        a, b = cls_obj[r.a], cls_obj[r.b]
        if r.kind == "assoc":
            o = node("UMLAssociation", a)
            if r.name:
                o["name"] = r.name
            e1 = node("UMLAssociationEnd", o, reference=ref(a))
            e2 = node("UMLAssociationEnd", o, reference=ref(b))
            if r.agg_a != "none":
                e1["aggregation"] = r.agg_a
            if r.nav_b:
                e2["navigable"] = "navigable"
            if r.mult_a:
                e1["multiplicity"] = r.mult_a
            if r.mult_b:
                e2["multiplicity"] = r.mult_b
            if r.role_a:
                e1["name"] = r.role_a
            if r.role_b:
                e2["name"] = r.role_b
            o["end1"], o["end2"] = e1, e2
        else:
            t = {"dep": "UMLDependency", "gen": "UMLGeneralization", "real": "UMLInterfaceRealization"}[r.kind]
            o = node(t, a, source=ref(a), target=ref(b))
            if r.stereo:
                o["stereotype"] = r.stereo
        if r.doc:
            o["documentation"] = r.doc
        a.setdefault("ownedElements", []).append(o)
        r.obj6 = o
    for d in model.diagrams:
        dg = node("UMLClassDiagram", top, name=d.name)
        dg["documentation"] = (d.doc + "\n\n" if d.doc else "") + quantitative(d)
        views, nview = [], {}
        for pk, x, y, w, h in d.pkg_boxes:
            views.append(node("UMLPackageView", dg, model=ref(pkg_obj[pk]), left=x, top=y, width=w, height=h,
                              stereotypeDisplay="label"))
        for k in d.order:
            c = model.cls[k]
            x, y, w, h = d.boxes[k]
            mode = d.nodes[k][2]
            v = node("UMLInterfaceView" if c.interface else "UMLClassView", dg, model=ref(cls_obj[k]),
                     left=x, top=y, width=w, height=h, stereotypeDisplay="label",
                     suppressAttributes=mode != "full", suppressOperations=mode != "full" or c.no_ops,
                     suppressReceptions=True)
            views.append(v)
            nview[k] = v
        for e in d.edges:
            r = e.rel
            t = {"assoc": "UMLAssociationView", "dep": "UMLDependencyView", "gen": "UMLGeneralizationView",
                 "real": "UMLInterfaceRealizationView"}[r.kind]
            v = node(t, dg, model=ref(r.obj6), tail=ref(nview[r.a]), head=ref(nview[r.b]), lineStyle=0,
                     points=_pts6(e.points))
            subs = []

            def lab(field, key, default_alpha, default_dist, pos, label_model=None):
                if key in e.labels:
                    _, al, ds, pos_, _t = e.labels[key]
                    lb = node("EdgeLabelView", v, model=ref(label_model or r.obj6), visible=True, alpha=al,
                              distance=ds, hostEdge=ref(v), edgePosition=pos_)
                else:
                    lb = node("EdgeLabelView", v, model=ref(label_model or r.obj6), visible=False,
                              alpha=default_alpha, distance=default_dist, hostEdge=ref(v), edgePosition=pos)
                v[field] = ref(lb)
                subs.append(lb)

            lab("nameLabel", "name", math.pi / 2, 15, 1)
            lab("stereotypeLabel", "stereotype", math.pi / 2, 30, 1)
            lab("propertyLabel", "property", -math.pi / 2, 15, 1)
            if r.kind == "assoc":
                e1, e2 = r.obj6["end1"], r.obj6["end2"]
                lab("tailRoleNameLabel", "tailRole", math.pi / 6, 30, 2, e1)
                lab("tailPropertyLabel", "tailProperty", math.pi / 4, 40, 2, e1)
                lab("tailMultiplicityLabel", "tailMultiplicity", -math.pi / 6, 25, 2, e1)
                lab("headRoleNameLabel", "headRole", -math.pi / 6, 30, 0, e2)
                lab("headPropertyLabel", "headProperty", -math.pi / 4, 40, 0, e2)
                lab("headMultiplicityLabel", "headMultiplicity", math.pi / 6, 25, 0, e2)
            v["subViews"] = subs
            views.append(v)
        dg["ownedViews"] = views
        owned.append(dg)
    top["ownedElements"] = owned
    return top


# ---------------------------------------------------------------- StarUML 5.0 (.uml)

def _pts5(points):
    return ";".join(f"{int(round(x))},{int(round(y))}" for x, y in points)


def _stereo5(o, name):
    o.attr("StereotypeProfile", "UMLStandard").attr("StereotypeName", name)


def _elabel(role, alpha, dist, model, visible, text=None, pos=None):
    lb = Obj("EdgeLabelView")
    if not visible:
        lb.attr("Visible", False)
    lb.attr("Alpha", float(alpha)).attr("Distance", float(dist))
    if pos:
        lb.attr("EdgePosition", pos, "EdgePositionKind")
    if text:
        lb.attr("Text", text)
    if model is not None:
        lb.ref("Model", model)
    return role, lb


def xpd_package(parent, model, container_name, container_doc):
    """UMLPackage «container_name» (Obj) с пакетами классов, отношениями и диаграммами."""
    top = Obj("UMLPackage")
    top.attr("Name", container_name).attr("Documentation", container_doc).ref("Namespace", parent)
    pkg_obj = {pk: Obj("UMLPackage") for pk in model.pkgs}
    cls_obj = {c.key: Obj("UMLInterface" if c.interface else "UMLClass") for c in model.cls_order}
    back = {k: {"Associations": [], "Generalizations": [], "Specializations": [], "ClientDependencies": [],
                "SupplierDependencies": [], "Views": []} for k in cls_obj}
    rel_obj, rel_views = {}, {}
    # отношения: объекты создаются заранее — на них ссылаются классы
    for r in model.rel_order:
        if r.kind == "assoc":
            o = Obj("UMLAssociation")
            o.ends = [Obj("UMLAssociationEnd"), Obj("UMLAssociationEnd")]
            back[r.a]["Associations"].append(o.ends[0])
            back[r.b]["Associations"].append(o.ends[1])
        elif r.kind == "gen":
            o = Obj("UMLGeneralization")
            back[r.a]["Generalizations"].append(o)
            back[r.b]["Specializations"].append(o)
        else:
            o = Obj("UMLDependency" if r.kind == "dep" else "UMLRealization")
            back[r.a]["ClientDependencies"].append(o)
            back[r.b]["SupplierDependencies"].append(o)
        rel_obj[r.key] = o
        rel_views[r.key] = []
    # диаграммы (представления создаются до записи моделей, чтобы проставить #Views)
    diagrams, pkg_views = [], {pk: [] for pk in model.pkgs}
    end_views = {}
    for d in model.diagrams:
        dg = Obj("UMLClassDiagram")
        dg.attr("Name", d.name).attr("Documentation", (d.doc + "\n\n" if d.doc else "") + quantitative(d))
        dg.ref("DiagramOwner", top)
        dv = dg.child("DiagramView", Obj("UMLClassDiagramView"))
        dv.ref("Diagram", dg)
        owned, nview = [], {}
        for pk, x, y, w, h in d.pkg_boxes:
            v = Obj("UMLPackageView")
            v.attr("Left", int(x)).attr("Top", int(y)).attr("Width", int(w)).attr("Height", int(h))
            v.ref("Model", pkg_obj[pk])
            nc = v.child("NameCompartment", Obj("UMLNameCompartmentView"))
            nc.child("NameLabel", Obj("LabelView")).attr("Text", model.pkgs[pk][0])
            nc.child("StereotypeLabel", Obj("LabelView")).attr("Visible", False)
            nc.child("PropertyLabel", Obj("LabelView")).attr("Visible", False)
            owned.append(v)
            pkg_views[pk].append(v)
        for k in d.order:
            c = model.cls[k]
            x, y, w, h = d.boxes[k]
            full = d.nodes[k][2] == "full"
            v = Obj("UMLInterfaceView" if c.interface else "UMLClassView")
            v.attr("Left", int(x)).attr("Top", int(y)).attr("Width", int(w)).attr("Height", int(h))
            v.attr("StereotypeDisplay", "sdkLabel", "UMLStereotypeDisplayKind")
            if not full:
                v.attr("SuppressAttributes", True)
            if not full or c.no_ops:
                v.attr("SuppressOperations", True)
            v.ref("Model", cls_obj[k])
            nc = v.child("NameCompartment", Obj("UMLNameCompartmentView"))
            nl = nc.child("NameLabel", Obj("LabelView"))
            nl.attr("FontStyle", 3 if c.abstract else 1).attr("Text", c.name)
            st = c.stereo_text()
            sl = nc.child("StereotypeLabel", Obj("LabelView"))
            if st:
                sl.attr("Text", f"<<{st}>>")
            else:
                sl.attr("Visible", False)
            nc.child("PropertyLabel", Obj("LabelView")).attr("Visible", False)
            ac = v.child("AttributeCompartment", Obj("UMLAttributeCompartmentView"))
            if not full:
                ac.attr("Visible", False)
            ac.ref("Model", cls_obj[k])
            oc = v.child("OperationCompartment", Obj("UMLOperationCompartmentView"))
            if not full or c.no_ops:
                oc.attr("Visible", False)
            oc.ref("Model", cls_obj[k])
            tc = v.child("TemplateParameterCompartment", Obj("UMLTemplateParameterCompartmentView"))
            tc.attr("Visible", False).ref("Model", cls_obj[k])
            owned.append(v)
            nview[k] = v
            back[k]["Views"].append(v)
        for e in d.edges:
            r = e.rel
            o = rel_obj[r.key]
            t = {"assoc": "UMLAssociationView", "dep": "UMLDependencyView", "gen": "UMLGeneralizationView",
                 "real": "UMLRealizationView"}[r.kind]
            v = Obj(t)
            v.attr("LineStyle", "lsRectilinear", "LineStyleKind").attr("Points", _pts5(e.points), "Points")
            v.ref("Model", o).ref("Head", nview[r.b]).ref("Tail", nview[r.a])
            labs = []

            def add(role, key, alpha, dist, model_obj, pos=None):
                if key in e.labels:
                    _, al, ds, _p, txt = e.labels[key]
                    labs.append(_elabel(role, al, ds, model_obj, True, txt, pos))
                else:
                    labs.append(_elabel(role, alpha, dist, model_obj, False, None, pos))

            add("NameLabel", "name", math.pi / 2, 15, o)
            stereo_txt = f"<<{r.stereo}>>" if r.stereo else None
            if "stereotype" in e.labels:
                _, al, ds, _p, _t = e.labels["stereotype"]
                labs.append(_elabel("StereotypeLabel", al, ds, o, True, stereo_txt))
            else:
                labs.append(_elabel("StereotypeLabel", math.pi / 2, 30, o, False))
            labs.append(_elabel("PropertyLabel", -math.pi / 2, 15, None, False))
            if r.kind == "assoc":
                e1, e2 = o.ends
                add("HeadRoleNameLabel", "headRole", -math.pi / 6, 30, e2, "epHead")
                add("TailRoleNameLabel", "tailRole", math.pi / 6, 30, e1, "epTail")
                add("HeadMultiplicityLabel", "headMultiplicity", math.pi / 6, 25, e2, "epHead")
                add("TailMultiplicityLabel", "tailMultiplicity", -math.pi / 6, 25, e1, "epTail")
                add("HeadPropertyLabel", "headProperty", -math.pi / 4, 40, e2, "epHead")
                add("TailPropertyLabel", "tailProperty", math.pi / 4, 40, e1, "epTail")
                for role, end in (("HeadQualifierCompartment", e2), ("TailQualifierCompartment", e1)):
                    q = Obj("UMLQualifierCompartmentView")
                    q.attr("Visible", False).attr("Left", -1000).attr("Top", -1000).attr("Width", 50).attr("Height", 8)
                    q.ref("Model", end)
                    labs.append((role, q))
                    end_views.setdefault(id(end), []).append(q)
            for role, lb in labs:
                v.child(role, lb)
                if r.kind == "assoc" and role.startswith(("Head", "Tail")) and not role.endswith("Compartment"):
                    end = o.ends[1] if role.startswith("Head") else o.ends[0]
                    end_views.setdefault(id(end), []).append(lb)
            rel_views[r.key].append(v)
            rel_views[r.key] += [lb for role, lb in labs if role in ("NameLabel", "StereotypeLabel")]
            owned.append(v)
        dv.children("OwnedViews", owned)
        diagrams.append(dg)
    # отношения: владелец — пакет класса-источника
    rel_by_pkg = {pk: [] for pk in model.pkgs}
    for r in model.rel_order:
        o = rel_obj[r.key]
        owner = pkg_obj[model.cls[r.a].pkg]
        if r.name:
            o.attr("Name", r.name)
        if r.doc:
            o.attr("Documentation", r.doc)
        if r.stereo:
            _stereo5(o, r.stereo)
        o.ref("Namespace", owner)
        o.refs("Views", rel_views[r.key])
        if r.kind == "assoc":
            for i, end in enumerate(o.ends):
                cls_key, mult, role = (r.a, r.mult_a, r.role_a) if i == 0 else (r.b, r.mult_b, r.role_b)
                if role:
                    end.attr("Name", role)
                if i == 0 and r.agg_a != "none":
                    end.attr("Aggregation", AGG5[r.agg_a], "UMLAggregationKind")
                if mult:
                    end.attr("Multiplicity", mult)
                if i == 0 and r.nav_b:                     # стрелка только к навигируемому концу
                    end.attr("IsNavigable", False)
                end.ref("Association", o).ref("Participant", cls_obj[cls_key])
                end.refs("Views", end_views.get(id(end), []))
            o.children("Connections", o.ends)
        elif r.kind == "gen":
            o.ref("Child", cls_obj[r.a]).ref("Parent", cls_obj[r.b])
        else:
            o.ref("Client", cls_obj[r.a]).ref("Supplier", cls_obj[r.b])
        rel_by_pkg[model.cls[r.a].pkg].append(o)
    # модель: классы
    for pk, (pname, pdoc, keys) in model.pkgs.items():
        p = pkg_obj[pk]
        p.attr("Name", pname)
        if pdoc:
            p.attr("Documentation", pdoc)
        p.ref("Namespace", top)
        p.refs("Views", pkg_views[pk])
        items = []
        for k in keys:
            c, o = model.cls[k], cls_obj[k]
            o.attr("Name", c.name)
            if c.doc:
                o.attr("Documentation", c.doc)
            if not c.interface and c.stereo_text():
                _stereo5(o, c.stereo_text())
            if c.abstract:
                o.attr("IsAbstract", True)
            o.ref("Namespace", p)
            o.refs("Views", back[k]["Views"])
            for name in ("Generalizations", "Specializations", "ClientDependencies", "SupplierDependencies",
                         "Associations"):
                o.refs(name, back[k][name])
            ops = []
            for op in c.ops:
                oo = Obj("UMLOperation")
                oo.attr("Name", op.name).attr("Visibility", VIS5[op.vis], "UMLVisibilityKind")
                if op.abstract:
                    oo.attr("IsAbstract", True)
                if op.doc:
                    oo.attr("Documentation", op.doc)
                oo.ref("Owner", o)
                params = []
                for n, t in op.params:
                    po = Obj("UMLParameter")
                    po.attr("Name", n)
                    if t:
                        po.attr("TypeExpression", t)
                    po.ref("BehavioralFeature", oo)
                    params.append(po)
                if op.ret:
                    po = Obj("UMLParameter")
                    po.attr("DirectionKind", "pdkReturn", "UMLParameterDirectionKind").attr("TypeExpression", op.ret)
                    po.ref("BehavioralFeature", oo)
                    params.append(po)
                oo.children("Parameters", params)
                ops.append(oo)
            o.children("Operations", ops)
            ats = []
            for a in c.attrs:
                ao = Obj("UMLAttribute")
                ao.attr("Name", a.name).attr("Visibility", VIS5[a.vis], "UMLVisibilityKind")
                if a.type:
                    ao.attr("TypeExpression", a.type)
                if a.default:
                    ao.attr("InitialValue", a.default)
                if a.read_only:
                    ao.attr("Changeability", "ckFrozen", "UMLChangeableKind")
                if a.doc:
                    ao.attr("Documentation", a.doc)
                ao.ref("Owner", o)
                ats.append(ao)
            o.children("Attributes", ats)
            items.append(o)
        p.children("OwnedElements", items + rel_by_pkg[pk])
    top.children("OwnedElements", [pkg_obj[pk] for pk in model.pkgs])
    top.children("OwnedDiagrams", diagrams)
    return top
