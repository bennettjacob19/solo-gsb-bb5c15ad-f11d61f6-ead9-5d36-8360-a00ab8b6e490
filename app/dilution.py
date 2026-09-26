"""串联稀释（serial dilution）核心计算逻辑。

全部使用 Decimal 高精度运算；可行性判断一律基于未取整的精确值，
展示用的取整只在序列化输出时进行，不参与任何判断。

算法：
1. 从末管向前回推每管需要制备的总量：
   制备量(i) = 保留体积(i) + 预留损耗(i) + 后管取液量(i+1)
   其中 后管取液量(i+1) = 制备量(i+1) × 目标浓度(i+1) / 目标浓度(i)
2. 再从前向后计算每级的取液量与稀释液量：
   取液量(i)   = 制备量(i) × 目标浓度(i) / 上一级浓度(i-1)（第 1 管的上一级为母液）
   稀释液量(i) = 制备量(i) - 取液量(i)
3. 可行性（按未取整值判断）：
   - 目标浓度未严格小于上一级浓度 -> 浓度次序错误
   - 取液量 < 移液下限           -> 取液不可行
   - 稀释液量 < 移液下限         -> 加液不可行
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, getcontext
from typing import Any, Dict, List

# 计算精度（有效位数），远高于任何移液场景所需
getcontext().prec = 50

# 展示用的小数位数（仅显示，不参与判断）
DISPLAY_PLACES = 3

ISSUE_CONCENTRATION_ORDER = "CONCENTRATION_ORDER"
ISSUE_TAKE_BELOW_MIN = "TAKE_BELOW_MIN"
ISSUE_DILUENT_BELOW_MIN = "DILUENT_BELOW_MIN"

ISSUE_TEXT = {
    ISSUE_CONCENTRATION_ORDER: "目标浓度未低于上一级浓度（浓度必须逐级递减）",
    ISSUE_TAKE_BELOW_MIN: "取液量低于移液下限",
    ISSUE_DILUENT_BELOW_MIN: "稀释液加入量低于移液下限",
}


class DilutionInputError(ValueError):
    """输入参数不合法。"""


@dataclass
class TubeSpec:
    concentration: Decimal
    retain_volume: Decimal
    loss_volume: Decimal


@dataclass
class Step:
    index: int  # 管号，从 1 开始
    source: str  # 取液来源（母液 / 第 N 管）
    target_concentration: Decimal
    prepare_volume: Decimal  # 该管需制备的总量
    take_volume: Decimal  # 从上一级取液量
    diluent_volume: Decimal  # 稀释液加入量
    retain_volume: Decimal  # 保留体积
    loss_volume: Decimal  # 预留损耗
    issues: List[str] = field(default_factory=list)


def _to_decimal(raw: Any, name: str) -> Decimal:
    try:
        text = str(raw).strip()
        if not text:
            raise InvalidOperation
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        raise DilutionInputError(f"{name} 不是有效数字：{raw!r}")
    if value.is_nan() or value.is_infinite():
        raise DilutionInputError(f"{name} 必须是有限数字：{raw!r}")
    return value


def _fmt(value: Decimal, places: int = DISPLAY_PLACES) -> str:
    """格式化为固定小数位并去掉末尾的 0，仅用于展示。"""
    quantum = Decimal(1).scaleb(-places)
    rounded = value.quantize(quantum, rounding=ROUND_HALF_UP)
    text = format(rounded, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _fmt_exact(value: Decimal) -> str:
    """原样输出精确值（用于浓度等用户输入的短小数）。"""
    return format(value.normalize(), "f")


def compute_plan(
    stock_concentration: Any,
    pipette_min: Any,
    tubes: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """计算串联稀释方案，返回可 JSON 序列化的结果。"""
    stock = _to_decimal(stock_concentration, "母液浓度")
    if stock <= 0:
        raise DilutionInputError("母液浓度必须大于 0")

    min_vol = _to_decimal(pipette_min, "移液下限")
    if min_vol < 0:
        raise DilutionInputError("移液下限不能为负")

    if not tubes:
        raise DilutionInputError("至少需要 1 个目标管")

    specs: List[TubeSpec] = []
    for idx, tube in enumerate(tubes, start=1):
        conc = _to_decimal(tube.get("concentration"), f"第 {idx} 管目标浓度")
        retain = _to_decimal(tube.get("retain_volume"), f"第 {idx} 管保留体积")
        loss_raw = tube.get("loss_volume")
        loss = (
            Decimal(0)
            if loss_raw is None or str(loss_raw).strip() == ""
            else _to_decimal(loss_raw, f"第 {idx} 管预留损耗")
        )
        if conc <= 0:
            raise DilutionInputError(f"第 {idx} 管目标浓度必须大于 0")
        if retain < 0:
            raise DilutionInputError(f"第 {idx} 管保留体积不能为负")
        if loss < 0:
            raise DilutionInputError(f"第 {idx} 管预留损耗不能为负")
        specs.append(TubeSpec(conc, retain, loss))

    n = len(specs)
    # 每一级的上一级浓度：第 1 级为母液，其余为前一管
    prev_concs = [stock] + [s.concentration for s in specs[:-1]]

    # 1) 从末管向前回推每管需要制备的总量（计入后管取液）
    prepare = [Decimal(0)] * n
    prepare[-1] = specs[-1].retain_volume + specs[-1].loss_volume
    for i in range(n - 2, -1, -1):
        next_take = prepare[i + 1] * specs[i + 1].concentration / specs[i].concentration
        prepare[i] = specs[i].retain_volume + specs[i].loss_volume + next_take

    # 2) 前向计算每级取液量与稀释液量，并按未取整值判定可行性
    steps: List[Step] = []
    for i in range(n):
        spec = specs[i]
        prev = prev_concs[i]
        take = prepare[i] * spec.concentration / prev
        diluent = prepare[i] - take

        issues: List[str] = []
        if spec.concentration >= prev:
            issues.append(ISSUE_CONCENTRATION_ORDER)
        if take < min_vol:
            issues.append(ISSUE_TAKE_BELOW_MIN)
        if diluent < min_vol:
            issues.append(ISSUE_DILUENT_BELOW_MIN)

        steps.append(
            Step(
                index=i + 1,
                source="母液" if i == 0 else f"第 {i} 管",
                target_concentration=spec.concentration,
                prepare_volume=prepare[i],
                take_volume=take,
                diluent_volume=diluent,
                retain_volume=spec.retain_volume,
                loss_volume=spec.loss_volume,
                issues=issues,
            )
        )

    # 母液总消耗 = 第 1 管从母液取出的体积
    total_stock = steps[0].take_volume
    feasible = all(not s.issues for s in steps)

    return {
        "feasible": feasible,
        "tube_count": n,
        "total_stock_consumption": _fmt(total_stock),
        "steps": [
            {
                "tube": s.index,
                "source": s.source,
                "target_concentration": _fmt_exact(s.target_concentration),
                "prepare_volume": _fmt(s.prepare_volume),
                "take_volume": _fmt(s.take_volume),
                "diluent_volume": _fmt(s.diluent_volume),
                "retain_volume": _fmt(s.retain_volume),
                "loss_volume": _fmt(s.loss_volume),
                "feasible": not s.issues,
                "issues": [ISSUE_TEXT[code] for code in s.issues],
            }
            for s in steps
        ],
    }
