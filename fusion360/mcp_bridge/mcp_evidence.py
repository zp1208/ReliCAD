# -*- coding: utf-8 -*-
"""
MCP Bridge -- 运行时证据捕获器

职责：
  记录建模序列的运行时真值（世界坐标），用于验证/调试/回溯。

核心流程：
  1. 草图图元 → _pending 缓冲区（记录 before）
  2. 约束求解（不记录）
  3. 特征消费草图 → flush _pending（读 after，比对 constraint_moved）
  4. 辅助线（未被消费的图元）自动丢弃
  5. dump_evidence 填变量名 → 写 .evidence.json
"""
import re
import json
from datetime import datetime

_REF_RE = re.compile(
    r"^(sketch|line|circle|arc|ellipse|elliptical_arc|nurbs|"
    r"extrude|revolve|helix_sweep|chamfer|fillet|thread)_\d+$"
)
_MOVE_TOL = 1e-3  # mm，判断约束是否移动图元的阈值


class MCPEvidence:
    """证据捕获混入类，记录建模序列的运行时真值。

    依赖：
      - self.get_entity_info(ref) — 读草图图元几何属性（世界坐标）。
        仅草图图元需要回读（约束求解会移动图元，要 before/after 比对）。
        特征参数不会被约束修改，输入即真值，由调用方直接以 values= 传入。

    容器：
      - _pending: {sketch_ref: [图元记录]} — 缓冲区，按草图分组
      - _sequence: [步骤字典] — 最终建模序列
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pending: dict[str, list[dict]] = {}   # {sketch_ref: [图元记录(含before)]}
        self._sequence: list[dict] = []             # 最终建模序列

    def reset_capture(self):
        """重置证据捕获状态（clear() 时调用）。"""
        self._pending.clear()
        self._sequence.clear()

    # ── 记录入口 ──────────────────────────────────────────────────────────

    def _log_sketch(self, ref, **rel):
        """记录草图创建（直接进 _sequence）。

        Args:
            ref: 草图引用（如 "sketch_0"）
            **rel: 附加属性（plane, offset, euler_angles, translation 等）
        """
        self._sequence.append({"op": "create_sketch", "ref": ref, **rel})

    def _log_primitive(self, op, ref, sketch):
        """记录草图图元（进 _pending 缓冲区，立刻读 before）。

        Args:
            op: 操作名（"add_line", "add_circle" 等）
            ref: 图元引用（如 "line_1"）
            sketch: 所属草图引用（如 "sketch_0"）
        """
        before = self.get_entity_info(ref)

        self._pending.setdefault(sketch, []).append({
            "op": op,
            "ref": ref,
            "sketch": sketch,
            "before": before,
        })

    def _capture_feature(self, op, ref, consumed_sketch=None, values=None, **rel):
        """捕获特征执行成功（成功路径，消费/不消费草图统一）。

        Args:
            op: 操作名（"extrude", "chamfer" 等）
            ref: 特征引用（如 "extrude_7"）
            consumed_sketch: 被消费的草图引用（如 "sketch_0"），
                           消费草图的特征（extrude/revolve/helix_sweep）传此参数，
                           不消费草图的（chamfer/fillet/thread）不传
            values: 特征自身真值字典（由调用方直接提供输入值）。
                    特征参数不会被约束求解修改，输入即真值，无需回读 Fusion。
                    thread 等含自动推断的特征，传创建时解析出的真实值。
            **rel: 附加属性（operation, profile_from, body_ref 等）

        流程：
            1. 如果消费草图：flush _pending[consumed_sketch]
               - 读每个图元的 after（草图图元会被约束移动，必须回读）
               - 比对 before vs after → constraint_moved + max_delta_mm
               - 追加进 _sequence
            2. 追加特征记录进 _sequence（values 直接用入参）
        """
        # 1. flush 被消费草图的图元（草图图元才需回读 after，因为约束会移动它）
        for p in self._pending.pop(consumed_sketch, []):
            after = self.get_entity_info(p["ref"])
            moved, delta = self._compare(p["before"], after)
            self._sequence.append({
                "op": p["op"],
                "ref": p["ref"],
                "sketch": p["sketch"],
                "values": after,
                "constraint_moved": moved,
                "max_delta_mm": delta,
            })

        # 2. 特征自身真值（输入即真值，调用方直接提供）
        feature_record = {
            "op": op,
            "ref": ref,
            **rel,
            "values": values or {},
        }
        # 消费草图的特征记录 consumed_sketch（dump 时据此分组）
        if consumed_sketch:
            feature_record["consumed_sketch"] = consumed_sketch
        self._sequence.append(feature_record)

    def _capture_failed(self, op, ref, consumed_sketch=None, **rel):
        """捕获特征执行失败（保留失败现场）。

        Args:
            op: 操作名
            ref: 特征引用
            consumed_sketch: 被消费的草图引用（如有）
            **rel: 附加属性

        流程：
            1. 如果消费草图：flush _pending[consumed_sketch]
               - 尽力读每个图元的当前值（失败现场）
               - 不比对 constraint_moved（因为特征失败了）
            2. 追加特征失败记录（status="failed"）
        """
        # 1. 保留失败现场（已画好的草图图元）
        for p in self._pending.pop(consumed_sketch, []):
            vals = self.get_entity_info(p["ref"])
            self._sequence.append({
                "op": p["op"],
                "ref": p["ref"],
                "sketch": p["sketch"],
                "values": vals,
            })

        # 2. 特征失败记录
        feature_record = {
            "op": op,
            "ref": ref,
            **rel,
            "status": "执行该特征时出现错误",
        }
        # 消费草图的特征记录 consumed_sketch（dump 时据此分组）
        if consumed_sketch:
            feature_record["consumed_sketch"] = consumed_sketch
        self._sequence.append(feature_record)

    # ── 辅助方法 ──────────────────────────────────────────────────────────

    def _compare(self, before, after):
        """比对 before/after 两次读取，判断约束是否移动图元。

        Args:
            before: get_entity_info 约束前读取的字典
            after: get_entity_info 约束后读取的字典

        Returns:
            (moved: bool | None, max_delta: float | None)
            - moved: 是否移动（Δ > _MOVE_TOL）
            - max_delta: 所有字段的最大变化量（mm）
        """
        if not before or not after:
            return None, None

        d = 0.0
        for k, b in before.items():
            if k == "type":
                continue
            a = after.get(k)
            if isinstance(b, (int, float)) and isinstance(a, (int, float)):
                d = max(d, abs(a - b))
            elif isinstance(b, list) and isinstance(a, list):
                for bi, ai in zip(b, a):
                    if isinstance(bi, (int, float)) and isinstance(ai, (int, float)):
                        d = max(d, abs(ai - bi))

        return d > _MOVE_TOL, round(d, 4)

    def _group_sequence(self, flat_seq):
        """将平铺序列分组为层次结构（消费草图的特征 → sketch_feature_group）。

        靠引用关系分组，不靠位置：图元缓冲在 _pending、被特征消费时才 flush，
        交错建模时草图/图元/特征在 flat_seq 里不一定相邻。但特征一定出现在
        它的草图和图元之后，所以单遍遍历、边走边攒、遇到消费特征即组装。

        Args:
            flat_seq: 平铺序列（已填好 name 的 self._sequence）

        Returns:
            分组后的序列（已经 _strip_node 精简：op→顶层 type、删 ref/max_delta_mm/
            基元 sketch/特征 profile_from/consumed_sketch、基元 values.type 上提）：
              - 消费草图的特征 → {"type": "sketch_feature_group", sketch, primitives, feature}
              - 不消费草图的特征（fillet/chamfer/thread）→ 原样平铺
              - 辅助草图（无特征消费）→ 丢弃（攒着没人取，永不输出）

        判定（无需硬编码操作名单）：
          create_sketch → 草图；带 "sketch" 字段 → 图元；带 "consumed_sketch" → 消费特征
        """
        grouped = []
        sketches = {}            # sketch_ref -> create_sketch 记录（攒着等特征取）
        prims = {}               # sketch_ref -> [图元记录]（攒着等特征取）
        for s in flat_seq:
            if s["op"] == "create_sketch":
                sketches[s["ref"]] = s
            elif s.get("sketch"):
                prims.setdefault(s["sketch"], []).append(s)
            elif s.get("consumed_sketch"):
                sk = s["consumed_sketch"]
                grouped.append({
                    "op": "sketch_feature_group",
                    "sketch": sketches.get(sk),
                    "primitives": prims.get(sk, []),
                    "feature": s,
                })
            else:
                grouped.append(s)   # 不消费草图的特征 → 平铺
        # 末尾精简：删内部字段、type 上提/补全（分组已完成，consumed_sketch 等可安全删）
        return [self._strip_node(s) for s in grouped]

    def _strip_node(self, node):
        """精简单节点：删 op/ref/max_delta_mm/profile_from/consumed_sketch/body_ref 及基元的 sketch
        字符串引用，确定顶层 type（置首位），递归下钻 group 的 primitives/sketch/feature。

        type：基元（values 是 dict 且含 "type"）取 values["type"]；其余取 op，
              op 以 "add_" 开头则去前缀（兜底基元失败 values=None 时仍得 line 等）。
        用 values 副本构建，绝不修改 self._sequence 原对象。
        """
        if not isinstance(node, dict):
            return node
        values = node.get("values")
        is_prim = isinstance(values, dict) and "type" in values
        if is_prim:
            type_val = values["type"]
        else:
            op = node.get("op", "")
            type_val = op[4:] if op.startswith("add_") else op
        out = {"type": type_val}
        for k, v in node.items():
            if k in ("op", "ref", "max_delta_mm", "profile_from", "consumed_sketch", "body_ref"):
                continue
            if k == "sketch" and isinstance(v, str):      # 基元的从属草图引用 → 删
                continue
            if k == "values" and is_prim:
                out[k] = {vk: vv for vk, vv in v.items() if vk != "type"}
            elif k == "primitives" and isinstance(v, list):
                out[k] = [self._strip_node(p) for p in v]
            elif k in ("sketch", "feature") and isinstance(v, dict):  # group 子结构 → 递归
                out[k] = self._strip_node(v)
            else:
                out[k] = v
        return out


    def dump_evidence(self, path, name_scope, partial=False):
        """填充变量名并写出 .evidence.json。

        Args:
            path: 输出文件路径（如 "result/xxx.evidence.json"）
            name_scope: locals() 字典（运行时变量作用域）
            partial: 是否为部分证据（失败时 True）

        流程：
            1. 从 name_scope 反查变量名（ref → 变量名）
            2. 填入 _sequence 的每个步骤
            3. 分组：消费草图的特征 → sketch_feature_group；辅助草图丢弃
            4. 写 JSON
        """
        # 1. 反查变量名
        names = {}
        for var, val in name_scope.items():
            if isinstance(val, str) and _REF_RE.match(val):
                names.setdefault(val, var)
            elif isinstance(val, (list, tuple)):
                for i, v in enumerate(val):
                    if isinstance(v, str) and _REF_RE.match(v):
                        names.setdefault(v, f"{var}[{i}]")

        # 2. 填入 _sequence
        for step in self._sequence:
            step["name"] = names.get(step["ref"])

        # 3. 分组（消费草图的特征 → sketch_feature_group，辅助草图丢弃）
        grouped_seq = self._group_sequence(self._sequence)

        # 4. 写 JSON
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "units": {"length": "mm", "angle": "deg"},
                    "captured_at": datetime.now().isoformat(),
                    "note": (
                        "All geometric values are in global coordinates. "
                        "'point_on' is one of the points that can be used to index/identify that edge/curve. "
                        "'constraint_moved' indicates if constraint solving moved the primitive. "
                        "'edge_point' is the index point used when adding fillet/chamfer to identify which edge."
                    ),
                    "sequence": grouped_seq,
                    # "sequence": self._sequence,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
