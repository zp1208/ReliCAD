# -*- coding: utf-8 -*-
"""
MCP Bridge -- 倒角与圆角操作
query_edges：查询实体所有边的几何信息，供 LLM 推理后选边
fillet：    对选定边施加等半径圆角
chamfer：   对选定边施加等距倒角
"""
import json as _json

from .mcp_base import MCPBase

_MM = 0.1  # mm → cm（Fusion 360 内部单位）


class MCPChamferFillet(MCPBase):
    """倒角与圆角操作混入类。

    选边方式（fillet / chamfer 均支持两种，必须恰好提供一种）：
      - 索引模式：先调用 query_edges() 获得边列表，再传 edge_indices=[...]
      - 点坐标模式：传 edge_point=(x, y[, z]) mm，自动选取距该点最近的边
    """

    # ── 私有辅助方法 ───────────────────────────────────────────────────────

    @staticmethod
    def _resolve_body_expr(body_ref) -> str:
        """返回 execute_python 代码中访问实体的表达式字符串。

        Args:
            body_ref: None=最后一个实体；字符串（如 "extrude_0"）=特征的第一个实体
        """
        if body_ref is None:
            return (
                "design.rootComponent.bRepBodies.item("
                "design.rootComponent.bRepBodies.count - 1)"
            )
        return f"{body_ref}.bodies.item(0)"

    @staticmethod
    def _index_select_code(edge_indices) -> str:
        """返回索引模式的边选择代码片段（结果存入 _col）。

        Args:
            edge_indices: query_edges 返回的整数索引列表
        """
        indices_repr = repr(list(edge_indices))
        return (
            f"_col = adsk.core.ObjectCollection.create()\n"
            f"for _i in {indices_repr}:\n"
            f"    _col.add(_edges.item(_i))\n"
        )

    @staticmethod
    def _point_select_code(edge_point, threshold_mm: float = 1.0) -> str:
        """返回点坐标模式的边选择代码片段（结果存入 _col）。

        取全局最近边，比 cad_operations.py 的"第一个满足阈值"更健壮。

        Args:
            edge_point: (x, y[, z]) mm 坐标，z 缺省补 0
        """
        pt = list(edge_point)
        while len(pt) < 3:
            pt.append(0.0)
        px_cm = float(pt[0]) * _MM
        py_cm = float(pt[1]) * _MM
        pz_cm = float(pt[2]) * _MM
        threshold_cm = float(threshold_mm) * _MM

        return (
            f"_target_pt = adsk.core.Point3D.create({px_cm!r}, {py_cm!r}, {pz_cm!r})\n"
            f"_min_dist = float('inf')\n"
            f"_best_edge = None\n"
            f"for _i in range(_edges.count):\n"
            f"    _e = _edges.item(_i)\n"
            f"    try:\n"
            f"        _ev = _e.geometry.evaluator\n"
            f"        _ok1, _tmin, _tmax = _ev.getParameterExtents()\n"
            f"        if not _ok1: continue\n"
            f"        _ok2, _param = _ev.getParameterAtPoint(_target_pt)\n"
            f"        if not _ok2: continue\n"
            f"        _param = max(_tmin, min(_tmax, _param))\n"
            f"        _ok3, _closest = _ev.getPointAtParameter(_param)\n"
            f"        if not _ok3: continue\n"
            f"        _d = _target_pt.distanceTo(_closest)\n"
            f"        if _d < _min_dist:\n"
            f"            _min_dist = _d\n"
            f"            _best_edge = _e\n"
            f"    except Exception:\n"
            f"        pass\n"
            f"if _best_edge is None or _min_dist > {threshold_cm!r}:\n"
            f"    raise RuntimeError(\n"
            f"        f'在全局坐标系下,点坐标 ({pt[0]:.3f}, {pt[1]:.3f}, {pt[2]:.3f}) mm 未匹配到任何可用边。'\n"
            f"        f'可能原因: 1) 用于选择倒角/圆角边的全局坐标点不准确; '\n"
            f"        f'2) 前序约束求解导致目标边位置发生偏移; '\n"
            f"        f'3) 目标边尚未生成,或已被布尔/倒角/圆角操作改变。'\n"
            f"    )\n"
            f"_col = adsk.core.ObjectCollection.create()\n"
            f"_col.add(_best_edge)\n"
        )

    # ── 公共操作方法 ──────────────────────────────────────────────────────

    def query_edges(self, body_ref=None) -> dict:
        """查询实体所有边的几何信息，供 LLM 推理后选边。

        Args:
            body_ref: None=最后一个实体；字符串（如 "extrude_0"）=特征的第一个实体

        Returns:
            {
              "ok": True,
              "edges": [
                {
                  "index": 0,
                  "type": "Line3D" | "Arc3D" | "Circle3D" | ...,
                  "length_mm": 20.0,
                  "midpoint_mm": [10, 0, 20],
                  "vertices_mm": [[0, 0, 20], [20, 0, 20]],   # 闭合边（圆）为 []
                  "adjacent_face_normals": [[0, 0, 1], [0, -1, 0]],  # 与 _ftypes 平行，失败为 None
                  "adjacent_face_types": ["Plane", "Cylinder"]
                }, ...
              ]
            }

        Notes:
            adjacent_face_normals 和 adjacent_face_types 是平行数组，
            索引对应同一邻接面；法向量无法计算时为 None。
            此操作只读，不修改模型，不分配 _next_ref。
        """
        body_expr = self._resolve_body_expr(body_ref)
        code = (
            f"import adsk.core, adsk.fusion, json\n"
            f"_body = {body_expr}\n"
            f"_edges = _body.edges\n"
            f"_result = []\n"
            f"for _i in range(_edges.count):\n"
            f"    _e = _edges.item(_i)\n"
            f"    _geom_type = type(_e.geometry).__name__\n"
            f"    _ev = _e.geometry.evaluator\n"
            f"    _ok1, _tmin, _tmax = _ev.getParameterExtents()\n"
            f"    if not _ok1: continue\n"
            f"    _tmid = (_tmin + _tmax) * 0.5\n"
            f"    _ok2, _pt = _ev.getPointAtParameter(_tmid)\n"
            f"    _mid = [round(_pt.x/0.1,4), round(_pt.y/0.1,4), round(_pt.z/0.1,4)] if _ok2 else None\n"
            f"    _verts = []\n"
            f"    if _e.startVertex is not None:\n"
            f"        _sv = _e.startVertex.geometry\n"
            f"        _verts.append([round(_sv.x/0.1,4), round(_sv.y/0.1,4), round(_sv.z/0.1,4)])\n"
            f"    if _e.endVertex is not None and _e.endVertex is not _e.startVertex:\n"
            f"        _ev2 = _e.endVertex.geometry\n"
            f"        _verts.append([round(_ev2.x/0.1,4), round(_ev2.y/0.1,4), round(_ev2.z/0.1,4)])\n"
            f"    _fnorms = []\n"
            f"    _ftypes = []\n"
            f"    if _ok2:\n"
            f"        for _f in _e.faces:\n"
            f"            try:\n"
            f"                _norm_val = None\n"
            f"                _fev = _f.evaluator\n"
            f"                _fok, _fp = _fev.getParameterAtPoint(_pt)\n"
            f"                if _fok:\n"
            f"                    _nok, _fn = _fev.getNormalAtParameter(_fp)\n"
            f"                    if _nok:\n"
            f"                        _norm_val = [round(_fn.x,6), round(_fn.y,6), round(_fn.z,6)]\n"
            f"                _fnorms.append(_norm_val)\n"
            f"                _ftypes.append(type(_f.geometry).__name__)\n"
            f"            except Exception:\n"
            f"                pass\n"
            f"    _ok3, _len = _ev.getLengthAtParameter(_tmin, _tmax)\n"
            f"    _result.append({{'index': _i, 'type': _geom_type,\n"
            f"                    'length_mm': round(_len/0.1,4) if _ok3 else None,\n"
            f"                    'midpoint_mm': _mid, 'vertices_mm': _verts,\n"
            f"                    'adjacent_face_normals': _fnorms,\n"
            f"                    'adjacent_face_types': _ftypes}})\n"
            f"print(json.dumps({{'ok': True, 'edges': _result}}))\n"
        )

        r = self.execute({"operation": "execute_python", "code": code})
        return _json.loads(r["data"]["stdout"])

    def fillet(
        self,
        radius_mm: float,
        edge_indices=None,
        edge_point=None,
        body_ref=None,
        is_tangent_chain: bool = True,
        threshold_mm: float = 1.0,
    ) -> dict:
        """对选定边施加等半径圆角。

        Args:
            radius_mm:        圆角半径（mm），必须 > 0
            edge_indices:     索引模式：query_edges 返回的整数索引列表，可多条
            edge_point:       点坐标模式：(x, y[, z]) mm，找距该点最近的单条边
            body_ref:         None=最后一个实体；字符串（如 "extrude_0"）=特征的第一个实体
            is_tangent_chain: 是否自动延伸到相切边（默认 True）

        Returns:
            {"ok": True, "ref": "fillet_N"}

        Raises:
            ValueError:   radius_mm ≤ 0；edge_indices 和 edge_point 同时提供或均未提供
            RuntimeError: Fusion 360 执行失败
        """
        # 1. 参数校验
        if float(radius_mm) <= 0:
            raise ValueError(f"radius_mm 必须 > 0，当前值: {radius_mm!r}")
        if edge_indices is not None and edge_point is not None:
            raise ValueError("edge_indices 和 edge_point 只能提供其中一个")
        if edge_indices is None and edge_point is None:
            raise ValueError("必须提供 edge_indices 或 edge_point")

        # 2. 生成边选择代码
        if edge_indices is not None:
            edge_select_code = self._index_select_code(edge_indices)
        else:
            edge_select_code = self._point_select_code(edge_point, threshold_mm)

        # 3. 解析 body_ref 和计算半径
        body_expr = self._resolve_body_expr(body_ref)
        radius_cm = float(radius_mm) * _MM
        key = self._next_ref("fillet")

        # 4. 构建执行代码
        code = (
            f"import adsk.core, adsk.fusion, json\n"
            f"_body = {body_expr}\n"
            f"_edges = _body.edges\n"
            + edge_select_code
            + f"_r = adsk.core.ValueInput.createByReal({radius_cm!r})\n"
            f"_fillets = design.rootComponent.features.filletFeatures\n"
            f"_finp = _fillets.createInput()\n"
            f"_finp.addConstantRadiusEdgeSet(_col, _r, {is_tangent_chain!r})\n"
            f"try:\n"
            f"    {key} = _fillets.add(_finp)\n"
            f"    print(json.dumps({{'ok': True, 'ref': {key!r}}}))\n"
            f"except Exception as _exc:\n"
            f"    _msg = str(_exc)\n"
            f"    if 'FILLET_NO_EDGE_FOUND' in _msg:\n"
            f"        print(json.dumps({{'ok': False, 'skipped': True, 'reason': 'FILLET_NO_EDGE_FOUND', 'message': _msg}}))\n"
            f"    else:\n"
            f"        raise\n"
        )

        # 5. 执行并解析结果
        try:
            r = self.execute({"operation": "execute_python", "code": code})
            info = _json.loads(r["data"]["stdout"])
            if info.get("skipped"):
                self._capture_failed(
                    "fillet", key, body_ref=body_ref,
                    values={"radius": radius_mm,"edge_point": edge_point},
                    reason = "该错误被跳过，因为该错误可能是因为前面的圆角导致形状改变而发生的"
                )
                return None
            info["ref"] = key
            self._capture_feature(
                "fillet", key, body_ref=body_ref,
                values={"radius": radius_mm,"edge_point": edge_point},
            )
            return info["ref"]
        except Exception:
            self._capture_failed("fillet", key, body_ref=body_ref,values={"radius": radius_mm,"edge_point": edge_point})
            raise

    def chamfer(
        self,
        distance_mm: float,
        edge_indices=None,
        edge_point=None,
        body_ref=None,
        is_tangent_chain: bool = True,
        threshold_mm: float = 1.0,
    ) -> dict:
        """对选定边施加等距倒角（MVP：仅支持等距模式）。

        Args:
            distance_mm:      倒角距离（mm），必须 > 0
            edge_indices:     索引模式：query_edges 返回的整数索引列表，可多条
            edge_point:       点坐标模式：(x, y[, z]) mm，找距该点最近的单条边
            body_ref:         None=最后一个实体；字符串（如 "extrude_0"）=特征的第一个实体
            is_tangent_chain: 是否自动延伸到相切边（默认 True）

        Returns:
            {"ok": True, "ref": "chamfer_N"}

        Raises:
            ValueError:   distance_mm ≤ 0；edge_indices 和 edge_point 同时提供或均未提供
            RuntimeError: Fusion 360 执行失败
        """
        # 1. 参数校验
        if float(distance_mm) <= 0:
            raise ValueError(f"distance_mm 必须 > 0，当前值: {distance_mm!r}")
        if edge_indices is not None and edge_point is not None:
            raise ValueError("edge_indices 和 edge_point 只能提供其中一个")
        if edge_indices is None and edge_point is None:
            raise ValueError("必须提供 edge_indices 或 edge_point")

        # 2. 生成边选择代码
        if edge_indices is not None:
            edge_select_code = self._index_select_code(edge_indices)
        else:
            edge_select_code = self._point_select_code(edge_point, threshold_mm)

        # 3. 解析 body_ref 和计算距离
        body_expr = self._resolve_body_expr(body_ref)
        distance_cm = float(distance_mm) * _MM
        key = self._next_ref("chamfer")

        # 4. 构建执行代码
        code = (
            f"import adsk.core, adsk.fusion, json\n"
            f"_body = {body_expr}\n"
            f"_edges = _body.edges\n"
            + edge_select_code
            + f"_chamfers = design.rootComponent.features.chamferFeatures\n"
            f"_cinp = _chamfers.createInput(_col, {is_tangent_chain!r})\n"
            f"_cinp.setToEqualDistance(adsk.core.ValueInput.createByReal({distance_cm!r}))\n"
            f"{key} = _chamfers.add(_cinp)\n"
            f"print(json.dumps({{'ok': True, 'ref': {key!r}}}))\n"
        )

        # 5. 执行并解析结果
        try:
            r = self.execute({"operation": "execute_python", "code": code})
            info = _json.loads(r["data"]["stdout"])
            info["ref"] = key
            self._capture_feature(
                "chamfer", key, body_ref=body_ref,
                values={"distance": distance_mm,"edge_point": edge_point},
            )
            return info["ref"]
        except Exception:
            self._capture_failed("chamfer", key, body_ref=body_ref, values={"distance": distance_mm,"edge_point": edge_point})
            raise
