# -*- coding: utf-8 -*-
"""
MCP Bridge -- 草图图元操作
add_line：线段
add_circle：圆
add_arc：三点弧
add_ellipse：完整椭圆
add_elliptical_arc：椭圆弧（SVG 风格参数）
add_nurbs：NURBS 样条曲线

用户输入约定：
  坐标/长度单位：毫米（mm），内部转 cm（× 0.1）后发给 Fusion 360
  角度单位：角度制（度），内部转弧度后用于计算
"""
import math

from .mcp_base import MCPBase

_MM = 0.1  # mm → cm（Fusion 360 内部单位）


# ── 模块级纯函数辅助 ──────────────────────────────────────────────────────────


def _default_knots(control_count: int, degree: int, closed: bool) -> list:
    """生成非闭合曲线的 clamped uniform 节点向量。

    closed=True 时节点构造有额外约束，要求调用方显式提供。
    """
    if closed:
        raise ValueError("closed=True 时必须显式提供 knots。")
    interior = control_count - degree - 1
    knots = [0.0] * (degree + 1)
    if interior > 0:
        step = 1.0 / (interior + 1)
        knots.extend(step * i for i in range(1, interior + 1))
    knots.extend([1.0] * (degree + 1))
    return knots


def _rotate_to_local(x: float, y: float, angle_rad: float):
    """将世界坐标旋转到椭圆局部坐标（逆旋转）。"""
    ca, sa = math.cos(angle_rad), math.sin(angle_rad)
    return ca * x + sa * y, -sa * x + ca * y


def _rotate_to_world(x: float, y: float, angle_rad: float):
    """将椭圆局部坐标旋转回世界坐标（正旋转）。"""
    ca, sa = math.cos(angle_rad), math.sin(angle_rad)
    return ca * x - sa * y, sa * x + ca * y


def _solve_elliptical_arc_candidates(
    start_xy, end_xy, major_cm: float, minor_cm: float, angle_rad: float
) -> list:
    """SVG 风格椭圆弧反算：返回两组候选解（中心坐标 + 起始/扫掠角）。

    算法：
    1. 将端点旋转到椭圆局部坐标，再缩放为单位圆空间；
    2. 在缩放空间里求"过两点单位圆"的两个圆心候选；
    3. 将圆心映射回世界坐标，计算对应的起始角和扫掠角。
    """
    sx, sy = start_xy
    ex, ey = end_xy
    # 旋转到局部坐标并归一化
    s1x, s1y = _rotate_to_local(sx, sy, angle_rad)
    e1x, e1y = _rotate_to_local(ex, ey, angle_rad)
    s1x /= major_cm; s1y /= minor_cm
    e1x /= major_cm; e1y /= minor_cm
    dx = e1x - s1x; dy = e1y - s1y
    chord = math.hypot(dx, dy)
    if chord < 1e-9:
        raise ValueError("椭圆弧起终点距离过近。")
    if chord > 2.0 + 1e-9:
        raise ValueError("给定起终点/半轴无法构成椭圆弧，请检查 major/minor 是否足够大。")
    chord = min(chord, 2.0)
    mx = (s1x + e1x) * 0.5; my = (s1y + e1y) * 0.5
    ux = dx / chord; uy = dy / chord
    nx = -uy; ny = ux
    h = math.sqrt(max(0.0, 1.0 - (chord * 0.5) ** 2))
    candidates = []
    for sign in (1.0, -1.0):
        tx = mx + sign * nx * h
        ty = my + sign * ny * h
        # 候选圆心映射回世界坐标
        cx_w, cy_w = _rotate_to_world(tx * major_cm, ty * minor_cm, angle_rad)
        # 计算在归一化空间里的起始角和 CCW/CW 扫掠角
        q1x = s1x - tx; q1y = s1y - ty
        q2x = e1x - tx; q2y = e1y - ty
        theta_s = math.atan2(q1y, q1x)
        theta_e = math.atan2(q2y, q2x)
        d_ccw = (theta_e - theta_s) % (2 * math.pi)
        d_cw  = (2 * math.pi - d_ccw) % (2 * math.pi)
        candidates.append({
            "center_x": cx_w, "center_y": cy_w,
            "theta_start": theta_s,
            "delta_ccw": d_ccw, "delta_cw": d_cw,
        })
    return candidates


