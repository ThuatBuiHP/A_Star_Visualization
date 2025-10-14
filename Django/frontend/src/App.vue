<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import axios from 'axios'
import { VueFlow, addEdge } from '@vue-flow/core'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'

const BASE_TICK_SPACING = 80
const MAX_TICKS_PER_AXIS = 50

const apiUrl = ref(import.meta.env.VITE_GRAPH_API ?? 'http://localhost:3000/api/map')

const baseNodeStyle = {
  padding: '0.5rem 0.75rem',
  borderRadius: '0.75rem',
  border: '1px solid #2563eb',
  background: '#ffffff',
  color: '#1e293b',
  fontWeight: 600,
  fontSize: '0.875rem',
}

const createNode = (id, position) => ({
  id: String(id),
  position,
  data: { label: `Node ${id}`, nodeId: Number(id) },
  draggable: true,
  style: { ...baseNodeStyle },
})

const nodes = ref([
  createNode(1, { x: 100, y: 100 }),
  createNode(2, { x: 320, y: 220 }),
  createNode(3, { x: 180, y: 360 }),
])

const edges = ref([])

const nodeIdCounter = ref(nodes.value.length)
const isSending = ref(false)
const lastError = ref('')
const lastResponse = ref(null)

const canvasRef = ref(null)
const canvasSize = ref({ width: 0, height: 0 })
const viewportTransform = ref({ x: 0, y: 0, zoom: 1 })
const currentZoom = computed(() => Math.max(viewportTransform.value.zoom ?? 1, 0.01))

const updateCanvasSize = () => {
  const el = canvasRef.value
  if (!el) return

  canvasSize.value = {
    width: el.clientWidth,
    height: el.clientHeight,
  }
}

let resizeObserver
let usingWindowResizeFallback = false

onMounted(() => {
  updateCanvasSize()

  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => updateCanvasSize())
    canvasRef.value && resizeObserver.observe(canvasRef.value)
  } else {
    usingWindowResizeFallback = true
    window.addEventListener('resize', updateCanvasSize)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  if (usingWindowResizeFallback) window.removeEventListener('resize', updateCanvasSize)
})

const axisOffset = ref({ x: 0, y: 0 })
const draggingAxis = ref(null)
const dragContext = ref({
  pointerId: null,
  startX: 0,
  startY: 0,
  startOffsetX: 0,
  startOffsetY: 0,
  target: null,
})

const axisLayerStyle = computed(() => ({
  '--axis-offset-x': `${axisOffset.value.x}px`,
  '--axis-offset-y': `${axisOffset.value.y}px`,
}))

const originPoint = computed(() => ({
  x: canvasSize.value.width / 2 + axisOffset.value.x,
  y: canvasSize.value.height / 2 + axisOffset.value.y,
}))

const createHorizontalTicks = (spacing, originX, width) => {
  const ticks = []
  if (spacing <= 0) return ticks

  const countRight = Math.min(
    MAX_TICKS_PER_AXIS,
    Math.floor(Math.max(0, width - originX) / spacing),
  )
  const countLeft = Math.min(MAX_TICKS_PER_AXIS, Math.floor(Math.max(0, originX) / spacing))

  for (let i = 1; i <= countRight; i += 1)
    ticks.push({ key: `h-pos-${i}`, value: i, position: originX + i * spacing })
  for (let i = 1; i <= countLeft; i += 1)
    ticks.push({ key: `h-neg-${i}`, value: -i, position: originX - i * spacing })

  return ticks
}

const createVerticalTicks = (spacing, originY, height) => {
  const ticks = []
  if (spacing <= 0) return ticks

  const countUp = Math.min(MAX_TICKS_PER_AXIS, Math.floor(Math.max(0, originY) / spacing))
  const countDown = Math.min(
    MAX_TICKS_PER_AXIS,
    Math.floor(Math.max(0, height - originY) / spacing),
  )

  for (let i = 1; i <= countUp; i += 1)
    ticks.push({ key: `v-pos-${i}`, value: i, position: originY - i * spacing })
  for (let i = 1; i <= countDown; i += 1)
    ticks.push({ key: `v-neg-${i}`, value: -i, position: originY + i * spacing })

  return ticks
}

