<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as L from 'leaflet'
import 'leaflet/dist/leaflet.css'

type SelectionMode = 'start' | 'end'

interface LatLngPoint {
  lat: number
  lon: number
}

interface GridMeta {
  rows: number
  cols: number
  latMin: number
  latMax: number
  lonMin: number
  lonMax: number
  latStep: number
  lonStep: number
}

interface GridCell extends LatLngPoint {
  row: number
  col: number
  walkable: boolean
}

interface BuiltGrid {
  meta: GridMeta
  cells: GridCell[][]
  blockedRatio: number
  cellLookup: Map<string, GridCell>
}

interface AStarFrame {
  index: number
  lat: number
  lon: number
  g: number
  h: number
  f: number
  openSize: number
  closedSize: number
}

interface SearchResult {
  path: LatLngPoint[]
  frames: AStarFrame[]
  gridMeta: GridMeta
  blockedRatio: number
  pathDistance: number
  expanded: number
  generated: number
}

interface SearchRecord extends GridCell {
  g: number
  h: number
  f: number
  key: string
}

const GRID_ROWS = 34
const GRID_COLS = 34
const PADDING_FACTOR = 0.4
const BLOCK_THRESHOLD = 0.72
const MIN_SPAN = 0.012
const MAX_EXPLORATION_MARKERS = 220

const mapContainer = ref<HTMLDivElement | null>(null)
const map = ref<L.Map | null>(null)
const startPoint = ref<LatLngPoint | null>(null)
const endPoint = ref<LatLngPoint | null>(null)
const activeSelection = ref<SelectionMode>('start')
const loading = ref(false)
const error = ref('')
const searchResult = ref<SearchResult | null>(null)

const startMarker = ref<L.Marker | null>(null)
const endMarker = ref<L.Marker | null>(null)
const pathLayer = ref<L.Polyline | null>(null)
const explorationLayer = ref<L.LayerGroup | null>(null)
const blockedLayer = ref<L.LayerGroup | null>(null)

const recentFrames = computed(() =>
  searchResult.value ? searchResult.value.frames.slice(-12).reverse() : [],
)
const pathRows = computed(() => searchResult.value?.path ?? [])
const formattedStart = computed(() => formatPoint(startPoint.value))
const formattedEnd = computed(() => formatPoint(endPoint.value))
const hasBothPoints = computed(() => Boolean(startPoint.value && endPoint.value))

let searchToken = 0

onMounted(() => {
  if (!mapContainer.value) return

  const createdMap = L.map(mapContainer.value, { zoomControl: true }).setView(
    [21.0285, 105.8542],
    13,
  )
  map.value = createdMap

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OSM</a>',
    maxZoom: 19,
  }).addTo(createdMap)

  createdMap.on('click', handleMapClick)
})

onBeforeUnmount(() => {
  map.value?.off('click', handleMapClick)
  map.value?.remove()
})

watch([startPoint, endPoint], ([start, end]) => {
  if (start && end) {
    runSearch()
  } else {
    cancelSearch()
  }
})

function handleMapClick(event: L.LeafletMouseEvent) {
  const { lat, lng } = event.latlng
  if (activeSelection.value === 'start') {
    setStart({ lat, lon: lng })
    activeSelection.value = 'end'
  } else {
    setEnd({ lat, lon: lng })
  }
}

function setStart(point: LatLngPoint) {
  startPoint.value = point
  placeMarker(startMarker, point, '#16a34a', 'S')
}

function setEnd(point: LatLngPoint) {
  endPoint.value = point
  placeMarker(endMarker, point, '#dc2626', 'G')
}

function placeMarker(
  markerRef: typeof startMarker | typeof endMarker,
  point: LatLngPoint,
  color: string,
  label: string,
) {
  const currentMap = map.value
  if (!currentMap) return
  const mapInstance = currentMap as L.Map
  const icon = L.divIcon({
    html: `<span class="pin" style="background:${color}">${label}</span>`,
    className: 'pin-wrapper',
    iconSize: [28, 34],
    iconAnchor: [14, 34],
  })

  if (markerRef.value) {
    markerRef.value.setLatLng([point.lat, point.lon])
  } else {
    markerRef.value = L.marker([point.lat, point.lon], { icon }).addTo(mapInstance)
  }
}

