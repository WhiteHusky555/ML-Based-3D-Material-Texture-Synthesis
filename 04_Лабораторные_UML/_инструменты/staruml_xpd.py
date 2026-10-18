"""Генератор проектов StarUML 5.0 (.uml, формат XPD) для диаграмм вариантов использования.

Формат восстановлен по примерам моделей и исходникам StarUML 5.0 из раздаточного
архива кафедры (Samples/*.uml, src/UMLModels.pas, src/UMLViews.pas, src/Core.pas):
  - элемент модели хранит ссылки на свои представления (#Views) и обратные ссылки
    отношений (#Associations, #Includes/#Includers, #Extends/#Extenders,
    #Generalizations/#Specializations);
  - представление ребра хранит Head/Tail (представления концов) и Points;
  - у include: Base/Addition, Head = представление Addition;
  - у extend: Base/Extension/Condition/ExtensionPoints, Head = представление Base;
  - у обобщения: Child/Parent, Head = представление Parent;
  - у ассоциации: Connections[0] = Tail, Connections[1] = Head, IsNavigable=False
    на ненавигируемом конце (стрелка рисуется к навигируемому).
"""
import base64
import math
import uuid
from xml.sax.saxutils import escape

PI2 = 1.5707963267949


def new_guid():
    return base64.b64encode(uuid.uuid4().bytes + b"\x00\x00").decode()


class Obj:
    """Узел XPD: атрибуты, ссылки и вложенные объекты в порядке добавления."""

    def __init__(self, type_):
        self.type = type_
        self.guid = new_guid()
        self.items = []

    def attr(self, name, value, typ=None):
        if typ is None:
            typ = ("boolean" if isinstance(value, bool) else "integer" if isinstance(value, int)
                   else "real" if isinstance(value, float) else "string")
        self.items.append(("attr", name, typ, value))
        return self

    def ref(self, name, target):
        self.items.append(("ref", name, target))
        return self

    def child(self, name, obj):
        self.items.append(("obj", name, obj))
        return obj

    def refs(self, name, targets):
        if targets:
            self.attr("#" + name, len(targets))
            for i, t in enumerate(targets):
                self.ref(f"{name}[{i}]", t)

    def children(self, name, objs):
        if objs:
            self.attr("#" + name, len(objs))
            for i, o in enumerate(objs):
                self.child(f"{name}[{i}]", o)

    def write(self, out, role):
        out.append(f'<XPD:OBJ name="{role}" type="{self.type}" guid="{self.guid}">')
        for it in self.items:
            if it[0] == "attr":
                _, n, t, v = it
                if isinstance(v, bool):
                    v = "True" if v else "False"
                out.append(f'<XPD:ATTR name="{n}" type="{t}">{escape(str(v))}</XPD:ATTR>')
            elif it[0] == "ref":
                _, n, t = it
                g = t.guid if isinstance(t, Obj) else t
                out.append(f'<XPD:REF name="{n}">{g}</XPD:REF>')
            else:
                _, n, o = it
                o.write(out, n)
        out.append("</XPD:OBJ>")


# ---------------------------------------------------------------- элементы модели

class Element:
    def __init__(self, kind, key, name, doc=""):
        self.kind, self.key, self.name, self.doc = kind, key, name, doc
        self.obj = Obj({"actor": "UMLActor", "worker": "UMLClass", "usecase": "UMLUseCase"}[kind])
        self.views = []
        self.assoc_ends = []
        self.includes, self.includers = [], []
        self.extends, self.extenders = [], []
        self.generalizations, self.specializations = [], []
        self.ext_points = []      # [(name, Obj)]
        self.attachments = []


class Relation:
    def __init__(self, kind, key, a, b, doc=""):
        self.kind, self.key, self.a, self.b, self.doc = kind, key, a, b, doc
        self.obj = Obj({"assoc": "UMLAssociation", "include": "UMLInclude",
                        "extend": "UMLExtend", "general": "UMLGeneralization"}[kind])
        self.views = []
        self.directed = False
        self.point = None
        self.condition = ""
        if kind == "assoc":
            self.ends = [Obj("UMLAssociationEnd"), Obj("UMLAssociationEnd")]
            self.end_views = [[], []]


# ---------------------------------------------------------------- геометрия

