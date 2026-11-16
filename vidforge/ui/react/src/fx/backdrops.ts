// 书房背景: a bookshelf behind the person, drawn here so it works offline and on the first day.
//
// What makes a drawn shelf read as a real room is not detail but depth of field: a real camera
// focused on a face 1 m away turns a shelf 2 m behind into soft blocks of colour and highlights.
// So the shelf is drawn plainly — boards, spines of varied height and lean, a plant, a lamp's warm
// pool — and then blurred the way a lens would, with a little vignette and grain. Sharp, it would
// look like a cartoon; blurred, it looks like a study.

type Room = {
  id: string
  name: string
  wall: [string, string] // gradient top -> bottom
  wood: string
  woodDark: string
  books: string[]
  lamp: string | null
  plant: boolean
}

export const ROOMS: Room[] = [
  { id: 'walnut', name: '胡桃木书房', wall: ['#e9dcc8', '#c9b393'], wood: '#6b4428', woodDark: '#4a2e1a', books: ['#c0392b', '#e67e22', '#f1c40f', '#27ae60', '#2980b9', '#8e44ad', '#ecf0f1', '#34495e', '#d35400'], lamp: '#ffd9a0', plant: true },
  { id: 'white', name: '白色书架', wall: ['#f6f4ef', '#e4e0d6'], wood: '#f7f7f5', woodDark: '#d9d6cf', books: ['#ff6b6b', '#feca57', '#48dbfb', '#1dd1a1', '#5f27cd', '#ff9ff3', '#576574', '#c8d6e5'], lamp: null, plant: true },
  { id: 'oak', name: '原木暖光', wall: ['#f3e3c7', '#dcbf92'], wood: '#b9854f', woodDark: '#8c6136', books: ['#e74c3c', '#f39c12', '#16a085', '#2c3e50', '#f5e6ca', '#9b59b6', '#3498db', '#e67e22'], lamp: '#ffcf87', plant: false },
  { id: 'green', name: '绿植书房', wall: ['#e3efe4', '#bcd6c0'], wood: '#8a6a4b', woodDark: '#5e4630', books: ['#ef476f', '#ffd166', '#06d6a0', '#118ab2', '#f8f9fa', '#073b4c', '#f78c6b'], lamp: null, plant: true },
  { id: 'blue', name: '蓝灰现代', wall: ['#dfe7ef', '#b8c6d6'], wood: '#3d4a5c', woodDark: '#2a3442', books: ['#f9c74f', '#f94144', '#90be6d', '#f8961e', '#ffffff', '#577590', '#43aa8b'], lamp: '#fff1c9', plant: true },
]

function rng(seed: number) {
  return () => ((seed = (seed * 16807) % 2147483647) / 2147483647)
}

function shade(hex: string, k: number): string {
  const n = parseInt(hex.slice(1), 16)
  const f = (c: number) => Math.max(0, Math.min(255, Math.round(c * k)))
  return `rgb(${f((n >> 16) & 255)},${f((n >> 8) & 255)},${f(n & 255)})`
}

