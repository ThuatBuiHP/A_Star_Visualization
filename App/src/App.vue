<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import osmXml from '../map.osm?raw'

type SelectionMode = 'start' | 'end'

interface LatLngPoint {
  lat: number
  lon: number
}

interface GraphNode extends LatLngPoint {
  id: string
}

interface GraphEdge {
  to: string
  cost: number
}

interface GraphData {
  nodes: Map<string, GraphNode>
  adjacency: Map<string, GraphEdge[]>
  nodeList: GraphNode[]
  bounds: L.LatLngBoundsLiteral | null
  wayCount: number
  edgeCount: number
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
  pathDistance: number
  expanded: number
  generated: number
  nodeCount: number
  edgeCount: number
  wayCount: number
}

interface GraphSearchRecord extends GraphNode {
  g: number
  h: number
  f: number
}

const MAX_EXPLORATION_MARKERS = 220
const WALKABLE_DISTANCE_THRESHOLD_METERS = 45
const MAX_SNAP_DISTANCE_METERS = 250
const OSM_WALKABLE_HIGHWAYS = new Set([
  'footway',
  'path',
  'pedestrian',
  'living_street',
  'residential',
  'service',
  'track',
  'unclassified',
  'steps',
  'cycleway',
])

const osmWalkablePoints = ref<LatLngPoint[]>([])
const osmWalkablePaths = ref<LatLngPoint[][]>([])
const osmBounds = ref<L.LatLngBoundsLiteral | null>(null)
const osmGraph = ref<GraphData | null>(null)

const mapContainer = ref<HTMLDivElement | null>(null)
const map = ref<L.Map | null>(null)
const tileLayerRef = ref<L.TileLayer | null>(null)
const startPoint = ref<LatLngPoint | null>(null)
const endPoint = ref<LatLngPoint | null>(null)
const activeSelection = ref<SelectionMode>('start')
const loading = ref(false)
const error = ref('')
const searchResult = ref<SearchResult | null>(null)

const startMarker = ref<L.Marker | null>(null)
const endMarker = ref<L.Marker | null>(null)
const pathLayer = ref<L.Polyline | null>(null)
const explorationLayer = ref<L.Polyline | null>(null)
const osmPathsLayer = ref<L.LayerGroup | null>(null)

const recentFrames = computed(() =>
  searchResult.value ? searchResult.value.frames.slice(-12).reverse() : [],
)
const pathRows = computed(() => searchResult.value?.path ?? [])
const formattedStart = computed(() => formatPoint(startPoint.value))
const formattedEnd = computed(() => formatPoint(endPoint.value))
const showRealMap = ref(false)
const hasBothPoints = computed(() => Boolean(startPoint.value && endPoint.value))
const showExplorationLine = ref(true)
const showLoadingOverlay = computed(() => loading.value)

let searchToken = 0
let explorationAnimationId: number | null = null
let explorationAnimationResolve: (() => void) | null = null
let pathAnimationId: number | null = null
let pathAnimationResolve: (() => void) | null = null

onMounted(() => {
  if (!mapContainer.value) return

  const createdMap = L.map(mapContainer.value, { zoomControl: true })
  map.value = createdMap

  if (osmBounds.value) {
    focusOnOsmBounds()
  } else {
    createdMap.setView([21.0285, 105.8542], 13)
  }

  syncBaseLayer()
  createdMap.on('click', handleMapClick)
  drawOsmWalkablePaths()
})