LINE_H = 16          # высота строки Arial 13 px в StarUML
EXT_ITEM_H = 18      # строка отсека (текст + интервал 2)


def char_w(ch):
    if ch == " ":
        return 3.6
    if ch in "«»()[].,:;/|'!":
        return 4.0
    if ch.isdigit():
        return 7.2
    if ch.isupper():
        return 8.6
    if "a" <= ch <= "z":
        return 6.6
    return 7.1


def text_w(s):
    return sum(char_w(c) for c in s)


def wrap(text, width):
    lines = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split(" "):
            cand = (cur + " " + word).strip()
            if text_w(cand) <= width or not cur:
                cur = cand
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
    return lines


def uc_layout(name, n_ext, width, ell_h=None):
    """Размеры представления прецедента по правилам StarUML 6: эллипс с названием
    (название переносится по ширине width/sqrt2), под ним — отсек точек расширения.
    Возвращает (высота эллипса, полная высота)."""
    lines = wrap(name, width / math.sqrt(2) - 10)
    name_h = LINE_H * len(lines) + 10
    min_ell = max(int(math.sqrt(2) * name_h), 40)
    ell = max(ell_h or 0, min_ell)
    total = ell + (5 + 10 + EXT_ITEM_H * n_ext - 2 if n_ext else 0)
    return ell, total


def clip(box, shape, toward, ell_h=None):
    """Точка на границе узла в направлении toward.
    shape: "ellipse" | "rect" | "ucx" (эллипс высотой ell_h + прямоугольный отсек под ним)."""
    x, y, w, h = box
    if shape == "ucx":
        cx, cy = x + w / 2, y + ell_h / 2
        dx, dy = toward[0] - cx, toward[1] - cy
        if dx == 0 and dy == 0:
            return cx, cy
        k = 1 / math.sqrt((dx / (w / 2)) ** 2 + (dy / (ell_h / 2)) ** 2)
        comp_top, bottom = y + ell_h + 5, y + h
        if dy > 0:
            t_top = (comp_top - cy) / dy
            x_at = cx + dx * t_top
            if x <= x_at <= x + w and t_top >= 0:
                kb = (bottom - cy) / dy
                ks = ((w / 2) / abs(dx)) if dx else 1e9
                k = max(k, min(kb, ks))
        return cx + dx * k, cy + dy * k
    cx, cy = x + w / 2, y + h / 2
    dx, dy = toward[0] - cx, toward[1] - cy
    if dx == 0 and dy == 0:
        return cx, cy
    if shape == "ellipse":
        k = 1 / math.sqrt((dx / (w / 2)) ** 2 + (dy / (h / 2)) ** 2)
    else:
        k = min((w / 2) / abs(dx) if dx else 1e9, (h / 2) / abs(dy) if dy else 1e9)
    return cx + dx * k, cy + dy * k


def label_pos(p_tail, p_head, alpha, distance):
    """Центр подписи ребра по формуле StarUML (Coord.getPointAwayLine) для двухточечного ребра."""
    mx, my = math.floor((p_tail[0] + p_head[0]) / 2), math.floor((p_tail[1] + p_head[1]) / 2)
    a, b = mx - p_head[0], my - p_head[1]
    th = math.atan(abs(b) / (abs(a) + 0.000001))
    if a > 0:
        th = math.pi - th if b > 0 else th + math.pi
    elif b < 0:
        th = 2 * math.pi - th
    return mx + math.floor(distance * math.cos(th + alpha)), my + math.floor(-distance * math.sin(th + alpha))


def _label(name, alpha, dist, model=None, visible=True, text=None, pos=None):
    o = Obj("EdgeLabelView")
    if not visible:
        o.attr("Visible", False)
    o.attr("Alpha", float(alpha)).attr("Distance", float(dist))
    if pos:
        o.attr("EdgePosition", pos, "EdgePositionKind")
    if text:
        o.attr("Text", text)
    if model is not None:
        o.ref("Model", model)
    return name, o


def _name_compartment(text, bold=True):
    nc = Obj("UMLNameCompartmentView")
    nl = nc.child("NameLabel", Obj("LabelView"))
    if bold:
        nl.attr("FontStyle", 1)
    nl.attr("Text", text)
    nc.child("StereotypeLabel", Obj("LabelView")).attr("Visible", False)
    nc.child("PropertyLabel", Obj("LabelView")).attr("Visible", False)
    return nc


