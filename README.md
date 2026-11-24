# 四象智投（bntStock）

用历史数据，给你的判断算概率。

面向私域投资者的 A 股投研网页服务：通过“小四”对话，问个股（上涨概率、场外期权 100c）、问方法（形态验证），由 Agent 团队取证、确定性引擎计算，并在到期后结算每一个判断。

本仓库是新版四象智投，取代旧版（`backtest-engine`），计算核心与页面结构来自 PatternLab。

- 产品与架构说明：[docs/产品与架构说明-V1.md](docs/产品与架构说明-V1.md)

当前状态：M1 骨架已搭建（行情快照、行情接口、首页 / 个股看盘 / 指数概览）；形态测试迁移中。

## 目录

```
backend/    Python 后端（包名 sixiang）：FastAPI 接口、行情快照导入与查询
frontend/   React + TypeScript + Vite 前端
docs/       产品与架构说明
prototypes/ 视觉样板（示意数据）
data/       行情快照与运行数据（不入库）
```

## 本地开发

需要 Python 3.10+ 与 Node 20+。

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

导入基线行情（PatternLab 随包数据，约 1 分钟）：

```powershell
.\.venv\Scripts\python -m sixiang.data.baseline_import --source <PatternLab>\app\runtime\data-store\snapshots\baseline-bundled-20261118
```

启动后端（http://127.0.0.1:8000，接口文档 /api/docs）：

```powershell
.\.venv\Scripts\python -m uvicorn sixiang.api.app:app --reload --port 8000
```

启动前端开发服务（http://127.0.0.1:5173，/api 代理到后端）：

```powershell
cd frontend
npm install
npm run dev
```

生产方式：`npm run build` 生成 `frontend/dist`，后端会同时提供页面与接口。

测试：

```powershell
cd backend; .\.venv\Scripts\python -m pytest
cd frontend; npm test; npm run typecheck
```

环境变量：`SIXIANG_DATA_DIR`（默认 `data/`）、`SIXIANG_FRONTEND_DIST`（默认 `frontend/dist`）。
