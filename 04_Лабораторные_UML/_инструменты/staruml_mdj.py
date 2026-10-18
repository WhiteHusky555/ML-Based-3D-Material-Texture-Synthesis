"""Генератор проектов StarUML 6.x (.mdj, JSON) для диаграмм вариантов использования.

Интерфейс совпадает с staruml_xpd.py (StarUML 5.0), поэтому одна и та же модель
собирается в оба формата. Формат сверен с метамоделью и кодом StarUML 6.3.3
(extensions/essential/uml/metamodel.json, elements.js, src/core/core.js):
  - представления создают вложенные подписи и отсеки в конструкторе; загрузчик
    сохраняет их, если в JSON их нет, поэтому в файле достаточно самих представлений;
  - отношения хранятся в ownedElements элемента-источника;
  - include: source = базовый, target = включаемый; extend: source = расширяющий,
    target = базовый, extensionLocations -> точки расширения базового;
  - ассоциация: end1 = tail, end2 = head; navigable="navigable" рисует стрелку;
  - точки ребра: "x:y;x:y".
"""
import base64
import json
import uuid

from staruml_xpd import clip, uc_layout

# EdgeView.lineStyle: без явного значения загрузчик берёт умолчание метамодели 0 (прямоугольные изломы)
RECTILINEAR, OBLIQUE = 0, 1


def new_id():
    return base64.b64encode(uuid.uuid4().bytes[:14]).decode()


def ref(obj):
    return {"$ref": obj["_id"]}


def node(type_, parent, **fields):
    o = {"_type": type_, "_id": new_id(), "_parent": ref(parent)}
    o.update(fields)
    return o


class Element:
    def __init__(self, kind, key, name, doc, parent):
        self.kind, self.key, self.name = kind, key, name
        t = {"actor": "UMLActor", "worker": "UMLClass", "usecase": "UMLUseCase"}[kind]
        self.obj = node(t, parent, name=name)
        if doc:
            self.obj["documentation"] = doc
        if kind == "worker":
            self.obj["stereotype"] = "worker"
        self.ext_points = {}


class Relation:
    def __init__(self, kind, key, a, b):
        self.kind, self.key, self.a, self.b = kind, key, a, b
        self.obj = None
        self.point = None
        self.condition = ""


