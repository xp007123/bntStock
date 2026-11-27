import { useParams } from 'react-router-dom'
import { type PickBlock, type PickSim, type PickSimStats, type PickStats, usePickStats } from '../../api/client'
import SubNav, { PICK_TABS } from '../../components/SubNav'
import SimChart from './SimChart'
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

const signed = (v: number) => `${v > 0 ? '+' : ''}${(v * 100).toFixed(1)}%`

/** 每个月的收益：一年一行，红赚绿亏，颜色深浅按幅度。上面一行讲赚钱的月份有多少、赚的月和亏的月各多少。 */
function MonthGrid({ months }: { months: PickSim['months'] }) {
  const win = months.filter(x => x.ret > 0), lose = months.filter(x => x.ret <= 0)
  const avg = (xs: typeof months) => xs.reduce((a, x) => a + x.ret, 0) / Math.max(1, xs.length)
  const best = months.reduce((a, x) => (x.ret > a.ret ? x : a), months[0])
  const worst = months.reduce((a, x) => (x.ret < a.ret ? x : a), months[0])
  const years = [...new Set(months.map(x => x.month.slice(0, 4)))]
  const by = Object.fromEntries(months.map(x => [x.month, x.ret]))
  const shade = (v: number) => `color-mix(in srgb, var(${v > 0 ? '--up' : '--down'}) ${Math.min(80, 10 + Math.abs(v) * 400)}%, var(--surface))`
  return (
    <>
      <div className="sim-mstat">
        <div><b className="num">{win.length} / {months.length}</b><span>赚钱的月份</span></div>
        <div><b className="num"><em className="up">{signed(avg(win))}</em> / <em className="down">{signed(avg(lose))}</em></b><span>赚钱的月平均 / 亏钱的月平均</span></div>
        <div><b className="num"><em className="up">{signed(best.ret)}</em> / <em className="down">{signed(worst.ret)}</em></b><span>最好的一个月 / 最差的一个月</span></div>
      </div>
      <div className="table-wrap">
        <table className="sim-months">
          <thead><tr><th />{Array.from({ length: 12 }, (_, i) => <th key={i}>{i + 1} 月</th>)}</tr></thead>
          <tbody>
            {years.map(y => (
              <tr key={y}>
                <th>{y}</th>
                {Array.from({ length: 12 }, (_, i) => {
                  const v = by[`${y}-${String(i + 1).padStart(2, '0')}`]
                  return <td key={i} className="num" style={v == null ? undefined : { background: shade(v), color: Math.abs(v) > 0.12 ? '#fff' : undefined }}>{v == null ? '' : signed(v)}</td>
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

/** 仿真模拟盘：一条净值曲线、几个数、每年的收益。只讲结果，不讲怎么选、怎么买卖。 */
function SimRecord({ s }: { s: PickSimStats }) {
  const m = s.sim
  const hs = m.benchmarks.find(b => b.code === 'sh000300')
  return (
    <>
      <p className="muted pk-range">{m.start} 到 {m.end}，{m.days} 个交易日的{m.label}。</p>
      <section className="pk-head card fade-in sim-nums">
        <div><span>累计收益</span><b className="num up">{signed(m.summary.total_return)}</b><small>{hs ? `同期沪深300 ${signed(hs.total)}` : ''}</small></div>
        <div><span>年化收益</span><b className="num up">{signed(m.summary.annualized)}</b><small>折算成每年</small></div>
        <div><span>最大回撤</span><b className="num">{(m.summary.max_drawdown * 100).toFixed(1)}%</b><small>从高点最多回落的幅度</small></div>
        <div><span>夏普比率</span><b className="num">{m.summary.sharpe.toFixed(2)}</b><small>赚的钱是亏的钱的 {m.summary.profit_factor.toFixed(1)} 倍</small></div>
      </section>

      <section className="card fade-in">
        <h2 className="card-title">净值曲线</h2>
        <SimChart sim={m} name={s.strategy.name} />
      </section>

      <section className="card fade-in">
        <h2 className="card-title">和指数比：收益接近，回撤小得多</h2>
        <div className="table-wrap">
          <table className="pk-table sim-vs">
            <thead><tr><th /><th>累计收益</th><th>最大回撤</th><th>收益 ÷ 回撤</th></tr></thead>
            <tbody>
              <tr className="self"><td><b>{s.strategy.name}</b></td><td className="num up">{signed(m.summary.total_return)}</td><td className="num">{pct1(m.summary.max_drawdown)}</td><td className="num"><b>{(m.summary.total_return / m.summary.max_drawdown).toFixed(1)} 倍</b></td></tr>
              {m.benchmarks.map(b => (
                <tr key={b.code}><td>同期{b.name}</td><td className={`num ${b.total >= 0 ? 'up' : 'down'}`}>{signed(b.total)}</td><td className="num">{pct1(b.max_drawdown)}</td><td className="num">{(b.total / b.max_drawdown).toFixed(1)} 倍</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted pk-foot">“收益 ÷ 回撤”：每承受 1 份最深的回落，换来几份收益。指数按同一段时间的收盘价算。</p>
      </section>

      <section className="card fade-in sim-costs">
        <h2 className="card-title">亏的时候亏得少，赚的时候赚得多</h2>
        <ul>
          <li><b className="num up">{signed(m.trades.win_avg)}</b><span>赚钱的交易，平均每笔</span></li>
          <li><b className="num down">{signed(m.trades.loss_avg)}</b><span>亏钱的交易，平均每笔</span></li>
          <li><b className="num">{m.trades.ge20} 笔</b><span>单笔赚超过 20%，其中 {m.trades.ge50} 笔超过 50%</span></li>
          <li><b className="num up">{signed(m.trades.best)}</b><span>赚得最多的一笔</span></li>
        </ul>
        <p className="muted pk-foot">一共 {m.trades.count.toLocaleString()} 笔完整的买卖。不是每笔都赚，靠的是赚的那些比亏的那些大得多。</p>
      </section>

      <section className="card fade-in">
        <h2 className="card-title">每个月</h2>
        <MonthGrid months={m.months} />
      </section>

      <section className="card fade-in">
        <h2 className="card-title">每一年</h2>
        <div className="sim-years">
          {m.years.map(y => (
            <div key={y.year}>
              <span>{y.year} 年{y.partial ? `（到 ${m.end.slice(5).replace('-', ' 月 ')} 日）` : ''}</span>
              <b className={`num ${y.ret >= 0 ? 'up' : 'down'}`}>{signed(y.ret)}</b>
            </div>
          ))}
        </div>
      </section>

      <section className="card fade-in sim-costs">
        <h2 className="card-title">成交按更难的价格算</h2>
        <ul>
          <li><b className="num">{(m.costs.buy_premium * 1000).toFixed(0)}‰</b><span>买入价比开盘价再高千分之{(m.costs.buy_premium * 1000).toFixed(0)}</span></li>
          <li><b className="num">{m.costs.slippage_bps} 个基点</b><span>每笔再扣一次滑点</span></li>
          <li><b className="num">{(m.costs.commission * 10000).toFixed(1)}‱</b><span>手续费，单笔最低 5 元</span></li>
        </ul>
      </section>

      <p className="muted pk-note">
        说明：以上是仿真模拟盘的数据——按平台的固定规则，在历史行情上模拟买入卖出得出，不是真实账户的交易记录。
        历史表现不代表以后，名单和这些数字都不是买卖建议。
      </p>
    </>
  )
}

/** 历史表现：把名单过去每一天的结果摊开，好的坏的都放上来。仿真模拟盘类的策略换成净值曲线。 */
export default function PickRecordPage() {
  const { strategy = '' } = useParams()
  const q = usePickStats(strategy)
  if (q.data && 'kind' in q.data) {
    return (
      <div className="picks">
        <SubNav items={PICK_TABS} />
        <StrategyHead id={strategy} s={q.data.strategy} />
        <SimRecord s={q.data} />
      </div>
    )
  }
  const s = q.data as PickStats | undefined
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
