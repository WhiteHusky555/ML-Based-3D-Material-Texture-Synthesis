"""Диаграммы последовательности для StarUML 6 (.mdj) и StarUML 5.0 (.uml) из описания на Python.

Модель ([5], гл. 5): линии жизни — объекты классов ЛР4 и акторы ЛР1; надпись над сплошной стрелкой — вызов
операции класса получателя (операция обязана быть в модели классов, иначе — ошибка сборки); пунктирные стрелки —
ответы и сообщения «create»; комбинированные фрагменты alt / opt / loop / par с операндами и условиями.

StarUML 6 (metamodel.json, elements.js 6.3.3):
  - UMLCollaboration (attributes — роли: UMLAttribute с type = класс или актор) → UMLInteraction (participants —
    UMLLifeline.represent → роль; messages — UMLMessage: source/target — линии жизни, signature — UMLOperation,
    messageSort synchCall / asynchCall / reply / createMessage; fragments — UMLCombinedFragment, operands —
    UMLInteractionOperand.guard) → UMLSequenceDiagram (ownedElements взаимодействия);
  - UMLSeqLifelineView: подвид linePart (UMLLinePartView), на который ссылаются концы сообщений; шапка
    высотой SEQ_OBJECT_MINHEIGHT = 40 на LIFELINE_TOP_POSITION = 40, у созданного сообщением «create» — по его y;
  - UMLSeqMessageView: подписи EdgeLabelView и activation (UMLActivationView) — top = y стрелки, ширина 14,
    высота сохраняется; левый край — у линии (left − 7) или на 7 правее родительской активации; концы стрелки —
    у краёв активаций (arrangeObject); showType = false — в подписи только имена параметров;
  - UMLCombinedFragmentView: operandCompartment (UMLInteractionOperandCompartmentView) с UMLInteractionOperandView,
    высоты операндов сохраняются, условие — «[guard]» в 20 px от левого и 15 px от верхнего края операнда.
StarUML 5.0 (UMLModels.pas, UMLViews.pas, UMLFacto.pas, Core.pas, Samples/*.uml):
  - UMLCollaborationInstanceSet во владельце-классификаторе (OwnedCollaborationInstanceSets) → UMLInteractionInstanceSet
    (ParticipatingStimuli, Fragments, OwnedDiagrams) и UMLObject (ParticipatingInstances; Classifier);
  - UMLStimulus: Sender / Receiver; Action — UMLCallAction (Operation, IsAsynchronous), UMLReturnAction,
    UMLCreateAction (Instantiation); обратные ссылки Instances, CallActions, CreateActions, SendingStimuli,
    ReceivingStimuli, Views;
  - UMLSequenceDiagram: UMLSeqObjectView (+ LifeLine — UMLLifeLineView; концы стрелок ссылаются на него),
    UMLSeqStimulusView (+ Activation), UMLCombinedFragmentView с вложенными (ContainedViews)
    UMLInteractionOperandView.
"""
import math

from activity import alpha_distance
from staruml_xpd import LINE_H, Obj, text_w

FONT_K = 1.07
LL_TOP = 40                 # LIFELINE_TOP_POSITION
HEAD_H = 40                 # SEQ_OBJECT_MINHEIGHT
ICON_NAME_H = 26            # отсек имени под значком актора
ACT_W = 14                  # ACTIVATION_MINWIDTH
ACT_MIN = 25                # ACTIVATION_MINHEIGHT
SELF_W, SELF_H = 30, 20     # SELF_MESSAGE_WIDTH / HEIGHT
ROW = 30                    # шаг сообщений по вертикали
FRAME_HDR = 26              # шапка фрагмента: подпись оператора + отступы
GUARD_DY, GUARD_DX = 15, 20  # INTERACTIONOPERAND_GUARD_VERT / HORZ_MARGIN
LABEL_GAP = 10              # зазор подписи от краёв промежутка
SORT6 = {"call": "synchCall", "async": "asynchCall", "reply": "reply", "create": "createMessage"}
OPERATOR5 = {"alt": "iokAlt", "opt": "iokOpt", "loop": "iokLoop", "par": "iokPar"}


def tw(s):
    return text_w(s) * FONT_K


class Lifeline:
    def __init__(self, key, cls=None, actor=None, name="", doc="", worker=False):
        self.key, self.cls, self.actor, self.name, self.doc = key, cls, actor, name, doc
        self.worker = worker            # работник ЛР1 (класс «worker») — прямоугольник, не значок актора
        self.type_name = self.stereo = ""
        self.created_by = None          # сообщение «create»
        self.x = self.w = 0
        self.top = LL_TOP
        self.line_top = self.line_bottom = 0
        self.idx = 0

    @property
    def is_actor(self):
        return self.actor is not None and not self.worker

    def head_text(self):
        return f"{self.name}: {self.type_name}"

    def head_h(self):
        return HEAD_H + ICON_NAME_H if self.is_actor else HEAD_H


class Message:
    def __init__(self, kind, a, b, op=None, args=None, text="", doc=""):
        self.kind, self.a, self.b, self.op, self.args, self.text, self.doc = kind, a, b, op, args, text, doc
        self.y = 0
        self.no = 0
        self.act = None                 # (left, top, height) активации получателя (видимой)
        self.act_bottom = None
        self.points = []
        self.label_c = None
        self.call_of = None             # для ответа — вызов, на который он отвечает
        self.params = []                # имена параметров операции (для подписи)

    @property
    def self_msg(self):
        return self.a == self.b

    def args_text(self):
        return self.args if self.args is not None else ", ".join(self.params)

    def label(self):
        if self.kind in ("call", "async"):
            return f"{self.no} : {self.op}({self.args_text()})"
        if self.kind == "create":
            return f"{self.no} : "
        return f"{self.no} : {self.text}"


