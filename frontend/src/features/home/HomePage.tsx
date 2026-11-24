import { useState } from 'react'
import { ArrowUp, CandlestickChart, FlaskConical, Percent } from 'lucide-react'
import HomeResearchPet from '../../components/xiaosi/HomeResearchPet'
import './HomePage.css'

const SUGGESTIONS = [
  { icon: Percent, title: '问个股', note: '这只票未来 20 天上涨的概率有多大？', prompt: '比亚迪未来 20 个交易日上涨的概率有多大？' },
  { icon: CandlestickChart, title: '问期权', note: '这个期限和费率的场外期权值不值？', prompt: '比亚迪 3 个月平值看涨，期权费 7.5%，值不值得买？' },
  { icon: FlaskConical, title: '问方法', note: '我的买入方法在历史上灵不灵？', prompt: '缩量回踩 20 日均线买入，这个方法历史上灵不灵？' },
]

/** 首页：小四。对话能力在 M2 开放，当前只展示入口，不伪造回答。 */
export default function HomePage() {
  const [text, setText] = useState('')
  return (
    <section className="home">
      <div className="home-pet">
        <HomeResearchPet size={156} />
        <span className="home-caption">你的投研伙伴</span>
      </div>
      <h1>我是小四，有什么能帮到你？</h1>
      <p className="home-lede">说出你的判断，我带团队用历史数据算给你看。</p>

      <form className="composer" onSubmit={e => e.preventDefault()}>
        <textarea
          aria-label="向小四提问"
          rows={2}
          maxLength={2000}
          placeholder="说说你想验证的股票、期权或方法…"
          value={text}
          onChange={e => setText(e.target.value)}
        />
        <div className="composer-foot">
          <span className="muted">小四对话将在下一阶段开放，现在可以先去看盘和形态测试。</span>
          <button type="submit" className="send" disabled aria-label="发送"><ArrowUp size={18} /></button>
        </div>
      </form>

      <div className="suggestions">
        {SUGGESTIONS.map(s => (
          <button key={s.title} onClick={() => setText(s.prompt)}>
            <span className="s-icon"><s.icon size={18} /></span>
            <strong>{s.title}</strong>
            <p>{s.note}</p>
          </button>
        ))}
      </div>
      <p className="home-foot">数字来自历史数据计算，不构成投资建议。</p>
    </section>
  )
}