onBeforeUnmount(() => {
  stopPathAnimation()
  clearExplorationTrail()
  clearOsmPathsLayer()
  clearBaseLayer()
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

watch(osmWalkablePaths, () => {
  drawOsmWalkablePaths()
})

watch(osmBounds, () => {
  focusOnOsmBounds()
})

watch(showRealMap, () => {
  syncBaseLayer()
})

watch(showExplorationLine, (visible) => {
  if (!visible) {
    clearExplorationTrail()
    return
  }
  if (searchResult.value) {
    void drawExplorationMarkers(searchResult.value.frames)
  }
})

if (typeof window !== 'undefined' && typeof DOMParser !== 'undefined') {
  const parsed = parseOsmWalkableData(osmXml)
  osmWalkablePoints.value = parsed.points
  osmWalkablePaths.value = parsed.paths
  osmBounds.value = parsed.bounds
  osmGraph.value = parsed.graph
}

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
  const graph = osmGraph.value
  if (!start || !end || !graph) return

  const token = ++searchToken
  loading.value = true
  error.value = ''

  await nextTick()

  try {
    const startNode = findClosestGraphNode(start, graph.nodeList)
    const goalNode = findClosestGraphNode(end, graph.nodeList)

    if (!startNode || !goalNode) {
      searchResult.value = null
      await drawPathOnMap([])
      clearExplorationTrail()
      error.value = 'Không tìm được node giao thông nào đủ gần hai điểm bạn chọn.'
      return
    }

    const result = runAStarOnGraph(graph, startNode, goalNode)

    if (token !== searchToken) return

    if (!result.path.length) {
      searchResult.value = null
      await drawPathOnMap([])
      clearExplorationTrail()
      error.value = 'Không tìm thấy đường kết nối hai nút trên bản đồ OSM.'
      return
    }

    searchResult.value = {
      ...result,
      nodeCount: graph.nodeList.length,
      edgeCount: graph.edgeCount,
      wayCount: graph.wayCount,
    }
    await drawPathOnMap([])
    await drawExplorationMarkers(result.frames)
    if (token !== searchToken) return
    await drawPathOnMap(result.path, true)
    if (token !== searchToken) return
    focusOnPath(result.path)
  } catch (err) {
    console.error(err)
    if (token !== searchToken) return
    searchResult.value = null
    await drawPathOnMap([])
    clearExplorationTrail()
    error.value = err instanceof Error ? err.message : 'Đã có lỗi trong lúc chạy tìm đường.'
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
  clearExplorationTrail()
}

function stopPathAnimation() {
  if (pathAnimationId !== null) {
    cancelAnimationFrame(pathAnimationId)
    pathAnimationId = null
  }
  if (pathAnimationResolve) {
    const resolve = pathAnimationResolve
    pathAnimationResolve = null
    resolve()
  }
}

function clearExplorationTrail() {
  if (explorationAnimationId !== null) {
    cancelAnimationFrame(explorationAnimationId)
    explorationAnimationId = null
  }
  if (explorationAnimationResolve) {
    const resolve = explorationAnimationResolve
    explorationAnimationResolve = null
    resolve()
  }
  explorationLayer.value?.remove()
  explorationLayer.value = null
}

function clearOsmPathsLayer() {
  osmPathsLayer.value?.remove()
  osmPathsLayer.value = null
}

function syncBaseLayer() {
  const currentMap = map.value as L.Map | null
  if (!currentMap) return
  clearBaseLayer()
  if (!showRealMap.value) return
  tileLayerRef.value = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OSM</a>',
    maxZoom: 19,
  }).addTo(currentMap)
}

function clearBaseLayer() {
  tileLayerRef.value?.remove()
  tileLayerRef.value = null
}

async function drawPathOnMap(points: LatLngPoint[], animate = false) {
  const currentMap = map.value as L.Map | null
  stopPathAnimation()
  pathLayer.value?.remove()
  pathLayer.value = null
  if (!currentMap || !points.length) return

  const latLngs = points.map((p) => [p.lat, p.lon] as L.LatLngTuple)
  pathLayer.value = L.polyline([latLngs[0]!], {
    color: '#22c55e',
    weight: 5,
    opacity: 0.95,
  }).addTo(currentMap)

  if (!animate || latLngs.length === 1) {
    pathLayer.value.setLatLngs(latLngs)
    return
  }

  await new Promise<void>((resolve) => {
    pathAnimationResolve = () => {
      pathAnimationResolve = null
      resolve()
    }
    let idx = 1
    const step = () => {
      const line = pathLayer.value
      if (!line) {
        pathAnimationId = null
        const finish = pathAnimationResolve
        pathAnimationResolve = null
        finish?.()
        return
      }
      if (idx >= latLngs.length) {
        pathAnimationId = null
        const finish = pathAnimationResolve
        pathAnimationResolve = null
        finish?.()
        return
      }
      line.addLatLng(latLngs[idx]!)
      idx += 1
      pathAnimationId = requestAnimationFrame(step)
    }
    pathAnimationId = requestAnimationFrame(step)
  })
}