# ---------------------------------------------------------------- диаграмма

class UseCaseDiagram:
    def __init__(self, pkg, name, doc):
        self.pkg, self.name, self.doc = pkg, name, doc
        self.obj = Obj("UMLUseCaseDiagram")
        self.view = Obj("UMLUseCaseDiagramView")
        self.owned = []
        self.node_view = {}    # key -> (Obj, box, shape)
        self.notes = {}        # key -> (Obj, box)
        self.counts = {"actors": set(), "usecases": set(), "edges": 0}

    # -- узлы
    def _box_view(self, el, view, box):
        x, y, w, h = (int(round(v)) for v in box)
        view.attr("Left", x).attr("Top", y).attr("Width", w).attr("Height", h)
        return (x, y, w, h)

    def uc(self, key, cx, cy, w, ell_h=None):
        """cx, cy — центр эллипса; высота эллипса и отсека точек расширения считаются по содержимому."""
        el = self.pkg.el[key]
        ell, total = uc_layout(el.name, len(el.ext_points), w, ell_h)
        v = Obj("UMLUseCaseView")
        box = self._box_view(el, v, (cx - w / 2, cy - ell / 2, w, total))
        v.attr("WordWrap", True)
        v.attr("StereotypeDisplay", "sdkIcon", "UMLStereotypeDisplayKind")
        v.ref("Model", el.obj)
        v.child("NameCompartment", _name_compartment(el.name))
        ac = v.child("AttributeCompartment", Obj("UMLAttributeCompartmentView"))
        ac.attr("Visible", False).ref("Model", el.obj)
        oc = v.child("OperationCompartment", Obj("UMLOperationCompartmentView"))
        oc.attr("Visible", False).ref("Model", el.obj)
        ep = v.child("ExtensionPointCompartment", Obj("UMLExtensionPointCompartmentView"))
        if el.ext_points:
            ep.ref("Model", el.obj)
            el.views += [v, ac, oc, ep]
        else:
            ep.attr("Visible", False)
            el.views += [v, ac, oc]
        self.owned.append(v)
        self.node_view[key] = (v, box, "ucx" if el.ext_points else "ellipse", ell)
        self.counts["usecases"].add(key)

    def actor(self, key, cx, cy):
        el = self.pkg.el[key]
        if el.kind == "worker":
            v = Obj("UMLClassView")
            w, h = 64, 74
            box = self._box_view(el, v, (cx - w / 2, cy - h / 2, w, h))
            v.attr("StereotypeDisplay", "sdkIcon", "UMLStereotypeDisplayKind")
            v.attr("SuppressAttributes", True).attr("SuppressOperations", True)
            v.ref("Model", el.obj)
            nc = _name_compartment(el.name)
            v.child("NameCompartment", nc)
            comps = []
            for nm, ty in (("AttributeCompartment", "UMLAttributeCompartmentView"),
                           ("OperationCompartment", "UMLOperationCompartmentView"),
                           ("TemplateParameterCompartment", "UMLTemplateParameterCompartmentView")):
                c = v.child(nm, Obj(ty))
                c.attr("Visible", False).ref("Model", el.obj)
                comps.append(c)
            el.views += [v] + comps
            shape = "rect"
        else:
            v = Obj("UMLActorView")
            w, h = 40, 90
            box = self._box_view(el, v, (cx - w / 2, cy - h / 2, w, h))
            v.ref("Model", el.obj)
            v.child("NameCompartment", _name_compartment(el.name))
            ac = v.child("AttributeCompartment", Obj("UMLAttributeCompartmentView"))
            ac.attr("Visible", False).ref("Model", el.obj)
            oc = v.child("OperationCompartment", Obj("UMLOperationCompartmentView"))
            oc.attr("Visible", False).ref("Model", el.obj)
            el.views += [v, ac, oc]
            shape = "rect"
        self.owned.append(v)
        self.node_view[key] = (v, box, shape, None)
        self.counts["actors"].add(key)

    def boundary(self, caption, x, y, w, h):
        v = Obj("UMLSystemBoundaryView")
        v.attr("LineColor", "clGray")
        v.attr("Left", int(x)).attr("Top", int(y)).attr("Width", int(w)).attr("Height", int(h))
        v.attr("Caption", caption)
        self.owned.insert(0, v)

    def note(self, nkey, text, x, y, w, h):
        v = Obj("UMLNoteView")
        v.attr("Left", int(x)).attr("Top", int(y)).attr("Width", int(w)).attr("Height", int(h))
        v.attr("Text", text)
        self.owned.append(v)
        self.notes[nkey] = (v, (int(x), int(y), int(w), int(h)))

    def text(self, text, x, y, w, h):
        v = Obj("UMLTextView")
        v.attr("Left", int(x)).attr("Top", int(y)).attr("Width", int(w)).attr("Height", int(h))
        v.attr("Text", text)
        self.owned.append(v)

    # -- рёбра
    def _center(self, key):
        v, b, s, ell = self.node_view[key]
        return (b[0] + b[2] / 2, b[1] + (ell / 2 if s == "ucx" else b[3] / 2))

    def _points(self, ka, kb):
        va, ba, sa, ea = self.node_view[ka]
        vb, bb, sb, eb = self.node_view[kb]
        p1, p2 = clip(ba, sa, self._center(kb), ea), clip(bb, sb, self._center(ka), eb)
        return va, vb, p1, p2

    @staticmethod
    def _pts(p1, p2):
        return f"{int(round(p1[0]))},{int(round(p1[1]))};{int(round(p2[0]))},{int(round(p2[1]))}"

    def edge(self, rkey, label_at=None, label_size=(170, 60)):
        """Ребро отношения. Для extend label_at=(dx, dy) — смещение текстовой подписи
        «(точка) [условие]» от середины ребра."""
        r = self.pkg.rel[rkey]
        self.counts["edges"] += 1
        if r.kind == "assoc":
            # tail = a (конец 0), head = b (конец 1)
            vt, vh, p1, p2 = self._points(r.a, r.b)
            v = Obj("UMLAssociationView")
            v.attr("Points", self._pts(p1, p2), "Points")
            v.ref("Model", r.obj).ref("Head", vh).ref("Tail", vt)
            labels = [_label("NameLabel", PI2, 15, r.obj, False),
                      _label("StereotypeLabel", PI2, 30, r.obj, False),
                      _label("PropertyLabel", -PI2, 15, r.obj, False)]
            e0, e1 = r.ends
            end_labels = [_label("HeadRoleNameLabel", -0.523598775598299, 30, e1, False, pos="epHead"),
                          _label("TailRoleNameLabel", 0.523598775598299, 30, e0, False, pos="epTail"),
                          _label("HeadMultiplicityLabel", 0.523598775598299, 25, e1, False, pos="epHead"),
                          _label("TailMultiplicityLabel", -0.523598775598299, 25, e0, False, pos="epTail"),
                          _label("HeadPropertyLabel", -0.785398163397448, 40, e1, False, pos="epHead"),
                          _label("TailPropertyLabel", 0.785398163397448, 40, e0, False, pos="epTail")]
            for n, o in labels + end_labels:
                v.child(n, o)
            q = {}
            for nm, end in (("HeadQualifierCompartment", e1), ("TailQualifierCompartment", e0)):
                c = v.child(nm, Obj("UMLQualifierCompartmentView"))
                c.attr("Visible", False).attr("Left", -1000).attr("Top", -1000).attr("Width", 50).attr("Height", 8)
                c.ref("Model", end)
                q[nm] = c
            r.views += [v] + [o for _, o in labels]
            r.end_views[1] += [end_labels[0][1], end_labels[2][1], end_labels[4][1], q["HeadQualifierCompartment"]]
            r.end_views[0] += [end_labels[1][1], end_labels[3][1], end_labels[5][1], q["TailQualifierCompartment"]]
            self.owned.append(v)
            return
        if r.kind == "include":       # a = base (tail), b = addition (head)
            vt, vh, p1, p2 = self._points(r.a, r.b)
            v = Obj("UMLIncludeView")
            st = _label("StereotypeLabel", PI2, 30, r.obj, True, text="<<include>>")
        elif r.kind == "extend":      # a = base (head), b = extension (tail)
            vt, vh, p1, p2 = self._points(r.b, r.a)
            v = Obj("UMLExtendView")
            st = _label("StereotypeLabel", PI2, 30, r.obj, False, text="<<extend>>")
        else:                         # general: a = child (tail), b = parent (head)
            vt, vh, p1, p2 = self._points(r.a, r.b)
            v = Obj("UMLGeneralizationView")
            st = _label("StereotypeLabel", PI2, 30, r.obj, False)
        v.attr("Points", self._pts(p1, p2), "Points")
        v.ref("Model", r.obj).ref("Head", vh).ref("Tail", vt)
        labels = [_label("NameLabel", PI2, 15, r.obj, False), st, _label("PropertyLabel", -PI2, 15, r.obj, False)]
        for n, o in labels:
            v.child(n, o)
        r.views += [v] + [o for _, o in labels]
        self.owned.append(v)
        if r.kind == "extend" and label_at is not None:
            mx, my = label_at
            w, h = label_size
            lines = ["«extend»", f"({r.point})"] + [f"[{r.condition}]"]
            self.text("\n".join(lines), mx - w / 2, my - h / 2, w, h)

    def notelink(self, nkey, target_key):
        nv, nb = self.notes[nkey]
        tv, tb, ts, te = self.node_view[target_key]
        cn = (nb[0] + nb[2] / 2, nb[1] + nb[3] / 2)
        p1, p2 = clip(nb, "rect", self._center(target_key)), clip(tb, ts, cn, te)
        v = Obj("UMLNoteLinkView")
        v.attr("Points", self._pts(p1, p2), "Points")
        v.ref("Head", tv).ref("Tail", nv)
        self.owned.append(v)

    def quantitative(self):
        a, u, e = len(self.counts["actors"]), len(self.counts["usecases"]), self.counts["edges"]
        return (f"Количественная характеристика диаграммы: акторов и работников — {a}; "
                f"прецедентов — {u}; дуг (отношений) — {e}.")