async function runSearch() {
  const start = startPoint.value
  const end = endPoint.value
  if (!start || !end) return

  const token = ++searchToken
  loading.value = true
  error.value = ''

  await nextTick()

  try {
    const builtGrid = buildGrid(start, end)
    const startCell = locateCell(start, builtGrid)
    const goalCell = locateCell(end, builtGrid)
    startCell.walkable = true
    goalCell.walkable = true

    const result = runAStarOnGrid(builtGrid, startCell, goalCell)

    if (token !== searchToken) return

    drawBlockedCells(builtGrid)

    if (!result.path.length) {
      searchResult.value = null
      drawPathOnMap([])
      drawExplorationMarkers([])
      focusOnGrid(builtGrid.meta)
      error.value = 'Không tìm thấy đường đi vì chướng ngại quá dày ở vùng này.'
      return
    }

    searchResult.value = result
    drawPathOnMap(result.path)
    drawExplorationMarkers(result.frames)
    focusOnPath(result.path)
  } catch (err) {
    console.error(err)
    if (token !== searchToken) return
    searchResult.value = null
    drawPathOnMap([])
    drawExplorationMarkers([])
    error.value = err instanceof Error ? err.message : 'Đã có lỗi trong lúc chạy A*.'
  } finally {
    if (token === searchToken) {
      loading.value = false
    }
  }
}

function cancelSearch() {
  searchToken += 1
  loading.value = false
  searchResult.value = null
  error.value = ''
  drawPathOnMap([])
  drawExplorationMarkers([])
  clearBlockedLayer()
}

function drawPathOnMap(points: LatLngPoint[]) {
  const currentMap = map.value as L.Map | null
  pathLayer.value?.remove()
  pathLayer.value = null
  if (!currentMap || !points.length) return

  const latLngs = points.map((p) => [p.lat, p.lon] as L.LatLngTuple)
  pathLayer.value = L.polyline(latLngs, {
    color: '#38bdf8',
    weight: 5,
    opacity: 0.9,
  }).addTo(currentMap)
}

function drawExplorationMarkers(frames: AStarFrame[]) {
  const currentMap = map.value as L.Map | null
  explorationLayer.value?.remove()
  explorationLayer.value = null
  if (!currentMap || !frames.length) return

  const step = Math.max(1, Math.floor(frames.length / MAX_EXPLORATION_MARKERS))
  const group = L.layerGroup()
  for (let i = 0; i < frames.length; i += step) {
    const frame = frames[i]
    if (!frame) continue
    const marker = L.circleMarker([frame.lat, frame.lon], {
      radius: 5,
      weight: 1,
      color: '#f97316',
      fillColor: '#fdba74',
      fillOpacity: 0.9,
    })
    group.addLayer(marker)
  }
  group.addTo(currentMap)
  explorationLayer.value = group
}

function drawBlockedCells(grid: BuiltGrid) {
  const currentMap = map.value as L.Map | null
  clearBlockedLayer()
  if (!currentMap) return

  const group = L.layerGroup()
  for (const row of grid.cells) {
    for (const cell of row) {
      if (cell.walkable) continue
      const south = grid.meta.latMin + cell.row * grid.meta.latStep
      const north = south + grid.meta.latStep
      const west = grid.meta.lonMin + cell.col * grid.meta.lonStep
      const east = west + grid.meta.lonStep
      const rect = L.rectangle(
        [
          [south, west],
          [north, east],
        ],
        {
          color: '#f87171',
          weight: 0,
          fillColor: '#ef4444',
          fillOpacity: 0.22,
          className: 'blocked-cell',
        },
      )
      group.addLayer(rect)
    }
  }
  group.addTo(currentMap)
  blockedLayer.value = group
}