function drawOsmWalkablePaths() {
  const currentMap = map.value as L.Map | null
  clearOsmPathsLayer()
  if (!currentMap) return
  const paths = osmWalkablePaths.value
  if (!paths.length) return
  const layer = L.layerGroup()
  for (const path of paths) {
    if (!path || path.length < 2) continue
    const latLngs = path.map((p) => [p.lat, p.lon] as L.LatLngTuple)
    L.polyline(latLngs, {
      color: '#fde047',
      weight: 2,
      opacity: 0.55,
      interactive: false,
    }).addTo(layer)
  }
  layer.addTo(currentMap)
  osmPathsLayer.value = layer
}

async function drawExplorationMarkers(frames: AStarFrame[]) {
  const currentMap = map.value as L.Map | null
  clearExplorationTrail()
  if (!currentMap || !frames.length || !showExplorationLine.value) return

  const step = Math.max(1, Math.floor(frames.length / MAX_EXPLORATION_MARKERS))
  const latLngs: L.LatLngTuple[] = []
  for (let i = 0; i < frames.length; i += step) {
    const frame = frames[i]
    if (!frame) continue
    latLngs.push([frame.lat, frame.lon])
  }
  if (!latLngs.length) return

  explorationLayer.value = L.polyline([latLngs[0]!], {
    color: '#ef4444',
    weight: 3,
    opacity: 0.85,
  }).addTo(currentMap)

  if (latLngs.length === 1) {
    return
  }

  await new Promise<void>((resolve) => {
    explorationAnimationResolve = () => {
      explorationAnimationResolve = null
      resolve()
    }
    let idx = 1
    const stepAnimation = () => {
      const line = explorationLayer.value
      if (!line) {
        explorationAnimationId = null
        const finish = explorationAnimationResolve
        explorationAnimationResolve = null
        finish?.()
        return
      }
      if (idx >= latLngs.length) {
        explorationAnimationId = null
        const finish = explorationAnimationResolve
        explorationAnimationResolve = null
        finish?.()
        return
      }
      line.addLatLng(latLngs[idx]!)
      idx += 1
      explorationAnimationId = requestAnimationFrame(stepAnimation)
    }
    explorationAnimationId = requestAnimationFrame(stepAnimation)
  })
}

function focusOnPath(points: LatLngPoint[]) {
  const currentMap = map.value as L.Map | null
  if (!currentMap || !points.length) return
  const bounds = L.latLngBounds(
    points.map((p) => [p.lat, p.lon] as L.LatLngTuple),
  )
  currentMap.fitBounds(bounds, { padding: [24, 24] })
}

function focusOnOsmBounds() {
  const currentMap = map.value as L.Map | null
  const boundsLiteral = osmBounds.value
  if (!currentMap || !boundsLiteral) return
  const bounds = L.latLngBounds(boundsLiteral)
  currentMap.fitBounds(bounds, { padding: [24, 24] })
  currentMap.setMaxBounds(bounds.pad(0.15))
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
  clearExplorationTrail()
}