def _select_elliptical_arc_solution(candidates: list, large_arc: bool, sweep: bool):
    """根据 large_arc/sweep 标志从候选解中选出正确的椭圆弧。

    Returns:
        (selected_candidate, sweep_angle)  sweep_angle > 0 逆时针，< 0 顺时针
    """
    want_large = bool(large_arc)
    want_ccw   = bool(sweep)
    filtered = []
    for c in candidates:
        ang = c["delta_ccw"] if want_ccw else -c["delta_cw"]
        if abs(ang) <= 1e-9:
            continue
        if (abs(ang) > math.pi + 1e-9) == want_large:
            return c, ang
        filtered.append((c, ang))
    if not filtered:
        raise RuntimeError("elliptical arc candidate selection failed; please check parameters.")
    return (max if want_large else min)(filtered, key=lambda x: abs(x[1]))


# -- MCPPrimitives mixin ------------------------------------------------------


class MCPPrimitives(MCPBase):
    """Sketch primitive operations mixin."""

    # Internal helpers

    def _transform_vector_cm(self, vector, sketch_ref):
        """Transform a sketch-local 2D vector in cm into Fusion sketch coordinates."""
        H = self._sketch_transforms[sketch_ref]["homogeneous_matrix"]
        x, y = float(vector[0]), float(vector[1])

        x_new = H[0][0] * x + H[0][1] * y
        y_new = H[1][0] * x + H[1][1] * y
        z_new = H[2][0] * x + H[2][1] * y

        return (x_new, y_new, z_new)

    def _resolve_sketch(self, sketch_ref):
        """将 sketch_ref=None 解析为最新草图的变量名。"""
        if sketch_ref is not None:
            return sketch_ref
        if not self._sketch_refs:
            raise RuntimeError("尚未创建草图，请先调用 create_sketch()。")
        return self._sketch_refs[-1]

    # ── 线段 ─────────────────────────────────────────────────────────────

    def add_line(self, start, end, sketch_ref=None) -> str:
        """向草图中添加一条线段。

        Args:
            start:      起点坐标，(x, y) 或 (x, y, z)，单位 mm
            end:        终点坐标，(x, y) 或 (x, y, z)，单位 mm
            sketch_ref: 目标草图变量名，None 取最新草图

        Returns:
            line_ref: str  — 如 "line_0"

        Raises:
            RuntimeError: 尚未创建草图，或 Fusion 360 执行失败。
        """
        ref = self._resolve_sketch(sketch_ref)
        sx, sy, sz = self._transform_point(start, ref)
        ex, ey, ez = self._transform_point(end, ref)
        key = self._next_ref("line")
        code = (
            f"import adsk.core\n"
            f"sk = {ref}\n"
            f"_s = adsk.core.Point3D.create({sx!r}, {sy!r}, {sz!r})\n"
            f"_e = adsk.core.Point3D.create({ex!r}, {ey!r}, {ez!r})\n"
            f"{key} = sk.sketchCurves.sketchLines.addByTwoPoints(_s, _e)\n"
        )
        self.execute({"operation": "execute_python", "code": code})
        self._log_primitive("add_line", key, ref)
        return key

    # ── 圆 ───────────────────────────────────────────────────────────────

    def add_circle(self, center, radius: float, sketch_ref=None) -> str:
        """向草图中添加一个圆。

        Args:
            center:     圆心坐标，(x, y) 或 (x, y, z)，单位 mm
            radius:     半径，单位 mm
            sketch_ref: 目标草图变量名，None 取最新草图

        Returns:
            circle_ref: str  — 如 "circle_0"
        """
        ref = self._resolve_sketch(sketch_ref)
        cx, cy, cz = self._transform_point(center, ref)
        r_cm = float(radius) * _MM
        key = self._next_ref("circle")
        code = (
            f"import adsk.core\n"
            f"sk = {ref}\n"
            f"_c = adsk.core.Point3D.create({cx!r}, {cy!r}, {cz!r})\n"
            f"{key} = sk.sketchCurves.sketchCircles.addByCenterRadius(_c, {r_cm!r})\n"
        )
        self.execute({"operation": "execute_python", "code": code})
        self._log_primitive("add_circle", key, ref)
        return key

    # ── 三点弧 ───────────────────────────────────────────────────────────

    def add_arc(self, start, along, end, sketch_ref=None) -> str:
        """向草图中添加一段三点弧（起点 → 弧上点 → 终点）。

        Args:
            start:      弧起点，(x, y) 或 (x, y, z)，单位 mm
            along:      弧上经过的中间点，单位 mm
            end:        弧终点，单位 mm
            sketch_ref: 目标草图变量名，None 取最新草图

        Returns:
            arc_ref: str  — 如 "arc_0"
        """
        ref = self._resolve_sketch(sketch_ref)
        sx, sy, sz = self._transform_point(start, ref)
        mx, my, mz = self._transform_point(along, ref)
        ex, ey, ez = self._transform_point(end, ref)
        key = self._next_ref("arc")
        code = (
            f"import adsk.core\n"
            f"sk = {ref}\n"
            f"_s = adsk.core.Point3D.create({sx!r}, {sy!r}, {sz!r})\n"
            f"_m = adsk.core.Point3D.create({mx!r}, {my!r}, {mz!r})\n"
            f"_e = adsk.core.Point3D.create({ex!r}, {ey!r}, {ez!r})\n"
            f"{key} = sk.sketchCurves.sketchArcs.addByThreePoints(_s, _m, _e)\n"
        )
        self.execute({"operation": "execute_python", "code": code})
        self._log_primitive("add_arc", key, ref)
        return key

    # ── 完整椭圆 ──────────────────────────────────────────────────────────

    def add_ellipse(
        self,
        center,
        major: float,
        minor: float,
        angle: float,
        sketch_ref=None,
    ) -> str:
        """向草图中添加完整椭圆。

        Args:
            center:     椭圆中心，(x, y) 或 (x, y, z)，单位 mm
            major:      长半轴长度，单位 mm
            minor:      短半轴长度，单位 mm
            angle:      长轴相对 X 轴的旋转角度，单位度（°）
            sketch_ref: 目标草图变量名，None 取最新草图

        Returns:
            ellipse_ref: str  — 如 "ellipse_0"
        """
        ref = self._resolve_sketch(sketch_ref)
        local_cx, local_cy = float(center[0]), float(center[1])
        rad  = math.radians(float(angle))
        ca, sa = math.cos(rad), math.sin(rad)
        cx, cy, cz = self._transform_point((local_cx, local_cy), ref)
        maj_x, maj_y, maj_z = self._transform_point(
            (local_cx + float(major) * ca, local_cy + float(major) * sa), ref
        )
        pas_x, pas_y, pas_z = self._transform_point(
            (local_cx - float(minor) * sa, local_cy + float(minor) * ca), ref
        )
        key = self._next_ref("ellipse")
        code = (
            f"import adsk.core\n"
            f"sk = {ref}\n"
            f"_c   = adsk.core.Point3D.create({cx!r},    {cy!r},    {cz!r})\n"
            f"_maj = adsk.core.Point3D.create({maj_x!r}, {maj_y!r}, {maj_z!r})\n"
            f"_pas = adsk.core.Point3D.create({pas_x!r}, {pas_y!r}, {pas_z!r})\n"
            f"{key} = sk.sketchCurves.sketchEllipses.add(_c, _maj, _pas)\n"
        )
        self.execute({"operation": "execute_python", "code": code})
        self._log_primitive("add_ellipse", key, ref)
        return key

    # ── 椭圆弧 ────────────────────────────────────────────────────────────

    def add_elliptical_arc(
        self,
        start,
        end,
        major: float,
        minor: float,
        angle: float,
        large_arc: bool = False,
        sweep: bool = True,     #这个为顺时针时，可能会把起点终点交换可能会影响到约束，暂不做修改
        sketch_ref=None,
    ) -> str:
        """向草图中添加椭圆弧（SVG 风格参数，与 SVG arc 命令兼容）。

        Args:
            start:      弧起点，(x, y)，单位 mm
            end:        弧终点，(x, y)，单位 mm
            major:      长半轴，单位 mm
            minor:      短半轴，单位 mm
            angle:      长轴旋转角度，单位度（°）
            large_arc:  True 取大弧段（> 180°），False 取小弧段
            sweep:      True 逆时针，False 顺时针
            sketch_ref: 目标��图变量名，None 取最新草图

        Returns:
            elliptical_arc_ref: str  — 如 "elliptical_arc_0"
        """
        ref = self._resolve_sketch(sketch_ref)
        a_cm = float(major) * _MM
        b_cm = float(minor) * _MM
        rad  = math.radians(float(angle))
        sx, sy = float(start[0]) * _MM, float(start[1]) * _MM
        ex, ey = float(end[0]) * _MM, float(end[1]) * _MM
        candidates = _solve_elliptical_arc_candidates(
            (sx, sy), (ex, ey), a_cm, b_cm, rad)
        selected, sweep_angle = _select_elliptical_arc_solution(
            candidates, large_arc, sweep)
        ca, sa = math.cos(rad), math.sin(rad)
        cx_local, cy_local = selected["center_x"], selected["center_y"]
        cx, cy, cz = self._transform_point((cx_local / _MM, cy_local / _MM), ref)
        maj_x, maj_y, maj_z = self._transform_vector_cm((ca * a_cm, sa * a_cm), ref)
        min_x, min_y, min_z = self._transform_vector_cm((-sa * b_cm, ca * b_cm), ref)
        theta_s = selected["theta_start"]
        key = self._next_ref("elliptical_arc")
        code = (
            f"import adsk.core\n"
            f"sk = {ref}\n"
            f"_c   = adsk.core.Point3D.create({cx!r}, {cy!r}, {cz!r})\n"
            f"_maj = adsk.core.Vector3D.create({maj_x!r}, {maj_y!r}, {maj_z!r})\n"
            f"_min = adsk.core.Vector3D.create({min_x!r}, {min_y!r}, {min_z!r})\n"
            f"{key} = sk.sketchCurves.sketchEllipticalArcs.addByAngle("
            f"_c, _maj, _min, {theta_s!r}, {sweep_angle!r})\n"
        )
        self.execute({"operation": "execute_python", "code": code})
        self._log_primitive("add_elliptical_arc", key, ref)
        return key

    # ── NURBS 样条 ────────────────────────────────────────────────────────

    def add_nurbs(
        self,
        degree: int,
        closed: bool,
        controls: list,
        weights=None,
        knots=None,
        sketch_ref=None,
    ) -> str:
        """向草图中添加 NURBS 样条曲线。

        Args:
            degree:     多项式次数（通常 3，即三次样条）
            closed:     True 生成闭合曲线（closed=True 时必须提供 knots）
            controls:   控制点列表，每个元素 (x, y, z)，单位 mm
            weights:    权重列表（None 表示均匀权重，即非有理曲线）
            knots:      节点向量（None 且非闭合时自动生成 clamped uniform 节点）
            sketch_ref: 目标草图变量名，None 取最新草图

        Returns:
            nurbs_ref: str  — 如 "nurbs_0"

        Raises:
            ValueError: 参数非法（degree < 1 / 控制点不足 / knots 长度错误）。
        """
        ref = self._resolve_sketch(sketch_ref)
        degree = int(degree)
        if degree < 1:
            raise ValueError(f"degree 需 >= 1，实际 {degree}")
        pts = []
        for c in controls:
            px, py, pz = self._transform_point(c, ref)
            pts.append((px, py, pz))
        if len(pts) < degree + 1:
            raise ValueError(
                f"控制点需至少 {degree + 1} 个，实际 {len(pts)} 个"
            )
        if not knots:
            knots = _default_knots(len(pts), degree, bool(closed))
        else:
            knots = [float(k) for k in knots]
        expected = len(pts) + degree + 1
        if len(knots) != expected:
            raise ValueError(
                f"knots 长度应为 control_count + degree + 1 = {expected}，"
                f"实际 {len(knots)}"
            )
        w_list = [float(w) for w in weights] if weights else None
        key = self._next_ref("nurbs")
        code = (
            f"import adsk.core\n"
            f"sk = {ref}\n"
            f"_pts = [adsk.core.Point3D.create(*p) for p in {pts!r}]\n"
            f"_w   = {w_list!r}\n"
            f"if _w is None:\n"
            f"    _nc = adsk.core.NurbsCurve3D.createNonRational("
            f"_pts, {degree!r}, {knots!r}, {bool(closed)!r})\n"
            f"else:\n"
            f"    _nc = adsk.core.NurbsCurve3D.createRational("
            f"_pts, {degree!r}, {knots!r}, _w, {bool(closed)!r})\n"
            f"{key} = sk.sketchCurves.sketchFixedSplines.addByNurbsCurve(_nc)\n"
        )
        self.execute({"operation": "execute_python", "code": code})
        self._log_primitive("add_nurbs", key, ref)
        return key

    # ── 图元信息查询 ──────────────────────────────────────────────────────

    def get_entity_info(self, ref: str) -> dict:
        """查询草图图元的几何属性。

        根据 ref 前缀自动识别图元类型，通过 execute_python 读取 Fusion 中的属性。

        Args:
            ref: 图元引用字符串，如 "line_1"、"circle_2"、"elliptical_arc_6"

        Returns:
            包含图元属性的字典，长度单位 mm，角度单位度（°）。
            所有坐标均为**世界坐标系**真值（读自 .worldGeometry），
            带 offset / 欧拉旋转的草图也能正确反映平面位置与朝向。
            公共字段 "type" 为图元类型字符串，其余字段按类型如下：
              line           → start / end / mid（mm），length（mm）
              circle         → center（mm），radius（mm），normal（单位向量），
                               point_on（mm，evaluator 取曲线起点）
              arc            → center（mm），normal（单位向量），radius（mm），
                               start_pt/end_pt/mid_pt（mm），start_angle/end_angle（°）
              ellipse        → center（mm），normal（单位向量），
                               major_radius/minor_radius（mm），major_axis（世界系单位向量），
                               point_on（45° 处，mm）
              elliptical_arc → 同 ellipse，另加 start_angle/end_angle（°），
                               point_on（弧参数中点，mm）
              nurbs          → degree，is_rational，control_points（世界系，mm），knots，
                               point_on（参数中点，mm）

        Raises:
            ValueError:  ref 前缀无法识别为已知图元类型。
            RuntimeError: Fusion 360 执行失败。
        """
        import json as _json

        # 取前缀："elliptical_arc_6" → "elliptical_arc"，"line_1" → "line"
        kind = ref.rsplit("_", 1)[0]

        if kind == "line":
            code = (
                f"import json\n"
                f"_g = {ref}.worldGeometry\n"          # Line3D（世界系）
                f"_s = _g.startPoint\n"
                f"_t = _g.endPoint\n"
                f"_mx, _my, _mz = (_s.x+_t.x)*5, (_s.y+_t.y)*5, (_s.z+_t.z)*5\n"
                f"_len = ((_t.x-_s.x)**2 + (_t.y-_s.y)**2 + (_t.z-_s.z)**2) ** 0.5 * 10\n"
                f"_info = {{\n"
                f"    'type':     'line',\n"
                f"    'start':    [_s.x*10, _s.y*10, _s.z*10],\n"
                f"    'end':      [_t.x*10, _t.y*10, _t.z*10],\n"
                f"    'mid':      [_mx, _my, _mz],\n"
                f"    'point_on': [_mx, _my, _mz],\n"
                f"    'length':   _len,\n"
                f"}}\n"
                f"print(json.dumps(_info))\n"
            )

        elif kind == "circle":
            code = (
                f"import json\n"
                f"_g = {ref}.worldGeometry\n"          # Circle3D（世界系）
                f"_c = _g.center\n"
                f"_n = _g.normal\n"
                f"_r = _g.radius * 10\n"
                # point_on：用 evaluator 在世界系取曲线起点，避免假设圆在 XY 面
                f"_ev = _g.evaluator\n"
                f"_ok, _t0, _t1 = _ev.getParameterExtents()\n"
                f"_ok2, _p = _ev.getPointAtParameter(_t0)\n"
                f"_pon = [_p.x*10, _p.y*10, _p.z*10] if _ok2 else None\n"
                f"_info = {{\n"
                f"    'type':     'circle',\n"
                f"    'center':   [_c.x*10, _c.y*10, _c.z*10],\n"
                f"    'radius':   _r,\n"
                f"    'normal':   [_n.x, _n.y, _n.z],\n"
                f"    'point_on': _pon,\n"
                f"}}\n"
                f"print(json.dumps(_info))\n"
            )

        elif kind == "arc":
            code = (
                f"import json, math\n"
                f"_g  = {ref}.worldGeometry\n"          # Arc3D（世界系）
                f"_c  = _g.center\n"
                f"_n  = _g.normal\n"
                f"_sp = _g.startPoint\n"
                f"_ep = _g.endPoint\n"
                f"_r  = _g.radius\n"
                f"_sa = _g.startAngle\n"
                f"_ea = _g.endAngle\n"
                # mid_pt：evaluator 在世界系取参数中点（绕开局部 cos/sin 手算）
                f"_ev = _g.evaluator\n"
                f"_ok, _t0, _t1 = _ev.getParameterExtents()\n"
                f"_ok2, _mp = _ev.getPointAtParameter((_t0 + _t1) / 2)\n"
                f"_mid = [_mp.x*10, _mp.y*10, _mp.z*10] if _ok2 else None\n"
                f"_info = {{\n"
                f"    'type':        'arc',\n"
                f"    'center':      [_c.x*10, _c.y*10, _c.z*10],\n"
                f"    'normal':      [_n.x, _n.y, _n.z],\n"
                f"    'radius':      _r * 10,\n"
                f"    'start_pt':    [_sp.x*10, _sp.y*10, _sp.z*10],\n"
                f"    'end_pt':      [_ep.x*10, _ep.y*10, _ep.z*10],\n"
                f"    'mid_pt':      _mid,\n"
                f"    'point_on':    _mid,\n"
                f"    'start_angle': math.degrees(_sa),\n"
                f"    'end_angle':   math.degrees(_ea),\n"
                f"}}\n"
                f"print(json.dumps(_info))\n"
            )

        elif kind == "ellipse":
            code = (
                f"import json, math\n"
                f"_g = {ref}.worldGeometry\n"           # Ellipse3D（世界系）
                f"_c = _g.center\n"
                f"_n = _g.normal\n"
                f"_maj_r = _g.majorRadius * 10\n"
                f"_min_r = _g.minorRadius * 10\n"
                f"_ax = _g.majorAxis\n"                 # 世界系长轴单位向量
                f"_ln = (_ax.x**2 + _ax.y**2 + _ax.z**2) ** 0.5\n"
                f"_ux, _uy, _uz = _ax.x/_ln, _ax.y/_ln, _ax.z/_ln\n"
                # 短轴单位向量 = normal × majorAxis（世界系）
                f"_vx = _n.y*_uz - _n.z*_uy\n"
                f"_vy = _n.z*_ux - _n.x*_uz\n"
                f"_vz = _n.x*_uy - _n.y*_ux\n"
                f"_cx, _cy, _cz = _c.x*10, _c.y*10, _c.z*10\n"
                # point_on 取 45°（0°=长轴端，90°=短轴端，避开端点）
                f"_lx = math.cos(math.pi/4) * _maj_r\n"
                f"_ly = math.sin(math.pi/4) * _min_r\n"
                f"_info = {{\n"
                f"    'type':         'ellipse',\n"
                f"    'center':       [_cx, _cy, _cz],\n"
                f"    'normal':       [_n.x, _n.y, _n.z],\n"
                f"    'major_radius': _maj_r,\n"
                f"    'minor_radius': _min_r,\n"
                f"    'major_axis':   [_ux, _uy, _uz],\n"
                f"    'point_on':     [_cx + _ux*_lx + _vx*_ly,\n"
                f"                     _cy + _uy*_lx + _vy*_ly,\n"
                f"                     _cz + _uz*_lx + _vz*_ly],\n"
                f"}}\n"
                f"print(json.dumps(_info))\n"
            )

        elif kind == "elliptical_arc":
            code = (
                f"import json, math\n"
                f"_g  = {ref}.worldGeometry\n"          # EllipticalArc3D（世界系）
                f"_c  = _g.center\n"
                f"_n  = _g.normal\n"
                f"_a  = _g.majorRadius\n"               # cm
                f"_b  = _g.minorRadius\n"               # cm
                f"_ax = _g.majorAxis\n"                 # 世界系长轴单位向量
                f"_ln = (_ax.x**2 + _ax.y**2 + _ax.z**2) ** 0.5\n"
                f"_ux, _uy, _uz = _ax.x/_ln, _ax.y/_ln, _ax.z/_ln\n"
                f"_sa = _g.startAngle\n"
                f"_ea = _g.endAngle\n"
                # point_on：evaluator 在世界系取参数中点
                f"_ev = _g.evaluator\n"
                f"_ok, _t0, _t1 = _ev.getParameterExtents()\n"
                f"_ok2, _mp = _ev.getPointAtParameter((_t0 + _t1) / 2)\n"
                f"_pon = [_mp.x*10, _mp.y*10, _mp.z*10] if _ok2 else None\n"
                f"_cx, _cy, _cz = _c.x*10, _c.y*10, _c.z*10\n"
                f"_info = {{\n"
                f"    'type':         'elliptical_arc',\n"
                f"    'center':       [_cx, _cy, _cz],\n"
                f"    'normal':       [_n.x, _n.y, _n.z],\n"
                f"    'major_radius': _a * 10,\n"
                f"    'minor_radius': _b * 10,\n"
                f"    'major_axis':   [_ux, _uy, _uz],\n"
                f"    'start_angle':  math.degrees(_sa),\n"
                f"    'end_angle':    math.degrees(_ea),\n"
                f"    'point_on':     _pon,\n"
                f"}}\n"
                f"print(json.dumps(_info))\n"
            )

        elif kind == "nurbs":
            code = (
                f"import json\n"
                f"_nc = {ref}.worldGeometry\n"          # NurbsCurve3D（世界系）
                f"_pts = [[_nc.controlPoints[i].x*10, _nc.controlPoints[i].y*10,\n"
                f"         _nc.controlPoints[i].z*10]\n"
                f"        for i in range(_nc.controlPointCount)]\n"
                f"_knots = list(_nc.knots)\n"
                # point_on：evaluator 在世界系取参数中点（有效域取自 evaluator）
                f"_ev = _nc.evaluator\n"
                f"_ok, _t0, _t1 = _ev.getParameterExtents()\n"
                f"_ok2, _pt = _ev.getPointAtParameter((_t0 + _t1) / 2)\n"
                f"_pon = [_pt.x*10, _pt.y*10, _pt.z*10] if _ok2 else None\n"
                f"_info = {{\n"
                f"    'type':           'nurbs',\n"
                f"    'degree':         _nc.degree,\n"
                f"    'is_rational':    _nc.isRational,\n"
                f"    'control_points': _pts,\n"
                f"    'knots':          _knots,\n"
                f"    'point_on':       _pon,\n"
                f"}}\n"
                f"print(json.dumps(_info))\n"
            )

        else:
            raise ValueError(
                f"未知图元类型，ref={ref!r}，解析前缀为 {kind!r}，"
                f"已知类型：line / circle / arc / ellipse / elliptical_arc / nurbs"
            )

        r = self.execute({"operation": "execute_python", "code": code})
        return _json.loads(r["data"]["stdout"])