function clearBlockedLayer() {
  blockedLayer.value?.remove()
  blockedLayer.value = null
}

function focusOnPath(points: LatLngPoint[]) {
  const currentMap = map.value as L.Map | null
  if (!currentMap || !points.length) return
  const bounds = L.latLngBounds(
    points.map((p) => [p.lat, p.lon] as L.LatLngTuple),
  )
  currentMap.fitBounds(bounds, { padding: [24, 24] })
}

function focusOnGrid(meta: GridMeta) {
  const currentMap = map.value as L.Map | null
  if (!currentMap) return
  const bounds = L.latLngBounds(
    [meta.latMin, meta.lonMin],
    [meta.latMax, meta.lonMax],
  )
  currentMap.fitBounds(bounds, { padding: [24, 24] })
}

function resetAll() {
  startPoint.value = null
  endPoint.value = null
  activeSelection.value = 'start'
  searchResult.value = null
  error.value = ''
  startMarker.value?.remove()
  startMarker.value = null
  endMarker.value?.remove()
  endMarker.value = null
  drawPathOnMap([])
  drawExplorationMarkers([])
  clearBlockedLayer()
}

function swapPoints() {
  if (!startPoint.value || !endPoint.value) return
  const oldStart = { ...startPoint.value }
  startPoint.value = { ...endPoint.value }
  endPoint.value = oldStart
  placeMarker(startMarker, startPoint.value, '#16a34a', 'S')
  placeMarker(endMarker, endPoint.value, '#dc2626', 'G')
}

function buildGrid(start: LatLngPoint, end: LatLngPoint): BuiltGrid {
  const latSpan = Math.max(Math.abs(end.lat - start.lat), MIN_SPAN)
  const lonSpan = Math.max(Math.abs(end.lon - start.lon), MIN_SPAN)
  const latMin = Math.min(start.lat, end.lat) - latSpan * PADDING_FACTOR
  const latMax = Math.max(start.lat, end.lat) + latSpan * PADDING_FACTOR
  const lonMin = Math.min(start.lon, end.lon) - lonSpan * PADDING_FACTOR
  const lonMax = Math.max(start.lon, end.lon) + lonSpan * PADDING_FACTOR

  const meta: GridMeta = {
    rows: GRID_ROWS,
    cols: GRID_COLS,
    latMin,
    latMax,
    lonMin,
    lonMax,
    latStep: (latMax - latMin) / GRID_ROWS,
    lonStep: (lonMax - lonMin) / GRID_COLS,
  }

  const cells: GridCell[][] = []
  const lookup = new Map<string, GridCell>()
  let blocked = 0

  for (let row = 0; row < GRID_ROWS; row += 1) {
    const rowCells: GridCell[] = []
    for (let col = 0; col < GRID_COLS; col += 1) {
      const lat = latMin + (row + 0.5) * meta.latStep
      const lon = lonMin + (col + 0.5) * meta.lonStep
      const noise = pseudoNoise(lat, lon)
      const walkable = noise > BLOCK_THRESHOLD ? false : true
      if (!walkable) blocked += 1
      const cell: GridCell = { row, col, lat, lon, walkable }
      rowCells.push(cell)
      lookup.set(cellKey(row, col), cell)
    }
    cells.push(rowCells)
  }

  return {
    meta,
    cells,
    blockedRatio: blocked / (GRID_ROWS * GRID_COLS),
    cellLookup: lookup,
  }
}

function locateCell(point: LatLngPoint, grid: BuiltGrid): GridCell {
  const row = clamp(
    Math.floor(((point.lat - grid.meta.latMin) / (grid.meta.latMax - grid.meta.latMin)) * grid.meta.rows),
    0,
    grid.meta.rows - 1,
  )
  const col = clamp(
    Math.floor(((point.lon - grid.meta.lonMin) / (grid.meta.lonMax - grid.meta.lonMin)) * grid.meta.cols),
    0,
    grid.meta.cols - 1,
  )
  const fallback = grid.cells[0]?.[0]
  if (!fallback) {
    throw new Error('Lưới chưa sẵn sàng.')
  }
  return grid.cells[row]?.[col] ?? fallback
}