class Operand:
    def __init__(self, guard, doc=""):
        self.guard, self.doc = guard, doc
        self.top = self.bottom = 0
        self.msgs = []


class Fragment:
    def __init__(self, kind, doc=""):
        self.kind, self.doc = kind, doc
        self.operands = []
        self.parent = None
        self.children = []
        self.top = self.bottom = 0
        self.left = self.right = 0


class Interaction:
    """Одна диаграмма последовательности. events — последовательность событий раскладки по вертикали."""

    def __init__(self, key, name, doc, diagram, diagram_doc, owner=None, cls_model=None, order=()):
        self.key, self.name, self.doc, self.diagram, self.diagram_doc = key, name, doc, diagram, diagram_doc
        self.owner = owner                  # ключ прецедента ЛР1 — владелец взаимодействия
        self.cm = cls_model                 # classdiagram.ClassModel (ЛР4)
        self.lls = {}
        self.order = list(order)
        self.msgs = []
        self.frags = []
        self.events = []                    # ("msg", m) / ("begin", f, op) / ("else", f, op) / ("end", f)
        self._stack = []                    # открытые фрагменты
        self._open = []                     # открытые активации (вложенные вызовы)
        self.width = self.height = 0

    # ---------------------------------------------------------------- линии жизни
    def lifeline(self, key, cls=None, actor=None, name="", doc="", actor_name="", stereo=None, worker=False):
        ll = Lifeline(key, cls, actor, name, doc, worker)
        if cls:
            c = self.cm.cls[cls]
            ll.type_name = c.name
            ll.stereo = "interface" if c.interface else c.stereo_text() if stereo is None else stereo
        else:
            ll.type_name = actor_name
            ll.stereo = "worker" if worker else ""
        self.lls[key] = ll
        if key not in self.order:
            self.order.append(key)
        return self

    # ---------------------------------------------------------------- сообщения
    def _op(self, b, op):
        ll = self.lls[b]
        if ll.cls is None:
            raise ValueError(f"{self.key}: сообщение «{op}» актору {b} — у актора нет операций")
        c = self.cm.cls[ll.cls]
        for o in c.ops:
            if o.name == op:
                return o, ll.cls
        # операции предков (обобщение)
        for r in self.cm.rel_order:
            if r.kind == "gen" and r.a == ll.cls:
                for o in self.cm.cls[r.b].ops:
                    if o.name == op:
                        return o, r.b
        raise ValueError(f"{self.key}: у класса {c.name} нет операции {op}() — [5]: операция обязана быть в модели классов")

    def _add(self, m):
        m.frag_op = self._stack[-1][1] if self._stack else None
        self.msgs.append(m)
        self.events.append(("msg", m))
        if m.frag_op:
            m.frag_op.msgs.append(m)
        return m

    def call(self, a, b, op, args=None, ret=None, doc="", ret_doc="", asynch=False):
        """Вызов без вложенных сообщений; ret — текст ответа (пунктирная стрелка сразу после вызова)."""
        o, owner = self._op(b, op)
        m = self._add(Message("async" if asynch else "call", a, b, op, args, doc=doc))
        m.params = [n for n, _ in o.params]
        m.op_cls = owner
        if ret is not None:
            r = self._add(Message("reply", b, a, text=ret, doc=ret_doc))
            r.call_of, m.reply = m, r
        return m

    def enter(self, a, b, op, args=None, ret=None, doc="", ret_doc="", asynch=False):
        """Вызов с вложенными сообщениями: with it.enter(...): сообщения, которые отправляет получатель."""
        it = self

        class _Ctx:
            def __enter__(self_):
                m = it.call(a, b, op, args, None, doc, asynch=asynch)
                self_.m = m
                it._open.append(m)
                m.inner_from = len(it.msgs)
                it.events.append(("open", m))
                return m

            def __exit__(self_, *exc):
                if exc[0]:
                    return False
                it._open.pop()
                m = self_.m
                m.inner = it.msgs[m.inner_from:]
                if ret is not None:
                    r = it._add(Message("reply", b, a, text=ret, doc=ret_doc))
                    r.call_of, m.reply = m, r
                it.events.append(("close", m))
                return False
        return _Ctx()

    def resume(self, m):
        """Продолжение активации ранее отправленного вызова m (обычно асинхронного): сообщения блока отправляет
        получатель m, его активация длится до конца блока."""
        it = self

        class _Ctx:
            def __enter__(self_):
                m.inner_from = len(it.msgs)
                it._open.append(m)
                it.events.append(("open", m))
                return m

            def __exit__(self_, *exc):
                if exc[0]:
                    return False
                it._open.pop()
                m.inner = it.msgs[m.inner_from:]
                it.events.append(("close", m))
                return False
        return _Ctx()

    def create(self, a, b, doc=""):
        m = self._add(Message("create", a, b, doc=doc))
        self.lls[b].created_by = m
        return m

    # ---------------------------------------------------------------- фрагменты
    def frag(self, kind, guard, doc="", guard_doc=""):
        f = Fragment(kind, doc)
        f.parent = self._stack[-1][0] if self._stack else None
        if f.parent:
            f.parent.children.append(f)
        op = Operand(guard, guard_doc)
        f.operands.append(op)
        self.frags.append(f)
        self._stack.append((f, op))
        self.events.append(("begin", f, op))
        return f

    def alt(self, guard, doc="", guard_doc=""):
        return self.frag("alt", guard, doc, guard_doc)

    def opt(self, guard, doc="", guard_doc=""):
        return self.frag("opt", guard, doc, guard_doc)

    def loop(self, guard, doc="", guard_doc=""):
        return self.frag("loop", guard, doc, guard_doc)

    def par(self, guard="", doc="", guard_doc=""):
        return self.frag("par", guard, doc, guard_doc)

    def else_(self, guard, guard_doc=""):
        f, _ = self._stack.pop()
        op = Operand(guard, guard_doc)
        f.operands.append(op)
        self._stack.append((f, op))
        self.events.append(("else", f, op))

    def end(self):
        f, _ = self._stack.pop()
        self.events.append(("end", f))

    # ---------------------------------------------------------------- раскладка
    def layout(self):
        assert not self._stack and not self._open, f"{self.key}: незакрытый фрагмент или вызов"
        for i, k in enumerate(self.order):
            self.lls[k].idx = i
        for i, m in enumerate(self.msgs, 1):
            m.no = i
        self._layout_y()
        self._layout_x()
        self._points()
        self._frames()
        right = max(ll.x + ll.w / 2 for ll in self.lls.values())
        for m in self.msgs:
            if m.label_c:
                right = max(right, m.label_c[0] + tw(m.label()) / 2 + 6)
        for f in self.frags:
            right = max(right, f.right)
        self.width = right + 30
        self.height = max(ll.line_bottom for ll in self.lls.values()) + 30

    def _layout_y(self):
        y = max(LL_TOP + ll.head_h() for ll in self.lls.values() if not ll.created_by) + 1 + 8
        leaf_bottom = 0                      # низ активации последнего вызова без вложенных сообщений
        leaf_owner = None                    # на чьей линии жизни эта активация
        close_bottom = 0                     # низ последней закрытой активации с вложенными сообщениями

        def clear(y):                        # рамка и разделитель операндов — ниже активаций операнда
            return max(y, leaf_bottom + 6, close_bottom - 6)
        for ev in self.events:
            kind = ev[0]
            if kind == "msg":
                m = ev[1]
                y += ROW + (10 if m.kind == "create" else 0)   # шапка созданного объекта — 20 px над стрелкой
                if leaf_bottom and leaf_owner == m.a:          # подпись не должна лечь на эту активацию
                    y = max(y, leaf_bottom + (2 * LINE_H if m.kind == "create" else LINE_H) + 10)
                m.y = y
                if m.kind == "create":
                    self.lls[m.b].top = y - HEAD_H // 2
                    y += HEAD_H // 2 - 6
                if m.self_msg:
                    y += SELF_H
                leaf_bottom, leaf_owner = 0, None
                if m.kind in ("call", "async"):
                    m.act_top = m.y + (SELF_H if m.self_msg else 0)
                    m.act_bottom = m.act_top + ACT_MIN
                    leaf_bottom, leaf_owner = m.act_bottom, m.b
                if m.kind == "reply" and m.call_of is not None:
                    m.call_of.act_bottom = max(m.call_of.act_bottom, m.y)
                    leaf_bottom = 0
            elif kind == "open":
                leaf_bottom = 0
            elif kind == "close":
                m = ev[1]
                inner = [q.act_bottom for q in m.inner if q.kind == "call" and q.a == m.b]
                if not getattr(m, "reply", None):
                    m.act_bottom = max([m.act_bottom, y + 10] + [b + 5 for b in inner])
                    y = max(y, m.act_bottom - ROW + 12)
                close_bottom = max(close_bottom, m.act_bottom)
                leaf_bottom = 0
            elif kind == "begin":
                f, op = ev[1], ev[2]
                y = clear(y) + 16
                f.top = op.top = y
                y += FRAME_HDR + (GUARD_DY + LINE_H if op.guard else 0)
                leaf_bottom = 0
            elif kind == "else":
                f, op = ev[1], ev[2]
                y = clear(y) + 14
                op.top = y
                y += GUARD_DY + LINE_H if op.guard else 4
                leaf_bottom = 0
            elif kind == "end":
                f = ev[1]
                y = clear(y) + 12
                f.bottom = y
                y += 2
                leaf_bottom = 0
        bottom = y + 30
        for m in self.msgs:
            if m.kind in ("call", "async"):
                bottom = max(bottom, m.act_bottom + 30)
        for ll in self.lls.values():
            ll.line_top = ll.top + ll.head_h() + 1
            ll.line_bottom = bottom
        for f in self.frags:
            for i, op in enumerate(f.operands):
                op.bottom = f.operands[i + 1].top if i + 1 < len(f.operands) else f.bottom

    def _acts_on(self, key, y, exclude=None):
        """Активации на линии жизни key, покрывающие y (как getActivationAt StarUML)."""
        res = []
        for m in self.msgs:
            if m is exclude or m.kind not in ("call", "async") or m.b != key:
                continue
            if m.act_top <= y < m.act_bottom:
                res.append(m)
        return res

    def _act_left(self, m):
        """Левый край активации вызова m: у линии или на 7 правее родительской (UMLActivationView.arrangeObject)."""
        if hasattr(m, "_act_left"):
            return m._act_left
        ll = self.lls[m.b]
        par = [p for p in self._acts_on(m.b, m.act_top - 1, exclude=m) if p.act_top < m.act_top]
        if par:
            front = max(par, key=lambda p: p.act_top)
            left = self._act_left(front) + ACT_W // 2
        else:
            left = ll.cx - ACT_W // 2
        m._act_left = left
        return left

    def _edge_x(self, key, y, side, own=None):
        """x края активации (или линии) линии жизни key на высоте y со стороны side ('left'/'right')."""
        ll = self.lls[key]
        cand = self._acts_on(key, y)
        if own is not None and own.kind in ("call", "async") and own not in cand:
            cand.append(own)
        if cand:
            front = max(cand, key=lambda p: p.act_top)
            left = self._act_left(front)
            return left if side == "left" else left + ACT_W
        return ll.cx if side == "left" else ll.cx + 1

    def _layout_x(self):
        lls = [self.lls[k] for k in self.order]
        for ll in lls:
            texts = [ll.head_text()] + ([f"«{ll.stereo}»"] if ll.stereo and not ll.is_actor else [])
            ll.w = max(30, max(tw(t) for t in texts) + 2 * 5 + 14)
            ll.w = int(math.ceil(ll.w / 2) * 2)
        n = len(lls)
        gap = [0.0] * n                      # gap[i] — между центрами i и i+1
        for i in range(n - 1):
            gap[i] = (lls[i].w + lls[i + 1].w) / 2 + 30
        for f in self.frags:                 # место слева от рамки под условия и пятиугольник оператора
            i0 = self._frag_min_idx(f)
            if i0 > 0:
                gap[i0 - 1] = max(gap[i0 - 1], self._frag_pad(f) + ACT_W + 20)
        slack = 2 * ACT_W + LABEL_GAP + 12       # края активаций, отступ от отправителя и запас

        def band(m):                             # вертикальная полоса подписи
            if m.self_msg:
                return m.y + 1, m.y + SELF_H - 1
            return m.y - LINE_H - 4 - (LINE_H if m.kind == "create" else 0), m.y - 2

        def idle(i, y1, y2):
            """Можно ли подписи пройти над пунктиром линии жизни i: нет активации и шапки в полосе ([5], рис. 5.3)."""
            ll = lls[i]
            if ll.created_by is not None:
                if y2 < ll.top:
                    return True
                if y1 <= ll.top + ll.head_h():
                    return False
            return not any(q.kind in ("call", "async") and q.b == ll.key and q.act_top < y2 and q.act_bottom > y1
                           for q in self.msgs)

        def runs(gaps_dir, y1, y2):
            """Промежутки по направлению от отправителя, разбитые на отрезки линиями жизни, через которые нельзя."""
            res, cur = [], []
            for j, g in enumerate(gaps_dir):
                cur.append(g)
                if j + 1 < len(gaps_dir) and not idle(max(g, gaps_dir[j + 1]), y1, y2):
                    res.append(cur)
                    cur = []
            if cur:
                res.append(cur)
            return res

        for m in sorted((m for m in self.msgs if not m.self_msg), key=lambda m: -self._label_w(m)):
            L = self._label_w(m)
            ia, ib = self.lls[m.a].idx, self.lls[m.b].idx
            path = list(range(min(ia, ib), max(ia, ib)))
            order = path if ib > ia else path[::-1]
            tgt = self.lls[m.b]

            def need(r):
                extra = tgt.w / 2 if m.kind == "create" and any(g in (tgt.idx - 1, tgt.idx) for g in r) else 0
                return L + slack + extra
            rs = runs(order, *band(m))
            fit = [r for r in rs if sum(gap[g] for g in r) >= need(r)]
            if fit:
                m.label_run = fit[0]
            else:                                   # расширить отрезок с наименьшим недостатком
                r = min(rs, key=lambda r: need(r) - sum(gap[g] for g in r))
                gap[r[0]] += need(r) - sum(gap[g] for g in r)
                m.label_run = r
        for m in self.msgs:                      # самовызов: подпись справа от петли или слева от линии жизни
            if not m.self_msg:
                continue
            L = self._label_w(m)
            ia = self.lls[m.a].idx
            y1, y2 = band(m)
            limit = max((self._frag_min_idx(f) for f in self._enclosing(m)), default=0)
            r_run = runs(list(range(ia, n - 1)), y1, y2)[0] if ia < n - 1 else []
            left = [g for g in range(ia - 1, -1, -1) if g >= limit]
            l_run = runs(left, y1, y2)[0] if left else []
            need_r = ACT_W * 2 + SELF_W + 8 + L + LABEL_GAP
            need_l = ACT_W * 2 + L + 2 * LABEL_GAP + 6
            def_r = need_r - sum(gap[g] for g in r_run) if r_run else 0
            def_l = need_l - sum(gap[g] for g in l_run) if l_run else 10 ** 9
            if def_r <= max(def_l, 0):
                m.self_side = "right"
                if def_r > 0:
                    gap[r_run[0]] += def_r
            else:
                m.self_side = "left"
                if def_l > 0:
                    gap[l_run[0]] += def_l
        x = 40 + lls[0].w / 2
        for i, ll in enumerate(lls):
            ll.cx = int(round(x))
            ll.x = ll.cx
            ll.left = int(round(ll.cx - ll.w / 2))
            if i < n - 1:
                x += gap[i]

    def _enclosing(self, m):
        """Фрагменты, внутри которых лежит сообщение m (от внутреннего к внешнему)."""
        res = []
        for f in self.frags:
            if any(m in op.msgs for op in f.operands):
                g = f
                while g:
                    res.append(g)
                    g = g.parent
        return res

    def _label_w(self, m):
        w = tw(m.label()) + 6
        return max(w, tw("«create»") + 6) if m.kind == "create" else w

    def _label_need(self, m, g, L, slack):
        """Нужное расстояние между центрами линий жизни g и g+1, чтобы подпись m легла в этот промежуток."""
        tgt = self.lls[m.b]
        if m.kind == "create" and g in (tgt.idx - 1, tgt.idx):
            return L + slack + tgt.w / 2
        return L + slack

    def _frag_min_idx(self, f):
        idx = [self.lls[k].idx for op in f.operands for m in op.msgs for k in (m.a, m.b)]
        idx += [self._frag_min_idx(c) for c in f.children]
        return min(idx)

    def _frag_pad(self, f):
        """Расстояние от центра крайней левой линии жизни до левого края рамки (с вложенными фрагментами)."""
        gw = max((tw(f"[{op.guard}]") for op in f.operands if op.guard), default=0)
        pw = 5 + tw(f.kind) * 1.12 + 4 + 5 + 13
        own = ACT_W // 2 + max(GUARD_DX + gw + 8, pw + 8)
        i0 = self._frag_min_idx(f)
        for c in f.children:
            if self._frag_min_idx(c) == i0:
                own = max(own, self._frag_pad(c) + 10)
        return own

    def _points(self):
        for m in self.msgs:
            a, b = self.lls[m.a], self.lls[m.b]
            y = m.y
            if m.kind in ("call", "async"):
                m.act = (self._act_left(m), m.act_top, m.act_bottom - m.act_top)
            if m.self_msg:
                x0 = self._edge_x(m.a, y, "right")
                x3 = (m.act[0] + ACT_W) if m.act else x0
                m.points = [(x0, y), (x0 + SELF_W, y), (x0 + SELF_W, y + SELF_H), (x3, y + SELF_H)]
                L = tw(m.label()) + 6
                if getattr(m, "self_side", "right") == "left":
                    m.label_c = (self._edge_x(m.a, y, "left") - LABEL_GAP - L / 2, y + SELF_H / 2)
                else:
                    m.label_c = (x0 + SELF_W + 6 + L / 2, y + SELF_H / 2)
                continue
            right = b.idx > a.idx
            own = m if m.kind in ("call", "async") else None
            if right:
                x0 = self._edge_x(m.a, y, "right")
                x1 = (m.act[0] if m.act else b.left if m.kind == "create" else self._edge_x(m.b, y, "left", own))
            else:
                x0 = self._edge_x(m.a, y, "left")
                x1 = (m.act[0] + ACT_W if m.act else b.left + b.w if m.kind == "create"
                      else self._edge_x(m.b, y, "right", own))
            m.points = [(x0, y), (x1, y)]
            # подпись — в выбранном при раскладке промежутке (не пересекает пунктиры других линий жизни)
            r = m.label_run
            left_ll, right_ll = self.lls[self.order[min(r)]], self.lls[self.order[max(r) + 1]]
            lo, hi = left_ll.cx + ACT_W, right_ll.cx - ACT_W
            if left_ll is (a if right else b):
                lo = min(x0, x1)
            if right_ll is (b if right else a):
                hi = max(x0, x1)
            if m.kind == "create":                  # шапка созданного объекта — на уровне стрелки
                if right_ll is b:
                    hi = min(hi, b.left - 4)
                if left_ll is b:
                    lo = max(lo, b.left + b.w + 4)
            src_edge = (left_ll is a) if right else (right_ll is a)
            L = self._label_w(m)
            if src_edge:
                cx = (lo + L / 2 + LABEL_GAP) if right else (hi - L / 2 - LABEL_GAP)
            else:
                cx = (lo + hi) / 2
            cx = min(max(cx, lo + L / 2 + 4), hi - L / 2 - 4) if hi - lo > L + 8 else (lo + hi) / 2
            m.label_c = (cx, y - (LINE_H / 2 + 3))

    def _frames(self):
        def extent(f):
            xs = []
            for op in f.operands:
                for m in op.msgs:
                    for k in (m.a, m.b):
                        ll = self.lls[k]
                        xs += [ll.cx + ACT_W]
                    xs += [p[0] for p in m.points]
                    if m.kind == "create":      # голова созданного объекта — внутри рамки
                        xs += [self.lls[m.b].left + self.lls[m.b].w - 4]
                    if m.label_c:
                        L = tw(m.label()) + 6
                        xs += [m.label_c[0] + L / 2]
            for c in f.children:
                extent(c)
                xs += [c.right + 10]
            x_min = self.lls[self.order[self._frag_min_idx(f)]].cx
            f.left = int(x_min - self._frag_pad(f))
            for c in f.children:
                f.left = min(f.left, c.left - 10)
            gw = max((tw(f"[{op.guard}]") for op in f.operands if op.guard), default=0)
            f.right = int(max(max(xs) + 14, f.left + GUARD_DX + gw + 10))
        for f in self.frags:
            if f.parent is None:
                extent(f)
        shift = max(0, 20 - min((f.left for f in self.frags), default=20))
        if shift:
            for ll in self.lls.values():
                ll.cx += shift
                ll.x, ll.left = ll.cx, ll.left + shift
            for m in self.msgs:
                m.points = [(x + shift, y) for x, y in m.points]
                if m.act:
                    m.act = (m.act[0] + shift, m.act[1], m.act[2])
                if m.label_c:
                    m.label_c = (m.label_c[0] + shift, m.label_c[1])
            for f in self.frags:
                f.left += shift
                f.right += shift

    # ---------------------------------------------------------------- количественная характеристика
    def quantitative(self):
        k = [m.kind for m in self.msgs]
        fr = {}
        for f in self.frags:
            fr[f.kind] = fr.get(f.kind, 0) + 1
        frs = ", ".join(f"{n} — {c}" for n, c in sorted(fr.items())) if fr else "нет"
        return (f"Количественная характеристика диаграммы: линий жизни — {len(self.lls)} (акторов — "
                f"{sum(1 for ll in self.lls.values() if ll.is_actor)}); сообщений — {len(self.msgs)}: синхронных "
                f"вызовов — {k.count('call')}, асинхронных — {k.count('async')}, ответов — {k.count('reply')}, «create» — "
                f"{k.count('create')}; комбинированных фрагментов — {len(self.frags)} ({frs}).")


