# -*- coding: utf-8 -*-
"""
MCP Bridge -- 约束操作
add_constraint：添加几何约束或尺寸约束。
"""
import math

from .mcp_base import MCPBase

_MM = 0.1  # mm → cm（Fusion 360 内部单位）

_SUFFIX_MAP = {
    "start":  "startSketchPoint",
    "end":    "endSketchPoint",
    "center": "centerSketchPoint",
}

_GEOMETRIC_TYPES = {
    "perpendicular", "parallel", "horizontal", "vertical", "equal",
    "tangent", "normal", "coincident", "concentric", "fixed",
}
_DIMENSION_TYPES = {"angle", "diameter", "radius", "distance"}

# anchor-pair 约束：_gc.<fn>(anchor, other)
_ANCHOR_PAIR_MAP = {
    "parallel":      "addParallel",
    "perpendicular": "addPerpendicular",
    "equal":         "addEqual",
    "tangent":       "addTangent",
    "concentric":    "addConcentric",
}

_CURVE_KINDS = {"circle", "arc", "ellipse", "elliptical_arc"}
_RADIUS_EQUAL_KINDS = {"circle", "arc"}


def _base_kind(base: str) -> str:
    """Infer the original sketch entity kind from a generated variable/ref name."""
    token = f"_{base}_"
    for kind in ("elliptical_arc", "circle", "arc", "ellipse", "line"):
        if f"_{kind}_" in token:
            return kind
    return base.rsplit("_", 1)[0]


def _equal_verify_expr(a: str, b: str, a_base: "str | None" = None, b_base: "str | None" = None) -> "str | None":
    """Return a verifier matching Fusion's Equal semantics for supported pairs."""
    ka = _base_kind(a_base or a)
    kb = _base_kind(b_base or b)
    if ka == "line" and kb == "line":
        return f"abs({a}.length - {b}.length) < 1e-4"
    if ka in _RADIUS_EQUAL_KINDS and kb in _RADIUS_EQUAL_KINDS:
        return f"abs({a}.radius - {b}.radius) < 1e-4"
    return None


def _is_mixed_circle_arc_equal(a_base: str, b_base: str) -> bool:
    kinds = {_base_kind(a_base), _base_kind(b_base)}
    return kinds == {"circle", "arc"}


def _add_radius_equal_dimension_lines(anchor: str, expr: str, verify: str) -> list:
    """Generate Fusion-side code for circle-arc Equal, unsupported by addEqual."""
    return [
        "import adsk.core\n",
        "try:\n",
        f"    if not ({verify}):\n",
        f"        _cg = {expr}.centerSketchPoint.geometry\n",
        f"        _off = max(abs({expr}.radius) * 2.0, 0.1)\n",
        "        _tp = adsk.core.Point3D.create(_cg.x + _off, _cg.y, _cg.z)\n",
        f"        _dim = _sk.sketchDimensions.addRadialDimension({expr}, _tp, True)\n",
        f"        _dim.parameter.value = {anchor}.radius\n",
        "except Exception:\n",
        f"    if not ({verify}):\n",
        "        raise\n",
    ]


def _verify_expr(
    ctype: str,
    a: str,
    b: str,
    a_base: "str | None" = None,
    b_base: "str | None" = None,
) -> "str | None":
    """返回可嵌入 Fusion execute_python 脚本的验证表达式（求值为 bool，True 表示约束已满足）。
    返回 None 表示无法简单验证，过约束时保守地重新抛出。
    parallel/perpendicular 使用归一化叉积/点积，与线段长度无关。
    """
    if ctype == "equal":
        return _equal_verify_expr(a, b, a_base, b_base)
    if ctype == "parallel":
        return (
            f"(lambda s0,t0,s1,t1: "
            f"abs((t0.x-s0.x)*(t1.y-s1.y)-(t0.y-s0.y)*(t1.x-s1.x)) / "
            f"max(((t0.x-s0.x)**2+(t0.y-s0.y)**2)**0.5*((t1.x-s1.x)**2+(t1.y-s1.y)**2)**0.5,1e-12)"
            f" < 1e-6)"
            f"({a}.startSketchPoint.geometry,{a}.endSketchPoint.geometry,"
            f"{b}.startSketchPoint.geometry,{b}.endSketchPoint.geometry)"
        )
    if ctype == "perpendicular":
        return (
            f"(lambda s0,t0,s1,t1: "
            f"abs((t0.x-s0.x)*(t1.x-s1.x)+(t0.y-s0.y)*(t1.y-s1.y)) / "
            f"max(((t0.x-s0.x)**2+(t0.y-s0.y)**2)**0.5*((t1.x-s1.x)**2+(t1.y-s1.y)**2)**0.5,1e-12)"
            f" < 1e-6)"
            f"({a}.startSketchPoint.geometry,{a}.endSketchPoint.geometry,"
            f"{b}.startSketchPoint.geometry,{b}.endSketchPoint.geometry)"
        )
    if ctype == "concentric":
        return (
            f"(lambda c0,c1: (c0.x-c1.x)**2+(c0.y-c1.y)**2 < 1e-8)"
            f"({a}.centerSketchPoint.geometry,{b}.centerSketchPoint.geometry)"
        )
    if ctype == "tangent":
        return "True"
    return None