function runAStarOnGrid(grid: BuiltGrid, startCell: GridCell, goalCell: GridCell): SearchResult {
  const startKey = cellKey(startCell.row, startCell.col)
  const goalKey = cellKey(goalCell.row, goalCell.col)
  const openHeap = new MinHeap<SearchRecord>((a, b) => a.f - b.f)
  const bestG = new Map<string, number>()
  const parents = new Map<string, string | null>()
  const openTracker = new Map<string, SearchRecord>()
  const closedSet = new Set<string>()
  const frames: AStarFrame[] = []
  let generated = 0

  const hStart = haversine(startCell.lat, startCell.lon, goalCell.lat, goalCell.lon)
  const startRecord: SearchRecord = { ...startCell, g: 0, h: hStart, f: hStart, key: startKey }
  openHeap.push(startRecord)
  openTracker.set(startKey, startRecord)
  bestG.set(startKey, 0)
  parents.set(startKey, null)

  while (openHeap.size() > 0) {
    const current = openHeap.pop()
    if (!current) break
    const known = bestG.get(current.key)
    if (known === undefined || current.g > known) {
      continue
    }
    openTracker.delete(current.key)

    frames.push({
      index: frames.length,
      lat: current.lat,
      lon: current.lon,
      g: current.g,
      h: current.h,
      f: current.f,
      openSize: openTracker.size,
      closedSize: frames.length + 1,
    })

    if (current.key === goalKey) {
      const path = buildPath(current.key, parents, grid.cellLookup)
      return {
        path,
        frames,
        gridMeta: grid.meta,
        blockedRatio: grid.blockedRatio,
        pathDistance: computePathDistance(path),
        expanded: frames.length,
        generated,
      }
    }

    closedSet.add(current.key)

    for (const neighbor of findNeighbors(current, grid)) {
      const neighborKey = cellKey(neighbor.row, neighbor.col)
      if (closedSet.has(neighborKey) || !neighbor.walkable) continue

      const tentativeG = current.g + haversine(current.lat, current.lon, neighbor.lat, neighbor.lon)
      const bestNeighbor = bestG.get(neighborKey)
      if (bestNeighbor !== undefined && tentativeG >= bestNeighbor) {
        continue
      }

      const h = haversine(neighbor.lat, neighbor.lon, goalCell.lat, goalCell.lon)
      const record: SearchRecord = {
        ...neighbor,
        g: tentativeG,
        h,
        f: tentativeG + h,
        key: neighborKey,
      }

      bestG.set(neighborKey, tentativeG)
      parents.set(neighborKey, current.key)
      openTracker.set(neighborKey, record)
      openHeap.push(record)
      generated += 1
    }
  }

  return {
    path: [],
    frames,
    gridMeta: grid.meta,
    blockedRatio: grid.blockedRatio,
    pathDistance: 0,
    expanded: frames.length,
    generated,
  }
}

function findNeighbors(cell: GridCell, grid: BuiltGrid) {
  const neighbors: GridCell[] = []
  for (const [dr, dc] of neighborOffsets) {
    const nr = cell.row + dr
    const nc = cell.col + dc
    if (nr < 0 || nr >= grid.meta.rows || nc < 0 || nc >= grid.meta.cols) continue
    const rowCells = grid.cells[nr]
    if (!rowCells) continue
    const neighbor = rowCells[nc]
    if (!neighbor) continue
    neighbors.push(neighbor)
  }
  return neighbors
}

const neighborOffsets: Array<[number, number]> = [
  [1, 0],
  [-1, 0],
  [0, 1],
  [0, -1],
  [1, 1],
  [1, -1],
  [-1, 1],
  [-1, -1],
]

