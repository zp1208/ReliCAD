# -*- coding: utf-8 -*-
"""
MCP Bridge -- 拉伸及三维实体操作
extrude：拉伸草图轮廓生成实体
revolve：旋转草图轮廓生成旋转体
helix_sweep：沿螺旋路径扫掠草图轮廓
"""
import json as _json
import math as _math

from .mcp_base import MCPBase

_MM = 0.1  # mm → cm（Fusion 360 内部单位）

_OP_MAP = {
    "new":       "NewBodyFeatureOperation",
    "newbody":   "NewBodyFeatureOperation",
    "join":      "JoinFeatureOperation",
    "cut":       "CutFeatureOperation",
    "intersect": "IntersectFeatureOperation",
}

_AXIS_ATTR = {
    "X": "xConstructionAxis",
    "Y": "yConstructionAxis",
    "Z": "zConstructionAxis",
}


class MCPExtrude(MCPBase):
    """拉伸与三维实体操作混入类。

    所有操作均基于已存在的草图轮廓。草图必须包含封闭轮廓才能执行拉伸/旋转操作。
    operation 参数控制实体的布尔运算方式。
    """

    # ── 私有辅助方法 ───────────────────────────────────────────────────────
    @staticmethod
    def _profile_selection_code() -> str:
        """Return profile selection code; expects _sk and stores the result in _sel."""
        return (
            "_profiles = _sk.profiles\n"
            "_pc = _profiles.count\n"
            "if _pc == 0:\n"
            "    raise RuntimeError('No profiles in sketch.')\n"
            "_sel = None\n"
            "for _i in range(_pc):\n"
            "    _p = _profiles.item(_i)\n"
            "    _loops = _p.profileLoops\n"
            "    _lc = _loops.count\n"
            "    _has_outer = any(_loops.item(_j).isOuter for _j in range(_lc))\n"
            "    _has_inner = any(not _loops.item(_j).isOuter for _j in range(_lc))\n"
            "    if _has_outer and _has_inner:\n"
            "        _sel = _p\n"
            "        break\n"
            "if _sel is None:\n"
            "    if _pc == 1:\n"
            "        _sel = _profiles.item(0)\n"
            "    else:\n"
            "        _col = adsk.core.ObjectCollection.create()\n"
            "        for _i in range(_pc):\n"
            "            _col.add(_profiles.item(_i))\n"
            "        _sel = _col\n"
        )

    @staticmethod
    def _resolve_revolve_axis_code(axis, p1, p2) -> str:
        """Return Fusion Python code that stores the resolved revolve axis in _ax."""
        if axis is not None:
            ax_attr = _AXIS_ATTR[axis]
            return f"_ax = design.rootComponent.{ax_attr}\n"

        p1 = list(p1)
        p2 = list(p2)
        while len(p1) < 3:
            p1.append(0.0)
        while len(p2) < 3:
            p2.append(0.0)

        p1x_cm, p1y_cm, p1z_cm = [c * _MM for c in p1]
        dx_raw = p2[0] - p1[0]
        dy_raw = p2[1] - p1[1]
        dz_raw = p2[2] - p1[2]
        length = _math.sqrt(dx_raw ** 2 + dy_raw ** 2 + dz_raw ** 2)
        if length < 1e-12:
            raise ValueError("axis_point1 和 axis_point2 重合，无法确定旋转轴方向。")
        dx, dy, dz = dx_raw / length, dy_raw / length, dz_raw / length

        _tol = 1e-6
        _cx = p1y_cm * dz - p1z_cm * dy
        _cy = p1z_cm * dx - p1x_cm * dz
        _cz = p1x_cm * dy - p1y_cm * dx
        if _math.sqrt(_cx * _cx + _cy * _cy + _cz * _cz) <= _tol:
            _tol2 = 1e-4
            if abs(dx) > 1 - _tol2 and abs(dy) <= _tol2 and abs(dz) <= _tol2:
                return "_ax = design.rootComponent.xConstructionAxis\n"
            if abs(dy) > 1 - _tol2 and abs(dx) <= _tol2 and abs(dz) <= _tol2:
                return "_ax = design.rootComponent.yConstructionAxis\n"
            if abs(dz) > 1 - _tol2 and abs(dx) <= _tol2 and abs(dy) <= _tol2:
                return "_ax = design.rootComponent.zConstructionAxis\n"

        return (
            f"_p1 = adsk.core.Point3D.create({p1x_cm!r}, {p1y_cm!r}, {p1z_cm!r})\n"
            f"_p2 = adsk.core.Point3D.create({p2[0] * _MM!r}, {p2[1] * _MM!r}, {p2[2] * _MM!r})\n"
            f"_ax = _sk.sketchCurves.sketchLines.addByTwoPoints(_p1, _p2)\n"
            f"_ax.isConstruction = True\n"
        )

    @staticmethod
    def _resolve_helix_axis_params(axis) -> tuple:
        """解析螺旋轴参数，返回 (ox_cm, oy_cm, oz_cm, dx, dy, dz)。

        Args:
            axis: [[x1,y1,z1],[x2,y2,z2]]，两点定义轴，坐标单位 mm。

        Raises:
            ValueError: axis 格式错误或两点重合。
        """
        if (
            not isinstance(axis, (list, tuple))
            or len(axis) != 2
            or not all(len(a) in (2, 3) for a in axis)
        ):
            raise ValueError(
                "axis 格式错误，期望 [[x1,y1,z1],[x2,y2,z2]]，每个子列表包含 2 或 3 个数值。"
            )

        p1 = list(axis[0])
        p2 = list(axis[1])
        while len(p1) < 3:
            p1.append(0.0)
        while len(p2) < 3:
            p2.append(0.0)

        ox_cm, oy_cm, oz_cm = [c * _MM for c in p1]

        dx_raw = p2[0] - p1[0]
        dy_raw = p2[1] - p1[1]
        dz_raw = p2[2] - p1[2]
        length = _math.sqrt(dx_raw ** 2 + dy_raw ** 2 + dz_raw ** 2)
        if length < 1e-12:
            raise ValueError("axis 两点重合，无法确定轴方向。")
        dx, dy, dz = dx_raw / length, dy_raw / length, dz_raw / length

        return ox_cm, oy_cm, oz_cm, dx, dy, dz

    # ── 公共操作方法 ──────────────────────────────────────────────────────

    def extrude(
        self,
        distance: float,
        operation: str,
        sketch_ref: str = None,
    ) -> str:
        """将草图中的封闭轮廓沿法线方向拉伸生成三维实体。

        Args:
            distance:   拉伸距离（单位：毫米，正值沿草图法线方向）
            sketch_ref: 包含封闭轮廓的草图会话变量名（None 使用最新草图）
            operation:  布尔运算类型（大小写不敏感）：
                        "NewBody"    -- 创建新实体
                        "Join"       -- 与已有实体合并
                        "Cut"        -- 从已有实体中切除
                        "Intersect"  -- 与已有实体取交集

        Returns:
            "extrude_N"
            为拉伸特征在 Fusion 持久命名空间中的变量名。

        Raises:
            RuntimeError: 草图无封闭轮廓，或 Fusion 360 执行失败。
            ValueError:   operation 不在支持列表中。
        """
        # 1. Resolve sketch_ref
        if sketch_ref is None:
            if not self._sketch_refs:
                raise RuntimeError("尚未创建草图，请先调用 create_sketch()。")
            sketch_ref = self._sketch_refs[-1]

        # 2. Normalize operation
        op_key = str(operation).strip().lower()
        if op_key not in _OP_MAP:
            raise ValueError(
                f"不支持的 operation: {operation!r}，可选: NewBody, Join, Cut, Intersect"
            )
        op_enum_name = _OP_MAP[op_key]

        # 3. Generate unique ref key
        key = self._next_ref("extrude")

        # 4. Build execute_python code — replicates _select_profile logic
        dist_val = float(distance) * _MM  # mm → cm
        code = (
            f"import adsk.core, adsk.fusion, json\n"
            f"_sk = {sketch_ref}\n"
            f"_profiles = _sk.profiles\n"
            f"_pc = _profiles.count\n"
            f"if _pc == 0:\n"
            f"    raise RuntimeError('No profiles in sketch.')\n"
            f"_sel = None\n"
            f"def _loop_identity_and_area(_loop):\n"
            f"    _tokens = []\n"
            f"    _min_x = None\n"
            f"    _min_y = None\n"
            f"    _max_x = None\n"
            f"    _max_y = None\n"
            f"    _curves = _loop.profileCurves\n"
            f"    for _ci in range(_curves.count):\n"
            f"        _curve = _curves.item(_ci)\n"
            f"        _ent = getattr(_curve, 'sketchEntity', None)\n"
            f"        _token = getattr(_ent, 'entityToken', None) if _ent is not None else None\n"
            f"        if not _token:\n"
            f"            raise RuntimeError('Profile loop curve has no sketchEntity entityToken.')\n"
            f"        _bb = getattr(_curve, 'boundingBox', None)\n"
            f"        if _bb is None and _ent is not None:\n"
            f"            _bb = getattr(_ent, 'boundingBox', None)\n"
            f"        if _bb is None:\n"
            f"            raise RuntimeError('Profile loop curve has no boundingBox.')\n"
            f"        _tokens.append(str(_token))\n"
            f"        _min_x = _bb.minPoint.x if _min_x is None else min(_min_x, _bb.minPoint.x)\n"
            f"        _min_y = _bb.minPoint.y if _min_y is None else min(_min_y, _bb.minPoint.y)\n"
            f"        _max_x = _bb.maxPoint.x if _max_x is None else max(_max_x, _bb.maxPoint.x)\n"
            f"        _max_y = _bb.maxPoint.y if _max_y is None else max(_max_y, _bb.maxPoint.y)\n"
            f"    if not _tokens:\n"
            f"        raise RuntimeError('Profile loop has no curves.')\n"
            f"    _area = max(0.0, float(_max_x - _min_x)) * max(0.0, float(_max_y - _min_y))\n"
            f"    return tuple(sorted(_tokens)), _area\n"
            f"_profile_infos = []\n"
            f"_loop_areas = {{}}\n"
            f"for _i in range(_pc):\n"
            f"    _p = _profiles.item(_i)\n"
            f"    _loops = _p.profileLoops\n"
            f"    _outer_key = None\n"
            f"    _inner_keys = []\n"
            f"    for _j in range(_loops.count):\n"
            f"        _loop = _loops.item(_j)\n"
            f"        _key, _area = _loop_identity_and_area(_loop)\n"
            f"        _loop_areas[_key] = max(_loop_areas.get(_key, 0.0), _area)\n"
            f"        if _loop.isOuter:\n"
            f"            _outer_key = _key\n"
            f"        else:\n"
            f"            _inner_keys.append(_key)\n"
            f"    if _outer_key is not None:\n"
            f"        _profile_infos.append((_p, _outer_key, _inner_keys))\n"
            f"_selected_profiles = []\n"
            f"_used_loops = set()\n"
            f"while True:\n"
            f"    _best_idx = -1\n"
            f"    _best_inner_area = -1.0\n"
            f"    _best_outer_area = -1.0\n"
            f"    for _idx, (_p, _outer_key, _inner_keys) in enumerate(_profile_infos):\n"
            f"        if not _inner_keys or _outer_key in _used_loops:\n"
            f"            continue\n"
            f"        if any(_inner_key in _used_loops for _inner_key in _inner_keys):\n"
            f"            continue\n"
            f"        _inner_area = max(_loop_areas[_inner_key] for _inner_key in _inner_keys)\n"
            f"        _outer_area = _loop_areas[_outer_key]\n"
            f"        if _inner_area > _best_inner_area or (_inner_area == _best_inner_area and _outer_area > _best_outer_area):\n"
            f"            _best_idx = _idx\n"
            f"            _best_inner_area = _inner_area\n"
            f"            _best_outer_area = _outer_area\n"
            f"    if _best_idx < 0:\n"
            f"        break\n"
            f"    _p, _outer_key, _inner_keys = _profile_infos[_best_idx]\n"
            f"    _selected_profiles.append(_p)\n"
            f"    _used_loops.add(_outer_key)\n"
            f"    for _inner_key in _inner_keys:\n"
            f"        _used_loops.add(_inner_key)\n"
            f"for _p, _outer_key, _inner_keys in _profile_infos:\n"
            f"    if _inner_keys or _outer_key in _used_loops:\n"
            f"        continue\n"
            f"    _selected_profiles.append(_p)\n"
            f"    _used_loops.add(_outer_key)\n"
            f"if _selected_profiles:\n"
            f"    if len(_selected_profiles) == 1:\n"
            f"        _sel = _selected_profiles[0]\n"
            f"    else:\n"
            f"        _col = adsk.core.ObjectCollection.create()\n"
            f"        for _p in _selected_profiles:\n"
            f"            _col.add(_p)\n"
            f"        _sel = _col\n"
            f"if _sel is None:\n"
            f"    if _pc == 1:\n"
            f"        _sel = _profiles.item(0)\n"
            f"    else:\n"
            f"        _col = adsk.core.ObjectCollection.create()\n"
            f"        for _i in range(_pc):\n"
            f"            _col.add(_profiles.item(_i))\n"
            f"        _sel = _col\n"
            f"_op = adsk.fusion.FeatureOperations.{op_enum_name}\n"
            f"_exts = design.rootComponent.features.extrudeFeatures\n"
            f"_inp = _exts.createInput(_sel, _op)\n"
            f"_inp.setDistanceExtent(False, adsk.core.ValueInput.createByReal({dist_val!r}))\n"
            f"{key} = _exts.add(_inp)\n"
            f"print(json.dumps({{'ok': True, 'ref': {key!r}}}))\n"
        )

        # 5. Execute and parse result
        try:
            r = self.execute({"operation": "execute_python", "code": code})
            info = _json.loads(r["data"]["stdout"])
            info["ref"] = key
            self._capture_feature(
                "extrude", key, consumed_sketch=sketch_ref,
                profile_from=sketch_ref, operation=operation,
                values={"distance": float(distance), "taper_angle": 0.0},
            )
            return info["ref"]
        except Exception:
            self._capture_failed(
                "extrude", key, consumed_sketch=sketch_ref,
                profile_from=sketch_ref, operation=operation,
            )
            raise

    def revolve(
        self,
        axis: str | None = None,
        axis_point1 = None,
        axis_point2 = None,
        angle: float = 360.0,
        sketch_ref: str = None,
        operation: str = "NewBody",
    ) -> str:
        """将草图轮廓绕指定轴旋转生成旋转体。

        旋转轴可通过两点定义，也可使用 axis 参数直接指定命名坐标轴。

        Args:
            axis_point1: 定义旋转轴的第一个点（单位：mm；axis 非 None 时忽略）
            axis_point2: 定义旋转轴的第二个点（单位：mm；axis 非 None 时忽略）
            angle:       旋转角度（单位：度，默认 360 为整圈旋转）
            sketch_ref:  草图会话变量名（None 使用最新草图）
            operation:   布尔运算类型（大小写不敏感）：
                         "NewBody" / "Join" / "Cut" / "Intersect"
            axis:        命名轴快捷方式 "X"、"Y" 或 "Z"；
                         设置后忽略 axis_point1/2

        Returns:
            "revolve_N"

        Raises:
            RuntimeError: 草图无封闭轮廓，或 Fusion 360 执行失败。
            ValueError:   operation 不在支持列表中，两点轴方向无效，或命名轴不合法。
        """
        # 1. Resolve sketch_ref
        if sketch_ref is None:
            if not self._sketch_refs:
                raise RuntimeError("尚未创建草图，请先调用 create_sketch()。")
            sketch_ref = self._sketch_refs[-1]

        # 2. Normalize operation
        op_key = str(operation).strip().lower()
        if op_key not in _OP_MAP:
            raise ValueError(
                f"不支持的 operation: {operation!r}，可选: NewBody, Join, Cut, Intersect"
            )
        op_enum_name = _OP_MAP[op_key]

        # 3. Validate named axis
        axis_norm = axis.strip().upper() if axis else None
        if axis_norm is not None and axis_norm not in _AXIS_ATTR:
            raise ValueError(f"不支持的命名轴: {axis!r}，可选: X, Y, Z")

        # 4. Generate unique ref key
        key = self._next_ref("revolve")

        # 5. Build axis setup code
        axis_code = self._resolve_revolve_axis_code(axis_norm, axis_point1, axis_point2)

        # 6. Build execute_python code
        angle_str = f"{float(angle):.8g} deg"
        profile_code = self._profile_selection_code()
        code = (
            f"import adsk.core, adsk.fusion, json\n"
            f"_sk = {sketch_ref}\n"
            + axis_code
            + profile_code
            + f"_op = adsk.fusion.FeatureOperations.{op_enum_name}\n"
            f"_revolves = design.rootComponent.features.revolveFeatures\n"
            f"_rinp = _revolves.createInput(_sel, _ax, _op)\n"
            f"_rinp.setAngleExtent(False, adsk.core.ValueInput.createByString({angle_str!r}))\n"
            f"{key} = _revolves.add(_rinp)\n"
            f"print(json.dumps({{'ok': True, 'ref': {key!r}}}))\n"
        )

        # 7. Execute and parse result
        try:
            r = self.execute({"operation": "execute_python", "code": code})
            info = _json.loads(r["data"]["stdout"])
            info["ref"] = key
            self._capture_feature(
                "revolve", key, consumed_sketch=sketch_ref,
                profile_from=sketch_ref, operation=operation,
                values={"angle": float(angle)},
            )
            return info["ref"]
        except Exception:
            self._capture_failed(
                "revolve", key, consumed_sketch=sketch_ref,
                profile_from=sketch_ref, operation=operation,
            )
            raise

    def helix_sweep(
        self,
        axis,
        pitch: float,
        turns: float,
        handedness: str = "Right",
        sketch_ref: str = None,
        operation: str = "NewBody",
    ) -> str:
        """将草图轮廓沿螺旋路径扫掠，用于生成螺纹、弹簧等螺旋形体。

        Args:
            axis:        螺旋轴定义 [[x1,y1,z1],[x2,y2,z2]]：
                         两点定义轴的位置和方向，坐标单位 mm。
                         螺旋从第一点向第二点方向前进（Right 旋）或反向前进（Left 旋）。
            pitch:       螺距，每圈轴向进给量（单位：mm，必须 > 0）
            turns:       螺旋圈数（必须 > 0）
            handedness:  螺旋方向："Right" 右旋沿 p1→p2 方向上升；
                                   "Left" 左旋沿 p1→p2 反方向上升
            sketch_ref:  草图会话变量名（None 使用最新草图）
            operation:   布尔运算类型（大小写不敏感）：
                         "NewBody" / "Join" / "Cut" / "Intersect"

        Returns:
            "helix_sweep_N"

        Raises:
            RuntimeError: 草图无封闭轮廓，螺旋导线创建失败，或 Fusion 360 执行失败。
            ValueError:   pitch/turns ≤ 0，operation 不在支持列表，axis 格式错误，
                          或 handedness 不合法。
        """
        # 1. Resolve sketch_ref
        if sketch_ref is None:
            if not self._sketch_refs:
                raise RuntimeError("尚未创建草图，请先调用 create_sketch()。")
            sketch_ref = self._sketch_refs[-1]

        # 2. Validate pitch and turns
        if float(pitch) <= 0:
            raise ValueError(f"pitch 必须 > 0，当前值: {pitch!r}")
        if float(turns) <= 0:
            raise ValueError(f"turns 必须 > 0，当前值: {turns!r}")

        # 3. Normalize operation
        op_key = str(operation).strip().lower()
        if op_key not in _OP_MAP:
            raise ValueError(
                f"不支持的 operation: {operation!r}，可选: NewBody, Join, Cut, Intersect"
            )
        op_enum_name = _OP_MAP[op_key]

        # 4. Parse axis and compute signed pitch
        ox_cm, oy_cm, oz_cm, dx, dy, dz = self._resolve_helix_axis_params(axis)
        pitch_cm = float(pitch) * _MM
        hand_lower = handedness.strip().lower()
        if hand_lower == "right":
            signed_pitch_cm = pitch_cm
        elif hand_lower == "left":
            signed_pitch_cm = -pitch_cm
        else:
            raise ValueError(f"不支持的 handedness: {handedness!r}，可选: Right, Left")

        # 5. Generate unique ref key
        key = self._next_ref("helix_sweep")

        # 6. Build execute_python code
        turns_val = float(turns)
        profile_code = self._profile_selection_code()
        code = (
            f"import adsk.core, adsk.fusion, json, math\n"
            f"_sk = {sketch_ref}\n"
            + profile_code
            + f"_ap = adsk.core.Point3D.create({ox_cm!r}, {oy_cm!r}, {oz_cm!r})\n"
            f"_av = adsk.core.Vector3D.create({dx!r}, {dy!r}, {dz!r})\n"
            # ── 计算螺旋起点候选列表 ───────────────────────────────────────
            # 优先使用截面轮廓的面积重心（对非对称截面如三角形更准确）；
            # 若 API 不可用则回退到包围盒中心。两者不同时均入候选列表，
            # 依序尝试，以规避 Fusion 对特定半径/螺距组合的数值敏感性。
            # centroid 返回的是草图局部坐标，需要用 sketch.transform 转为全局坐标。
            f"_p0 = _sel if hasattr(_sel, 'areaProperties') else _sk.profiles.item(0)\n"
            f"_sk_transform = _sk.transform\n"
            f"_starts = []\n"
            f"try:\n"
            f"    _aprops = _p0.areaProperties(adsk.fusion.CalculationAccuracy.LowCalculationAccuracy)\n"
            f"    _cen = _aprops.centroid\n"
            f"    _cen.transformBy(_sk_transform)\n"
            f"    _starts.append((_cen.x, _cen.y, _cen.z))\n"
            f"except Exception:\n"
            f"    pass\n"
            f"_bbox0 = _p0.boundingBox\n"
            f"_bmin = _bbox0.minPoint.copy()\n"
            f"_bmax = _bbox0.maxPoint.copy()\n"
            f"_bmin.transformBy(_sk_transform)\n"
            f"_bmax.transformBy(_sk_transform)\n"
            f"_bx = (_bmin.x + _bmax.x) * 0.5\n"
            f"_by = (_bmin.y + _bmax.y) * 0.5\n"
            f"_bz = (_bmin.z + _bmax.z) * 0.5\n"
            # 仅当包围盒中心与重心不同时，才添加为第二个候选（避免重复）
            f"if not _starts or abs(_starts[0][0]-_bx)>1e-7 or abs(_starts[0][1]-_by)>1e-7:\n"
            f"    _starts.append((_bx, _by, _bz))\n"
            # ── 辅助函数：由中心点生成螺旋路径 ────────────────────────────
            # _bf_bodies 收集 baseFeature 创建的 wire body，清理时排除，
            # 避免删除 baseFeature body 时连带撤销依赖它的 sweep 特征。
            f"_bf_bodies = []\n"
            f"def _make_helix_path(scx, scy, scz):\n"
            f"    _t2 = (scx-_ap.x)*_av.x + (scy-_ap.y)*_av.y + (scz-_ap.z)*_av.z\n"
            f"    _fx2 = _ap.x+_t2*_av.x; _fy2 = _ap.y+_t2*_av.y; _fz2 = _ap.z+_t2*_av.z\n"
            f"    _rx2 = scx-_fx2; _ry2 = scy-_fy2; _rz2 = scz-_fz2\n"
            f"    _r2 = math.sqrt(_rx2*_rx2+_ry2*_ry2+_rz2*_rz2)\n"
            f"    if _r2 <= 1e-8:\n"
            f"        _pv2 = adsk.core.Vector3D.create(1,0,0) if abs(_av.x)<0.9 else adsk.core.Vector3D.create(0,1,0)\n"
            f"        _radv2 = _av.crossProduct(_pv2); _radv2.normalize(); _r2 = 1e-3\n"
            f"        _sp2 = adsk.core.Point3D.create(_fx2+_radv2.x*_r2, _fy2+_radv2.y*_r2, _fz2+_radv2.z*_r2)\n"
            f"    else:\n"
            f"        _sp2 = adsk.core.Point3D.create(scx, scy, scz)\n"
            f"    _tbm2 = adsk.fusion.TemporaryBRepManager.get()\n"
            f"    _hw2 = _tbm2.createHelixWire(_ap, _av, _sp2, {signed_pitch_cm!r}, {turns_val!r}, 0.0)\n"
            f"    if _hw2 is None or _hw2.edges.count == 0:\n"
            f"        return None\n"
            f"    try:\n"
            f"        return design.rootComponent.features.createPath(_hw2.edges.item(0), False)\n"
            f"    except Exception:\n"
            f"        _bf2 = design.rootComponent.features.baseFeatures.add()\n"
            f"        _bf2.startEdit()\n"
            f"        _pw2 = design.rootComponent.bRepBodies.add(_hw2, _bf2)\n"
            f"        _bf2.finishEdit()\n"
            f"        if _pw2 is None or _pw2.edges.count == 0:\n"
            f"            return None\n"
            f"        _bf_bodies.append(_pw2)\n"
            f"        try:\n"
            f"            return design.rootComponent.features.createPath(_pw2.edges.item(0), False)\n"
            f"        except Exception:\n"
            f"            return None\n"
            # ── 依次尝试各起点，直到扫掠成功 ───────────────────────────────
            f"_requested_op = adsk.fusion.FeatureOperations.{op_enum_name}\n"
            f"_direct_op = (_requested_op if _requested_op == adsk.fusion.FeatureOperations.NewBodyFeatureOperation "
            f"else adsk.fusion.FeatureOperations.NewBodyFeatureOperation)\n"
            f"_sweeps = design.rootComponent.features.sweepFeatures\n"
            f"_pre_existing = [design.rootComponent.bRepBodies.item(_i) for _i in range(design.rootComponent.bRepBodies.count)]\n"
            f"{key} = None\n"
            f"_last_path = None\n"
            f"for _s in _starts:\n"
            f"    _path = _make_helix_path(*_s)\n"
            f"    if _path is None: continue\n"
            f"    _last_path = _path\n"
            f"    _sinp = _sweeps.createInput(_sel, _path, _direct_op)\n"
            f"    _sinp.orientation = adsk.fusion.SweepOrientationTypes.PerpendicularOrientationType\n"
            f"    try:\n"
            f"        {key} = _sweeps.add(_sinp)\n"
            f"        break\n"
            f"    except Exception:\n"
            f"        pass\n"
            # ── Pipe 回退（所有扫掠候选均失败时）─────────────────────────
            f"_used_pipe = False\n"
            f"if {key} is None:\n"
            f"    if _last_path is None:\n"
            f"        raise RuntimeError('Failed to create helix wire/path for any start candidate.')\n"
            f"    _bbp = _p0.boundingBox\n"
            f"    _dxp = abs(_bbp.maxPoint.x - _bbp.minPoint.x)\n"
            f"    _dyp = abs(_bbp.maxPoint.y - _bbp.minPoint.y)\n"
            f"    _diam = min(v for v in (_dxp, _dyp) if v > 1e-8)\n"
            f"    _pipes = design.rootComponent.features.pipeFeatures\n"
            f"    _pinp = _pipes.createInput(_last_path, _direct_op)\n"
            f"    _pinp.sectionType = adsk.fusion.PipeSectionTypes.CircularPipeSectionType\n"
            f"    _pinp.sectionSize = adsk.core.ValueInput.createByReal(_diam)\n"
            f"    {key} = _pipes.add(_pinp)\n"
            f"    _used_pipe = True\n"
            f"if _requested_op != adsk.fusion.FeatureOperations.NewBodyFeatureOperation:\n"
            f"    _new_body = None\n"
            f"    for _i in range(design.rootComponent.bRepBodies.count - 1, -1, -1):\n"
            f"        _cand = design.rootComponent.bRepBodies.item(_i)\n"
            f"        if (_cand.isSolid) and all(_cand != _old for _old in _pre_existing) and all(_cand != _bf for _bf in _bf_bodies):\n"
            f"            _new_body = _cand\n"
            f"            break\n"
            f"    if _new_body is None:\n"
            f"        raise RuntimeError('Helix sweep did not create a tool body for combine.')\n"
            f"    if not _pre_existing:\n"
            f"        raise RuntimeError('No target body available for helix combine operation.')\n"
            f"    _tools = adsk.core.ObjectCollection.create()\n"
            f"    _tools.add(_new_body)\n"
            f"    _target = _pre_existing[-1]\n"
            f"    _comb = design.rootComponent.features.combineFeatures\n"
            f"    _cinp = _comb.createInput(_target, _tools)\n"
            f"    _cinp.operation = _requested_op\n"
            f"    _cinp.isKeepToolBodies = False\n"
            f"    {key} = _comb.add(_cinp)\n"
            f"_trash = adsk.core.ObjectCollection.create()\n"
            f"for _i in range(design.rootComponent.bRepBodies.count):\n"
            f"    _btmp = design.rootComponent.bRepBodies.item(_i)\n"
            f"    if (not _btmp.isSolid) and all(_btmp != _old for _old in _pre_existing) and all(_btmp != _bf for _bf in _bf_bodies):\n"
                f"        _trash.add(_btmp)\n"
            f"if _trash.count > 0:\n"
            f"    design.deleteEntities(_trash)\n"
            f"print(json.dumps({{'ok': True, 'ref': {key!r}, 'used_pipe': _used_pipe}}))\n"
        )

        # 7. Execute and parse result
        try:
            r = self.execute({"operation": "execute_python", "code": code})
            info = _json.loads(r["data"]["stdout"])
            info["ref"] = key
            self._capture_feature(
                "helix_sweep", key, consumed_sketch=sketch_ref,
                profile_from=sketch_ref, operation=operation,
                values={"pitch": float(pitch), "turns": float(turns),
                        "handedness": handedness},
            )
            return info["ref"]
        except Exception:
            self._capture_failed(
                "helix_sweep", key, consumed_sketch=sketch_ref,
                profile_from=sketch_ref, operation=operation,
            )
            raise
