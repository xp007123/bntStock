import HomeResearchPet from '../../components/xiaosi/HomeResearchPet'
import AskPanel from './AskPanel'
import './HomePage.css'


/** 首页：小四。先用结构化提问（问个股 / 问期权 / 问方法）；自由对话在下一版开放。 */
export default function HomePage() {
  return (
    <section className="home">
      <div className="home-pet fade-in">
        <HomeResearchPet size={64} />
        <span className="home-caption"><b>小四</b>你的投研伙伴</span>
      </div>
      <h1 className="fade-in">想验证什么？<br />说给小四听。</h1>
      <p className="home-lede fade-in">一只股票、一个期权报价、一个你常用的买点都行。小四会去翻 2007 年以来的历史，告诉你类似的情况后来大多怎么样，最坏会怎样。</p>

      <AskPanel />

      <p className="home-foot">所有数字都来自历史统计，不构成投资建议。</p>
    </section>
  )
}
