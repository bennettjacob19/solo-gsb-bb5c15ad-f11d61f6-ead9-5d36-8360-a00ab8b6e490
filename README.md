# 串联稀释配液计算器

基于 **FastAPI + Decimal + 原生 JS** 的串联稀释（serial dilution）配液 Web 应用。

输入母液浓度、逐级递减的目标浓度、各管保留体积、预留损耗和移液下限后，应用会**从末管向前回推**每管需要制备的总量（计入后管取液），再逐级算出每管的**前管取液量**与**稀释液量**，并展示逐管步骤与母液总消耗。所有计算使用 `Decimal` 高精度完成，**可行性一律按未取整的精确值判定**（页面显示值取整到 0.001，仅供参考）。

## 一键启动

只需一条命令（自动完成依赖安装与初始化，无需数据库等额外组件）：

```bash
docker compose up --build
```

启动后在浏览器访问：

- **本地地址：** http://localhost:8000
- **端口：** 8000

## 配置

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| 对外端口 | `8000` | 通过环境变量 `PORT` 修改，如 `PORT=9000 docker compose up --build`，然后访问 http://localhost:9000 |
| 容器内端口 | `8000` | 固定，见 `Dockerfile` 与 `docker-compose.yml` |

除端口外无需其他配置；停止服务用 `docker compose down`。

## 使用说明

1. 填写**母液浓度**与**移液下限**（体积单位，如 µL）。
2. 为每个目标管填写**目标浓度**（必须逐级递减）、**保留体积**、**预留损耗**；可点击「＋ 添加目标管」增加级数。
3. 点击「计 算」，页面展示：
   - 方案是否可行、**母液总消耗**（= 第 1 管从母液取出的体积）；
   - 逐管步骤表：制备总量、取液来源、取液量、稀释液量、保留体积、预留损耗、状态；
   - 文字版操作步骤。
4. **不可行步骤**会以红色标出，判定规则（均按未取整值）：
   - 目标浓度未严格小于上一级浓度 → 浓度次序错误；
   - 取液量 < 移液下限 → 取液不可行；
   - 稀释液加入量 < 移液下限 → 加液不可行。

页面上的「填入可行示例 / 填入不可行示例」按钮可快速体验两种情形。数字输入支持科学计数法（如 `1e-3`）。

## 计算逻辑

设母液浓度为 `C₀`，各管目标浓度 `C₁…Cₙ`（须严格递减），第 `i` 管保留体积 `Rᵢ`、预留损耗 `Lᵢ`：

1. **从末管向前回推制备量**（计入后管取液）：
   - `Pₙ = Rₙ + Lₙ`
   - `Pᵢ = Rᵢ + Lᵢ + Tᵢ₊₁`，其中 `Tᵢ₊₁ = Pᵢ₊₁ × Cᵢ₊₁ / Cᵢ`
2. **从前向后计算取液与加液**：
   - 取液量 `Tᵢ = Pᵢ × Cᵢ / Cᵢ₋₁`（第 1 管的 `C₀` 为母液浓度）
   - 稀释液量 `Dᵢ = Pᵢ − Tᵢ`
3. **可行性判定**（未取整值）：`Cᵢ < Cᵢ₋₁`、`Tᵢ ≥ 下限`、`Dᵢ ≥ 下限`，三者同时满足该管才可行。
4. **母液总消耗** = `T₁`。

## API

### `POST /api/plan`

请求体（数值可传字符串或数字，建议字符串以保证精度）：

```json
{
  "stock_concentration": "100",
  "pipette_min": "2",
  "tubes": [
    { "concentration": "10",  "retain_volume": "500", "loss_volume": "50" },
    { "concentration": "1",   "retain_volume": "500", "loss_volume": "50" },
    { "concentration": "0.1", "retain_volume": "500", "loss_volume": "50" }
  ]
}
```

响应（节选）：

```json
{
  "feasible": true,
  "tube_count": 3,
  "total_stock_consumption": "61.05",
  "steps": [
    {
      "tube": 1,
      "source": "母液",
      "target_concentration": "10",
      "prepare_volume": "610.5",
      "take_volume": "61.05",
      "diluent_volume": "549.45",
      "retain_volume": "500",
      "loss_volume": "50",
      "feasible": true,
      "issues": []
    }
  ]
}
```

输入不合法时返回 `400`，`detail` 为中文错误信息。另有 `GET /api/health` 健康检查接口。

## 本地开发（不用 Docker）

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## 目录结构

```
├── Dockerfile             # 镜像构建（python:3.12-slim）
├── docker-compose.yml     # 一键启动
├── requirements.txt       # Python 依赖
└── app/
    ├── main.py            # FastAPI 入口与 API 路由
    ├── dilution.py        # Decimal 高精度稀释计算核心
    └── static/            # 原生 JS 前端（index.html / app.js / style.css）
```
