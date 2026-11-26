import { type PickBase, type PickBlock, usePickStats } from '../../api/client'
import SubNav, { PICK_TABS } from '../../components/SubNav'
import { fmtPct, trendClass } from '../../lib/format'
import './picks.css'

const pct1 = (v: number | null | undefined) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`)

/** 一条对比：名单、同样高开的其他股票、全市场，各自占多少。条的长度按三者里最大的那个定。 */
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
        <thead><tr><th /><th>只数</th><th>封住涨停</th><th>摸过涨停</th><th>开盘买到收盘（平均）</th><th>其中赚钱的</th><th>拿到第二天开盘（平均）</th></tr></thead>
        <tbody>
          {items.map(b => (
            <tr key={b.label}>
              <td><b>{b.label}</b></td>
              <td className="num">{b.n}</td>
              <td className="num">{pct1(b.sealed_rate)}</td>
              <td className="num">{pct1(b.touched_rate)}</td>
              <td className={`num ${trendClass(b.intraday_mean)}`}>{fmtPct(b.intraday_mean)}</td>
              <td className="num">{pct1(b.intraday_win)}</td>
              <td className={`num ${trendClass(b.next_open_mean)}`}>{fmtPct(b.next_open_mean)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** 历史表现：把名单过去每一天的结果摊开，好的坏的都放上来。 */
export default function PickRecordPage() {
  const q = usePickStats('sjm')
  const s = q.data
  const base = s?.baseline
  const win = (b: PickBase | null | undefined) => b?.intraday_win
  const gap = s?.range && base?.same_gap ? base.same_gap.sealed_rate - s.overall.sealed_rate : null
  const gapText = gap == null ? '' : gap > 0.01 ? '，比名单还高一点' : gap < -0.01 ? '，比名单低一些' : '，和名单差不多'

  return (
    <div className="picks">
      <SubNav items={PICK_TABS} />
      <header className="page-head fade-in">
        <h1>竞价先锋的历史表现</h1>
        <p className="muted">
          {s?.range ? `${s.range.start} 到 ${s.range.end}，${s.range.days} 个交易日，每天 10 只，一共 ${s.range.n} 只。` : ''}
          买入价按当天开盘价算，因为名单 09:25 才出，最早只能买在开盘。
        </p>
      </header>

      {q.isLoading ? <div className="state">正在算…第一次打开要等几秒</div>
        : q.isError || !s?.range ? <div className="state">还没有可以统计的名单。</div> : (
          <>
            <section className="card pk-find fade-in">
              <h2 className="card-title">先说结论</h2>
              <ul>
                <li><b>容易涨停，是真的。</b>名单里的票当天收盘封住涨停的占 {pct1(s.overall.sealed_rate)}，同期全市场只有 {pct1(base?.market?.sealed_rate)}。{pct1(s.per_day.any_sealed_rate)} 的交易日里，名单至少有一只封板，平均每天 {s.per_day.sealed_mean.toFixed(1)} 只。</li>
                <li><b>但开盘追进去，平均是亏的。</b>开盘买、收盘卖平均 <span className={trendClass(s.overall.intraday_mean)}>{fmtPct(s.overall.intraday_mean)}</span>，赚钱的只有 {pct1(s.overall.intraday_win)}；拿到第二天开盘平均 <span className={trendClass(s.overall.next_open_mean)}>{fmtPct(s.overall.next_open_mean)}</span>。原因是这些票开盘已经高开了一大截（中位数 {fmtPct(s.overall.open_pct_median)}），没封住的那些会回落。</li>
                <li><b>容易涨停主要是因为高开。</b>同一天里，别的同样高开的股票封板的比例是 {pct1(base?.same_gap?.sealed_rate)}{gapText}。也就是说，这份名单并没有比“随便挑一只同样高开的票”更会抓涨停。</li>
              </ul>
              <p className="muted">所以这份名单适合当“今天哪些票被抢”的观察清单，不适合闭着眼开盘就买。</p>
            </section>

            <section className="card pk-compare fade-in">
              <h2 className="card-title">和别的股票比</h2>
              <div className="pk-vs-grid">
                <Versus title="当天封住涨停的比例" note="“同样高开的其他股票”指同一天里，高开幅度不低于名单里最低那只、开盘没有直接涨停的股票。"
                        rows={[{ label: '竞价先锋', value: s.overall.sealed_rate, main: true }, { label: '同样高开的其他股票', value: base?.same_gap?.sealed_rate }, { label: '全市场', value: base?.market?.sealed_rate }]} />
                <Versus title="开盘买到收盘，赚钱的比例" note="全市场不含 ST、科创板、北交所，和名单的选股范围一致。"
                        rows={[{ label: '竞价先锋', value: s.overall.intraday_win, main: true }, { label: '同样高开的其他股票', value: win(base?.same_gap) }, { label: '全市场', value: win(base?.market) }]} />
              </div>
            </section>

            <section className="card fade-in">
              <h2 className="card-title">排第几名差别大吗</h2>
              <Rows items={s.by_rank} />
              <p className="muted pk-foot">名次按 09:25 的竞价涨幅排。越靠前越容易涨停，但开盘买进去同样不占便宜。</p>
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
              说明：历史名单是现在回头用同一句选股条件查出来的。其中“总市值、流通市值、是不是次新股”这几项，查询时用的可能是现在的数值而不是当时的，早期的名单和当时实际看到的会有少量出入。
              “封板”指收盘价等于涨停价，“摸过涨停”指最高价到过涨停价。没有扣手续费。
            </p>
          </>
        )}
    </div>
  )
}