# ---------------------------------------------------------------- пакет модели

class UseCaseModel:
    def __init__(self, name, doc=""):
        self.name, self.doc = name, doc
        self.obj = Obj("UMLModel")
        self.el, self.rel = {}, {}
        self.order_el, self.order_rel = [], []
        self.diagrams = []

    def _add_el(self, kind, key, name, doc):
        e = Element(kind, key, name, doc)
        self.el[key] = e
        self.order_el.append(e)
        return e

    def actor(self, key, name, doc=""):
        return self._add_el("actor", key, name, doc)

    def worker(self, key, name, doc=""):
        return self._add_el("worker", key, name, doc)

    def usecase(self, key, name, doc="", ext_points=()):
        e = self._add_el("usecase", key, name, doc)
        for p in ext_points:
            e.ext_points.append((p, Obj("UMLExtensionPoint")))
        return e

    def _add_rel(self, kind, a, b, doc):
        key = f"{kind}:{a}->{b}"
        r = Relation(kind, key, a, b, doc)
        self.rel[key] = r
        self.order_rel.append(r)
        return r

    def assoc(self, a, b, directed=False, doc=""):
        r = self._add_rel("assoc", a, b, doc)
        r.directed = directed
        self.el[a].assoc_ends.append(r.ends[0])
        self.el[b].assoc_ends.append(r.ends[1])
        return r.key

    def include(self, base, addition, doc=""):
        r = self._add_rel("include", base, addition, doc)
        self.el[base].includes.append(r.obj)
        self.el[addition].includers.append(r.obj)
        return r.key

    def extend(self, base, extension, point, condition, doc=""):
        r = self._add_rel("extend", base, extension, doc)
        r.point, r.condition = point, condition
        self.el[base].extenders.append(r.obj)
        self.el[extension].extends.append(r.obj)
        return r.key

    def general(self, child, parent, doc=""):
        r = self._add_rel("general", child, parent, doc)
        self.el[child].generalizations.append(r.obj)
        self.el[parent].specializations.append(r.obj)
        return r.key

    def diagram(self, name, doc=""):
        d = UseCaseDiagram(self, name, doc)
        self.diagrams.append(d)
        return d

    # -- сборка XPD
    def build(self, project_obj):
        m = self.obj
        m.attr("Name", self.name)
        if self.doc:
            m.attr("Documentation", self.doc)
        m.ref("Namespace", project_obj)
        owned = []
        for e in self.order_el:
            o = e.obj
            o.attr("Name", e.name)
            if e.doc:
                o.attr("Documentation", e.doc)
            if e.attachments:
                o.attr("Attachments", "\n".join(e.attachments) + "\n")
            if e.kind == "worker":
                o.attr("StereotypeProfile", "UMLStandard").attr("StereotypeName", "worker")
            o.ref("Namespace", m)
            o.refs("Views", e.views)
            eps = []
            for pname, po in e.ext_points:
                po.attr("Name", pname)
                po.ref("UseCase", o)
                exts = [r.obj for r in self.order_rel if r.kind == "extend" and r.a == e.key and r.point == pname]
                po.refs("Extends", exts)
                eps.append(po)
            o.children("ExtensionPoints", eps)
            o.refs("Generalizations", e.generalizations)
            o.refs("Specializations", e.specializations)
            o.refs("Includes", e.includes)
            o.refs("Includers", e.includers)
            o.refs("Extends", e.extends)
            o.refs("Extenders", e.extenders)
            o.refs("Associations", e.assoc_ends)
            owned.append(o)
        for r in self.order_rel:
            o = r.obj
            if r.doc:
                o.attr("Documentation", r.doc)
            o.ref("Namespace", m)
            if r.kind == "assoc":
                o.refs("Views", r.views)
                e0, e1 = r.ends
                if r.directed:
                    e0.attr("IsNavigable", False)
                e0.ref("Association", o).ref("Participant", self.el[r.a].obj)
                e0.refs("Views", r.end_views[0])
                e1.ref("Association", o).ref("Participant", self.el[r.b].obj)
                e1.refs("Views", r.end_views[1])
                o.children("Connections", [e0, e1])
            elif r.kind == "include":
                o.ref("Addition", self.el[r.b].obj).ref("Base", self.el[r.a].obj)
                o.refs("Views", r.views)
            elif r.kind == "extend":
                o.attr("Condition", r.condition)
                o.ref("Base", self.el[r.a].obj).ref("Extension", self.el[r.b].obj)
                point_obj = [po for pn, po in self.el[r.a].ext_points if pn == r.point]
                o.refs("ExtensionPoints", point_obj)
                o.refs("Views", r.views)
            else:
                o.ref("Child", self.el[r.a].obj).ref("Parent", self.el[r.b].obj)
                o.refs("Views", r.views)
            owned.append(o)
        m.children("OwnedElements", owned)
        diags = []
        for d in self.diagrams:
            d.obj.attr("Name", d.name)
            doc = (d.doc + "\n\n" if d.doc else "") + d.quantitative()
            d.obj.attr("Documentation", doc)
            d.obj.ref("DiagramOwner", m)
            dv = d.obj.child("DiagramView", d.view)
            dv.ref("Diagram", d.obj)
            dv.children("OwnedViews", d.owned)
            diags.append(d.obj)
        m.children("OwnedDiagrams", diags)


