/** 尚未迁移的页面：如实说明当前状态和计划，不展示假数据。 */
export default function ComingSoon({ title, plan, items }: { title: string; plan: string; items: string[] }) {
  return (
    <section className="card" style={{ maxWidth: 720, margin: '24px auto', padding: '28px 32px' }}>
      <h1 style={{ fontSize: 22, fontWeight: 600 }}>{title}</h1>
      <p className="muted" style={{ marginTop: 6 }}>{plan}</p>
      <ul style={{ marginTop: 16, paddingLeft: 20, lineHeight: 2 }}>
        {items.map(i => <li key={i}>{i}</li>)}
      </ul>
    </section>
  )
}