function parseOsmWalkableData(xml: string) {
  const emptyGraph: GraphData = {
    nodes: new Map(),
    adjacency: new Map(),
    nodeList: [],
    bounds: null,
    wayCount: 0,
    edgeCount: 0,
  }
  if (!xml) {
    return { points: [], paths: [], bounds: null, graph: emptyGraph }
  }
  try {
    const parser = new DOMParser()
    const doc = parser.parseFromString(xml, 'text/xml')
    const nodeElements = Array.from(doc.getElementsByTagName('node'))
    const nodes = new Map<string, GraphNode>()
    let minLat = Number.POSITIVE_INFINITY
    let maxLat = Number.NEGATIVE_INFINITY
    let minLon = Number.POSITIVE_INFINITY
    let maxLon = Number.NEGATIVE_INFINITY
    for (const nodeEl of nodeElements) {
      const id = nodeEl.getAttribute('id')
      const lat = Number(nodeEl.getAttribute('lat'))
      const lon = Number(nodeEl.getAttribute('lon'))
      if (!id || Number.isNaN(lat) || Number.isNaN(lon)) continue
      nodes.set(id, { id, lat, lon })
      if (lat < minLat) minLat = lat
      if (lat > maxLat) maxLat = lat
      if (lon < minLon) minLon = lon
      if (lon > maxLon) maxLon = lon
    }

    const walkableNodes = new Map<string, GraphNode>()
    const adjacency = new Map<string, GraphEdge[]>()
    const walkablePaths: LatLngPoint[][] = []
    const wayElements = Array.from(doc.getElementsByTagName('way'))
    let wayCount = 0

    for (const wayEl of wayElements) {
      const tagElements = Array.from(wayEl.getElementsByTagName('tag'))
      let highway: string | null = null
      let foot: string | null = null
      let access: string | null = null
      for (const tagEl of tagElements) {
        const key = tagEl.getAttribute('k')
        const value = tagEl.getAttribute('v')
        if (!key || !value) continue
        if (key === 'highway') highway = value
        if (key === 'foot') foot = value
        if (key === 'access') access = value
      }
      const isWalkableHighway = Boolean(highway && OSM_WALKABLE_HIGHWAYS.has(highway))
      const allowsFoot = foot === 'yes' || access === 'permissive' || access === 'yes'
      if (!isWalkableHighway && !allowsFoot) continue

      const ndElements = Array.from(wayEl.getElementsByTagName('nd'))
      const pathNodeIds: string[] = []
      const pathPoints: LatLngPoint[] = []
      for (const nd of ndElements) {
        const ref = nd.getAttribute('ref')
        if (!ref) continue
        const node = nodes.get(ref)
        if (!node) continue
        pathNodeIds.push(ref)
        pathPoints.push({ lat: node.lat, lon: node.lon })
        walkableNodes.set(ref, node)
      }

      if (pathPoints.length >= 2) {
        wayCount += 1
        walkablePaths.push(pathPoints)
        for (let i = 1; i < pathNodeIds.length; i += 1) {
          const prevId = pathNodeIds[i - 1]
          const currId = pathNodeIds[i]
          if (!prevId || !currId) continue
          const prevNode = nodes.get(prevId)
          const currNode = nodes.get(currId)
          if (!prevNode || !currNode) continue
          const distance = haversine(prevNode.lat, prevNode.lon, currNode.lat, currNode.lon)
          addEdge(adjacency, prevId, currId, distance)
          addEdge(adjacency, currId, prevId, distance)
        }
      }
    }

    const hasBounds =
      Number.isFinite(minLat) && Number.isFinite(maxLat) && Number.isFinite(minLon) && Number.isFinite(maxLon)
    const nodeList = Array.from(walkableNodes.values())
    const totalEdges = Array.from(adjacency.values()).reduce((sum, edges) => sum + edges.length, 0)

    const graph: GraphData = {
      nodes: walkableNodes,
      adjacency,
      nodeList,
      bounds: hasBounds ? ([ [minLat, minLon], [maxLat, maxLon] ] as L.LatLngBoundsLiteral) : null,
      wayCount,
      edgeCount: totalEdges,
    }

    return {
      points: nodeList.map((node) => ({ lat: node.lat, lon: node.lon })),
      paths: walkablePaths,
      bounds: graph.bounds,
      graph,
    }
  } catch (err) {
    console.warn('Không đọc được dữ liệu walkable từ OSM.', err)
    return { points: [], paths: [], bounds: null, graph: emptyGraph }
  }
}

