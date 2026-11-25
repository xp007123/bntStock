import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router-dom'
import { router } from './app/router'
import './styles/global.css'

// 页面不在渲染（嵌在看不见的窗口里）时动画时钟不走，淡入的内容会一直透明。
// 这种情况下直接关掉动画，等页面真的开始渲染再打开。
const root = document.documentElement
const timer = window.setTimeout(() => root.classList.add('still'), 400)
// 连续两帧间隔正常，才算真的在渲染（被节流的页面偶尔也会出一帧）
const probe = () => requestAnimationFrame(a => requestAnimationFrame(b => {
  if (b - a < 100) { window.clearTimeout(timer); root.classList.remove('still') } else probe()
}))
probe()

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 5 * 60_000 } },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