class UseCaseDiagram:
    def __init__(self, pkg, name, doc):
        self.pkg, self.name, self.doc = pkg, name, doc
        self.obj = node("UMLUseCaseDiagram", pkg.obj, name=name)
        self.views = []
        self.node_view = {}
        self.notes = {}
        self.counts = {"actors": set(), "usecases": set(), "edges": 0}

    def _view(self, type_, **fields):
        v = node(type_, self.obj, **fields)
        self.views.append(v)
        return v

    def uc(self, key, cx, cy, w, ell_h=None):
        """cx, cy — центр эллипса; высота эллипса и отсека точек расширения считаются по содержимому."""
        el = self.pkg.el[key]
        ell, total = uc_layout(el.name, len(el.ext_points), w, ell_h)
        box = (int(round(cx - w / 2)), int(round(cy - ell / 2)), int(round(w)), int(round(total)))
        v = self._view("UMLUseCaseView", model=ref(el.obj), left=box[0], top=box[1], width=box[2], height=box[3],
                       wordWrap=True, suppressAttributes=True, suppressOperations=True, suppressReceptions=True)
        self.node_view[key] = (v, box, "ucx" if el.ext_points else "ellipse", ell)
        self.counts["usecases"].add(key)

    def actor(self, key, cx, cy):
        el = self.pkg.el[key]
        if el.kind == "worker":
            w, h = 130, 48
            box = (int(cx - w / 2), int(cy - h / 2), w, h)
            v = self._view("UMLClassView", model=ref(el.obj), left=box[0], top=box[1], width=w, height=h,
                           suppressAttributes=True, suppressOperations=True, suppressReceptions=True,
                           stereotypeDisplay="label")
        else:
            w, h = 40, 90
            box = (int(cx - w / 2), int(cy - h / 2), w, h)
            v = self._view("UMLActorView", model=ref(el.obj), left=box[0], top=box[1], width=w, height=h,
                           suppressAttributes=True, suppressOperations=True, suppressReceptions=True)
        self.node_view[key] = (v, box, "rect", None)
        self.counts["actors"].add(key)

    def boundary(self, caption, x, y, w, h):
        subj = node("UMLUseCaseSubject", self.pkg.obj, name=caption)
        self.pkg.extra.append(subj)
        v = node("UMLUseCaseSubjectView", self.obj, model=ref(subj), left=int(x), top=int(y), width=int(w), height=int(h))
        self.views.insert(0, v)

    def note(self, nkey, text, x, y, w, h):
        v = self._view("UMLNoteView", text=text, left=int(x), top=int(y), width=int(w), height=int(h))
        self.notes[nkey] = (v, (int(x), int(y), int(w), int(h)))

    def text(self, text, x, y, w, h):
        # horzAlign 2 = по центру, vertAlign 5 = по середине (Canvas.AL_CENTER / AL_MIDDLE)
        self._view("UMLTextView", text=text, left=int(x), top=int(y), width=int(w), height=int(h),
                   horzAlign=2, vertAlign=5)

    def _center(self, key):
        v, b, s, ell = self.node_view[key]
        return (b[0] + b[2] / 2, b[1] + (ell / 2 if s == "ucx" else b[3] / 2))

    def _ends(self, ka, kb):
        va, ba, sa, ea = self.node_view[ka]
        vb, bb, sb, eb = self.node_view[kb]
        return va, vb, clip(ba, sa, self._center(kb), ea), clip(bb, sb, self._center(ka), eb)

    @staticmethod
    def _pts(p1, p2):
        return f"{int(round(p1[0]))}:{int(round(p1[1]))};{int(round(p2[0]))}:{int(round(p2[1]))}"

    def edge(self, rkey, label_at=None, label_size=(170, 60)):
        r = self.pkg.rel[rkey]
        self.counts["edges"] += 1
        types = {"assoc": "UMLAssociationView", "include": "UMLIncludeView",
                 "extend": "UMLExtendView", "general": "UMLGeneralizationView"}
        if r.kind == "extend":
            tail, head = r.b, r.a          # расширяющий -> базовый
        else:
            tail, head = r.a, r.b
        vt, vh, p1, p2 = self._ends(tail, head)
        extra = {"stereotypeDisplay": "none"} if r.kind == "extend" else {}
        self._view(types[r.kind], model=ref(r.obj), tail=ref(vt), head=ref(vh), points=self._pts(p1, p2),
                   lineStyle=OBLIQUE, **extra)
        if r.kind == "extend" and label_at is not None:
            mx, my = label_at
            w, h = label_size
            self.text(f"«extend»\n({r.point})\n[{r.condition}]", mx - w / 2, my - h / 2, w, h)

    def notelink(self, nkey, target_key):
        nv, nb = self.notes[nkey]
        tv, tb, ts, te = self.node_view[target_key]
        cn = (nb[0] + nb[2] / 2, nb[1] + nb[3] / 2)
        p1, p2 = clip(nb, "rect", self._center(target_key)), clip(tb, ts, cn, te)
        self._view("UMLNoteLinkView", tail=ref(nv), head=ref(tv), points=self._pts(p1, p2), lineStyle=OBLIQUE)

    def quantitative(self):
        a, u, e = len(self.counts["actors"]), len(self.counts["usecases"]), self.counts["edges"]
        return (f"Количественная характеристика диаграммы: акторов и работников — {a}; "
                f"прецедентов — {u}; дуг (отношений) — {e}.")