function addEdge(adjacency: Map<string, GraphEdge[]>, from: string, to: string, cost: number) {
  const list = adjacency.get(from)
  if (list) {
    list.push({ to, cost })
  } else {
    adjacency.set(from, [{ to, cost }])
  }
}

function findClosestGraphNode(point: LatLngPoint, nodes: GraphNode[]) {
  if (!nodes.length) return null
  let closest: GraphNode | null = null
  let bestDistance = Number.POSITIVE_INFINITY
  for (const node of nodes) {
    const distance = haversine(point.lat, point.lon, node.lat, node.lon)
    if (distance < bestDistance) {
      bestDistance = distance
      closest = node
    }
  }
  if (bestDistance > MAX_SNAP_DISTANCE_METERS) {
    return null
  }
  return closest
}

function runAStarOnGraph(graph: GraphData, startNode: GraphNode, goalNode: GraphNode) {
  const openHeap = new MinHeap<GraphSearchRecord>((a, b) => a.f - b.f)
  const bestG = new Map<string, number>()
  const parents = new Map<string, string | null>()
  const openTracker = new Map<string, GraphSearchRecord>()
  const frames: AStarFrame[] = []
  let generated = 0

  const hStart = haversine(startNode.lat, startNode.lon, goalNode.lat, goalNode.lon)
  const startRecord: GraphSearchRecord = { ...startNode, g: 0, h: hStart, f: hStart }
  openHeap.push(startRecord)
  openTracker.set(startNode.id, startRecord)
  bestG.set(startNode.id, 0)
  parents.set(startNode.id, null)

  while (openHeap.size() > 0) {
    const current = openHeap.pop()
    if (!current) break
    const known = bestG.get(current.id)
    if (known === undefined || current.g > known) {
      continue
    }
    openTracker.delete(current.id)

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

    if (current.id === goalNode.id) {
      const path = buildGraphPath(current.id, parents, graph.nodes)
      return {
        path,
        frames,
        pathDistance: computePathDistance(path),
        expanded: frames.length,
        generated,
      }
    }

    const neighbors = graph.adjacency.get(current.id) ?? []
    for (const edge of neighbors) {
      const neighborNode = graph.nodes.get(edge.to)
      if (!neighborNode) continue

      const tentativeG = current.g + edge.cost
      const bestNeighbor = bestG.get(neighborNode.id)
      if (bestNeighbor !== undefined && tentativeG >= bestNeighbor) {
        continue
      }

      const h = haversine(neighborNode.lat, neighborNode.lon, goalNode.lat, goalNode.lon)
      const record: GraphSearchRecord = {
        ...neighborNode,
        g: tentativeG,
        h,
        f: tentativeG + h,
      }

      bestG.set(neighborNode.id, tentativeG)
      parents.set(neighborNode.id, current.id)
      openTracker.set(neighborNode.id, record)
      openHeap.push(record)
      generated += 1
    }
  }

  return {
    path: [],
    frames,
    pathDistance: 0,
    expanded: frames.length,
    generated,
  }
}