class Project:
    def __init__(self, title, author="", doc=""):
        self.obj = Obj("UMLProject")
        self.title, self.author, self.doc = title, author, doc
        self.models = []

    def add(self, model):
        self.models.append(model)
        return model

    def empty_model(self, name):
        m = Obj("UMLModel")
        m.attr("Name", name).ref("Namespace", self.obj)
        self.models.append(m)
        return m

    def save(self, path):
        p = self.obj
        if self.doc:
            p.attr("Documentation", self.doc)
        p.attr("Title", self.title)
        if self.author:
            p.attr("Author", self.author)
        owned = []
        for m in self.models:
            if isinstance(m, UseCaseModel):
                m.build(p)
                owned.append(m.obj)
            else:
                owned.append(m)
        p.children("OwnedElements", owned)
        out = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<XPD:PROJECT xmlns:XPD="http://www.plasticsoftware.com/products/plastic" version="1">',
               "<XPD:HEADER>", "<XPD:SUBUNITS>", "</XPD:SUBUNITS>",
               "<XPD:PROFILES>", "<XPD:PROFILE>UMLStandard</XPD:PROFILE>", "</XPD:PROFILES>",
               "</XPD:HEADER>", "<XPD:BODY>"]
        p.write(out, "DocumentElement")
        out += ["</XPD:BODY>", "</XPD:PROJECT>", ""]
        with open(path, "w", encoding="utf-8", newline="\r\n") as f:
            f.write("\n".join(out))
