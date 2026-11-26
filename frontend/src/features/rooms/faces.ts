/**
 * 角色的头像：“小四家族”。每个角色都是和小四一样的圆团子（一个纯色的圆 + 两只竖着的眼睛），
 * 靠一两样配饰认人：巴菲特的白发圆眼镜红领带、养家的碎刘海、Serenity 的白长发、利弗莫尔的礼帽……
 * 底色是角色自己的颜色。以后加新角色（包括分工型的 agent）照这个套路画：团子 + 一样招牌配饰。
 *
 * 返回的是 SVG 字符串：页面上当图片用，分享图的画布上也能直接画，一处定义两处用。
 * 后台新建的角色这里没有画像，返回 null，由调用方退回“名字首字”。
 */
const CREAM = '#fff8f2', DARK = '#23232b'

/** 两只竖着的眼睛。y 是眼睛顶端的位置；深色团子用米白眼睛，浅色团子用深色眼睛。 */
const eyes = (y: number, color = CREAM, h = 22) =>
  `<rect x="36" y="${y}" width="9" height="${h}" rx="4.5" fill="${color}"/><rect x="55" y="${y}" width="9" height="${h}" rx="4.5" fill="${color}"/>`
const line = (d: string, w = 3) => `<path d="${d}" fill="none" stroke="${CREAM}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"/>`
const tie = (c: string) => `<path d="M45 84 L55 84 L58 100 L42 100Z" fill="${c}"/>`
const bow = (c: string) => `<path d="M50 87 L39 81 L39 93Z M50 87 L61 81 L61 93Z" fill="${c}"/><circle cx="50" cy="87" r="3" fill="${c}"/>`

