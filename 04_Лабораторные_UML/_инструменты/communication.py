"""Диаграммы коммуникации (кооперации) для взаимодействий sequence.Interaction -> StarUML 6 (.mdj) и 5.0 (.uml).

Диаграмма добавляется в то же взаимодействие, что и диаграмма последовательности ([6], п. 8.3.1): объекты и
сообщения — те же элементы модели, новыми становятся только связи между объектами. Номера сообщений совпадают
с диаграммой последовательности.

Раскладка — дерево «лесенкой»: объект, первым получивший сообщение от другого, стоит ниже и правее отправителя;
связь идёт от низа отправителя вниз и вправо к получателю. Сообщения связи — столбик строк «стрелка + подпись»
над горизонтальным участком связи. Сообщения объекта самому себе — у петли над его правым углом. Связи вне дерева
идут справа, их сообщения — у вертикального участка.

Формат:
  - StarUML 6: UMLCommunicationDiagram в UMLInteraction; UMLCommLifelineView; UMLConnector (в роли-атрибуте
    кооперации, end1 / end2 — роли) и UMLConnectorView; UMLCommMessageView (EdgeNodeView: hostEdge, alpha,
    distance от середины среднего участка связи) с NodeLabelView; UMLMessage.connector — связь;
  - StarUML 5.0: UMLCollaborationDiagram в UMLInteractionInstanceSet; UMLColObjectView; UMLLink с двумя
    UMLLinkEnd (ParticipatingLinks набора экземпляров) и UMLLinkView; UMLColStimulusView; у стимула —
    CommunicationLink. Стрелка «вперёд», если отправитель — первый конец связи.
  Связь дерева — 3 точки (лишнюю точку на прямом участке StarUML 6 убирает сам), петля и связь вне дерева — 4.
"""
import math

from activity import alpha_distance
from sequence import _label5, _pts5, _pts6, tw
from staruml_xpd import LINE_H, Obj

ROW = 17            # шаг строк сообщений у горизонтального участка
VROW = 48           # шаг сообщений у вертикального участка (стрелка 40 px)
ARROW = 40          # длина стрелки сообщения (UMLCommMessageView._calcPosition)
GAP = 6             # стрелка — подпись
PAD = 12            # отступ строки от концов участка
TRUNK = 18          # от левого края объекта до его «ствола» вниз
VGAP = 22           # между полосами объектов
LOOP_H = 14         # высота петли над объектом
LIFT = 11           # строка над участком связи


class Link:
    def __init__(self, a, b, kind):
        self.a, self.b, self.kind = a, b, kind      # a — первый конец (хвост): родитель / верхний объект
        self.msgs = []
        self.points = []
        self.rows = {}                              # id(m) -> (центр стрелки, вертикальная?)
        self.doc = ""