function buildPath(key: string, parents: Map<string, string | null>, lookup: Map<string, GridCell>) {
  const path: LatLngPoint[] = []
  let currentKey: string | null | undefined = key
  while (currentKey) {
    const cell = lookup.get(currentKey)
    if (!cell) break
    path.push({ lat: cell.lat, lon: cell.lon })
    currentKey = parents.get(currentKey) ?? null
  }
  return path.reverse()
}

function computePathDistance(points: LatLngPoint[]) {
  let total = 0
  for (let i = 1; i < points.length; i += 1) {
    const prev = points[i - 1]
    const curr = points[i]
    if (!prev || !curr) continue
    total += haversine(prev.lat, prev.lon, curr.lat, curr.lon)
  }
  return total
}

function cellKey(row: number, col: number) {
  return `${row}:${col}`
}

function haversine(lat1: number, lon1: number, lat2: number, lon2: number) {
  const R = 6371000
  const toRad = (deg: number) => (deg * Math.PI) / 180
  const dLat = toRad(lat2 - lat1)
  const dLon = toRad(lon2 - lon1)
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) * Math.sin(dLon / 2)
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
  return R * c
}

function pseudoNoise(lat: number, lon: number) {
  const raw = Math.sin(lat * 21.9898 + lon * 47.233 + lat * lon * 11.73) * 43758.5453
  return raw - Math.floor(raw)
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value))
}

function formatPoint(point: LatLngPoint | null) {
  if (!point) return '--'
  return `${point.lat.toFixed(5)}, ${point.lon.toFixed(5)}`
}

function formatDistance(distance: number) {
  if (distance >= 1000) {
    return `${(distance / 1000).toFixed(2)} km`
  }
  return `${distance.toFixed(0)} m`
}

class MinHeap<T> {
  private heap: T[] = []

  constructor(private comparator: (a: T, b: T) => number) {}

  push(value: T) {
    this.heap.push(value)
    this.bubbleUp(this.heap.length - 1)
  }

  pop() {
    if (this.heap.length === 0) return undefined
    const top = this.heap[0]!
    const end = this.heap.pop()
    if (this.heap.length > 0 && end !== undefined) {
      this.heap[0] = end
      this.bubbleDown(0)
    }
    return top
  }

  size() {
    return this.heap.length
  }

  private bubbleUp(index: number) {
    let idx = index
    while (idx > 0) {
      const parentIdx = Math.floor((idx - 1) / 2)
      const parent = this.heap[parentIdx]
      const current = this.heap[idx]
      if (parent === undefined || current === undefined) break
      if (this.comparator(current, parent) >= 0) break
      this.swap(idx, parentIdx)
      idx = parentIdx
    }
  }

  private bubbleDown(index: number) {
    let idx = index
    const length = this.heap.length
    while (true) {
      const left = idx * 2 + 1
      const right = left + 1
      let smallest = idx

      const leftValue = this.heap[left]
      const smallestValue = this.heap[smallest]
      if (
        left < length &&
        leftValue !== undefined &&
        smallestValue !== undefined &&
        this.comparator(leftValue, smallestValue) < 0
      ) {
        smallest = left
      }
      const rightValue = this.heap[right]
      const currentSmallest = this.heap[smallest]
      if (
        right < length &&
        rightValue !== undefined &&
        currentSmallest !== undefined &&
        this.comparator(rightValue, currentSmallest) < 0
      ) {
        smallest = right
      }
      if (smallest === idx) break
      this.swap(idx, smallest)
      idx = smallest
    }
  }

  private swap(i: number, j: number) {
    if (i === j) return
    const first = this.heap[i]
    const second = this.heap[j]
    if (first === undefined || second === undefined) return
    this.heap[i] = second
    this.heap[j] = first
  }
}
</script>