class UseCaseModel:
    def __init__(self, name, doc=""):
        self.name, self.doc = name, doc
        self.obj = None
        self._pending = []
        self.el, self.rel = {}, {}
        self.order_el, self.order_rel = [], []
        self.diagrams = []
        self.extra = []

    def bind(self, project_obj):
        self.obj = node("UMLModel", project_obj, name=self.name)
        if self.doc:
            self.obj["documentation"] = self.doc

    def actor(self, key, name, doc=""):
        return self._add("actor", key, name, doc)

    def worker(self, key, name, doc=""):
        return self._add("worker", key, name, doc)

    def usecase(self, key, name, doc="", ext_points=()):
        e = self._add("usecase", key, name, doc)
        if ext_points:
            e.obj["extensionPoints"] = []
            for p in ext_points:
                ep = node("UMLExtensionPoint", e.obj, name=p)
                e.obj["extensionPoints"].append(ep)
                e.ext_points[p] = ep
        return e

    def _add(self, kind, key, name, doc):
        e = Element(kind, key, name, doc, self.obj)
        self.el[key] = e
        self.order_el.append(e)
        return e

    def _owned(self, el, rel_obj):
        el.obj.setdefault("ownedElements", []).append(rel_obj)

    def _rel(self, kind, a, b, doc):
        key = f"{kind}:{a}->{b}"
        r = Relation(kind, key, a, b)
        self.rel[key] = r
        self.order_rel.append(r)
        return r, doc

    def assoc(self, a, b, directed=False, doc=""):
        r, doc = self._rel("assoc", a, b, doc)
        ea, eb = self.el[a], self.el[b]
        r.obj = node("UMLAssociation", ea.obj)
        if doc:
            r.obj["documentation"] = doc
        e1 = node("UMLAssociationEnd", r.obj, reference=ref(ea.obj))
        e2 = node("UMLAssociationEnd", r.obj, reference=ref(eb.obj))
        if directed:
            e2["navigable"] = "navigable"
        r.obj["end1"], r.obj["end2"] = e1, e2
        self._owned(ea, r.obj)
        return r.key

    def include(self, base, addition, doc=""):
        r, doc = self._rel("include", base, addition, doc)
        r.obj = node("UMLInclude", self.el[base].obj, source=ref(self.el[base].obj), target=ref(self.el[addition].obj))
        if doc:
            r.obj["documentation"] = doc
        self._owned(self.el[base], r.obj)
        return r.key

    def extend(self, base, extension, point, condition, doc=""):
        r, doc = self._rel("extend", base, extension, doc)
        r.point, r.condition = point, condition
        eb, ex = self.el[base], self.el[extension]
        r.obj = node("UMLExtend", ex.obj, source=ref(ex.obj), target=ref(eb.obj), condition=condition,
                     extensionLocations=[ref(eb.ext_points[point])])
        if doc:
            r.obj["documentation"] = doc
        self._owned(ex, r.obj)
        return r.key

    def general(self, child, parent, doc=""):
        r, doc = self._rel("general", child, parent, doc)
        r.obj = node("UMLGeneralization", self.el[child].obj, source=ref(self.el[child].obj), target=ref(self.el[parent].obj))
        if doc:
            r.obj["documentation"] = doc
        self._owned(self.el[child], r.obj)
        return r.key

    def diagram(self, name, doc=""):
        d = UseCaseDiagram(self, name, doc)
        self.diagrams.append(d)
        return d

    def finish(self):
        owned = [e.obj for e in self.order_el] + self.extra
        for d in self.diagrams:
            d.obj["documentation"] = (d.doc + "\n\n" if d.doc else "") + d.quantitative()
            d.obj["ownedViews"] = d.views
            owned.append(d.obj)
        self.diagrams[0].obj["defaultDiagram"] = True
        self.obj["ownedElements"] = owned


class Project:
    def __init__(self, title, author="", doc=""):
        self.obj = {"_type": "Project", "_id": new_id(), "name": title}
        if author:
            self.obj["author"] = author
        if doc:
            self.obj["documentation"] = doc
        self.models = []

    def add(self, model):
        model.bind(self.obj)
        self.models.append(model)
        return model

    def empty_model(self, name):
        m = node("UMLModel", self.obj, name=name)
        self.models.append(m)
        return m

    def save(self, path):
        owned = []
        for m in self.models:
            if isinstance(m, UseCaseModel):
                m.finish()
                owned.append(m.obj)
            else:
                owned.append(m)
        self.obj["ownedElements"] = owned
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.obj, f, ensure_ascii=False, indent="\t")