const horizontalTicks = computed(() =>
  createHorizontalTicks(
    BASE_TICK_SPACING * currentZoom.value,
    originPoint.value.x,
    canvasSize.value.width,
  ),
)
const verticalTicks = computed(() =>
  createVerticalTicks(
    BASE_TICK_SPACING * currentZoom.value,
    originPoint.value.y,
    canvasSize.value.height,
  ),
)

const getAxisOriginWorld = () => {
  const zoom = currentZoom.value || 1

  return {
    x: (originPoint.value.x - viewportTransform.value.x) / zoom,
    y: (originPoint.value.y - viewportTransform.value.y) / zoom,
  }
}

const getNodePositionsRelativeToAxes = () => {
  const origin = getAxisOriginWorld()
  const scale = BASE_TICK_SPACING

  return nodes.value.map((node) => {
    const relativeX = (node.position.x - origin.x) / scale
    const relativeY = (origin.y - node.position.y) / scale

    return {
      id: Number(node.data?.nodeId ?? node.id),
      x: Number(relativeX.toFixed(2)),
      y: Number(relativeY.toFixed(2)),
    }
  })
}

watch(
  nodes,
  () => {
    console.log(
      'Node positions:',
      nodes.value.map((node) => ({
        id: Number(node.data?.nodeId ?? node.id),
        x: Math.round(node.position.x),
        y: Math.round(node.position.y),
      })),
    )
    console.log('Relative to axes:', getNodePositionsRelativeToAxes())
  },
  { deep: true, immediate: true },
)

watch(
  [nodes, axisOffset, viewportTransform],
  () => {
    const relative = getNodePositionsRelativeToAxes()

    relative.forEach((entry) => {
      const node = nodes.value.find((item) => Number(item.data?.nodeId ?? item.id) === entry.id)

      if (!node) return

      const label = `Node ${entry.id} (${entry.x.toFixed(1)}, ${entry.y.toFixed(1)})`

      if (node.data?.label !== label) {
        node.data = {
          ...node.data,
          label,
        }
      }
    })
  },
  { deep: true, immediate: true },
)

const onAxisPointerDown = (axis, event) => {
  event.preventDefault()
  event.stopPropagation()

  draggingAxis.value = axis
  dragContext.value = {
    pointerId: event.pointerId ?? null,
    startX: event.clientX,
    startY: event.clientY,
    startOffsetX: axisOffset.value.x,
    startOffsetY: axisOffset.value.y,
    target: event.currentTarget ?? null,
  }

  event.currentTarget?.setPointerCapture?.(event.pointerId)
}

const updateAxisOffset = (axis, deltaX, deltaY) => {
  if (axis === 'x') {
    axisOffset.value = {
      ...axisOffset.value,
      x: dragContext.value.startOffsetX + deltaX,
    }
  } else if (axis === 'y') {
    axisOffset.value = {
      ...axisOffset.value,
      y: dragContext.value.startOffsetY + deltaY,
    }
  } else {
    axisOffset.value = {
      x: dragContext.value.startOffsetX + deltaX,
      y: dragContext.value.startOffsetY + deltaY,
    }
  }
}

const onAxisPointerMove = (event) => {
  if (!draggingAxis.value) return

  event.preventDefault()

  const deltaX = event.clientX - dragContext.value.startX
  const deltaY = event.clientY - dragContext.value.startY

  updateAxisOffset(draggingAxis.value, deltaX, deltaY)
}

const clearDragState = () => {
  const { pointerId, target } = dragContext.value
  if (pointerId !== null) {
    try {
      target?.releasePointerCapture?.(pointerId)
    } catch (error) {
      // ignore
    }
  }

  draggingAxis.value = null
  dragContext.value = {
    pointerId: null,
    startX: 0,
    startY: 0,
    startOffsetX: 0,
    startOffsetY: 0,
    target: null,
  }
}

const onAxisPointerUp = () => {
  if (!draggingAxis.value) return
  clearDragState()
}

const handleViewportChange = (flowTransform) => {
  if (!flowTransform) return

  viewportTransform.value = {
    x: flowTransform.x ?? viewportTransform.value.x,
    y: flowTransform.y ?? viewportTransform.value.y,
    zoom: flowTransform.zoom ?? viewportTransform.value.zoom,
  }
}

