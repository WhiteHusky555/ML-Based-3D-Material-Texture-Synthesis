"""Диаграммы автомата (state machine) для StarUML 6 (.mdj) и StarUML 5.0 (.uml).

Раскладка, трассировка переходов и подписи — общие с диаграммами деятельности (activity.py):
автомат — это Activity с одной невидимой «дорожкой»; узлы — состояния и псевдосостояния.

StarUML 6 (metamodel.json, elements.js 6.3.3):
  - UMLStateMachine.regions[0] (UMLRegion): vertices, transitions; диаграмма UMLStatechartDiagram —
    в ownedElements автомата;
  - UMLState: entryActivities / doActivities / exitActivities — UMLOpaqueBehavior (подписи entry/, do/,
    exit/), submachine — ссылка на автомат (подпись «имя: Автомат» и значок внизу справа);
  - UMLPseudostate.kind: initial | choice | junction; UMLFinalState;
  - UMLTransition: triggers — UMLEvent, guard, effects — UMLOpaqueBehavior; подпись «событие [условие] / действие».
StarUML 5.0 (UMLModels.pas, UMLFacto.pas): UMLStateMachine в Behaviors пакета, вершины — в Top
(UMLCompositeState «TOP»); состояние — UMLCompositeState с EntryActions / DoActivities / ExitActions
(UMLUninterpretedAction); ссылочное — UMLSubmachineState; эффекты перехода — Effects.
"""
import math

from activity import BAR_H, BARS, XPD_PSEUDO, Activity, Node, RAKE, label_text  # noqa: F401
from staruml_xpd import LINE_H, Obj, text_w

PSIZE = {"initial": (20, 20), "final": (26, 26), "choice": (28, 22), "junction": (16, 16)}
FONT_K = 1.06          # реальный шрифт шире оценки text_w
SUB_ICON = 16          # место под значок ссылочного состояния


class StateNode(Node):
    def __init__(self, key, kind, name="", doc="", row=0, dx=0, w=None, entry=(), do=(), exit=(), sub=None):
        super().__init__(key, kind, name, doc, 0, row, dx, w)
        self.entry, self.do, self.exit = list(entry), list(do), list(exit)
        self.sub = sub            # ключ автомата для ссылочного состояния

    def label(self, machines):
        return f"{self.name}: {machines[self.sub].name}" if self.sub else self.name

    def items(self):
        return [f"entry/{t}" for t in self.entry] + [f"do/{t}" for t in self.do] + [f"exit/{t}" for t in self.exit]

    def size(self, machines):
        if self.kind in PSIZE:
            return PSIZE[self.kind]
        if self.kind in BARS:
            return 0, BAR_H
        texts = [self.label(machines)] + self.items()
        w = max([math.ceil(text_w(t) * FONT_K) + 24 for t in texts] + [self.w or 0, 80])
        h = LINE_H + 10 + ((LINE_H * len(self.items()) + 10) if self.items() else 0) + (SUB_ICON if self.sub else 0)
        return (w + 1) // 2 * 2, max(40, (h + 1) // 2 * 2)


class Machine(Activity):
    """Автомат с диаграммой. width — ширина поля раскладки (координаты колонок задаются dx от центра)."""

    def __init__(self, key, name, doc="", diagram=None, diagram_doc="", width=600, variables=()):
        super().__init__(key, name, doc, diagram, diagram_doc, lanes=[("", width)])
        self.variables = list(variables)          # [(имя, тип, пояснение)] — внутренние переменные

    def initial(self, key, row, doc="", dx=0):
        return self._add(StateNode(key, "initial", "", doc, row, dx))

    def final(self, key, row, doc="", dx=0):
        return self._add(StateNode(key, "final", "", doc, row, dx))

    def choice(self, key, row, doc="", dx=0):
        return self._add(StateNode(key, "choice", "", doc, row, dx))

    def junction(self, key, row, doc="", dx=0):
        return self._add(StateNode(key, "junction", "", doc, row, dx))

    def _bar(self, kind, key, row, cols, doc, pad):
        n = StateNode(key, kind, "", doc, row)
        n.cols, n.pad = [(0, dx) for dx in cols], pad
        return self._add(n)

    def fork(self, key, row, cols, doc="", pad=40):
        """Псевдосостояние разветвления (линейка); cols — dx колонок параллельных состояний."""
        return self._bar("fork", key, row, cols, doc, pad)

    def join(self, key, row, cols, doc="", pad=40):
        """Псевдосостояние синхронизации: переход дальше — после завершения всех параллельных состояний."""
        return self._bar("join", key, row, cols, doc, pad)

    def state(self, key, name, row, doc="", dx=0, w=None, entry=(), do=(), exit=()):
        return self._add(StateNode(key, "state", name, doc, row, dx, w, entry, do, exit))

    def sub(self, key, ref_name, target, row, doc="", dx=0, w=None):
        return self._add(StateNode(key, "state", ref_name, doc, row, dx, w, sub=target))

    def tr(self, a, b, trigger="", guard="", effect="", doc="", **kw):
        return self.flow(a, b, trigger, guard, doc, effect=effect, **kw)