function buildGraphPath(key: string, parents: Map<string, string | null>, nodes: Map<string, GraphNode>) {
  const path: LatLngPoint[] = []
  let currentKey: string | null | undefined = key
  while (currentKey) {
    const node = nodes.get(currentKey)
    if (!node) break
    path.push({ lat: node.lat, lon: node.lon })
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
          <div class="base-toggle">
            <p class="label">Nền bản đồ</p>
            <button class="map-toggle-btn" :class="{ active: showRealMap }" @click="showRealMap = !showRealMap">
              {{ showRealMap ? 'Bản đồ' : 'Overlay' }}
            </button>
          </div>
          <div class="line-toggle">
            <p class="label">Line đỏ</p>
            <button
              class="map-toggle-btn"
              :class="{ active: showExplorationLine }"
              @click="showExplorationLine = !showExplorationLine"
            >
              {{ showExplorationLine ? 'Ẩn line đỏ' : 'Hiện line đỏ' }}
            </button>
          </div>
        </div>
        <div class="map-stage">
          <div ref="mapContainer" class="map-container"></div>
          <div v-if="showLoadingOverlay" class="map-preloader">
            <div class="spinner"></div>
            <p>Đang dựng graph từ dữ liệu OSM và chạy A*...</p>
          </div>
        </div>
        <p class="map-hint">
          Đường đỏ thể hiện thứ tự các node đã được mở rộng trong quá trình chạy A* trên graph OSM.
        </p>
      </section>

      <section class="details-panel">
        <h2>Diễn tiến tìm đường</h2>
        <div class="graph-density">
          <div>
            <p class="label">Graph đang dùng</p>
            <p class="graph-density-note">Dữ liệu lấy từ file OSM cục bộ, lọc theo các loại đường cho người đi bộ.</p>
          </div>
          <div class="graph-density-stats">
            <div>
              <p class="label">Nodes</p>
              <strong>{{ osmGraph?.nodeList.length ?? 0 }}</strong>
            </div>
            <div>
              <p class="label">Cạnh</p>
              <strong>{{ osmGraph?.edgeCount ?? 0 }}</strong>
            </div>
            <div>
              <p class="label">Ways</p>
              <strong>{{ osmGraph?.wayCount ?? 0 }}</strong>
            </div>
          </div>
        </div>
        <p class="hint">
          Graph gom đúng node/way của OSM nên đường tìm được bám sát thực tế và heuristic haversine giúp A* hội tụ nhanh.
        </p>

        <div v-if="error" class="state error">{{ error }}</div>
        <div v-else-if="loading" class="state">Đang dựng graph và chạy A*...</div>
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
                <p class="label">Nodes trong graph</p>
                <strong>{{ searchResult.nodeCount }}</strong>
              </div>
              <div>
                <p class="label">Cạnh trong graph</p>
                <strong>{{ searchResult.edgeCount }}</strong>
              </div>
              <div>
                <p class="label">Số ways</p>
                <strong>{{ searchResult.wayCount }}</strong>
              </div>
            </div>

          </div>

          <p v-else class="state muted">
            Chọn hai điểm bất kỳ trên bản đồ để khởi chạy A*.
          </p>
        </template>
      </section>
    </main>

    <footer>Demo chạy offline trên dữ liệu OSM cục bộ, chưa bao gồm đầy đủ thuộc tính giao thông.</footer>
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

.base-toggle,
.line-toggle {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.map-toggle-btn {
  border: 1px solid rgba(148, 163, 184, 0.4);
  background: rgba(15, 23, 42, 0.6);
  color: #e2e8f0;
  border-radius: 999px;
  padding: 6px 14px;
  cursor: pointer;
  font-weight: 600;
  transition: background 0.2s ease, color 0.2s ease, border-color 0.2s ease;
}

.map-toggle-btn.active {
  background: #1d4ed8;
  border-color: #2563eb;
  color: white;
}

.coord {
  font-size: 14px;
  color: #e2e8f0;
}

.map-stage {
  position: relative;
  border-radius: 20px;
  overflow: hidden;
}

.map-container {
  height: clamp(320px, 60vh, 520px);
  background: #020617;
}

.map-preloader {
  position: absolute;
  inset: 0;
  background: rgba(2, 6, 23, 0.88);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  text-align: center;
  padding: 20px;
  color: #e2e8f0;
  font-weight: 600;
  letter-spacing: 0.01em;
  z-index: 20;
}

.map-preloader .spinner {
  width: 46px;
  height: 46px;
  border-radius: 999px;
  border: 3px solid rgba(248, 250, 252, 0.18);
  border-top-color: #2563eb;
  animation: spin 0.8s linear infinite;
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

.graph-density {
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 12px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: rgba(15, 23, 42, 0.6);
}

.graph-density-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
  gap: 12px;
}

.graph-density-stats strong {
  font-size: 20px;
}

.graph-density-note {
  font-size: 13px;
  color: #94a3b8;
  margin: 4px 0 0;
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

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