class Comm:
    """Раскладка диаграммы коммуникации одного взаимодействия."""

    def __init__(self, it, name, doc):
        self.it, self.name, self.doc = it, name, doc
        self.box = {}                               # ключ объекта -> (left, top, w, h)
        self.links = []
        self._layout()
        self._docs()

    @staticmethod
    def text(m):
        return m.label()

    def label_w(self, m):
        return tw(self.text(m)) + 6 + (tw("«create»") + 8 if m.kind == "create" else 0)

    def _layout(self):
        it = self.it
        par, kids = {it.msgs[0].a: None}, {}
        for m in it.msgs:
            if m.b not in par:
                par[m.b] = m.a
                kids.setdefault(m.a, []).append(m.b)
        assert set(par) == set(it.order), f"{it.key}: объект без входящих сообщений"
        rows = []

        def walk(k):
            rows.append(k)
            for c in kids.get(k, []):
                walk(c)
        walk(it.msgs[0].a)
        row = {k: i for i, k in enumerate(rows)}
        by = {}
        for m in it.msgs:
            if m.a == m.b:
                key, kind = (m.a, m.a), "self"
            elif par[m.b] == m.a:
                key, kind = (m.a, m.b), "tree"
            elif par[m.a] == m.b:
                key, kind = (m.b, m.a), "tree"
            else:
                key, kind = tuple(sorted((m.a, m.b), key=row.get)), "extra"
            if key not in by:
                by[key] = Link(key[0], key[1], kind)
                self.links.append(by[key])
            by[key].msgs.append(m)
        occ = []                                    # занятые прямоугольники — для связей вне дерева

        def size(k):
            ll = it.lls[k]
            return ll.w, ll.head_h()

        def place(k, left, y):
            w, h = size(k)
            inc, slf = by.get((par[k], k)), by.get((k, k))
            r_in, r_self = len(inc.msgs) if inc else 0, len(slf.msgs) if slf else 0
            up = max(h / 2, r_in * ROW + 4 if r_in else 0,
                     h / 2 + LOOP_H + (r_self - 1) * ROW + ROW / 2 + 2 if r_self else 0)
            cy = int(y + up)
            top = cy - h // 2
            self.box[k] = (int(left), top, w, h)
            occ.append((left, top, left + w, top + h))
            if inc:
                tx = inc.points[0][0]
                inc.points += [(tx, cy), (left, cy)]
                self._rows(inc, tx + PAD + ARROW / 2, [cy - LIFT - (r_in - 1 - i) * ROW for i in range(r_in)], occ)
            if slf:
                r = left + w
                slf.points = [(r - 40, top), (r - 40, top - LOOP_H), (r - 12, top - LOOP_H), (r - 12, top)]
                self._rows(slf, r + 6 + ARROW / 2,
                           [top - LOOP_H - (r_self - 1 - i) * ROW for i in range(r_self)], occ)
            y = top + h + VGAP
            tx = int(left + (w / 2 if it.lls[k].is_actor else TRUNK))
            for c in kids.get(k, []):
                ln = by[(k, c)]
                ln.points = [(tx, top + h)]
                seg = PAD + ARROW + GAP + max(self.label_w(m) for m in ln.msgs) + PAD
                y = place(c, tx + max(seg, 60), y)
            return y
        place(rows[0], 20, 20)
        extra = sorted((ln for ln in self.links if ln.kind == "extra"), key=lambda ln: row[ln.b] - row[ln.a])
        slot = {}
        for k in rows:                              # точки присоединения: внешняя связь не пересекает внутреннюю
            inc = sorted((ln for ln in extra if k in (ln.a, ln.b)),
                         key=lambda ln: (ln.a == k, -row[ln.b if ln.a == k else ln.a]))
            for j, ln in enumerate(inc):
                mid = 20 if it.lls[k].is_actor else self.box[k][3] / 2      # у актора — на высоте значка
                slot[(id(ln), k)] = self.box[k][1] + mid + (j - (len(inc) - 1) / 2) * 12
        for ln in extra:
            (xa, _, wa, _), (xb, _, wb, _) = self.box[ln.a], self.box[ln.b]
            y1, y2 = int(slot[(id(ln), ln.a)]), int(slot[(id(ln), ln.b)])
            n = len(ln.msgs)
            ys = [(y1 + y2) / 2 + (i - (n - 1) / 2) * VROW for i in range(n)]
            lo, hi = min(y1, ys[0] - ARROW / 2) - 10, max(y2, ys[-1] + ARROW / 2) + 10
            lane = int(max(b[2] for b in occ if b[3] > lo and b[1] < hi) + 24)
            ln.points = [(xa + wa, y1), (lane, y1), (lane, y2), (xb + wb, y2)]
            self._rows(ln, lane + 12, ys, occ, vertical=True)
            occ.append((lane - 2, y1, lane + 2, y2))

    def _rows(self, ln, x, ys, occ, vertical=False):
        for m, y in zip(ln.msgs, ys):
            ln.rows[id(m)] = ((x, y), vertical)
            x2 = x + (12 if vertical else ARROW / 2 + GAP) + self.label_w(m)
            half = ARROW / 2 if vertical else LINE_H / 2
            occ.append((x - (6 if vertical else ARROW / 2), y - half, x2, y + half))

    def label_center(self, ln, m):
        """Центр подписи сообщения: справа от стрелки."""
        (x, y), vertical = ln.rows[id(m)]
        return x + (12 if vertical else ARROW / 2 + GAP) + (tw(self.text(m)) + 6) / 2, y

    def _docs(self):
        it = self.it

        def nm(k):
            return f"«{it.lls[k].head_text().strip()}»"
        for ln in self.links:
            fw = [str(m.no) for m in ln.msgs if m.a == ln.a]
            bk = [str(m.no) for m in ln.msgs if m.a != ln.a]
            if ln.kind == "self":
                ln.doc = (f"Связь объекта {nm(ln.a)} с самим собой (петля): по ней объект вызывает собственные "
                          f"операции — сообщения {', '.join(fw)}.")
                continue
            parts = [f"от {nm(ln.a)} к {nm(ln.b)} — {', '.join(fw)}"] if fw else []
            if bk:
                parts.append(f"обратно — {', '.join(bk)}")
            ln.doc = (f"Связь объектов {nm(ln.a)} и {nm(ln.b)}: объекты видят друг друга и обмениваются "
                      f"сообщениями ({'; '.join(parts)}).")

    def quantitative(self):
        k = [m.kind for m in self.it.msgs]
        loops = sum(1 for ln in self.links if ln.kind == "self")
        return (f"Количественная характеристика диаграммы: объектов — {len(self.box)} (акторов — "
                f"{sum(1 for ll in self.it.lls.values() if ll.is_actor)}); связей — {len(self.links)} (петель — "
                f"{loops}); сообщений — {len(k)}: синхронных вызовов — {k.count('call')}, асинхронных — "
                f"{k.count('async')}, ответов — {k.count('reply')}, «create» — {k.count('create')}.")

    def _msg_geom(self, ln, m, v5=False):
        """alpha / distance стрелки и подписи, размер стрелки. Опорная точка у связи из трёх точек: StarUML 6 —
        угол (EdgeParasiticView), StarUML 5.0 — середина последнего участка (CalcPosition)."""
        (x, y), vertical = ln.rows[id(m)]
        al, ds = alpha_distance(ln.points[-2:] if v5 and len(ln.points) == 3 else ln.points, (x, y))
        lx, _ = self.label_center(ln, m)
        sx = lx + (tw(self.text(m)) + 6) / 2 + 4 + tw("«create»") / 2
        return al, ds, (0, ARROW) if vertical else (ARROW, 0), lx - x, sx - x

    # ================================================================ StarUML 6 (.mdj)
    def mdj(self, mod):
        """Диаграмма в UMLInteraction, собранном sequence.mdj_interaction (it.mdj6)."""
        node, ref = mod.node, mod.ref
        it = self.it
        inter, lfs, roles = it.mdj6
        dg = node("UMLCommunicationDiagram", inter, name=self.name,
                  documentation=(self.doc + "\n\n" if self.doc else "") + self.quantitative(),
                  showSequenceNumber=True, showSignature=True, sequenceNumbering="auto")
        views, nv = [], {}
        for k in it.order:
            left, top, w, h = self.box[k]
            nv[k] = node("UMLCommLifelineView", dg, model=ref(lfs[k]), left=left, top=top, width=w, height=h,
                         stereotypeDisplay="icon" if it.lls[k].is_actor else "label")
            views.append(nv[k])
        for ln in self.links:
            c = node("UMLConnector", roles[ln.a], documentation=ln.doc)
            c["end1"] = node("UMLConnectorEnd", c, reference=ref(roles[ln.a]))
            c["end2"] = node("UMLConnectorEnd", c, reference=ref(roles[ln.b]))
            roles[ln.a].setdefault("ownedElements", []).append(c)
            v = node("UMLConnectorView", dg, model=ref(c), tail=ref(nv[ln.a]), head=ref(nv[ln.b]), lineStyle=0,
                     points=_pts6(ln.points))
            subs = []
            for field, al, ds, pos, lm in (("nameLabel", math.pi / 2, 15, 1, c),
                                           ("stereotypeLabel", math.pi / 2, 30, 1, c),
                                           ("propertyLabel", -math.pi / 2, 15, 1, c),
                                           ("tailRoleNameLabel", math.pi / 6, 30, 2, c["end1"]),
                                           ("tailPropertyLabel", math.pi / 4, 40, 2, c["end1"]),
                                           ("tailMultiplicityLabel", -math.pi / 6, 25, 2, c["end1"]),
                                           ("headRoleNameLabel", -math.pi / 6, 30, 0, c["end2"]),
                                           ("headPropertyLabel", -math.pi / 4, 40, 0, c["end2"]),
                                           ("headMultiplicityLabel", math.pi / 6, 25, 0, c["end2"])):
                lb = node("EdgeLabelView", v, model=ref(lm), visible=False, alpha=al, distance=ds, hostEdge=ref(v),
                          edgePosition=pos)
                v[field] = ref(lb)
                subs.append(lb)
            v["subViews"] = subs
            views.append(v)
            for m in ln.msgs:
                m.obj6["connector"] = ref(c)
                al, ds, (w, h), ldx, sdx = self._msg_geom(ln, m)
                (x, y), _ = ln.rows[id(m)]
                mv = node("UMLCommMessageView", dg, model=ref(m.obj6), hostEdge=ref(v), edgePosition=1, alpha=al,
                          distance=ds, left=int(x - w // 2), top=int(y - h // 2), width=w, height=h, showType=False)
                labs = []
                for field, vis, dx, txt in (("nameLabel", True, ldx, self.text(m)),
                                            ("stereotypeLabel", m.kind == "create", sdx, "«create»"),
                                            ("propertyLabel", False, 10, "")):
                    lw = int(tw(txt) + 6)
                    lb = node("NodeLabelView", mv, model=ref(m.obj6), visible=vis, alpha=0, distance=dx,
                              left=int(x + dx - lw / 2), top=int(y - LINE_H / 2), width=lw, height=LINE_H)
                    mv[field] = ref(lb)
                    labs.append(lb)
                mv["subViews"] = labs
                views.append(mv)
        dg["ownedViews"] = views
        inter["ownedElements"].append(dg)

    # ================================================================ StarUML 5.0 (.uml)
    def xpd(self, cis, iis, objs, stims, obj_views, stim_views):
        """Диаграмма кооперации того же набора экземпляров; вызывается из sequence.xpd_interaction.
        Возвращает (диаграмма, связи, {id(сообщения): связь}, {ключ объекта: концы связей})."""
        it = self.it
        dg, dv = Obj("UMLCollaborationDiagram"), Obj("UMLCollaborationDiagramView")
        owned, ov, links, link_of, ends_of = [], {}, [], {}, {}
        for k in it.order:
            ll = it.lls[k]
            left, top, w, h = self.box[k]
            v = Obj("UMLColObjectView")
            v.attr("Left", left).attr("Top", top).attr("Width", int(w)).attr("Height", int(h))
            if ll.is_actor:
                v.attr("StereotypeDisplay", "sdkIcon", "UMLStereotypeDisplayKind")
            v.ref("Model", objs[k])
            nc = v.child("NameCompartment", Obj("UMLNameCompartmentView"))
            nc.child("NameLabel", Obj("LabelView")).attr("Text", ll.head_text())
            sl = nc.child("StereotypeLabel", Obj("LabelView"))
            if ll.stereo and not ll.is_actor:
                sl.attr("Text", f"<<{ll.stereo}>>")
            else:
                sl.attr("Visible", False)
            nc.child("PropertyLabel", Obj("LabelView")).attr("Visible", False)
            obj_views[k].append(v)
            ov[k] = v
            owned.append(v)
        for ln in self.links:
            lk = Obj("UMLLink")
            e1, e2 = Obj("UMLLinkEnd"), Obj("UMLLinkEnd")
            v = Obj("UMLLinkView")
            v.attr("LineStyle", "lsRectilinear", "LineStyleKind").attr("Points", _pts5(ln.points), "Points")
            v.ref("Model", lk).ref("Head", ov[ln.b]).ref("Tail", ov[ln.a])
            labs = [_label5("NameLabel", "", math.pi / 2, 15, lk, None, visible=False),
                    _label5("StereotypeLabel", "", math.pi / 2, 30, lk, None, visible=False),
                    _label5("PropertyLabel", "", -math.pi / 2, 15, None, None, visible=False),
                    _label5("HeadEndLabel", "", -math.pi / 6, 30, e2, None, visible=False),
                    _label5("TailEndLabel", "", math.pi / 6, 30, e1, None, visible=False)]
            labs[3][1].attr("EdgePosition", "epHead", "EdgePositionKind")
            labs[4][1].attr("EdgePosition", "epTail", "EdgePositionKind")
            for role, lb in labs:
                v.child(role, lb)
            owned.append(v)
            lk.attr("Documentation", ln.doc).ref("CollaborationInstanceSet", cis)
            lk.refs("Views", [v, labs[0][1], labs[1][1]])
            for e, k, lb in ((e1, ln.a, labs[4][1]), (e2, ln.b, labs[3][1])):
                e.ref("Instance", objs[k]).ref("Link", lk)
                e.refs("Views", [lb])
                ends_of.setdefault(k, []).append(e)
            lk.children("Connections", [e1, e2])
            lk.refs("Stimuli", [stims[id(m)] for m in ln.msgs])
            links.append(lk)
            for m in ln.msgs:
                s = stims[id(m)]
                link_of[id(m)] = lk
                al, ds, (w, h), ldx, sdx = self._msg_geom(ln, m, v5=True)
                mv = Obj("UMLColStimulusView")
                mv.attr("Width", w).attr("Height", h).attr("Alpha", float(al)).attr("Distance", float(ds))
                mv.ref("Model", s).ref("HostEdge", v)
                made = []
                for role, vis, dx, txt, model in (("NameLabel", True, ldx, self.text(m), s),
                                                  ("StereotypeLabel", m.kind == "create", sdx, "<<create>>", s),
                                                  ("PropertyLabel", False, 10, "", None)):
                    lb = mv.child(role, Obj("NodeLabelView"))
                    if not vis:
                        lb.attr("Visible", False)
                    lb.attr("Height", 13).attr("Alpha", 0.0).attr("Distance", float(dx))
                    if vis:
                        lb.attr("Text", txt)
                    if model is not None:
                        lb.ref("Model", model)
                        made.append(lb)
                stim_views[id(m)] += [mv] + made
                owned.append(mv)
        dv.ref("Diagram", dg).children("OwnedViews", owned)
        dg.attr("Name", self.name)
        dg.attr("Documentation", (self.doc + "\n\n" if self.doc else "") + self.quantitative())
        dg.ref("DiagramOwner", iis)
        dg.child("DiagramView", dv)
        return dg, links, link_of, ends_of