def quantitative(m):
    kinds = [n.kind for n in m.nodes.values()]
    subs = sum(1 for n in m.nodes.values() if getattr(n, "sub", None))
    bars = (f"разветвления — {kinds.count('fork')}; синхронизации — {kinds.count('join')}; "
            if "fork" in kinds else "")
    return (f"Количественная характеристика диаграммы: простых состояний — {kinds.count('state') - subs}; "
            f"ссылочных состояний — {subs}; псевдосостояний выбора — {kinds.count('choice')}; соединения — "
            f"{kinds.count('junction')}; {bars}начальных — {kinds.count('initial')}; конечных — "
            f"{kinds.count('final')}; переходов — {len(m.flows)}.")


# ---------------------------------------------------------------- StarUML 6 (.mdj)

def _pts6(points):
    return ";".join(f"{int(round(x))}:{int(round(y))}" for x, y in points)


def mdj_machines(mod, parent_model, machines):
    """Список UMLStateMachine для ownedElements пакета parent_model (dict)."""
    node, ref = mod.node, mod.ref
    objs = {k: node("UMLStateMachine", parent_model, name=m.name) for k, m in machines.items()}
    out = []
    for k, m in machines.items():
        o = objs[k]
        if m.doc:
            o["documentation"] = m.doc
        reg = node("UMLRegion", o, vertices=[], transitions=[])
        vobj = {}
        for n in m.order:
            if n.kind == "state":
                v = node("UMLState", reg, name=n.name)
                for attr, items in (("entryActivities", n.entry), ("doActivities", n.do), ("exitActivities", n.exit)):
                    if items:
                        v[attr] = [node("UMLOpaqueBehavior", v, name=t) for t in items]
                if n.sub:
                    v["submachine"] = ref(objs[n.sub])
            elif n.kind == "final":
                v = node("UMLFinalState", reg, name="")
            else:
                v = node("UMLPseudostate", reg, name="", kind=n.kind)
            if n.doc:
                v["documentation"] = n.doc
            reg["vertices"].append(v)
            vobj[n.key] = v
        for f in m.flows:
            t = node("UMLTransition", reg, source=ref(vobj[f.a]), target=ref(vobj[f.b]))
            if f.trigger:
                t["triggers"] = [node("UMLEvent", t, name=f.trigger, kind="signal")]
            if f.guard:
                t["guard"] = f.guard
            if f.effect:
                t["effects"] = [node("UMLOpaqueBehavior", t, name=f.effect)]
            if f.doc:
                t["documentation"] = f.doc
            reg["transitions"].append(t)
            f._obj = t
        o["regions"] = [reg]
        d = node("UMLStatechartDiagram", o, name=m.diagram)
        d["documentation"] = (m.diagram_doc + "\n\n" if m.diagram_doc else "") + quantitative(m)
        views, nview = [], {}
        for n in m.order:
            x, y, w, h = n.box
            t = {"state": "UMLStateView", "final": "UMLFinalStateView"}.get(n.kind, "UMLPseudostateView")
            v = node(t, d, model=ref(vobj[n.key]), left=x, top=y, width=w, height=h)
            views.append(v)
            nview[n.key] = v
        for f in m.flows:
            v = node("UMLTransitionView", d, model=ref(f._obj), head=ref(nview[f.b]), tail=ref(nview[f.a]),
                     lineStyle=0, points=_pts6(f.points))
            labels = []
            for nm, vis, al, ds in (("nameLabel", bool(f.text), f.alpha, f.distance),
                                    ("stereotypeLabel", False, math.pi / 2, 30),
                                    ("propertyLabel", False, -math.pi / 2, 15)):
                lb = node("EdgeLabelView", v, model=ref(f._obj), visible=vis, alpha=al, distance=ds,
                          hostEdge=ref(v), edgePosition=1)
                labels.append(lb)
                v[nm] = ref(lb)
            v["subViews"] = labels
            views.append(v)
        d["ownedViews"] = views
        o["ownedElements"] = [d]
        out.append(o)
    return out


# ---------------------------------------------------------------- StarUML 5.0 (.uml)

def _pts5(points):
    return ";".join(f"{int(round(x))},{int(round(y))}" for x, y in points)


def _action(name, back_role, owner):
    a = Obj("UMLUninterpretedAction")
    a.attr("Name", name).ref(back_role, owner)
    return a