# ==================================================================== StarUML 6 (.mdj)

def _pts6(points):
    return ";".join(f"{int(round(x))}:{int(round(y))}" for x, y in points)


def mdj_interaction(mod, owner, it, cls6, ops6, actors6):
    """UMLCollaboration взаимодействия it в ownedElements owner (dict); cls6 / actors6 — объекты классов и акторов,
    ops6[(ключ класса, имя операции)] — операции."""
    node, ref = mod.node, mod.ref
    col = node("UMLCollaboration", owner, name=it.name, documentation=f"Кооперация взаимодействия «{it.name}».")
    inter = node("UMLInteraction", col, name=it.name, documentation=it.doc)
    roles, lfs = [], {}
    for k in it.order:
        ll = it.lls[k]
        t = cls6[ll.cls] if ll.cls else actors6[ll.actor]
        r = node("UMLAttribute", col, name=ll.name, type=ref(t))
        roles.append(r)
        lf = node("UMLLifeline", inter, name=ll.name, represent=ref(r), documentation=ll.doc)
        if ll.stereo:
            lf["stereotype"] = ll.stereo
        lfs[k] = lf
    msgs = []
    for m in it.msgs:
        o = node("UMLMessage", inter, source=ref(lfs[m.a]), target=ref(lfs[m.b]), messageSort=SORT6[m.kind],
                 documentation=m.doc)
        if m.kind in ("call", "async"):
            o["signature"] = ref(ops6[(m.op_cls, m.op)])
            o["name"] = m.op
            if m.args is not None:
                o["arguments"] = m.args
        elif m.kind == "reply":
            o["name"] = m.text
        m.obj6 = o
        msgs.append(o)
    frags = []
    for f in it.frags:
        o = node("UMLCombinedFragment", inter, interactionOperator=f.kind, documentation=f.doc)
        o["operands"] = []
        for op in f.operands:
            oo = node("UMLInteractionOperand", o, guard=op.guard, documentation=op.doc)
            op.obj6 = oo
            o["operands"].append(oo)
        f.obj6 = o
        frags.append(o)
    dg = node("UMLSequenceDiagram", inter, name=it.diagram,
              documentation=(it.diagram_doc + "\n\n" if it.diagram_doc else "") + it.quantitative(),
              showSequenceNumber=True, showSignature=True, showActivation=True, sequenceNumbering="auto")
    views, lp = [], {}
    for f in it.frags:                                    # фрагменты — под сообщениями (zIndex у StarUML свой)
        v = node("UMLCombinedFragmentView", dg, model=ref(f.obj6), left=f.left, top=f.top,
                 width=f.right - f.left, height=f.bottom - f.top)
        oc = node("UMLInteractionOperandCompartmentView", v, model=ref(f.obj6), left=f.left,
                  top=f.operands[0].top + FRAME_HDR, width=f.right - f.left,
                  height=f.bottom - f.operands[0].top - FRAME_HDR)
        ovs = []
        for i, op in enumerate(f.operands):
            top = op.top + FRAME_HDR if i == 0 else op.top
            ovs.append(node("UMLInteractionOperandView", oc, model=ref(op.obj6), left=f.left, top=top,
                            width=f.right - f.left, height=max(op.bottom - top, 15)))
        oc["subViews"] = ovs
        v["operandCompartment"] = ref(oc)
        v["subViews"] = [oc]
        views.append(v)
    for k in it.order:
        ll = it.lls[k]
        hh = ll.head_h()
        v = node("UMLSeqLifelineView", dg, model=ref(lfs[k]), left=ll.left, top=ll.top, width=ll.w,
                 height=ll.line_bottom - ll.top, stereotypeDisplay="icon" if ll.is_actor else "label")
        p = node("UMLLinePartView", v, model=ref(lfs[k]), left=ll.cx, top=ll.top + hh + 1, width=1,
                 height=ll.line_bottom - (ll.top + hh + 1))
        v["linePart"] = ref(p)
        v["subViews"] = [p]
        lp[k] = p
        views.append(v)
    for m in it.msgs:
        v = node("UMLSeqMessageView", dg, model=ref(m.obj6), tail=ref(lp[m.a]), head=ref(lp[m.b]),
                 points=_pts6(m.points), lineStyle=0, showType=False)
        al, ds = alpha_distance(m.points, m.label_c)
        sa, sd = alpha_distance(m.points, (m.label_c[0], m.label_c[1] - LINE_H))
        subs = []
        for nm, vis, a_, d_ in (("nameLabel", True, al, ds),
                                ("stereotypeLabel", m.kind == "create", sa, sd),
                                ("propertyLabel", False, -math.pi / 2, 10)):
            lb = node("EdgeLabelView", v, model=ref(m.obj6), visible=vis, alpha=a_, distance=d_, hostEdge=ref(v),
                      edgePosition=1)
            v[nm] = ref(lb)
            subs.append(lb)
        if m.act:
            act = node("UMLActivationView", v, model=ref(m.obj6), left=m.act[0], top=m.act[1], width=ACT_W,
                       height=m.act[2], visible=True)
        else:
            x = m.points[-1][0]
            act = node("UMLActivationView", v, model=ref(m.obj6), left=int(x), top=m.y, width=ACT_W, height=ACT_MIN,
                       visible=False)
        v["activation"] = ref(act)
        subs.append(act)
        v["subViews"] = subs
        views.append(v)
    dg["ownedViews"] = views
    inter["participants"] = list(lfs.values())
    inter["messages"] = msgs
    if frags:
        inter["fragments"] = frags
    inter["ownedElements"] = [dg]
    col["attributes"] = roles
    col["ownedElements"] = [inter]
    owner.setdefault("ownedElements", []).append(col)
    return col


