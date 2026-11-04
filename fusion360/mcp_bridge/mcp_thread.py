# -*- coding: utf-8 -*-
"""
MCP Bridge -- 螺纹操作
add_thread：对圆柱面施加 modeled 螺纹（isModeled=True）
"""
import json as _json

from .mcp_base import MCPBase

_MM = 0.1  # mm → cm（Fusion 360 内部单位）


class MCPThread(MCPBase):
    """螺纹操作混入类。

    自动选取圆柱面：
      is_internal=True  → 选半径最小的圆柱面（孔内壁）
      is_internal=False → 选面积最大的圆柱面（外圆柱面）
    支持 face_point 参数通过坐标精确指定目标圆柱面。
    自动跳过已有螺纹特征的面。
    """

    @staticmethod
    def _resolve_body_expr(body_ref) -> str:
        if body_ref is None:
            return (
                "design.rootComponent.bRepBodies.item("
                "design.rootComponent.bRepBodies.count - 1)"
            )
        return f"{body_ref}.bodies.item(0)"

    @staticmethod
    def _point_select_face_code(face_point) -> str:
        """生成 Fusion 360 代码：通过空间点定位最近的圆柱面。"""
        pt = list(face_point)
        while len(pt) < 3:
            pt.append(0.0)
        px_cm = float(pt[0]) * _MM
        py_cm = float(pt[1]) * _MM
        pz_cm = float(pt[2]) * _MM

        return (
            f"_target_pt = adsk.core.Point3D.create({px_cm!r}, {py_cm!r}, {pz_cm!r})\n"
            f"_thread_features = design.rootComponent.features.threadFeatures\n"
            f"_min_dist = float('inf')\n"
            f"_candidate = None\n"
            f"for _idx in range(_body.faces.count):\n"
            f"    _face = _body.faces.item(_idx)\n"
            f"    _geom = _face.geometry\n"
            f"    if not (_geom and _geom.objectType.endswith('Cylinder')):\n"
            f"        continue\n"
            f"    _origin = _geom.origin\n"
            f"    _axis = _geom.axis\n"
            f"    _vx = _target_pt.x - _origin.x\n"
            f"    _vy = _target_pt.y - _origin.y\n"
            f"    _vz = _target_pt.z - _origin.z\n"
            f"    _proj = _vx * _axis.x + _vy * _axis.y + _vz * _axis.z\n"
            f"    _dx = _vx - _proj * _axis.x\n"
            f"    _dy = _vy - _proj * _axis.y\n"
            f"    _dz = _vz - _proj * _axis.z\n"
            f"    _d = (_dx*_dx + _dy*_dy + _dz*_dz) ** 0.5\n"
            f"    if _d < _min_dist:\n"
            f"        _min_dist = _d\n"
            f"        _candidate = (_geom.radius, _face.area, _idx)\n"
            f"if _candidate is None:\n"
            f"    raise RuntimeError('No cylindrical face found near the specified point.')\n"
            f"_selected_faces = [_body.faces.item(_candidate[2])]\n"
        )

    @staticmethod
    def _multi_point_select_face_code(face_points) -> str:
        """生成 Fusion 360 代码：通过多个空间点定位多个圆柱面。"""
        # 生成所有目标点
        points_code = "_target_pts = [\n"
        for pt in face_points:
            pt_list = list(pt)
            while len(pt_list) < 3:
                pt_list.append(0.0)
            px_cm = float(pt_list[0]) * _MM
            py_cm = float(pt_list[1]) * _MM
            pz_cm = float(pt_list[2]) * _MM
            points_code += f"    adsk.core.Point3D.create({px_cm!r}, {py_cm!r}, {pz_cm!r}),\n"
        points_code += "]\n"

        return (
            points_code +
            f"_thread_features = design.rootComponent.features.threadFeatures\n"
            f"_selected_faces = []\n"
            f"for _target_pt in _target_pts:\n"
            f"    _min_dist = float('inf')\n"
            f"    _candidate = None\n"
            f"    for _idx in range(_body.faces.count):\n"
            f"        _face = _body.faces.item(_idx)\n"
            f"        _geom = _face.geometry\n"
            f"        if not (_geom and _geom.objectType.endswith('Cylinder')):\n"
            f"            continue\n"
            f"        _origin = _geom.origin\n"
            f"        _axis = _geom.axis\n"
            f"        _vx = _target_pt.x - _origin.x\n"
            f"        _vy = _target_pt.y - _origin.y\n"
            f"        _vz = _target_pt.z - _origin.z\n"
            f"        _proj = _vx * _axis.x + _vy * _axis.y + _vz * _axis.z\n"
            f"        _dx = _vx - _proj * _axis.x\n"
            f"        _dy = _vy - _proj * _axis.y\n"
            f"        _dz = _vz - _proj * _axis.z\n"
            f"        _d = (_dx*_dx + _dy*_dy + _dz*_dz) ** 0.5\n"
            f"        if _d < _min_dist:\n"
            f"            _min_dist = _d\n"
            f"            _candidate = (_geom.radius, _face.area, _idx)\n"
            f"    if _candidate is None:\n"
            f"        raise RuntimeError('No cylindrical face found near one of the specified points.')\n"
            f"    _selected_faces.append(_body.faces.item(_candidate[2]))\n"
        )

    @staticmethod
    def _auto_select_face_code(is_internal: bool, num: int = 1) -> str:
        """生成 Fusion 360 代码：按半径/面积自动选择 num 个圆柱面。"""
        return (
            f"_thread_features = design.rootComponent.features.threadFeatures\n"
            f"_internal = {is_internal!r}\n"
            f"_candidates = []\n"
            f"for _idx in range(_body.faces.count):\n"
            f"    _face = _body.faces.item(_idx)\n"
            f"    _geom = _face.geometry\n"
            f"    if not (_geom and _geom.objectType.endswith('Cylinder')):\n"
            f"        continue\n"
            f"    _candidates.append((_geom.radius, _face.area, _idx, _face))\n"
            f"if not _candidates:\n"
            f"    raise RuntimeError('No cylindrical face found for thread feature.')\n"
            f"# 按半径（内螺纹）或面积（外螺纹）排序\n"
            f"if _internal:\n"
            f"    _candidates.sort(key=lambda x: x[0])  # 半径升序\n"
            f"else:\n"
            f"    _candidates.sort(key=lambda x: x[1], reverse=True)  # 面积降序\n"
            f"# 选择前 num 个\n"
            f"_num = min({num}, len(_candidates))\n"
            f"_selected_faces = [c[3] for c in _candidates[:_num]]\n"
        )

    def add_thread(
        self,
        is_internal: bool,
        designation: str = None,
        handedness: str = "Right",
        full_length: bool = True,
        thread_length: float = None,
        thread_offset: float = 0.0,
        thread_location: str = "start",
        body_ref=None,
        face_point=None,
        num: int = 1,
    ) -> str:
        """对圆柱面施加 modeled 螺纹。

        Args:
            is_internal:     True=内螺纹（选最小半径圆柱面），False=外螺纹（选最大面积圆柱面）
            designation:     ISO 公制规格如 "M10x1.5"；None 时根据圆柱直径自动推断
            handedness:      "Right" / "Left"
            full_length:     True=整段起牙；False=部分螺纹，需配合 thread_length
            thread_length:   螺纹长度（mm）；仅 full_length=False 时有效
            thread_offset:   螺纹起点距端面偏移（mm），默认 0
            thread_location: "start" / "end"，偏移从哪端量
            body_ref:        None=最后一个实体；"extrude_0"=特征第一个实体
            face_point:      单个坐标 (x,y,z) 或坐标列表 [(x1,y1,z1), (x2,y2,z2), ...]，
                             指定目标圆柱面位置；None 时按半径/面积自动选择
            num:             自动选择的圆柱面数量（仅 face_point=None 时有效），默认 1

        Returns:
            "thread_N"

        Raises:
            ValueError:   handedness / thread_location 不合法；
                          full_length=False 时未提供 thread_length
            RuntimeError: 找不到圆柱面，或 Fusion 360 执行失败
        """
        # 1. 参数校验
        hand_lower = str(handedness).strip().lower()
        if hand_lower not in ("right", "left"):
            raise ValueError(f"不支持的 handedness: {handedness!r}，可选: Right, Left")
        is_right_handed = hand_lower == "right"

        loc_lower = str(thread_location).strip().lower()
        if loc_lower not in ("start", "end"):
            raise ValueError(f"不支持的 thread_location: {thread_location!r}，可选: start, end")
        is_from_end = loc_lower == "end"

        if not full_length and thread_length is None:
            raise ValueError("full_length=False 时必须提供 thread_length")
        if thread_length is not None and float(thread_length) <= 0:
            raise ValueError(f"thread_length 必须 > 0，当前值: {thread_length!r}")

        # 2. 单位转换
        thread_length_cm = float(thread_length) * _MM if thread_length is not None else 0.0
        thread_offset_cm = float(thread_offset) * _MM

        # 3. 生成 ref key
        key = self._next_ref("thread")

        # 4. 构建执行代码
        body_expr = self._resolve_body_expr(body_ref)
        designation_repr = repr(designation)  # None 或 "M10x1.5"

        # 判断 face_point 类型并选择对应的选面代码
        if face_point is not None:
            # 检查是否是坐标列表
            if isinstance(face_point, (list, tuple)) and len(face_point) > 0:
                # 判断第一个元素是否也是列表/元组（多个坐标）
                if isinstance(face_point[0], (list, tuple)):
                    face_select_code = self._multi_point_select_face_code(face_point)
                else:
                    # 单个坐标元组
                    face_select_code = self._point_select_face_code(face_point)
            else:
                face_select_code = self._point_select_face_code(face_point)
        else:
            # 自动选择 num 个面
            face_select_code = self._auto_select_face_code(is_internal, num)

        # _selected_faces 是一个列表，包含所有要加螺纹的面
        code = (
            f"import adsk.core, adsk.fusion, json\n"
            f"_body = {body_expr}\n"
            + face_select_code
            # _thread_features 和 _selected_faces 已在 face_select_code 中定义
            + f"# 使用第一个面的半径推断螺纹规格\n"
            f"_first_face = _selected_faces[0]\n"
            f"_first_geom = _first_face.geometry\n"
            f"_query = _thread_features.threadDataQuery\n"
            f"_thread_type = _query.defaultMetricThreadType\n"
            f"_recommended = _query.recommendThreadData(_first_geom.radius * 2.0, {is_internal!r}, _thread_type)\n"
            f"if not isinstance(_recommended, (list, tuple)) or len(_recommended) < 3:\n"
            f"    raise RuntimeError(f'recommendThreadData failed: {{_recommended!r}}')\n"
            f"_ok, _rec_designation, _thread_class = _recommended[:3]\n"
            f"if not _ok:\n"
            f"    raise RuntimeError('recommendThreadData returned False')\n"
            f"_designation = {designation_repr} if {designation_repr} is not None else _rec_designation\n"
            f"_thread_info = _thread_features.createThreadInfo({is_internal!r}, _thread_type, _designation, _thread_class)\n"
            # 创建 ThreadFeatureInput
            f"_thread_input = _thread_features.createInput(_first_face, _thread_info)\n"
            f"_thread_input.isModeled = True\n"
            f"_thread_input.isFullLength = {full_length!r}\n"
            f"_thread_input.isRightHanded = {is_right_handed!r}\n"
        )

        if not full_length:
            code += (
                f"_thread_input.threadLength = adsk.core.ValueInput.createByReal({thread_length_cm!r})\n"
                f"_thread_input.threadOffset = adsk.core.ValueInput.createByReal({thread_offset_cm!r})\n"
                f"_thread_input.isFromEnd = {is_from_end!r}\n"
            )

        # 使用 inputCylindricalFaces 设置多个面
        code += (
            f"# 使用 inputCylindricalFaces 一次性给多个面加螺纹\n"
            f"_faces_collection = adsk.core.ObjectCollection.create()\n"
            f"for _f in _selected_faces:\n"
            f"    _faces_collection.add(_f)\n"
            f"_thread_input.inputCylindricalFaces = _faces_collection\n"
            f"{key} = _thread_features.add(_thread_input)\n"
            f"print(json.dumps({{'ok': True, 'ref': {key!r}, "
            f"'designation': {key}.threadInfo.threadDesignation, "
            f"'thread_class': {key}.threadInfo.threadClass, "
            f"'is_internal': {key}.threadInfo.isInternal, "
            f"'is_right_handed': {key}.isRightHanded, "
            f"'is_full_length': {key}.isFullLength, "
            f"'major_diameter': {key}.threadInfo.majorDiameter * 10, "
            f"'minor_diameter': {key}.threadInfo.minorDiameter * 10, "
            f"'pitch': {key}.threadInfo.threadPitch * 10, "
            f"'faces_count': _faces_collection.count}}))\n"
        )

        # 5. 执行并解析结果
        try:
            r = self.execute({"operation": "execute_python", "code": code})
            info = _json.loads(r["data"]["stdout"])
            info["ref"] = key
            # thread 含自动推断（designation 可为 None 由 Fusion 推断），
            # 用 Fusion 创建时已解析出的真实值作为证据，而非用户输入。
            self._capture_feature(
                "thread", key, body_ref=body_ref,
                values={
                    "designation": info.get("designation"),
                    "thread_class": info.get("thread_class"),
                    "is_internal": info.get("is_internal"),
                    "is_right_handed": info.get("is_right_handed"),
                    "is_full_length": info.get("is_full_length"),
                    "major_diameter": info.get("major_diameter"),
                    "minor_diameter": info.get("minor_diameter"),
                    "pitch": info.get("pitch"),
                },
            )
            return info["ref"]
        except Exception:
            self._capture_failed("thread", key, body_ref=body_ref)
            raise
