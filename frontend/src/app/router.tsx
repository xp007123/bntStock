import { createBrowserRouter, Navigate } from 'react-router-dom'
import AppLayout from './AppLayout'
import HomePage from '../features/home/HomePage'
import StockPage, { DEFAULT_STOCK } from '../features/stocks/StockPage'
import MarketPage from '../features/market/MarketPage'
import ComingSoon from '../components/ComingSoon'

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'stocks', element: <Navigate to={`/stocks/${DEFAULT_STOCK}`} replace /> },
      { path: 'stocks/:code', element: <StockPage /> },
      {
        path: 'patterns',
        element: <ComingSoon title="形态测试" plan="M1 迁移中：从 PatternLab 迁入规则引擎与历史验证。"
          items={['从内置模板创建形态，调整参数后运行全市场选股与历史验证', '研究报告：各周期胜率、收益分位、年度统计', '条件对比、增减一条条件、最新符合名单']} />,
      },
      {
        path: 'records',
        element: <ComingSoon title="研究记录" plan="形态研究、小四对话与期权分析会统一记录在这里，并在到期后结算。"
          items={['每条记录写明数据版本与证据截止时间', '判断冻结后自动到期结算，与原判断并排对照']} />,
      },
      { path: 'market', element: <MarketPage /> },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
])
