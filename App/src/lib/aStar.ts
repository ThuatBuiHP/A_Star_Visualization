import type { LatLngBoundsLiteral } from 'leaflet'

export interface LatLngPoint {
  lat: number
  lon: number
}

export interface GraphNode extends LatLngPoint {
  id: string
}

export interface GraphEdge {
  to: string
  cost: number
}

export interface GraphData {
  nodes: Map<string, GraphNode>
  adjacency: Map<string, GraphEdge[]>
  nodeList: GraphNode[]
  bounds: LatLngBoundsLiteral | null
  wayCount: number
  edgeCount: number
}

export interface AStarFrame {
  index: number
  lat: number
  lon: number
  g: number
  h: number
  f: number
  openSize: number
  closedSize: number
}

interface GraphSearchRecord extends GraphNode {
  g: number
  h: number
  f: number
}

export interface RunAStarResult {
  path: LatLngPoint[]
  frames: AStarFrame[]
  pathDistance: number
  expanded: number
  generated: number
}

export function runAStarOnGraph(graph: GraphData, startNode: GraphNode, goalNode: GraphNode): RunAStarResult {
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

export function haversine(lat1: number, lon1: number, lat2: number, lon2: number) {
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
