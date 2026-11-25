import { useState } from 'react'
import { ArrowUp } from 'lucide-react'
import HomeResearchPet from '../../components/xiaosi/HomeResearchPet'
import './HomePage.css'

const SUGGESTIONS = [
  { title: '问个股', note: '这只票接下来一个月，涨的时候多还是跌的时候多？', prompt: '比亚迪接下来 20 个交易日，上涨的概率有多大？' },
  { title: '问期权', note: '这个期权费贵不贵，回本的机会有多大？', prompt: '比亚迪 3 个月平值看涨，期权费 7.5%，值不值得买？' },
  { title: '问方法', note: '我常用的买点，过去 17 年到底灵不灵？', prompt: '缩量回踩 20 日均线买入，这个方法历史上灵不灵？' },
]

/** 首页：小四。对话能力在 M2 开放，当前只展示入口，不伪造回答。 */
export default function HomePage() {
  const [text, setText] = useState('')
  return (
    <section className="home">
      <div className="home-pet fade-in">
        <HomeResearchPet size={64} />
        <span className="home-caption"><b>小四</b>你的投研伙伴</span>
      </div>
      <h1 className="fade-in">想验证什么？<br />说给小四听。</h1>
      <p className="home-lede fade-in">一只股票、一个期权报价、一个你常用的买点都行。小四会去翻 2007 年以来的历史，告诉你这种情况后来大多怎么样。</p>

      <form className="composer" onSubmit={e => e.preventDefault()}>
        <textarea
          aria-label="向小四提问"
          rows={2}
          maxLength={2000}
          placeholder="比如：比亚迪 3 个月平值看涨，期权费 7.5%，值不值？"
          value={text}
          onChange={e => setText(e.target.value)}
        />
        <div className="composer-foot">
          <span className="muted">小四对话即将开放，现在可以先去“形态”验证你的买点。</span>
          <button type="submit" className="send" disabled aria-label="发送"><ArrowUp size={18} /></button>
        </div>
      </form>

      <div className="suggestions">
        {SUGGESTIONS.map(s => (
          <button key={s.title} onClick={() => setText(s.prompt)}>
            <strong>{s.title}</strong>
            <p>{s.note}</p>
          </button>
        ))}
      </div>
      <p className="home-foot">所有数字都来自历史统计，不构成投资建议。</p>
    </section>
  )
}
