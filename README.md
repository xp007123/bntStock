# 四象智投（bntStock）

用历史数据，给你的判断算概率。

面向私域投资者的 A 股投研网页服务：通过“小四”对话，问个股（上涨概率、场外期权 100c）、问方法（形态验证），由 Agent 团队取证、确定性引擎计算，并在到期后结算每一个判断。

本仓库是新版四象智投，取代旧版（`backtest-engine`），计算核心与页面结构来自 PatternLab。

- 产品与架构说明：[docs/产品与架构说明-V1.md](docs/产品与架构说明-V1.md)
- 视觉规范：[docs/视觉规范-V3.md](docs/视觉规范-V3.md)
- 群聊：[docs/群聊-需求与架构.md](docs/群聊-需求与架构.md)
- 量化选股（竞价先锋已上，文哥选股与模拟盘的调研）：[docs/量化选股-调研记录.md](docs/量化选股-调研记录.md)

当前状态：M1 进行中。已完成行情快照与接口、首页、个股看盘、指数概览、形态测试（与 PatternLab 全市场对数一致，含增减条件与对比）、研究记录、登录与后台审核、iFinD 每日同步、财务数据与估值。

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

创建管理员（交互输入密码）；之后其他用户在登录页注册，由管理员在“管理”页审核：

```powershell
.\.venv\Scripts\python -m sixiang.auth.cli create-admin --username 你的用户名 --phone 你的手机号
```

导入财务数据（按披露时点，约 1 分钟）：

```powershell
.\.venv\Scripts\python -m sixiang.data.financial_import --source <PatternLab>pp
untime\data-store\snapshotsaseline-bundled-20261118inancial
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

iFinD 增量同步（凭证写在仓库根目录 `.env`，不入库）：

```powershell
.\.venv\Scripts\python -m sixiang.data.ifind_sync --dry-run
.\.venv\Scripts\python -m sixiang.data.ifind_sync
```

环境变量（可写在 `.env`）：`SIXIANG_DATA_DIR`（默认 `data/`）、`SIXIANG_FRONTEND_DIST`（默认 `frontend/dist`）、`SIXIANG_IFIND_REFRESH_TOKEN`（iFinD 凭证）、`SIXIANG_SYNC_AT`（如 `17:30`，启用每日自动同步）、`SIXIANG_PICKS_AT`（如 `09:25:40`，启用每天开盘前自动取选股名单）、`SIXIANG_DATABASE_URL`（默认 SQLite `data/app.db`）、`SIXIANG_COOKIE_SECURE=1`（HTTPS 部署时开启）。