def xpd_machines(model, machines):
    """Список UMLStateMachine (Obj) для Behaviors пакета model (Obj)."""
    sms = {k: Obj("UMLStateMachine") for k in machines}
    sub_refs = {k: [] for k in machines}
    built = []
    for k, m in machines.items():
        sm = sms[k]
        sm.attr("Name", m.name)
        if m.doc:
            sm.attr("Documentation", m.doc)
        sm.ref("Context", model)
        top = Obj("UMLCompositeState")
        top.attr("Name", "TOP").ref("StateMachine", sm)
        vert, out, inc = {}, {}, {}
        for n in m.order:
            if n.kind == "state":
                vert[n.key] = Obj("UMLSubmachineState" if n.sub else "UMLCompositeState")
            elif n.kind == "final":
                vert[n.key] = Obj("UMLFinalState")
            else:
                vert[n.key] = Obj("UMLPseudostate")
            out[n.key], inc[n.key] = [], []
            if n.sub:
                sub_refs[n.sub].append(vert[n.key])
        trans = [Obj("UMLTransition") for _ in m.flows]
        for f, t in zip(m.flows, trans):
            out[f.a].append(t)
            inc[f.b].append(t)
        views, owned = {}, []
        for n in m.order:
            x, y, w, h = n.box
            if n.kind == "state":
                v = Obj("UMLSubmachineStateView" if n.sub else "UMLStateView")
            else:
                v = Obj("UMLFinalStateView" if n.kind == "final" else "UMLPseudostateView")
            v.attr("Left", int(x)).attr("Top", int(y)).attr("Width", int(w)).attr("Height", int(h))
            v.ref("Model", vert[n.key])
            extra = []
            if n.kind == "state":
                nc = v.child("NameCompartment", Obj("UMLNameCompartmentView"))
                nc.child("NameLabel", Obj("LabelView")).attr("Text", n.name)
                nc.child("StereotypeLabel", Obj("LabelView")).attr("Visible", False)
                nc.child("PropertyLabel", Obj("LabelView")).attr("Visible", False)
                itc = v.child("InternalTransitionCompartment", Obj("UMLInternalTransitionCompartmentView"))
                itc.ref("Model", vert[n.key])
                extra.append(itc)
                if n.sub:
                    v.child("IncludeLabel", Obj("LabelView")).attr("Text", "include / " + machines[n.sub].name)
            owned.append(v)
            views[n.key] = [v] + extra
        tviews = {}
        for f, t in zip(m.flows, trans):
            v = Obj("UMLTransitionView")
            v.attr("LineStyle", "lsRectilinear", "LineStyleKind")
            v.attr("Points", _pts5(f.points), "Points")
            v.ref("Model", t).ref("Head", views[f.b][0]).ref("Tail", views[f.a][0])
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
            owned.append(v)
            tviews[id(t)] = [v, nl, sl]
        subs = []
        for n in m.order:
            o = vert[n.key]
            if n.kind == "state":
                o.attr("Name", n.name)
            if n.doc:
                o.attr("Documentation", n.doc)
            if n.kind in XPD_PSEUDO:
                o.attr("PseudostateKind", XPD_PSEUDO[n.kind], "UMLPseudostateKind")
            if n.sub:
                o.ref("Submachine", sms[n.sub])
            o.ref("ContainerState", top)
            o.refs("Views", views[n.key])
            o.refs("Outgoings", out[n.key])
            o.refs("Incomings", inc[n.key])
            if n.kind == "state":
                o.children("EntryActions", [_action(t, "EntryState", o) for t in n.entry])
                o.children("DoActivities", [_action(t, "DoActivityState", o) for t in n.do])
                o.children("ExitActions", [_action(t, "ExitState", o) for t in n.exit])
            subs.append(o)
        top.children("Subvertices", subs)
        sm.child("Top", top)
        for f, t in zip(m.flows, trans):
            if f.guard:
                t.attr("GuardCondition", f.guard)
            if f.doc:
                t.attr("Documentation", f.doc)
            t.ref("StateMachine", sm).ref("Source", vert[f.a]).ref("Target", vert[f.b])
            t.refs("Views", tviews[id(t)])
            if f.trigger:
                ev = Obj("UMLSignalEvent")
                ev.attr("Name", f.trigger).ref("Transition", t)
                t.children("Triggers", [ev])
            if f.effect:
                t.children("Effects", [_action(f.effect, "Transition", t)])
        sm.children("Transitions", trans)
        built.append((m, sm, owned))
    for m, sm, owned in built:
        sm.refs("SubmachineStates", sub_refs[m.key])
        d = Obj("UMLStatechartDiagram")
        d.attr("Name", m.diagram)
        d.attr("Documentation", (m.diagram_doc + "\n\n" if m.diagram_doc else "") + quantitative(m))
        d.ref("DiagramOwner", sm)
        dv = d.child("DiagramView", Obj("UMLStatechartDiagramView"))
        dv.ref("Diagram", d)
        dv.children("OwnedViews", owned)
        sm.children("OwnedDiagrams", [d])
    return [sms[k] for k in machines]
