import { useParams } from 'react-router-dom'
import { type PickBlock, usePickStats } from '../../api/client'
import SubNav, { PICK_TABS } from '../../components/SubNav'
import StrategyHead from './StrategyHead'
import './picks.css'

const pct1 = (v: number | null | undefined) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`)

/** 一条对比：名单和全市场各自占多少。条的长度按里面最大的那个定。 */
function Versus({ title, note, rows }: { title: string; note: string; rows: { label: string; value: number | null | undefined; main?: boolean }[] }) {
  const max = Math.max(...rows.map(r => r.value ?? 0), 0.0001)
  return (
    <div className="pk-vs">
      <h3>{title}</h3>
      {rows.map(r => (
        <div key={r.label} className={r.main ? 'main' : ''}>
          <span>{r.label}</span>
          <i><b style={{ width: `${Math.max(2, ((r.value ?? 0) / max) * 100)}%` }} /></i>
          <em className="num">{pct1(r.value)}</em>
        </div>
      ))}
      <p className="muted">{note}</p>
    </div>
  )
}

function Rows({ items }: { items: (PickBlock & { label: string })[] }) {
  return (
    <div className="table-wrap">
      <table className="pk-table">
        <thead><tr><th /><th>只数</th><th>封住涨停</th><th>摸过涨停</th><th>当天收盘是涨的</th></tr></thead>
        <tbody>
          {items.map(b => (
            <tr key={b.label}>
              <td><b>{b.label}</b></td>
              <td className="num">{b.n}</td>
              <td className="num">{pct1(b.sealed_rate)}</td>
              <td className="num">{pct1(b.touched_rate)}</td>
              <td className="num">{pct1(b.day_up_rate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** 历史表现：把名单过去每一天的结果摊开，好的坏的都放上来。 */
export default function PickRecordPage() {
  const { strategy = '' } = useParams()
  const q = usePickStats(strategy)
  const s = q.data
  const base = s?.baseline
  const top = s?.range ? s.by_rank.find(b => b.label === '第 1 名') : undefined
  const main = s?.range ? s.by_board.find(b => b.label === '主板') : undefined
  const times = s?.range && base?.market?.sealed_rate ? s.overall.sealed_rate / base.market.sealed_rate : null

  return (
    <div className="picks">
      <SubNav items={PICK_TABS} />
      <StrategyHead id={strategy} s={s?.strategy} />
      {s?.range && <p className="muted pk-range">{s.range.start} 到 {s.range.end}，{s.range.days} 个交易日，一共 {s.range.n} 只。</p>}

      {q.isLoading ? <div className="state">正在算…第一次打开要等几秒</div>
        : q.isError || !s?.range ? <div className="state">还没有可以统计的名单。</div> : (
          <>
            <section className="card pk-find fade-in">
              <h2 className="card-title">这份名单强在哪</h2>
              <ul>
                <li><b>涨停的机会是全市场的 {times ? Math.round(times) : '—'} 倍。</b>名单里的票当天收盘封住涨停的占 {pct1(s.overall.sealed_rate)}，同期全市场只有 {pct1(base?.market?.sealed_rate)}；盘中摸到过涨停的占 {pct1(s.overall.touched_rate)}。</li>
                <li><b>几乎天天有板。</b>{pct1(s.per_day.any_sealed_rate)} 的交易日里，名单至少有一只封住涨停，平均每天 {s.per_day.sealed_mean.toFixed(1)} 只。</li>
                {top && <li><b>排第 1 名的最强。</b>竞价涨幅最高的那只，{pct1(top.sealed_rate)} 当天封住涨停，{pct1(top.touched_rate)} 摸到过涨停。</li>}
                {main && <li><b>主板的票更容易封板。</b>名单里的主板股票，封住涨停的占 {pct1(main.sealed_rate)}。</li>}
              </ul>
            </section>

            <section className="card pk-compare fade-in">
              <h2 className="card-title">和全市场比</h2>
              <div className="pk-vs-grid">
                <Versus title="当天封住涨停的比例" note="全市场不含 ST、科创板、北交所。"
                        rows={[{ label: s.strategy.name, value: s.overall.sealed_rate, main: true }, { label: '全市场', value: base?.market?.sealed_rate }]} />
              </div>
            </section>

            <section className="card fade-in">
              <h2 className="card-title">排第几名差别大吗</h2>
              <Rows items={s.by_rank} />
              <p className="muted pk-foot">名次按 09:25 的竞价涨幅排。越靠前越容易涨停。</p>
            </section>

            <section className="card fade-in">
              <h2 className="card-title">主板和创业板</h2>
              <Rows items={s.by_board} />
              <p className="muted pk-foot">创业板涨停要涨 20%，比主板的 10% 难得多。</p>
            </section>

            <section className="card fade-in">
              <h2 className="card-title">每个月的情况</h2>
              <Rows items={[...(s.recent ? [{ ...s.recent, label: `最近 ${s.recent.days} 个交易日` }] : []), ...[...s.by_month].reverse()]} />
            </section>

            <p className="muted pk-note">
              说明：“封板”指收盘价等于涨停价，“摸过涨停”指最高价到过涨停价，“当天收盘是涨的”指收盘价高于前一天收盘价。
            </p>
          </>
        )}
    </div>
  )
}