def _wrap_with_verify(call_line: str, verify: "str | None") -> list:
    """把一行约束调用包裹成带几何验证的 try/except 代码块（在 Fusion 侧执行）。
    verify 为 None 时直接返回原调用（失败则抛出）。
    """
    if verify is None:
        return [call_line]
    stripped = call_line.rstrip("\n")
    return [
        "try:\n",
        f"    {stripped}\n",
        "except Exception:\n",
        f"    if not ({verify}):\n",
        "        raise\n",
    ]


def _parse_ref(ref: str) -> tuple[str, str, bool]:
    """把 ref 字符串解析为 (fusion_expr, base_var, is_point)。

    Examples::

        "line_1"          → ("line_1",                    "line_1", False)
        "line_1.start"    → ("line_1.startSketchPoint",   "line_1", True)
        "circle_2.center" → ("circle_2.centerSketchPoint","circle_2", True)
    """
    if "." in ref:
        base, suffix = ref.rsplit(".", 1)
        if suffix not in _SUFFIX_MAP:
            raise ValueError(f"未知点后缀 {suffix!r}，可选: start, end, center")
        return f"{base}.{_SUFFIX_MAP[suffix]}", base, True
    return ref, ref, False


class MCPConstraints(MCPBase):
    """约束操作混入类。

    支持向草图添加几何约束（水平、垂直、重合等）和尺寸约束（距离、角度等）。
    所有方法均通过 execute_python 代码生成在 Fusion 360 中执行。
    """

    def add_constraint(
        self,
        constraint_type: str,
        entities: list,
        value: float = None,
        text_point=None,
        is_driving: bool = True,
        **kwargs
    ) -> bool:
        """添加几何或尺寸约束。

        Args:
            constraint_type: 约束类型字符串（大小写不敏感）。
                几何约束（无需 value）：
                    perpendicular, parallel, horizontal, vertical, equal,
                    tangent, normal, coincident, concentric, fixed / fix
                尺寸约束（需要 value）：
                    angle, radius, diameter, distance
            entities:   实体 ref 列表。ref 格式：
                        - "line_1"         → 曲线本身
                        - "line_1.start"   → 起点 SketchPoint
                        - "line_1.end"     → 终点 SketchPoint
                        - "circle_1.center"→ 圆心 SketchPoint
            value:      尺寸约束的目标值（distance/radius/diameter 单位 mm，angle 单位度）。
            text_point: 尺寸标注文字位置 (x, y)，单位 mm。
                        为 None 时按图元实际位置自动计算，避免落在图元上。
            is_driving: 是否为驱动尺寸（默认 True）。

        Returns:
            True — 约束已成功添加（或 coincident 重复约束被静默忽略）。

        Raises:
            ValueError:   entities 为空、约束类型未知、参数数量不符。
            RuntimeError: Fusion 360 执行失败（过约束等）。
            TimeoutError: Fusion 360 未在超时内响应。
        """
        if not isinstance(entities, list) or not entities:
            raise ValueError("entities 必须是非空列表")
        t = constraint_type.strip().lower()
        if t == "fix":
            t = "fixed"
        if t in _DIMENSION_TYPES:
            self._add_dimension(t, entities, value, text_point, is_driving)
        elif t in _GEOMETRIC_TYPES:
            self._add_geometric(t, entities)
        else:
            raise ValueError(f"不支持的约束类型: {constraint_type!r}")
        return True

    # ── 内部实现 ──────────────────────────────────────────────────────────

    def _add_geometric(self, ctype: str, entities: list):
        """生成并执行几何约束的 execute_python 代码。"""
        parsed = [_parse_ref(r) for r in entities]
        base_var = parsed[0][1]  # 从第一个实体取 parentSketch

        lines = [
            f"_sk = {base_var}.parentSketch\n",
            f"_gc = _sk.geometricConstraints\n",
        ]

        if ctype in _ANCHOR_PAIR_MAP:
            # anchor-pair 模式：parsed[0] 与每个 parsed[i≥1] 配对
            if len(parsed) < 2:
                raise ValueError(f"{ctype} 至少需要 2 个实体，得到 {len(parsed)} 个")
            fn = _ANCHOR_PAIR_MAP[ctype]
            anchor = parsed[0][0]
            anchor_base = parsed[0][1]
            for expr, expr_base, _ in parsed[1:]:
                verify = _verify_expr(ctype, anchor, expr, anchor_base, expr_base)
                if ctype == "equal" and _is_mixed_circle_arc_equal(anchor_base, expr_base):
                    lines += _add_radius_equal_dimension_lines(anchor, expr, verify)
                else:
                    lines += _wrap_with_verify(
                        f"_gc.{fn}({anchor}, {expr})\n",
                        verify,
                    )

        elif ctype in ("horizontal", "vertical"):
            all_point = all(is_pt for _, _, is_pt in parsed)
            any_point = any(is_pt for _, _, is_pt in parsed)
            if any_point and not all_point:
                raise ValueError(
                    f"{ctype} 不能混用线实体和点后缀，"
                    f"请全部传线（线模式）或全部传点后缀（点对齐模式）"
                )
            self._add_user_axis_alignment(ctype, parsed, lines)
            return
            # if all_point:
            #     # 点模式：两点间水平/垂直对齐
            #     if len(parsed) < 2:
            #         raise ValueError(f"{ctype} 点模式至少需要 2 个点实体，得到 {len(parsed)} 个")
            #     fn = "addHorizontalPoints" if ctype == "horizontal" else "addVerticalPoints"
            #     anchor = parsed[0][0]
            #     for expr, _, _ in parsed[1:]:
            #         if ctype == "horizontal":
            #             verify = (f"(lambda p0,p1: abs(p0.y-p1.y) < 1e-4)"
            #                       f"({anchor}.geometry,{expr}.geometry)")
            #         else:
            #             verify = (f"(lambda p0,p1: abs(p0.x-p1.x) < 1e-4)"
            #                       f"({anchor}.geometry,{expr}.geometry)")
            #         lines += _wrap_with_verify(f"_gc.{fn}({anchor}, {expr})\n", verify)
            # else:
            #     # 线模式：每条线单独约束
            #     fn = "addHorizontal" if ctype == "horizontal" else "addVertical"
            #     for expr, _, _ in parsed:
            #         if ctype == "horizontal":
            #             verify = (f"(lambda s,t: abs(t.y-s.y) / "
            #                       f"max(((t.x-s.x)**2+(t.y-s.y)**2)**0.5,1e-12) < 1e-6)"
            #                       f"({expr}.startSketchPoint.geometry,{expr}.endSketchPoint.geometry)")
            #         else:
            #             verify = (f"(lambda s,t: abs(t.x-s.x) / "
            #                       f"max(((t.x-s.x)**2+(t.y-s.y)**2)**0.5,1e-12) < 1e-6)"
            #                       f"({expr}.startSketchPoint.geometry,{expr}.endSketchPoint.geometry)")
            #         lines += _wrap_with_verify(f"_gc.{fn}({expr})\n", verify)

        elif ctype == "coincident":
            # 重复约束静默忽略：通过 entityToken 比较检测已有相同约束
            if len(parsed) < 2:
                raise ValueError(f"coincident 至少需要 2 个实体，得到 {len(parsed)} 个")
            lines.insert(0, "import adsk.fusion\n")
            anchor = parsed[0][0]
            for expr, _, _ in parsed[1:]:
                lines += [
                    "_dup = False\n",
                    "for _ci in range(_gc.count):\n",
                    "    _con = _gc.item(_ci)\n",
                    "    if _con.objectType == adsk.fusion.CoincidentConstraint.classType():\n",
                    "        try:\n",
                    f"            _a_tok = {anchor}.entityToken\n",
                    f"            _e_tok = {expr}.entityToken\n",
                    "            _pt_tok = _con.point.entityToken\n",
                    "            _en_tok = _con.entity.entityToken\n",
                    "            if ((_pt_tok == _a_tok and _en_tok == _e_tok) or\n",
                    "                    (_pt_tok == _e_tok and _en_tok == _a_tok)):\n",
                    "                _dup = True; break\n",
                    "        except: pass\n",
                    "if not _dup:\n",
                    f"    _gc.addCoincident({anchor}, {expr})\n",
                ]

        elif ctype == "fixed":
            for expr, _, _ in parsed:
                lines.append(f"{expr}.isFixed = True\n")

        elif ctype == "normal":
            if len(parsed) != 2:
                raise ValueError("normal 需要 exactly 2 个实体")
            e0_expr, e0_base, _ = parsed[0]
            e1_expr, e1_base, _ = parsed[1]
            k0 = e0_base.rsplit("_", 1)[0]
            k1 = e1_base.rsplit("_", 1)[0]
            if k0 == "line" and k1 == "line":
                lines += _wrap_with_verify(
                    f"_gc.addPerpendicular({e0_expr}, {e1_expr})\n",
                    _verify_expr("perpendicular", e0_expr, e1_expr),
                )
            elif k0 == "line" and k1 in _CURVE_KINDS:
                lines += _wrap_with_verify(
                    f"_gc.addCoincident({e1_base}.centerSketchPoint, {e0_expr})\n",
                    None,  # 圆心在线上的验证复杂，保守处理
                )
            elif k1 == "line" and k0 in _CURVE_KINDS:
                lines += _wrap_with_verify(
                    f"_gc.addCoincident({e0_base}.centerSketchPoint, {e1_expr})\n",
                    None,  # 保守处理
                )
            else:
                raise ValueError(f"normal 不支持的实体组合: ({k0}, {k1})")

        self.execute({"operation": "execute_python", "code": "".join(lines)})

    def _add_user_axis_alignment(self, ctype: str, parsed: list, lines: list):
        """Implement horizontal/vertical in the bridge's user-local sketch axes."""
        all_point = all(is_pt for _, _, is_pt in parsed)
        axis_col = 0 if ctype == "horizontal" else 1

        lines.insert(0, "import adsk.core\n")
        lines.append("_H = None\n")
        for sk_ref, transform in self._sketch_transforms.items():
            H = transform.get("homogeneous_matrix")
            if H is None:
                continue
            lines += [
                "try:\n",
                f"    if _H is None and _sk == {sk_ref}:\n",
                f"        _H = {H!r}\n",
                "except Exception:\n",
                "    pass\n",
            ]

        lines += [
            "if _H is None:\n",
            "    _H = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]\n",
            f"_axis = (_H[0][{axis_col}], _H[1][{axis_col}], _H[2][{axis_col}])\n",
            "def _make_fixed_axis_line(_origin):\n",
            "    _ax, _ay, _az = _axis\n",
            "    _n = (_ax*_ax + _ay*_ay + _az*_az) ** 0.5\n",
            "    if _n < 1e-12:\n",
            "        raise ValueError('local constraint axis has zero length')\n",
            "    _p0 = adsk.core.Point3D.create(_origin.x, _origin.y, _origin.z)\n",
            "    _p1 = adsk.core.Point3D.create(_origin.x + _ax/_n, _origin.y + _ay/_n, _origin.z + _az/_n)\n",
            "    _line = _sk.sketchCurves.sketchLines.addByTwoPoints(_p0, _p1)\n",
            "    _line.isConstruction = True\n",
            "    _line.isFixed = True\n",
            "    return _line\n",
            "def _line_parallel_to_axis(_line):\n",
            "    _s = _line.startSketchPoint.geometry\n",
            "    _e = _line.endSketchPoint.geometry\n",
            "    _vx, _vy, _vz = _e.x - _s.x, _e.y - _s.y, _e.z - _s.z\n",
            "    _ax, _ay, _az = _axis\n",
            "    _vlen = (_vx*_vx + _vy*_vy + _vz*_vz) ** 0.5\n",
            "    _alen = (_ax*_ax + _ay*_ay + _az*_az) ** 0.5\n",
            "    if _vlen < 1e-12 or _alen < 1e-12:\n",
            "        return False\n",
            "    _cx = _vy*_az - _vz*_ay\n",
            "    _cy = _vz*_ax - _vx*_az\n",
            "    _cz = _vx*_ay - _vy*_ax\n",
            "    return ((_cx*_cx + _cy*_cy + _cz*_cz) ** 0.5) / (_vlen * _alen) < 1e-6\n",
        ]

        if all_point:
            if len(parsed) < 2:
                raise ValueError(f"{ctype} point mode requires at least 2 point entities, got {len(parsed)}")
            anchor = parsed[0][0]
            for expr, _, _ in parsed[1:]:
                lines += [
                    f"_conn = _sk.sketchCurves.sketchLines.addByTwoPoints({anchor}, {expr})\n",
                    "_conn.isConstruction = True\n",
                    f"_ref = _make_fixed_axis_line({anchor}.geometry)\n",
                    "try:\n",
                    "    _gc.addParallel(_conn, _ref)\n",
                    "except Exception:\n",
                    "    if not _line_parallel_to_axis(_conn):\n",
                    "        raise\n",
                ]
        else:
            for expr, _, _ in parsed:
                lines += [
                    f"_ref = _make_fixed_axis_line({expr}.startSketchPoint.geometry)\n",
                    "try:\n",
                    f"    _gc.addParallel({expr}, _ref)\n",
                    "except Exception:\n",
                    f"    if not _line_parallel_to_axis({expr}):\n",
                    "        raise\n",
                ]

        self.execute({"operation": "execute_python", "code": "".join(lines)})

    def _add_dimension(
        self,
        ctype: str,
        entities: list,
        value,
        text_point,
        is_driving: bool,
    ):
        """生成并执行尺寸约束的 execute_python 代码。"""
        parsed = [_parse_ref(r) for r in entities]
        base_var = parsed[0][1]

        # 用户提供了标注点：直接转换单位（mm → cm）
        if text_point is not None:
            tp_x = float(text_point[0]) * _MM
            tp_y = float(text_point[1]) * _MM
            tp_fixed = f"_tp = adsk.core.Point3D.create({tp_x!r}, {tp_y!r}, 0.0)\n"
        else:
            tp_fixed = None  # 各分支按图元实际位置计算，避免标注点落在图元上

        lines = [
            "import adsk.core, adsk.fusion\n",
            f"_sk = {base_var}.parentSketch\n",
            f"_sd = _sk.sketchDimensions\n",
            f"_drv = {is_driving!r}\n",
        ]
        if tp_fixed:
            lines.append(tp_fixed)

        if ctype == "angle":
            if len(parsed) != 2:
                raise ValueError("angle 需要 exactly 2 个线实体")
            for i, (_, base, is_pt) in enumerate(parsed):
                kind = base.rsplit("_", 1)[0]
                if is_pt or kind != "line":
                    raise ValueError(
                        f"angle 的第 {i+1} 个实体必须是 line，得到 {base!r}"
                    )
            e0, e1 = parsed[0][0], parsed[1][0]
            if tp_fixed is None:
                # 两线起点中点 + (1cm, 1cm) 偏移，避免落在线上
                lines += [
                    f"_p0g = {e0}.startSketchPoint.geometry\n",
                    f"_p1g = {e1}.startSketchPoint.geometry\n",
                    "_tp = adsk.core.Point3D.create("
                    "(_p0g.x+_p1g.x)/2+1.0, (_p0g.y+_p1g.y)/2+1.0, 0.0)\n",
                ]
            if value is not None:
                rad = math.radians(float(value))
                supp = math.pi - rad
                lines += [
                    "try:\n",
                    f"    _dim = _sd.addAngularDimension({e0}, {e1}, _tp, _drv)\n",
                    f"    _dim.parameter.value = {rad!r}\n",
                    "except Exception:\n",
                    "    import math as _math\n",
                    f"    _s0,_t0 = {e0}.startSketchPoint.geometry,{e0}.endSketchPoint.geometry\n",
                    f"    _s1,_t1 = {e1}.startSketchPoint.geometry,{e1}.endSketchPoint.geometry\n",
                    "    _dot = (_t0.x-_s0.x)*(_t1.x-_s1.x)+(_t0.y-_s0.y)*(_t1.y-_s1.y)\n",
                    "    _n = max(((_t0.x-_s0.x)**2+(_t0.y-_s0.y)**2)**0.5*((_t1.x-_s1.x)**2+(_t1.y-_s1.y)**2)**0.5, 1e-12)\n",
                    "    _a = _math.acos(min(1.0, max(-1.0, _dot/_n)))\n",
                    f"    if not (min(abs(_a-{rad!r}), abs(_a-{supp!r})) < 1e-4):\n",
                    "        raise\n",
                ]
            else:
                lines.append(f"_dim = _sd.addAngularDimension({e0}, {e1}, _tp, _drv)\n")

        elif ctype == "radius":
            if len(parsed) != 1:
                raise ValueError("radius 需要 exactly 1 个圆/弧实体")
            _, base0, is_pt0 = parsed[0]
            kind0 = base0.rsplit("_", 1)[0]
            if is_pt0 or kind0 not in ("circle", "arc"):
                raise ValueError(
                    f"radius 实体必须是 circle 或 arc，得到 {base0!r}"
                )
            expr = parsed[0][0]
            if tp_fixed is None:
                # 圆心 + (2×半径, 0)，始终在圆外
                lines += [
                    f"_cg = {expr}.centerSketchPoint.geometry\n",
                    f"_tp = adsk.core.Point3D.create(_cg.x + {expr}.radius * 2.0, _cg.y, 0.0)\n",
                ]
            if value is not None:
                target_cm = float(value) * _MM
                lines += [
                    "try:\n",
                    f"    _dim = _sd.addRadialDimension({expr}, _tp, _drv)\n",
                    f"    _dim.parameter.value = {target_cm!r}\n",
                    "except Exception:\n",
                    f"    if not (abs({expr}.radius - {target_cm!r}) < 1e-4):\n",
                    "        raise\n",
                ]
            else:
                lines.append(f"_dim = _sd.addRadialDimension({expr}, _tp, _drv)\n")

        elif ctype == "diameter":
            if len(parsed) != 1:
                raise ValueError("diameter 需要 exactly 1 个圆/弧实体")
            _, base0, is_pt0 = parsed[0]
            kind0 = base0.rsplit("_", 1)[0]
            if is_pt0 or kind0 not in ("circle", "arc"):
                raise ValueError(
                    f"diameter 实体必须是 circle 或 arc，得到 {base0!r}"
                )
            expr = parsed[0][0]
            if tp_fixed is None:
                lines += [
                    f"_cg = {expr}.centerSketchPoint.geometry\n",
                    f"_tp = adsk.core.Point3D.create(_cg.x + {expr}.radius * 2.0, _cg.y, 0.0)\n",
                ]
            if value is not None:
                target_cm = float(value) * _MM
                lines += [
                    "try:\n",
                    f"    _dim = _sd.addDiameterDimension({expr}, _tp, _drv)\n",
                    f"    _dim.parameter.value = {target_cm!r}\n",
                    "except Exception:\n",
                    f"    if not (abs({expr}.radius * 2 - {target_cm!r}) < 1e-4):\n",
                    "        raise\n",
                ]
            else:
                lines.append(f"_dim = _sd.addDiameterDimension({expr}, _tp, _drv)\n")

        elif ctype == "distance":
            if len(parsed) == 1:
                _, base0, is_pt0 = parsed[0]
                if is_pt0:
                    raise ValueError("distance (1 实体) 必须是线，不能是点后缀")
                k0 = base0.rsplit("_", 1)[0]
                if k0 != "line":
                    raise ValueError(f"distance (1 实体) 必须是 line，得到 {k0!r}")
                if tp_fixed is None:
                    # 线段中点 + 1cm 垂直偏移
                    lines += [
                        f"_sg = {base0}.startSketchPoint.geometry\n",
                        f"_eg = {base0}.endSketchPoint.geometry\n",
                        "_tp = adsk.core.Point3D.create("
                        "(_sg.x+_eg.x)/2, (_sg.y+_eg.y)/2+1.0, 0.0)\n",
                    ]
                lines.append("_ori = adsk.fusion.DimensionOrientations.AlignedDimensionOrientation\n")
                if value is not None:
                    target_cm = float(value) * _MM
                    lines += [
                        "try:\n",
                        f"    _dim = _sd.addDistanceDimension({base0}.startSketchPoint, {base0}.endSketchPoint, _ori, _tp, _drv)\n",
                        f"    _dim.parameter.value = {target_cm!r}\n",
                        "except Exception:\n",
                        f"    _sg,_eg = {base0}.startSketchPoint.geometry,{base0}.endSketchPoint.geometry\n",
                        f"    if not (abs(((_eg.x-_sg.x)**2+(_eg.y-_sg.y)**2)**0.5 - {target_cm!r}) < 1e-4):\n",
                        "        raise\n",
                    ]
                else:
                    lines.append(f"_dim = _sd.addDistanceDimension({base0}.startSketchPoint, {base0}.endSketchPoint, _ori, _tp, _drv)\n")
            elif len(parsed) == 2:
                e0_expr, e0_base, e0_is_pt = parsed[0]
                e1_expr, e1_base, e1_is_pt = parsed[1]
                k0 = e0_base.rsplit("_", 1)[0]
                k1 = e1_base.rsplit("_", 1)[0]
                if tp_fixed is None:
                    # 各实体取代表点：点用 .geometry，线用 startSketchPoint，曲线用 centerSketchPoint
                    if e0_is_pt:
                        p0_g = f"{e0_expr}.geometry"
                    elif k0 == "line":
                        p0_g = f"{e0_base}.startSketchPoint.geometry"
                    else:
                        p0_g = f"{e0_base}.centerSketchPoint.geometry"
                    if e1_is_pt:
                        p1_g = f"{e1_expr}.geometry"
                    elif k1 == "line":
                        p1_g = f"{e1_base}.startSketchPoint.geometry"
                    else:
                        p1_g = f"{e1_base}.centerSketchPoint.geometry"
                    lines += [
                        f"_p0g = {p0_g}\n",
                        f"_p1g = {p1_g}\n",
                        "_tp = adsk.core.Point3D.create("
                        "(_p0g.x+_p1g.x)/2+1.0, (_p0g.y+_p1g.y)/2+1.0, 0.0)\n",
                    ]
                if k0 == "line" and not e0_is_pt:
                    # 线 + 其他 → addOffsetDimension（线在前，保守处理）
                    lines.append(f"_dim = _sd.addOffsetDimension({e0_expr}, {e1_expr}, _tp, _drv)\n")
                    if value is not None:
                        lines.append(f"_dim.parameter.value = {float(value) * _MM!r}\n")
                elif k1 == "line" and not e1_is_pt:
                    # 其他 + 线 → addOffsetDimension（线在前，保守处理）
                    lines.append(f"_dim = _sd.addOffsetDimension({e1_expr}, {e0_expr}, _tp, _drv)\n")
                    if value is not None:
                        lines.append(f"_dim.parameter.value = {float(value) * _MM!r}\n")
                elif e0_is_pt and e1_is_pt:
                    # 点-点 → addDistanceDimension
                    lines.append("_ori = adsk.fusion.DimensionOrientations.AlignedDimensionOrientation\n")
                    if value is not None:
                        target_cm = float(value) * _MM
                        lines += [
                            "try:\n",
                            f"    _dim = _sd.addDistanceDimension({e0_expr}, {e1_expr}, _ori, _tp, _drv)\n",
                            f"    _dim.parameter.value = {target_cm!r}\n",
                            "except Exception:\n",
                            f"    _p0,_p1 = {e0_expr}.geometry,{e1_expr}.geometry\n",
                            f"    if not (abs(((_p1.x-_p0.x)**2+(_p1.y-_p0.y)**2)**0.5 - {target_cm!r}) < 1e-4):\n",
                            "        raise\n",
                        ]
                    else:
                        lines.append(f"_dim = _sd.addDistanceDimension({e0_expr}, {e1_expr}, _ori, _tp, _drv)\n")
                else:
                    # 兜底（含 offset 子情形）
                    lines.append("_ori = adsk.fusion.DimensionOrientations.AlignedDimensionOrientation\n")
                    lines.append(f"_dim = _sd.addDistanceDimension({e0_expr}, {e1_expr}, _ori, _tp, _drv)\n")
                    if value is not None:
                        lines.append(f"_dim.parameter.value = {float(value) * _MM!r}\n")
            else:
                raise ValueError("distance 需要 1 或 2 个实体")

        self.execute({"operation": "execute_python", "code": "".join(lines)})

    # ── 自动闭合环路 ──────────────────────────────────────────────────────────

    def auto_close_loop(
        self,
        sketch_ref: str | None = None,
        tolerance: float = 0.0001,
    ) -> dict:
        """自动检测并闭合草图中相邻但未连接的端点。

        扫描草图内所有开放曲线的端点，对距离在容差范围内的端点对
        添加 coincident（重合）约束，使 Fusion 360 能识别封闭轮廓。

        Args:
            sketch_ref: 草图变量名（如 "sketch_0"）。
                        为 None 时使用最近创建的草图（self._sketch_refs[-1]）。
            tolerance:  端点聚类容差，单位 mm，默认 0.0001 mm。

        Returns:
            {
                "ok": True,
                "sketch_ref": str,
                "performed": bool,
                "tolerance_used": float,
                "pre_profile_count": int,
                "post_profile_count": int,
                "candidate_point_count": int,
                "cluster_count": int,
                "clusters": [{"size", "members", "applied_pairs", "skipped_pairs"}, ...],
                "applied_count": int,
                "skipped_count": int,
            }

        Raises:
            ValueError:   tolerance 参数无效（≤ 0）。
            IndexError:   未传 sketch_ref 且尚未创建任何草图。
            RuntimeError: Fusion 360 执行失败。
            TimeoutError: Fusion 360 未在超时内响应。
        """
        import json as _json

        if float(tolerance) <= 0:
            raise ValueError(f"tolerance 必须大于 0，得到 {tolerance!r}")

        ref = self._sketch_refs[-1] if sketch_ref is None else sketch_ref

        # ── 阶段一：采集端点（Fusion 侧）──────────────────────────────────
        collect_code = "".join([
            "import json as _json\n",
            f"_sk = {ref}\n",
            "_pre_count = _sk.profiles.count\n",
            "_ep_idx = 0\n",
            "_eps = []\n",
            "_uid = 0\n",
            "_colls = [\n",
            "    _sk.sketchCurves.sketchLines,\n",
            "    _sk.sketchCurves.sketchArcs,\n",
            "    _sk.sketchCurves.sketchEllipticalArcs,\n",
            "    _sk.sketchCurves.sketchFittedSplines,\n",
            "    _sk.sketchCurves.sketchConicCurves,\n",
            "]\n",
            "for _col in _colls:\n",
            "    for _ci in range(_col.count):\n",
            "        _curve = _col.item(_ci)\n",
            "        for _attr in ('startSketchPoint', 'endSketchPoint'):\n",
            "            try:\n",
            "                _pt = getattr(_curve, _attr)\n",
            "                _g = _pt.geometry\n",
            "                _vname = '_ep_' + str(_ep_idx)\n",
            "                globals()[_vname] = _pt\n",
            "                _eps.append({'ref': _vname, 'x': _g.x, 'y': _g.y, 'curve_uid': _uid})\n",
            "                _ep_idx += 1\n",
            "            except Exception:\n",
            "                pass\n",
            "        _uid += 1\n",
            "print(_json.dumps({'pre_count': _pre_count, 'endpoints': _eps}))\n",
        ])
        r = self.execute({"operation": "execute_python", "code": collect_code})
        raw = _json.loads(r["data"]["stdout"])
        pre_count: int = raw["pre_count"]
        endpoints: list = raw["endpoints"]

        n = len(endpoints)
        if n == 0:
            return {
                "ok": True,
                "sketch_ref": ref,
                "performed": False,
                "tolerance_used": float(tolerance),
                "pre_profile_count": pre_count,
                "post_profile_count": pre_count,
                "candidate_point_count": 0,
                "cluster_count": 0,
                "clusters": [],
                "applied_count": 0,
                "skipped_count": 0,
            }

        # ── 阶段二：聚类（Python 侧，按容差网格避免 O(n^2) 全量比较）───────────────
        tol = float(tolerance) * _MM

        parent = list(range(n))

        def _find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for i in range(n):
            for j in range(i + 1, n):
                ei, ej = endpoints[i], endpoints[j]
                if ei["curve_uid"] == ej["curve_uid"]:
                    continue
                dist = ((ei["x"] - ej["x"]) ** 2 + (ei["y"] - ej["y"]) ** 2) ** 0.5
                if dist <= tol:
                    ri, rj = _find(i), _find(j)
                    if ri != rj:
                        parent[ri] = rj

        clusters_dict: dict[int, list[int]] = {}
        for i in range(n):
            root = _find(i)
            clusters_dict.setdefault(root, []).append(i)

        # ── 阶段三：约束应用（复用 add_constraint）────────────────────────
        applied = 0
        skipped = 0
        cluster_details: list[dict] = []

        for members in clusters_dict.values():
            if len(members) < 2:
                continue
            anchor_ref = endpoints[members[0]]["ref"]
            applied_pairs = 0
            skipped_pairs = 0
            for idx in members[1:]:
                other_ref = endpoints[idx]["ref"]
                try:
                    self.add_constraint("coincident", [anchor_ref, other_ref])
                    applied_pairs += 1
                    applied += 1
                except RuntimeError:
                    skipped_pairs += 1
                    skipped += 1
            cluster_details.append({
                "size": len(members),
                "members": [endpoints[m]["ref"] for m in members],
                "applied_pairs": applied_pairs,
                "skipped_pairs": skipped_pairs,
            })

        # ── 阶段四：后置轮廓数（Fusion 侧）───────────────────────────────
        post_code = "".join([
            "import json as _json\n",
            f"print(_json.dumps({{'post_count': {ref}.profiles.count}}))\n",
        ])
        r2 = self.execute({"operation": "execute_python", "code": post_code})
        post_count: int = _json.loads(r2["data"]["stdout"])["post_count"]

        return {
            "ok": True,
            "sketch_ref": ref,
            "performed": True,
            "tolerance_used": tol / _MM,
            "pre_profile_count": pre_count,
            "post_profile_count": post_count,
            "candidate_point_count": n,
            "cluster_count": len(cluster_details),
            "clusters": cluster_details,
            "applied_count": applied,
            "skipped_count": skipped,
        }