<template>
  <div class="app-shell">
    <header class="hero">
      <div>
        <p class="kicker">A* sandbox</p>
        <h1>Biểu diễn đường đi bằng thuật toán A*</h1>
        <p class="subtitle">
          Chọn hai điểm trên bản đồ, hệ thống sẽ dựng một lưới chướng ngại giả lập và chạy A*
          (heuristic = haversine) ngay trong trình duyệt để nối chúng lại.
        </p>
      </div>
      <div class="hero-actions">
        <button class="ghost" @click="swapPoints" :disabled="!hasBothPoints">Đổi vị trí</button>
        <button class="ghost" @click="resetAll">Làm mới</button>
      </div>
    </header>

    <main class="layout">
      <section class="map-panel">
        <div class="map-toolbar">
          <div>
            <p class="label">Chế độ chọn</p>
            <div class="mode-toggle">
              <button
                class="mode"
                :class="{ active: activeSelection === 'start' }"
                @click="activeSelection = 'start'"
              >
                Điểm bắt đầu
              </button>
              <button
                class="mode"
                :class="{ active: activeSelection === 'end' }"
                @click="activeSelection = 'end'"
              >
                Điểm kết thúc
              </button>
            </div>
          </div>
          <div class="coords">
            <div>
              <p class="label">Start</p>
              <p class="coord">{{ formattedStart }}</p>
            </div>
            <div>
              <p class="label">Goal</p>
              <p class="coord">{{ formattedEnd }}</p>
            </div>
          </div>
        </div>
        <div ref="mapContainer" class="map-container"></div>
        <p class="map-hint">
          Ô màu đỏ = chướng ngại. Vệt cam thể hiện các node đã được mở rộng trong quá trình chạy
          A*.
        </p>
      </section>

      <section class="details-panel">
        <h2>Diễn tiến tìm đường</h2>
        <p class="hint">
          Lưới ({{ GRID_ROWS }}×{{ GRID_COLS }}) được tạo theo bounding box của hai điểm. Ta dùng
          heuristic nhất quán nên A* luôn tìm ra đường tối ưu nếu tồn tại.
        </p>

        <div v-if="error" class="state error">{{ error }}</div>
        <div v-else-if="loading" class="state">Đang dựng lưới và chạy A*...</div>
        <template v-else>
          <div v-if="searchResult" class="summary">
            <div class="summary-grid">
              <div>
                <p class="label">Độ dài đường đi</p>
                <strong>{{ formatDistance(searchResult.pathDistance) }}</strong>
              </div>
              <div>
                <p class="label">Số bước trên đường đi</p>
                <strong>{{ pathRows.length }}</strong>
              </div>
              <div>
                <p class="label">Node đã mở rộng</p>
                <strong>{{ searchResult.expanded }}</strong>
              </div>
              <div>
                <p class="label">Node đã sinh</p>
                <strong>{{ searchResult.generated }}</strong>
              </div>
              <div>
                <p class="label">Kích thước lưới</p>
                <strong>{{ searchResult.gridMeta.rows }} × {{ searchResult.gridMeta.cols }}</strong>
              </div>
              <div>
                <p class="label">Tỉ lệ chướng ngại</p>
                <strong>{{ (searchResult.blockedRatio * 100).toFixed(1) }}%</strong>
              </div>
            </div>

            <div class="table-wrapper">
              <div>
                <h3>Nhật ký mở rộng (mới nhất)</h3>
                <div class="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Lat</th>
                        <th>Lon</th>
                        <th>g</th>
                        <th>h</th>
                        <th>f</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="frame in recentFrames" :key="`frame-${frame.index}`">
                        <td>{{ frame.index }}</td>
                        <td>{{ frame.lat.toFixed(4) }}</td>
                        <td>{{ frame.lon.toFixed(4) }}</td>
                        <td>{{ formatDistance(frame.g) }}</td>
                        <td>{{ formatDistance(frame.h) }}</td>
                        <td>{{ formatDistance(frame.f) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <div>
                <h3>Đường đi cuối cùng</h3>
                <div class="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Lat</th>
                        <th>Lon</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(node, idx) in pathRows" :key="`path-${idx}`">
                        <td>{{ idx }}</td>
                        <td>{{ node.lat.toFixed(4) }}</td>
                        <td>{{ node.lon.toFixed(4) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>

          <p v-else class="state muted">
            Chọn hai điểm bất kỳ trên bản đồ để khởi chạy A*.
          </p>
        </template>
      </section>
    </main>

    <footer>Demo chạy offline: dữ liệu chỉ gồm lưới giả lập nên kết quả khác bản đồ thực tế.</footer>
  </div>
</template>

<style scoped>
:global(body) {
  font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: #0f172a;
  color: #e2e8f0;
}

.app-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  gap: 24px;
  padding: 32px clamp(16px, 4vw, 64px);
}

.hero {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-end;
}

.hero h1 {
  font-size: clamp(24px, 4vw, 36px);
  margin: 4px 0;
}

.subtitle {
  color: #cbd5f5;
  max-width: 640px;
}

.kicker {
  text-transform: uppercase;
  font-size: 12px;
  letter-spacing: 0.4em;
  color: #a5b4fc;
}

.hero-actions {
  display: flex;
  gap: 12px;
}

.ghost {
  border: 1px solid rgba(148, 163, 184, 0.4);
  color: #e2e8f0;
  background: transparent;
  padding: 8px 16px;
  border-radius: 999px;
  cursor: pointer;
  transition: border-color 0.2s ease, color 0.2s ease;
}

.ghost:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.ghost:not(:disabled):hover {
  border-color: #e2e8f0;
}

.layout {
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  gap: clamp(16px, 2vw, 32px);
}

@media (max-width: 960px) {
  .layout {
    grid-template-columns: 1fr;
  }

  .hero {
    flex-direction: column;
    align-items: flex-start;
  }
}

.map-panel {
  background: #0b1120;
  border-radius: 20px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.map-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
  flex-wrap: wrap;
}

.label {
  color: #94a3b8;
  font-size: 12px;
  letter-spacing: 0.05em;
}

.mode-toggle {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.mode {
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: transparent;
  color: #e2e8f0;
  border-radius: 10px;
  padding: 6px 12px;
  cursor: pointer;
}

.mode.active {
  background: #1d4ed8;
  border-color: #2563eb;
}

.coords {
  display: flex;
  gap: 24px;
}

.coord {
  font-size: 14px;
  color: #e2e8f0;
}

.map-container {
  height: clamp(320px, 60vh, 520px);
}

:global(.leaflet-container) {
  width: 100%;
  height: 100%;
  border-bottom-left-radius: 20px;
  border-bottom-right-radius: 20px;
}

.map-hint {
  font-size: 13px;
  padding: 12px 20px 20px;
  color: #cbd5f5;
  border-top: 1px solid rgba(148, 163, 184, 0.2);
}

.details-panel {
  background: #0b1120;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 20px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.details-panel h2 {
  margin: 0;
}

.hint {
  font-size: 14px;
  color: #cbd5f5;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  align-items: flex-start;
}

.summary-grid strong {
  font-size: 20px;
}

.table-wrapper {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
}

.table-scroll {
  max-height: 280px;
  overflow: auto;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 14px;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

th,
td {
  padding: 8px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
  text-align: left;
}

th {
  background: rgba(15, 23, 42, 0.6);
  position: sticky;
  top: 0;
}

.state {
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.6);
}

.state.error {
  border: 1px solid rgba(248, 113, 113, 0.4);
  color: #fecaca;
  background: rgba(127, 29, 29, 0.3);
}

.state.muted {
  color: #94a3b8;
  border: 1px dashed rgba(148, 163, 184, 0.4);
}

.pin-wrapper {
  width: 0;
  height: 0;
}

.pin {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 999px;
  color: #0f172a;
  font-weight: 700;
  box-shadow:
    0 10px 20px rgba(0, 0, 0, 0.3),
    inset 0 -2px 4px rgba(0, 0, 0, 0.2);
}

footer {
  text-align: center;
  font-size: 12px;
  color: #94a3b8;
  margin-top: auto;
}
</style>