const handlePaneReady = (instance) => {
  instance?.getViewport && handleViewportChange(instance.getViewport())
}
</script>

<template>
  <div class="app">
    <header class="toolbar">
      <div>
        <h1>Ban do gia lap</h1>
        <p>Di chuyen node tren truc XY va noi cac path giua chung.</p>
      </div>

      <div class="actions">
        <label class="api-input">
          <span>API URL</span>
          <input v-model="apiUrl" type="text" placeholder="http://localhost:3000/api/map" />
        </label>
        <button type="button" class="btn secondary" @click="addNode">Them node</button>
        <button type="button" class="btn primary" :disabled="isSending" @click="sendGraph">
          {{ isSending ? 'Dang gui...' : 'Gui du lieu' }}
        </button>
      </div>
    </header>

    <div class="canvas" ref="canvasRef">
      <VueFlow
        v-model:nodes="nodes"
        v-model:edges="edges"
        class="flow"
        :min-zoom="0.2"
        :max-zoom="2"
        :fit-view-on-init="true"
        :snap-to-grid="true"
        :snap-grid="[20, 20]"
        @connect="onConnect"
        @viewport-change="handleViewportChange"
        @pane-ready="handlePaneReady"
      >
        <Controls />
        <MiniMap />
      </VueFlow>

      <div class="axis-layer" :style="axisLayerStyle">
        <div class="axis-ticks axis-ticks-x" :style="{ top: `${originPoint.y}px` }">
          <div
            v-for="tick in horizontalTicks"
            :key="tick.key"
            class="axis-tick axis-tick-x"
            :style="{ left: `${tick.position}px` }"
          >
            <span class="axis-tick-mark axis-tick-mark-x" />
            <span class="axis-tick-label axis-tick-label-x">{{ tick.value }}</span>
          </div>
        </div>

        <div class="axis-ticks axis-ticks-y" :style="{ left: `${originPoint.x}px` }">
          <div
            v-for="tick in verticalTicks"
            :key="tick.key"
            class="axis-tick axis-tick-y"
            :style="{ top: `${tick.position}px` }"
          >
            <span class="axis-tick-label axis-tick-label-y">{{ tick.value }}</span>
            <span class="axis-tick-mark axis-tick-mark-y" />
          </div>
        </div>

        <div
          class="axis-label axis-label-origin"
          :style="{ left: `${originPoint.x}px`, top: `${originPoint.y}px` }"
        >
          0
        </div>

        <div
          class="axis-line axis-y"
          @pointerdown="(event) => onAxisPointerDown('x', event)"
          @pointermove="onAxisPointerMove"
          @pointerup="onAxisPointerUp"
          @pointercancel="onAxisPointerUp"
        />
        <div
          class="axis-line axis-x"
          @pointerdown="(event) => onAxisPointerDown('y', event)"
          @pointermove="onAxisPointerMove"
          @pointerup="onAxisPointerUp"
          @pointercancel="onAxisPointerUp"
        />
        <div
          class="axis-origin"
          title="Keo de di chuyen giao diem"
          @pointerdown="(event) => onAxisPointerDown('both', event)"
          @pointermove="onAxisPointerMove"
          @pointerup="onAxisPointerUp"
          @pointercancel="onAxisPointerUp"
        />
      </div>
    </div>

    <section class="output">
      <div class="payload">
        <h2>Payload</h2>
        <pre>{{ formattedPayload }}</pre>
      </div>
      <div class="status">
        <h2>Ket qua</h2>
        <template v-if="lastResponse">
          <p>Server tra ve:</p>
          <pre>{{ responsePreview }}</pre>
        </template>
        <p v-else-if="lastError" class="error">Loi: {{ lastError }}</p>
        <p v-else>Chua gui du lieu.</p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.app {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  padding: 1.5rem;
  font-family:
    system-ui,
    -apple-system,
    BlinkMacSystemFont,
    'Segoe UI',
    sans-serif;
  height: 100vh;
  box-sizing: border-box;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}

.toolbar h1 {
  margin: 0;
  font-size: 1.5rem;
}

.toolbar p {
  margin: 0;
  color: #475569;
}