const FACES: Record<string, string> = {
  // 巴菲特：白发、大圆眼镜、红领带
  buffett: `<path d="M20 36 Q28 10 50 10 Q72 10 80 36 Q66 25 50 25 Q34 25 20 36Z" fill="#f4f1ec"/>${eyes(43)}
    <g fill="none" stroke="${CREAM}" stroke-width="3"><circle cx="40.5" cy="54" r="13"/><circle cx="59.5" cy="54" r="13"/></g>${tie('#d23b3b')}`,
  // 炒股养家：黑色碎刘海，一边嘴角上扬
  yangjia: `<path d="M14 40 Q20 8 50 7 Q80 8 86 40 L75 29 L67 38 L58 27 L50 38 L42 27 L33 38 L25 29Z" fill="#1d1512"/>${eyes(45)}${line('M43 78 Q52 83 61 75')}`,
  // 索罗斯：两鬓灰白卷发、细框方眼镜、抿着嘴
  soros: `<path d="M5 50 Q-3 34 9 27 Q10 16 22 19 Q30 21 27 31 Q21 37 21 50 Q12 56 5 50Z M95 50 Q103 34 91 27 Q90 16 78 19 Q70 21 73 31 Q79 37 79 50 Q88 56 95 50Z" fill="#d3d0cc"/>
    ${eyes(44, CREAM, 20)}<g fill="none" stroke="${CREAM}" stroke-width="2.6"><rect x="27" y="41" width="21" height="26" rx="6"/><rect x="52" y="41" width="21" height="26" rx="6"/></g>
    ${line('M43 80 H57')}${tie('#b9a3f0')}`,
  // Serenity：白色长发、腮红（团子是灰色的，眼睛用深色）
  serenity: `<path d="M8 62 Q2 6 50 5 Q98 6 92 62 L96 100 L74 100 Q80 70 74 46 Q62 30 50 42 Q38 30 26 46 Q20 70 26 100 L4 100Z" fill="#fbfbfe"/>
    ${eyes(50, DARK, 20)}<ellipse cx="31" cy="74" rx="5" ry="2.6" fill="#f4a0a0"/><ellipse cx="69" cy="74" rx="5" ry="2.6" fill="#f4a0a0"/>`,
  // 利弗莫尔：礼帽、红领结
  livermore: `<path d="M26 31 Q26 5 50 5 Q74 5 74 31Z" fill="#6a6056"/><path d="M26 24 H74 V31 H26Z" fill="#2b2622"/><ellipse cx="50" cy="32" rx="39" ry="6.5" fill="#574e45"/>
    ${eyes(46)}${bow('#d23b3b')}`,
  // 彼得·林奇：一头蓬松的银发、方眼镜、咧嘴大笑、黄领带
  lynch: `<path d="M10 42 Q5 24 20 19 Q24 6 39 10 Q50 1 61 10 Q76 6 80 19 Q95 24 90 42 Q78 29 65 33 Q50 25 35 33 Q22 29 10 42Z" fill="#ececf1"/>
    ${eyes(45, CREAM, 18)}<g fill="none" stroke="${CREAM}" stroke-width="3"><rect x="27" y="42" width="21" height="24" rx="6"/><rect x="52" y="42" width="21" height="24" rx="6"/></g>
    <path d="M38 73 Q50 87 62 73Z" fill="${CREAM}"/>${tie('#f2c94c')}`,
  // 邓普顿：光头顶、两鬓一点白发、细圆眼镜、白领结
  templeton: `<path d="M3 56 Q0 38 13 33 Q18 44 16 58Z M97 56 Q100 38 87 33 Q82 44 84 58Z" fill="#f3f1ec"/>
    ${line('M40 24 H60 M43 18 H57', 2)}${eyes(45, CREAM, 20)}
    <g fill="none" stroke="${CREAM}" stroke-width="2.2"><circle cx="40.5" cy="55" r="12.5"/><circle cx="59.5" cy="55" r="12.5"/></g>${line('M43 76 Q50 81 57 76')}${bow('#f3f1ec')}`,
  // 芒格：侧分的白发、又厚又方的眼镜、嘴角往下
  munger: `<path d="M20 38 Q24 14 54 12 Q74 14 80 36 Q58 20 20 38Z" fill="#ebe8e1"/>${eyes(45, CREAM, 18)}
    <g fill="none" stroke="${CREAM}" stroke-width="4.5"><rect x="25" y="41" width="22" height="25" rx="3"/><rect x="53" y="41" width="22" height="25" rx="3"/></g>
    ${line('M43 82 Q50 78 57 82')}${tie('#a9c1dc')}`,
  // 塔勒布：光头、压低的眉毛、一圈灰白的络腮胡
  taleb: `${line('M33 40 L46 44 M67 40 L54 44', 3.4)}${eyes(47, CREAM, 18)}
    <path d="M17 62 Q18 97 50 99 Q82 97 83 62 Q74 77 50 77 Q26 77 17 62Z" fill="#dedbd5"/>
    <path d="M43 86 H57" fill="none" stroke="#5f5a55" stroke-width="3" stroke-linecap="round"/>`,
  // 小四：主持人，平台的那只橙色小四本尊
  xiaosi: `<ellipse cx="33" cy="27" rx="13" ry="6" fill="#ffffff" opacity=".22" transform="rotate(-28 33 27)"/>
    <rect x="36" y="38" width="9" height="23" rx="4.5" fill="#2b0f05"/><rect x="55" y="38" width="9" height="23" rx="4.5" fill="#2b0f05"/>`,
}

const cache = new Map<string, string>()

/** 这个角色的头像（data URL）。没有画像的返回 null。 */
export function faceUrl(id: string | undefined | null, color: string): string | null {
  if (!id || !FACES[id]) return null
  const key = `${id}|${color}`
  let url = cache.get(key)
  if (!url) {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><clipPath id="c"><circle cx="50" cy="50" r="50"/></clipPath></defs>`
      + `<g clip-path="url(#c)"><rect width="100" height="100" fill="${color}"/>${FACES[id]}</g></svg>`
    url = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
    cache.set(key, url)
  }
  return url
}