function drawRoom(g: CanvasRenderingContext2D, W: number, H: number, r: Room, seed: number) {
  const rand = rng(seed)
  const wall = g.createLinearGradient(0, 0, 0, H)
  wall.addColorStop(0, r.wall[0])
  wall.addColorStop(1, r.wall[1])
  g.fillStyle = wall
  g.fillRect(0, 0, W, H)

  // the bookcase fills most of the frame, a little off centre like a real room
  const x0 = W * 0.06
  const x1 = W * 0.94
  const shelves = 4
  const top = H * 0.04
  const bottom = H * 0.98
  const rowH = (bottom - top) / shelves
  g.fillStyle = r.woodDark
  g.fillRect(x0 - W * 0.015, top - H * 0.02, x1 - x0 + W * 0.03, bottom - top + H * 0.04)
  for (let row = 0; row < shelves; row++) {
    const y = top + row * rowH
    // back panel, darker toward the bottom of each cubby
    const back = g.createLinearGradient(0, y, 0, y + rowH)
    back.addColorStop(0, shade(r.woodDark, 0.8))
    back.addColorStop(1, shade(r.woodDark, 1.15))
    g.fillStyle = back
    g.fillRect(x0, y, x1 - x0, rowH)
    // books
    let x = x0 + 6
    while (x < x1 - 20) {
      if (rand() < 0.08) {
        x += 30 + rand() * 60 // a gap, or an ornament's worth of space
        continue
      }
      const w = 14 + rand() * 26
      const h = rowH * (0.55 + rand() * 0.35)
      const c = r.books[Math.floor(rand() * r.books.length)]
      const lean = rand() < 0.07 ? (rand() - 0.5) * 0.35 : 0
      g.save()
      g.translate(x + w / 2, y + rowH - 8)
      g.rotate(lean)
      const spine = g.createLinearGradient(-w / 2, 0, w / 2, 0)
      spine.addColorStop(0, shade(c, 0.75))
      spine.addColorStop(0.45, c)
      spine.addColorStop(1, shade(c, 0.7))
      g.fillStyle = spine
      g.fillRect(-w / 2, -h, w, h)
      if (rand() < 0.5) {
        g.fillStyle = 'rgba(255,255,255,.55)'
        g.fillRect(-w / 2 + 3, -h * 0.75, w - 6, Math.max(2, h * 0.04))
      }
      g.restore()
      x += w + 1 + rand() * 2
    }
    // shelf board
    g.fillStyle = r.wood
    g.fillRect(x0 - W * 0.01, y + rowH - 10, x1 - x0 + W * 0.02, 14)
    g.fillStyle = 'rgba(0,0,0,.18)'
    g.fillRect(x0, y + rowH + 4, x1 - x0, 6)
  }
  // side panels
  g.fillStyle = r.wood
  g.fillRect(x0 - W * 0.015, top - H * 0.02, W * 0.015, bottom - top + H * 0.04)
  g.fillRect(x1, top - H * 0.02, W * 0.015, bottom - top + H * 0.04)

  if (r.plant) {
    const px = W * (0.12 + rand() * 0.1)
    const py = top + rowH * 2 - 10
    for (let i = 0; i < 26; i++) {
      g.fillStyle = `hsl(${105 + rand() * 40}, ${45 + rand() * 25}%, ${28 + rand() * 22}%)`
      g.beginPath()
      g.ellipse(px + (rand() - 0.5) * 120, py - 40 - rand() * 120, 14 + rand() * 18, 6 + rand() * 8, rand() * Math.PI, 0, Math.PI * 2)
      g.fill()
    }
    g.fillStyle = '#d8d2c6'
    g.fillRect(px - 32, py - 48, 64, 48)
  }
  if (r.lamp) {
    const lx = W * 0.78
    const ly = H * 0.3
    const glow = g.createRadialGradient(lx, ly, 10, lx, ly, H * 0.55)
    glow.addColorStop(0, r.lamp + 'cc')
    glow.addColorStop(1, r.lamp + '00')
    g.fillStyle = glow
    g.fillRect(0, 0, W, H)
  }
}

/** A blurred, vignetted study as a data URL (1920x1080, cover-fitted by the engine). */
export function roomUrl(id: string, seed = 7): string {
  const r = ROOMS.find((x) => x.id === id) || ROOMS[0]
  const W = 1920
  const H = 1080
  const sharp = document.createElement('canvas')
  sharp.width = W
  sharp.height = H
  drawRoom(sharp.getContext('2d')!, W, H, r, seed)
  const out = document.createElement('canvas')
  out.width = W
  out.height = H
  const g = out.getContext('2d')!
  // the lens: 9 px at 1080p is a 50 mm f/2 with the face a metre away and the shelf two behind
  g.filter = 'blur(9px) saturate(1.1)'
  g.drawImage(sharp, -20, -20, W + 40, H + 40)
  g.filter = 'none'
  const v = g.createRadialGradient(W / 2, H / 2, H * 0.35, W / 2, H / 2, H * 0.95)
  v.addColorStop(0, 'rgba(0,0,0,0)')
  v.addColorStop(1, 'rgba(0,0,0,.28)')
  g.fillStyle = v
  g.fillRect(0, 0, W, H)
  // grain, so it does not look cleaner than the camera image in front of it
  const img = g.getImageData(0, 0, W, H)
  const rand = rng(seed + 1)
  for (let i = 0; i < img.data.length; i += 4) {
    const n = (rand() - 0.5) * 10
    img.data[i] += n
    img.data[i + 1] += n
    img.data[i + 2] += n
  }
  g.putImageData(img, 0, 0)
  return out.toDataURL('image/jpeg', 0.9)
}