.actions {
  display: flex;
  gap: 0.75rem;
  align-items: flex-end;
  flex-wrap: wrap;
}

.api-input {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.85rem;
  color: #475569;
}

.api-input input {
  min-width: 260px;
  padding: 0.5rem 0.75rem;
  border: 1px solid #cbd5f5;
  border-radius: 0.5rem;
}

.api-input input:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.25);
}

.btn {
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  border: none;
  cursor: pointer;
  font-weight: 600;
  transition: background-color 0.2s ease;
}

.btn.primary {
  background-color: #2563eb;
  color: #ffffff;
}

.btn.primary:disabled {
  background-color: #93c5fd;
  cursor: not-allowed;
}

.btn.secondary {
  background-color: #e2e8f0;
  color: #1e293b;
}

.canvas {
  position: relative;
  flex: 1;
  min-height: 420px;
  border: 1px solid #cbd5f5;
  border-radius: 1rem;
  overflow: hidden;
  background-color: #ffffff;
}

.flow {
  width: 100%;
  height: 100%;
}

.axis-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 10;
  font-size: 0.875rem;
  color: #1e293b;
}

.axis-ticks {
  position: absolute;
  pointer-events: none;
  user-select: none;
}

.axis-ticks.axis-ticks-x {
  left: 0;
  right: 0;
  height: 0;
}

.axis-tick.axis-tick-x {
  position: absolute;
  display: flex;
  flex-direction: column;
  align-items: center;
  transform: translate(-50%, -50%);
  gap: 4px;
}

.axis-tick-mark-x {
  width: 2px;
  height: 12px;
  background-color: rgba(37, 99, 235, 0.7);
}

.axis-tick-label-x {
  font-weight: 500;
}

.axis-ticks.axis-ticks-y {
  top: 0;
  bottom: 0;
  width: 0;
}

.axis-tick.axis-tick-y {
  position: absolute;
  display: flex;
  align-items: center;
  transform: translate(-50%, -50%);
  gap: 6px;
}

.axis-tick-mark-y {
  width: 12px;
  height: 2px;
  background-color: rgba(37, 99, 235, 0.7);
}

.axis-tick-label-y {
  font-weight: 500;
}

.axis-label-origin {
  position: absolute;
  transform: translate(-110%, 40%);
  font-weight: 600;
  pointer-events: none;
  user-select: none;
}

.axis-line {
  position: absolute;
  background-color: rgba(37, 99, 235, 0.35);
  pointer-events: auto;
  touch-action: none;
}

.axis-line.axis-y {
  top: 0;
  bottom: 0;
  width: 2px;
  left: calc(50% + var(--axis-offset-x, 0px));
  cursor: ew-resize;
}

.axis-line.axis-x {
  left: 0;
  right: 0;
  height: 2px;
  top: calc(50% + var(--axis-offset-y, 0px));
  cursor: ns-resize;
}

.axis-origin {
  width: 14px;
  height: 14px;
  border-radius: 9999px;
  border: 2px solid rgba(37, 99, 235, 0.75);
  background-color: #ffffff;
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.15);
  position: absolute;
  left: calc(50% + var(--axis-offset-x, 0px));
  top: calc(50% + var(--axis-offset-y, 0px));
  transform: translate(-50%, -50%);
  pointer-events: auto;
  cursor: move;
  touch-action: none;
}

.output {
  display: grid;
  grid-template-columns: minmax(320px, 1fr) minmax(220px, 1fr);
  gap: 1rem;
}

.payload,
.status {
  padding: 1rem;
  border: 1px solid #e2e8f0;
  border-radius: 0.75rem;
  background-color: #ffffff;
  min-height: 160px;
}

.payload pre,
.status pre {
  background-color: #f1f5f9;
  padding: 0.75rem;
  border-radius: 0.5rem;
  overflow: auto;
  max-height: 220px;
  margin: 0;
  font-size: 0.85rem;
}

.status h2,
.payload h2 {
  margin: 0 0 0.75rem 0;
  font-size: 1rem;
}

.error {
  color: #dc2626;
  white-space: pre-wrap;
}

@media (max-width: 960px) {
  .output {
    grid-template-columns: 1fr;
  }
}
</style>