# ==================================================================== StarUML 5.0 (.uml)

def _pts5(points):
    return ";".join(f"{int(round(x))},{int(round(y))}" for x, y in points)


def _label5(role, text, alpha, dist, model=None, host=None, visible=True, edge=True):
    lb = Obj("EdgeLabelView" if edge else "LabelView")
    if not visible:
        lb.attr("Visible", False)
    if edge:
        lb.attr("Alpha", float(alpha)).attr("Distance", float(dist))
    if text:
        lb.attr("Text", text)
    if model is not None:
        lb.ref("Model", model)
    if host is not None:
        lb.ref("HostEdge", host)
    return role, lb


def xpd_interaction(owner, it, cls5, ops5, actors5, back):
    """UMLCollaborationInstanceSet взаимодействия it; owner — классификатор-владелец (Obj).
    back — словарь обратных ссылок {id(Obj): {имя: [...]}}, проставляется вызывающим после всех взаимодействий."""
    def br(o, name, x):
        back.setdefault(id(o), {"obj": o}).setdefault(name, []).append(x)

    cis = Obj("UMLCollaborationInstanceSet")
    iis = Obj("UMLInteractionInstanceSet")
    objs = {k: Obj("UMLObject") for k in it.order}
    stims = {id(m): Obj("UMLStimulus") for m in it.msgs}
    frag5 = {id(f): Obj("UMLCombinedFragment") for f in it.frags}
    oper5 = {id(op): Obj("UMLInteractionOperand") for f in it.frags for op in f.operands}
    dg = Obj("UMLSequenceDiagram")
    dv = Obj("UMLSequenceDiagramView")
    obj_views = {k: [] for k in it.order}
    stim_views = {id(m): [] for m in it.msgs}
    owned, lifeline_v = [], {}
    # ---- представления
    for f in it.frags:
        v = Obj("UMLCombinedFragmentView")
        v.attr("Left", int(f.left)).attr("Top", int(f.top)).attr("Width", int(f.right - f.left))
        v.attr("Height", int(f.bottom - f.top)).ref("Model", frag5[id(f)])
        v.child("NameLabel", Obj("LabelView")).attr("Visible", False)
        v.child("FrameTypeLabel", Obj("LabelView")).attr("FontStyle", 1).attr("Text", f.kind)
        ops = []
        for i, op in enumerate(f.operands):
            top = op.top + FRAME_HDR if i == 0 else op.top
            ov = Obj("UMLInteractionOperandView")
            ov.attr("Left", int(f.left)).attr("Top", int(top)).attr("Width", int(f.right - f.left))
            ov.attr("Height", int(max(op.bottom - top, 15))).ref("Model", oper5[id(op)]).ref("ContainerView", v)
            gl = ov.child("GuardLabel", Obj("LabelView"))
            if op.guard:
                gl.attr("Text", f"[{op.guard}]")
            else:
                gl.attr("Visible", False)
            br(oper5[id(op)], "Views", ov)
            ops.append(ov)
        v.children("ContainedViews", ops)
        br(frag5[id(f)], "Views", v)
        owned.append(v)
    for k in it.order:
        ll = it.lls[k]
        v = Obj("UMLSeqObjectView")
        v.attr("Left", int(ll.left)).attr("Top", int(ll.top)).attr("Width", int(ll.w))
        v.attr("Height", int(ll.line_bottom - ll.top))
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
        lv = v.child("LifeLine", Obj("UMLLifeLineView"))
        lv.ref("Model", objs[k])
        lifeline_v[k] = lv
        obj_views[k] += [v, lv]
        owned.append(v)
    for m in it.msgs:
        s = stims[id(m)]
        v = Obj("UMLSeqStimulusView")
        v.attr("LineStyle", "lsRectilinear", "LineStyleKind").attr("Points", _pts5(m.points), "Points")
        v.ref("Model", s).ref("Head", lifeline_v[m.b]).ref("Tail", lifeline_v[m.a])
        al, ds = alpha_distance(m.points, m.label_c)
        sa, sd = alpha_distance(m.points, (m.label_c[0], m.label_c[1] - LINE_H))
        labs = [_label5("NameLabel", m.label(), al, ds, s, v),
                _label5("StereotypeLabel", "<<create>>" if m.kind == "create" else "", sa, sd, s, v,
                        visible=m.kind == "create"),
                _label5("PropertyLabel", "", -math.pi / 2, 10, None, v, visible=False)]
        for role, lb in labs:
            v.child(role, lb)
        act = v.child("Activation", Obj("UMLActivationView"))
        if m.act:
            act.attr("Left", int(m.act[0])).attr("Top", int(m.act[1])).attr("Width", ACT_W).attr("Height", int(m.act[2]))
        else:
            act.attr("Visible", False).attr("Left", int(m.points[-1][0])).attr("Top", int(m.y)).attr("Width", ACT_W)
            act.attr("Height", ACT_MIN)
        stim_views[id(m)] += [v, labs[0][1], labs[1][1]]
        owned.append(v)
    dv.ref("Diagram", dg).children("OwnedViews", owned)
    dg.attr("Name", it.diagram)
    dg.attr("Documentation", (it.diagram_doc + "\n\n" if it.diagram_doc else "") + it.quantitative())
    dg.ref("DiagramOwner", iis)
    dg.child("DiagramView", dv)
    # ---- модель
    for m in it.msgs:
        s = stims[id(m)]
        if m.kind == "reply":
            s.attr("Name", m.text)
        if m.args is not None:
            s.attr("Arguments", m.args)
        if m.doc:
            s.attr("Documentation", m.doc)
        s.ref("Sender", objs[m.a]).ref("Receiver", objs[m.b])
        if m.kind in ("call", "async"):
            a = Obj("UMLCallAction")
            if m.kind == "async":
                a.attr("IsAsynchronous", True)
            op = ops5[(m.op_cls, m.op)]
            a.ref("Stimulus", s).ref("Operation", op)
            br(op, "CallActions", a)
        elif m.kind == "create":
            a = Obj("UMLCreateAction")
            ll = it.lls[m.b]
            cl = cls5[ll.cls] if ll.cls else actors5[ll.actor]
            a.ref("Stimulus", s).ref("Instantiation", cl)
            br(cl, "CreateActions", a)
        else:
            a = Obj("UMLReturnAction")
            a.ref("Stimulus", s)
        s.child("Action", a)
        s.ref("InteractionInstanceSet", iis)
        s.refs("Views", stim_views[id(m)])
    for k in it.order:
        ll, o = it.lls[k], objs[k]
        if ll.name:
            o.attr("Name", ll.name)
        if ll.doc:
            o.attr("Documentation", ll.doc)
        if ll.stereo and not ll.is_actor and not ll.worker:
            o.attr("StereotypeProfile", "UMLStandard").attr("StereotypeName", ll.stereo)
        cl = cls5[ll.cls] if ll.cls else actors5[ll.actor]
        o.ref("Classifier", cl).ref("CollaborationInstanceSet", cis)
        br(cl, "Instances", o)
        o.refs("Views", obj_views[k])
        o.refs("SendingStimuli", [stims[id(m)] for m in it.msgs if m.a == k])
        o.refs("ReceivingStimuli", [stims[id(m)] for m in it.msgs if m.b == k])
    frs = []
    for f in it.frags:
        fo = frag5[id(f)]
        if f.doc:
            fo.attr("Documentation", f.doc)
        fo.attr("InteractionOperator", OPERATOR5[f.kind], "UMLInteractionOperatorKind")
        fo.ref("EnclosingInteractionInstanceSet", iis)
        ops = []
        for op in f.operands:
            oo = oper5[id(op)]
            if op.guard:
                oo.attr("Guard", op.guard)
            if op.doc:
                oo.attr("Documentation", op.doc)
            oo.ref("CombinedFragment", fo)
            ops.append(oo)
        fo.children("Operands", ops)
        frs.append(fo)
    iis.attr("Name", it.name).attr("Documentation", it.doc).ref("Context", cis)
    iis.children("OwnedDiagrams", [dg])
    iis.children("ParticipatingStimuli", [stims[id(m)] for m in it.msgs])
    iis.children("Fragments", frs)
    for f in it.frags:
        frag5[id(f)].refs("Views", back.get(id(frag5[id(f)]), {}).pop("Views", []))
        for op in f.operands:
            oper5[id(op)].refs("Views", back.get(id(oper5[id(op)]), {}).pop("Views", []))
    cis.attr("Name", it.name).attr("Documentation", f"Набор экземпляров взаимодействия «{it.name}».")
    cis.ref("RepresentedClassifier", owner)
    cis.children("InteractionInstanceSets", [iis])
    cis.children("ParticipatingInstances", [objs[k] for k in it.order])
    return cis


def xpd_backrefs(back):
    """Обратные ссылки у классов, акторов и операций модели (Instances, CallActions, CreateActions)."""
    for rec in back.values():
        o = rec["obj"]
        for name in ("Instances", "CallActions", "CreateActions"):
            if rec.get(name):
                o.refs(name, rec[name])
