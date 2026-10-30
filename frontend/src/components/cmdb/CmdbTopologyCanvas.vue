<template>
  <div ref="containerRef" class="topology-stage">
    <canvas
      ref="canvasRef"
      class="topology-canvas"
      @mousedown="handleMouseDown"
      @mousemove="handleMouseMove"
      @mouseup="handleMouseUp"
      @mouseleave="handleMouseLeave"
      @wheel.prevent="handleWheel"
      @dblclick="handleDoubleClick"
    ></canvas>

    <div v-if="hoveredNode" class="topology-tooltip" :style="tooltipStyle">
      <div class="tooltip-title">{{ hoveredNode.name }}</div>
      <div class="tooltip-row">{{ labels.type }}: {{ hoveredNode.type }}</div>
      <div class="tooltip-row">{{ labels.businessLine }}: {{ hoveredNode.business_line || labels.unassigned }}</div>
      <div class="tooltip-row">{{ labels.environment }}: {{ envLabel(hoveredNode.env) }}</div>
      <div class="tooltip-row">IP: {{ hoveredNode.ip || '-' }}</div>
      <div class="tooltip-row">{{ labels.monthlyCost }}: {{ formatCurrency(hoveredNode.monthly_cost) }}</div>
    </div>

    <button type="button" class="topology-fit-btn" @click="fitView()">{{ labels.resetCanvas }}</button>

    <div v-if="visibleCiTypes.length || relationLegendItems.length" class="topology-legend">
      <div class="legend-title">{{ labels.legend }}</div>
      <div v-for="type in visibleCiTypes" :key="type.id" class="legend-item">
        <span class="legend-dot" :style="{ background: type.color }"></span>
        <span>{{ type.name }}</span>
      </div>
      <template v-if="relationLegendItems.length">
        <div v-if="visibleCiTypes.length" class="legend-divider"></div>
        <div v-for="item in relationLegendItems" :key="item.type" class="legend-item">
          <span class="legend-line" :class="item.className"></span>{{ item.label }}
        </div>
      </template>
    </div>

    <div v-if="minimapNodes.length" class="topology-minimap">
      <div class="minimap-title">{{ labels.globalView }}</div>
      <div class="minimap-body">
        <span
          v-for="node in minimapNodes"
          :key="node.id"
          class="minimap-node"
          :style="node.style"
        ></span>
        <span class="minimap-viewport" :style="minimapViewportStyle"></span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { resolveThemeColor, theme } from '@/theme'
import {
  EDGE_COLORS,
  buildGraphLookup,
  envLabel,
  layoutTopology,
  pointToSegmentDistance,
} from './useTopologyGraph'

const defaultLabels = {
  type: '\u7c7b\u578b',
  businessLine: '\u4e1a\u52a1\u7ebf',
  environment: '\u73af\u5883',
  monthlyCost: '\u6708\u6210\u672c',
  resetCanvas: '\u91cd\u7f6e\u753b\u5e03',
  legend: '\u56fe\u4f8b',
  dependsOn: '\u4e1a\u52a1\u4f9d\u8d56',
  runsOn: '\u90e8\u7f72\u5728',
  connectsTo: '\u8fde\u63a5\u5230',
  globalView: '\u5168\u5c40\u89c6\u56fe',
  unassigned: '\u672a\u5206\u914d',
}

const props = defineProps({
  nodes: {
    type: Array,
    default: () => [],
  },
  edges: {
    type: Array,
    default: () => [],
  },
  ciTypes: {
    type: Array,
    default: () => [],
  },
  resourceTree: {
    type: Array,
    default: () => [],
  },
  matchedNodeIds: {
    type: Array,
    default: () => [],
  },
  selectedNodeId: {
    type: Number,
    default: null,
  },
  selectedEdgeId: {
    type: Number,
    default: null,
  },
  resetToken: {
    type: String,
    default: '',
  },
  labels: {
    type: Object,
    default: () => ({}),
  },
  editable: {
    type: Boolean,
    default: true,
  },
})

const emit = defineEmits(['select-node', 'select-edge', 'clear-selection', 'edit-node'])

const containerRef = ref(null)
const canvasRef = ref(null)
const hoveredNode = ref(null)
const tooltipPos = ref({ x: 0, y: 0 })
const canvasSize = ref({ width: 0, height: 0, dpr: 1 })
const viewport = ref({ x: 0, y: 0, scale: 1 })
const layoutState = ref({ nodes: [], sections: [], laneLabels: [], bounds: null })
const dragState = ref({ active: false, moved: false, start: null, viewport: null })

let resizeObserver = null
let frameHandle = null

const labels = computed(() => ({ ...defaultLabels, ...(props.labels || {}) }))
const tooltipStyle = computed(() => ({
  left: `${tooltipPos.value.x}px`,
  top: `${tooltipPos.value.y}px`,
}))

const visibleCiTypes = computed(() => {
  const nodeTypes = new Set(layoutState.value.nodes.map(node => node.type))
  return props.ciTypes.filter(type => nodeTypes.has(type.name))
})

const relationLegendItems = computed(() => {
  const nodeIds = new Set(layoutState.value.nodes.map(node => node.id))
  const edgeTypes = new Set(props.edges
    .filter(edge => nodeIds.has(edge.source) && nodeIds.has(edge.target))
    .map(edge => edge.type))
  return [
    { type: 'depends_on', label: labels.value.dependsOn, className: 'legend-solid' },
    { type: 'runs_on', label: labels.value.runsOn, className: 'legend-runs' },
    { type: 'connects_to', label: labels.value.connectsTo, className: 'legend-dashed' },
  ].filter(item => edgeTypes.has(item.type))
})

const matchedNodeIdSet = computed(() => new Set(props.matchedNodeIds || []))
const graphLookup = computed(() => buildGraphLookup(layoutState.value.nodes, props.edges))

const minimapNodes = computed(() => {
  const bounds = layoutState.value.bounds
  if (!bounds || !layoutState.value.nodes.length) return []
  const width = Math.max(bounds.width, 1)
  const height = Math.max(bounds.height, 1)
  const scale = Math.min(150 / width, 92 / height)

  return layoutState.value.nodes.map(node => ({
    id: node.id,
    style: {
      left: `${8 + (node.x - bounds.minX) * scale}px`,
      top: `${8 + (node.y - bounds.minY) * scale}px`,
      background: node.color,
      opacity: props.selectedNodeId && props.selectedNodeId !== node.id ? 0.35 : 0.92,
      transform: props.selectedNodeId === node.id ? 'scale(1.45)' : 'scale(1)',
    },
  }))
})

const minimapViewportStyle = computed(() => {
  const bounds = layoutState.value.bounds
  if (!bounds || !canvasSize.value.width || !canvasSize.value.height) return {}
  const width = Math.max(bounds.width, 1)
  const height = Math.max(bounds.height, 1)
  const scale = Math.min(150 / width, 92 / height)
  const worldLeft = (0 - viewport.value.x) / viewport.value.scale
  const worldTop = (0 - viewport.value.y) / viewport.value.scale
  const worldWidth = canvasSize.value.width / viewport.value.scale
  const worldHeight = canvasSize.value.height / viewport.value.scale

  return {
    left: `${8 + (worldLeft - bounds.minX) * scale}px`,
    top: `${8 + (worldTop - bounds.minY) * scale}px`,
    width: `${Math.max(worldWidth * scale, 18)}px`,
    height: `${Math.max(worldHeight * scale, 18)}px`,
  }
})

function formatCurrency(value) {
  return `\u00A5${Number(value || 0).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`
}
function scheduleDraw() {
  if (frameHandle) return
  frameHandle = requestAnimationFrame(() => {
    frameHandle = null
    drawGraph()
  })
}

function syncCanvasSize() {
  const container = containerRef.value
  const canvas = canvasRef.value
  if (!container || !canvas) return false
  const width = Math.max(container.clientWidth, 320)
  const height = Math.max(container.clientHeight, 520)
  const dpr = window.devicePixelRatio || 1

  canvas.style.width = `${width}px`
  canvas.style.height = `${height}px`
  canvas.width = Math.floor(width * dpr)
  canvas.height = Math.floor(height * dpr)
  canvasSize.value = { width, height, dpr }
  return true
}

function rebuildGraph({ fit = false } = {}) {
  if (!syncCanvasSize()) return
  layoutState.value = layoutTopology({
    nodes: props.nodes,
    resourceTree: props.resourceTree,
    width: canvasSize.value.width,
    height: canvasSize.value.height,
  })

  if (props.selectedNodeId && !layoutState.value.nodes.some(node => node.id === props.selectedNodeId)) {
    emit('clear-selection')
  }
  if (props.selectedEdgeId && !props.edges.some(edge => edge.id === props.selectedEdgeId)) {
    emit('clear-selection')
  }

  if (fit || (viewport.value.scale === 1 && viewport.value.x === 0 && viewport.value.y === 0)) {
    fitView()
  } else {
    scheduleDraw()
  }
}

function fitView() {
  const bounds = layoutState.value.bounds
  if (!bounds || !canvasSize.value.width || !canvasSize.value.height) {
    scheduleDraw()
    return
  }

  const topSafeInset = 58
  const bottomSafeInset = 28
  const leftBias = 32
  const availableWidth = Math.max(canvasSize.value.width - 52, 120)
  const availableHeight = Math.max(canvasSize.value.height - topSafeInset - bottomSafeInset, 120)
  const scale = Math.min(1.18, availableWidth / Math.max(bounds.width, 1), availableHeight / Math.max(bounds.height, 1))
  const finalScale = Math.max(Math.min(scale * 1.04, 1.24), 0.5)
  const centeredYOffset = (availableHeight - bounds.height * finalScale) / 2 + 8

  viewport.value = {
    scale: finalScale,
    x: (canvasSize.value.width - bounds.width * finalScale) / 2 - bounds.minX * finalScale - leftBias,
    y: topSafeInset + centeredYOffset - bounds.minY * finalScale,
  }
  scheduleDraw()
}

function clientToLocalPoint(event) {
  const rect = canvasRef.value.getBoundingClientRect()
  return {
    x: event.clientX - rect.left,
    y: event.clientY - rect.top,
  }
}

function localToWorld(point) {
  return {
    x: (point.x - viewport.value.x) / viewport.value.scale,
    y: (point.y - viewport.value.y) / viewport.value.scale,
  }
}

function getNodeAt(worldPoint) {
  for (let index = layoutState.value.nodes.length - 1; index >= 0; index -= 1) {
    const node = layoutState.value.nodes[index]
    const offsetX = worldPoint.x - node.x
    const offsetY = worldPoint.y - node.y
    if (offsetX * offsetX + offsetY * offsetY <= (node.r + 5) * (node.r + 5)) {
      return node
    }
  }
  return null
}

function getEdgeAt(worldPoint) {
  const { nodeMap } = graphLookup.value
  let closestEdge = null
  let closestDistance = Infinity

  props.edges.forEach(edge => {
    const source = nodeMap.get(edge.source)
    const target = nodeMap.get(edge.target)
    if (!source || !target) return
    const distance = pointToSegmentDistance(worldPoint, source, target)
    if (distance < 10 && distance < closestDistance) {
      closestDistance = distance
      closestEdge = edge
    }
  })

  return closestEdge
}

function isNodeEmphasized(node) {
  const selectedEdge = props.selectedEdgeId ? props.edges.find(edge => edge.id === props.selectedEdgeId) : null
  if (props.selectedNodeId) {
    const neighbors = graphLookup.value.neighborsById.get(props.selectedNodeId) || new Set()
    return node.id === props.selectedNodeId || neighbors.has(node.id)
  }
  if (selectedEdge) {
    return node.id === selectedEdge.source || node.id === selectedEdge.target
  }
  return true
}

function isEdgeEmphasized(edge) {
  if (props.selectedNodeId) {
    return edge.source === props.selectedNodeId || edge.target === props.selectedNodeId
  }
  return !props.selectedEdgeId || props.selectedEdgeId === edge.id
}

function buildEdgeRouteMeta(edges = []) {
  const groups = new Map()
  edges.forEach(edge => {
    const sourceId = Math.min(edge.source, edge.target)
    const targetId = Math.max(edge.source, edge.target)
    const key = `${sourceId}:${targetId}`
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(edge)
  })

  const routeMeta = new Map()
  groups.forEach(groupEdges => {
    const orderedEdges = groupEdges.slice().sort((left, right) => {
      if (left.source !== right.source) return left.source - right.source
      if (left.target !== right.target) return left.target - right.target
      if (left.type !== right.type) return String(left.type).localeCompare(String(right.type))
      return left.id - right.id
    })
    const center = (orderedEdges.length - 1) / 2
    orderedEdges.forEach((edge, index) => {
      routeMeta.set(edge.id, {
        offset: (index - center) * 16,
        index,
        count: orderedEdges.length,
      })
    })
  })
  return routeMeta
}

function buildEdgePath(edge, nodeMap, nodes, routeMetaMap) {
  const source = nodeMap.get(edge.source)
  const target = nodeMap.get(edge.target)
  if (!source || !target) return null
  const routeMeta = routeMetaMap.get(edge.id) || { offset: 0, index: 0, count: 1 }
  const points = buildOrthogonalPath(source, target, nodes, routeMeta)
  return {
    source,
    target,
    points,
    routeMeta,
  }
}

function buildOrthogonalPath(source, target, nodes = [], routeMeta = {}) {
  const dx = target.x - source.x
  const dy = target.y - source.y
  const horizontalFirst = Math.abs(dx) >= Math.abs(dy)
  const baseGap = 36 + Math.abs(routeMeta.offset || 0) * 0.25
  const obstacles = nodes.filter(node => node.id !== source.id && node.id !== target.id)
  const preferredOffset = routeMeta.offset || 0

  const centerPathHV = (middleX, sourceY = source.y, targetY = target.y) => ([
    { x: source.x, y: source.y },
    { x: middleX, y: source.y },
    { x: middleX, y: target.y },
    { x: target.x, y: target.y },
  ])
  const centerPathVH = (middleY, sourceX = source.x, targetX = target.x) => ([
    { x: source.x, y: source.y },
    { x: source.x, y: middleY },
    { x: target.x, y: middleY },
    { x: target.x, y: target.y },
  ])
  const doglegHV = (sourceY, middleX, targetY) => ([
    { x: source.x, y: source.y },
    { x: source.x, y: sourceY },
    { x: middleX, y: sourceY },
    { x: middleX, y: targetY },
    { x: target.x, y: targetY },
    { x: target.x, y: target.y },
  ])
  const doglegVH = (sourceX, middleY, targetX) => ([
    { x: source.x, y: source.y },
    { x: sourceX, y: source.y },
    { x: sourceX, y: middleY },
    { x: targetX, y: middleY },
    { x: targetX, y: target.y },
    { x: target.x, y: target.y },
  ])

  const xCandidates = uniqueNumberList([
    source.x + dx / 2 + preferredOffset,
    Math.min(source.x, target.x) - baseGap,
    Math.max(source.x, target.x) + baseGap,
    ...obstacles.flatMap(node => [node.x - node.r - baseGap, node.x + node.r + baseGap]),
  ])
  const yCandidates = uniqueNumberList([
    source.y + dy / 2 + preferredOffset,
    Math.min(source.y, target.y) - baseGap,
    Math.max(source.y, target.y) + baseGap,
    ...obstacles.flatMap(node => [node.y - node.r - baseGap, node.y + node.r + baseGap]),
  ])

  const candidatePaths = []
  xCandidates.forEach(value => candidatePaths.push(centerPathHV(value)))
  yCandidates.forEach(value => candidatePaths.push(centerPathVH(value)))
  xCandidates.forEach(middleX => {
    yCandidates.slice(0, 6).forEach(sourceY => {
      yCandidates.slice(0, 6).forEach(targetY => candidatePaths.push(doglegHV(sourceY, middleX, targetY)))
    })
  })
  yCandidates.forEach(middleY => {
    xCandidates.slice(0, 6).forEach(sourceX => {
      xCandidates.slice(0, 6).forEach(targetX => candidatePaths.push(doglegVH(sourceX, middleY, targetX)))
    })
  })

  let bestPath = null
  let bestScore = Infinity
  let fallbackPath = null
  let fallbackScore = Infinity

  candidatePaths.forEach(path => {
    const anchoredPath = anchorPathToNodes(path, source, target)
    const obstacleHits = countPathObstacleHits(anchoredPath, obstacles)
    const score = scorePath(anchoredPath, obstacleHits, preferredOffset, horizontalFirst)
    if (score < fallbackScore) {
      fallbackPath = anchoredPath
      fallbackScore = score
    }
    if (obstacleHits === 0 && score < bestScore) {
      bestPath = anchoredPath
      bestScore = score
    }
  })

  return bestPath || fallbackPath || anchorPathToNodes(centerPathHV(source.x + dx / 2 + preferredOffset), source, target)
}

function uniqueNumberList(values) {
  return Array.from(new Set(values.map(value => Math.round(value))))
}

function anchorPathToNodes(points, source, target) {
  const anchored = compressPath(points.map(point => ({ ...point })))
  if (!anchored.length) return anchored
  const nextPoint = anchored[1] || anchored[0]
  const previousPoint = anchored[anchored.length - 2] || anchored[anchored.length - 1]
  anchored[0] = projectPointToNodeEdge(source, nextPoint)
  anchored[anchored.length - 1] = projectPointToNodeEdge(target, previousPoint)
  return compressPath(anchored)
}

function projectPointToNodeEdge(node, towardPoint) {
  const dx = towardPoint.x - node.x
  const dy = towardPoint.y - node.y
  const offset = node.r + 2
  if (Math.abs(dx) >= Math.abs(dy)) {
    return {
      x: node.x + (dx >= 0 ? offset : -offset),
      y: node.y,
    }
  }
  return {
    x: node.x,
    y: node.y + (dy >= 0 ? offset : -offset),
  }
}

function compressPath(points) {
  const result = []
  points.forEach(point => {
    const lastPoint = result[result.length - 1]
    if (lastPoint && lastPoint.x === point.x && lastPoint.y === point.y) return
    result.push(point)
    if (result.length < 3) return
    const a = result[result.length - 3]
    const b = result[result.length - 2]
    const c = result[result.length - 1]
    if ((a.x === b.x && b.x === c.x) || (a.y === b.y && b.y === c.y)) {
      result.splice(result.length - 2, 1)
    }
  })
  return result
}

function scorePath(points, obstacleHits = 0, preferredOffset = 0, horizontalFirst = true) {
  let total = 0
  for (let index = 1; index < points.length; index += 1) {
    total += Math.abs(points[index].x - points[index - 1].x) + Math.abs(points[index].y - points[index - 1].y)
  }
  const bends = Math.max(points.length - 2, 0)
  const preferencePenalty = points.length > 3
    ? Math.abs((horizontalFirst ? points[1].x - points[0].x : points[1].y - points[0].y) - preferredOffset) * 0.08
    : 0
  return total + bends * 20 + obstacleHits * 100000 + preferencePenalty
}

function countPathObstacleHits(points, nodes) {
  let count = 0
  nodes.forEach(node => {
    const box = getNodeObstacleBox(node)
    for (let index = 1; index < points.length; index += 1) {
      if (segmentIntersectsBox(points[index - 1], points[index], box)) {
        count += 1
        break
      }
    }
  })
  return count
}

function getNodeObstacleBox(node) {
  return {
    left: node.x - node.r - 12,
    right: node.x + node.r + 12,
    top: node.y - node.r - 12,
    bottom: node.y + node.r + 38,
  }
}

function getNodeLabelBox(node) {
  const width = Math.max(76, String(node.name || '').length * 12 + 18)
  return {
    left: node.x - width / 2,
    right: node.x + width / 2,
    top: node.y + node.r + 8,
    bottom: node.y + node.r + 36,
  }
}

function getLongestSegment(points) {
  let best = null
  let bestLength = -1
  for (let index = 1; index < points.length; index += 1) {
    const start = points[index - 1]
    const end = points[index]
    const length = Math.abs(end.x - start.x) + Math.abs(end.y - start.y)
    if (length > bestLength) {
      bestLength = length
      best = { start, end, length }
    }
  }
  return best
}

function chooseEdgeLabelPlacement(ctx, edge, points, nodes, occupiedBoxes = []) {
  const segment = getLongestSegment(points)
  if (!segment) {
    const x = points[0]?.x || 0
    const y = points[0]?.y || 0
    return {
      x,
      y,
      width: 48,
      height: 18,
      left: x - 24,
      right: x + 24,
      top: y - 9,
      bottom: y + 9,
    }
  }

  ctx.font = '11px sans-serif'
  const width = Math.max(52, ctx.measureText(edge.label).width + 16)
  const height = 18
  const middleX = (segment.start.x + segment.end.x) / 2
  const middleY = (segment.start.y + segment.end.y) / 2
  const isHorizontal = segment.start.y === segment.end.y
  const candidates = isHorizontal
    ? [
        { x: middleX, y: middleY - 16 },
        { x: middleX, y: middleY + 16 },
        { x: middleX - 22, y: middleY - 16 },
        { x: middleX + 22, y: middleY + 16 },
      ]
    : [
        { x: middleX - 32, y: middleY },
        { x: middleX + 32, y: middleY },
        { x: middleX - 32, y: middleY - 20 },
        { x: middleX + 32, y: middleY + 20 },
      ]

  let best = null
  let bestScore = Infinity
  candidates.forEach(candidate => {
    const box = {
      x: candidate.x,
      y: candidate.y,
      width,
      height,
      left: candidate.x - width / 2,
      right: candidate.x + width / 2,
      top: candidate.y - height / 2,
      bottom: candidate.y + height / 2,
    }
    const nodeOverlap = nodes.some(node => boxIntersects(box, getNodeObstacleBox(node)) || boxIntersects(box, getNodeLabelBox(node)))
    const labelOverlap = occupiedBoxes.some(occupied => boxIntersects(box, occupied))
    const score = (nodeOverlap ? 10000 : 0) + (labelOverlap ? 5000 : 0) + Math.abs(candidate.x - middleX) + Math.abs(candidate.y - middleY)
    if (score < bestScore) {
      best = box
      bestScore = score
    }
  })

  return best || {
    x: middleX,
    y: middleY,
    width,
    height,
    left: middleX - width / 2,
    right: middleX + width / 2,
    top: middleY - height / 2,
    bottom: middleY + height / 2,
  }
}

function boxIntersects(a, b) {
  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top
}

function segmentIntersectsBox(start, end, box) {
  if (start.x === end.x) {
    const x = start.x
    if (x <= box.left || x >= box.right) return false
    const minY = Math.min(start.y, end.y)
    const maxY = Math.max(start.y, end.y)
    return maxY > box.top && minY < box.bottom
  }
  if (start.y === end.y) {
    const y = start.y
    if (y <= box.top || y >= box.bottom) return false
    const minX = Math.min(start.x, end.x)
    const maxX = Math.max(start.x, end.x)
    return maxX > box.left && minX < box.right
  }
  return false
}

function drawOrthogonalLine(ctx, points) {
  if (!points.length) return
  ctx.beginPath()
  ctx.moveTo(points[0].x, points[0].y)
  for (let index = 1; index < points.length; index += 1) {
    ctx.lineTo(points[index].x, points[index].y)
  }
  ctx.stroke()
}

function drawArrow(ctx, fromPoint, toPoint, color) {
  const dx = toPoint.x - fromPoint.x
  const dy = toPoint.y - fromPoint.y
  const length = Math.sqrt(dx * dx + dy * dy)
  if (!length) return
  const ux = dx / length
  const uy = dy / length
  const arrowPoint = {
    x: toPoint.x,
    y: toPoint.y,
  }
  const size = 8

  ctx.beginPath()
  ctx.moveTo(arrowPoint.x, arrowPoint.y)
  ctx.lineTo(arrowPoint.x - ux * size + uy * size * 0.5, arrowPoint.y - uy * size - ux * size * 0.5)
  ctx.lineTo(arrowPoint.x - ux * size - uy * size * 0.5, arrowPoint.y - uy * size + ux * size * 0.5)
  ctx.closePath()
  ctx.fillStyle = color
  ctx.fill()
}

const LANE_TINTS = [
  { fill: 'rgba(59, 130, 246, 0.08)', border: 'rgba(59, 130, 246, 0.22)' },
  { fill: 'rgba(16, 185, 129, 0.08)', border: 'rgba(16, 185, 129, 0.22)' },
  { fill: 'rgba(245, 158, 11, 0.08)', border: 'rgba(245, 158, 11, 0.22)' },
  { fill: 'rgba(236, 72, 153, 0.07)', border: 'rgba(236, 72, 153, 0.2)' },
  { fill: 'rgba(14, 165, 233, 0.08)', border: 'rgba(14, 165, 233, 0.22)' },
]

function getLaneTint(name = '') {
  let hash = 0
  for (let index = 0; index < name.length; index += 1) {
    hash = (hash * 31 + name.charCodeAt(index)) >>> 0
  }
  return LANE_TINTS[hash % LANE_TINTS.length]
}

function drawBlueprintGrid(ctx, width, height) {
  const minor = 22
  const major = minor * 4

  ctx.save()
  ctx.strokeStyle = resolveThemeColor('rgba(148, 163, 184, 0.07)', 'surface')
  ctx.lineWidth = 1
  for (let x = 0; x <= width; x += minor) {
    ctx.beginPath()
    ctx.moveTo(x + 0.5, 0)
    ctx.lineTo(x + 0.5, height)
    ctx.stroke()
  }
  for (let y = 0; y <= height; y += minor) {
    ctx.beginPath()
    ctx.moveTo(0, y + 0.5)
    ctx.lineTo(width, y + 0.5)
    ctx.stroke()
  }

  ctx.strokeStyle = resolveThemeColor('rgba(59, 130, 246, 0.1)', 'surface')
  for (let x = 0; x <= width; x += major) {
    ctx.beginPath()
    ctx.moveTo(x + 0.5, 0)
    ctx.lineTo(x + 0.5, height)
    ctx.stroke()
  }
  for (let y = 0; y <= height; y += major) {
    ctx.beginPath()
    ctx.moveTo(0, y + 0.5)
    ctx.lineTo(width, y + 0.5)
    ctx.stroke()
  }
  ctx.restore()
}

function drawGraph() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  const { width, height, dpr } = canvasSize.value
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, width, height)

  const background = ctx.createLinearGradient(0, 0, 0, height)
  background.addColorStop(0, resolveThemeColor('#f8fbff', 'surface'))
  background.addColorStop(1, resolveThemeColor('#f1f7fd', 'surface'))
  ctx.fillStyle = background
  ctx.fillRect(0, 0, width, height)
  drawBlueprintGrid(ctx, width, height)

  ctx.save()
  ctx.translate(viewport.value.x, viewport.value.y)
  ctx.scale(viewport.value.scale, viewport.value.scale)

  layoutState.value.sections.forEach((section, index) => {
    const laneTint = getLaneTint(section.businessLine)
    ctx.save()
    const sectionBackground = ctx.createLinearGradient(section.x, section.y, section.x, section.y + section.height)
    sectionBackground.addColorStop(0, resolveThemeColor(index % 2 === 0 ? 'rgba(255, 255, 255, 0.9)' : 'rgba(248, 250, 252, 0.92)', 'surface'))
    sectionBackground.addColorStop(1, resolveThemeColor(laneTint.fill, 'surface'))
    ctx.fillStyle = sectionBackground
    ctx.strokeStyle = resolveThemeColor(laneTint.border, 'border')
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.roundRect(section.x, section.y, section.width, section.height, 18)
    ctx.fill()
    ctx.stroke()

    ctx.strokeStyle = resolveThemeColor('rgba(255, 255, 255, 0.28)', 'surface')
    ctx.lineWidth = 0.8
    for (let x = section.x + 18; x < section.x + section.width - 18; x += 28) {
      ctx.beginPath()
      ctx.moveTo(x, section.y + 10)
      ctx.lineTo(x, section.y + section.height - 10)
      ctx.stroke()
    }
    for (let y = section.y + 16; y < section.y + section.height - 12; y += 28) {
      ctx.beginPath()
      ctx.moveTo(section.x + 10, y)
      ctx.lineTo(section.x + section.width - 10, y)
      ctx.stroke()
    }
    ctx.restore()
  })

  layoutState.value.sections.forEach(section => {
    const businessFontSize = Math.max(28, Math.min(42, Math.floor(section.width / 5.8)))
    const envFontSize = Math.max(18, Math.min(24, Math.floor(section.width / 10)))
    const centerX = section.x + section.width / 2
    const centerY = section.y + section.height / 2

    ctx.save()
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = 'rgba(148, 163, 184, 0.10)'
    ctx.font = `700 ${businessFontSize}px sans-serif`
    ctx.fillText(section.businessLine, centerX, centerY + 6)

    ctx.fillStyle = 'rgba(148, 163, 184, 0.12)'
    ctx.font = `600 ${envFontSize}px sans-serif`
    ctx.fillText(envLabel(section.env), centerX, centerY - businessFontSize * 0.7)
    ctx.restore()
  })

  const { nodeMap } = graphLookup.value
  props.edges.forEach(edge => {
    const source = nodeMap.get(edge.source)
    const target = nodeMap.get(edge.target)
    if (!source || !target) return

    const emphasized = isEdgeEmphasized(edge)
    const color = resolveThemeColor(EDGE_COLORS[edge.type] || EDGE_COLORS.connects_to)
    ctx.save()
    ctx.strokeStyle = color
    ctx.globalAlpha = emphasized ? 0.88 : 0.18
    ctx.lineWidth = props.selectedEdgeId === edge.id ? 3 : 1.7
    if (edge.type === 'connects_to') ctx.setLineDash([6, 6])
    if (edge.type === 'runs_on') ctx.setLineDash([10, 4])
    ctx.beginPath()
    ctx.moveTo(source.x, source.y)
    ctx.lineTo(target.x, target.y)
    ctx.stroke()
    ctx.setLineDash([])
    drawArrow(ctx, source, target, color)

    const middleX = (source.x + target.x) / 2
    const middleY = (source.y + target.y) / 2
    ctx.fillStyle = resolveThemeColor('rgba(255, 255, 255, 0.96)', 'surface')
    ctx.beginPath()
    ctx.roundRect(middleX - 24, middleY - 12, 48, 18, 7)
    ctx.fill()
    ctx.strokeStyle = resolveThemeColor('rgba(148, 163, 184, 0.26)', 'border')
    ctx.stroke()
    ctx.fillStyle = resolveThemeColor(emphasized ? '#0f172a' : '#64748b')
    ctx.font = '11px sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(edge.label, middleX, middleY + 0.5)
    ctx.restore()
  })

  layoutState.value.nodes.forEach(node => {
    const emphasized = isNodeEmphasized(node)
    const matched = matchedNodeIdSet.value.size === 0 || matchedNodeIdSet.value.has(node.id)
    const alpha = emphasized ? 1 : 0.18

    ctx.save()
    ctx.globalAlpha = matched ? alpha : alpha * 0.72
    const glow = ctx.createRadialGradient(node.x, node.y, node.r * 0.45, node.x, node.y, node.r * 1.8)
    glow.addColorStop(0, `${node.color}3d`)
    glow.addColorStop(1, 'transparent')
    ctx.fillStyle = glow
    ctx.beginPath()
    ctx.arc(node.x, node.y, node.r * 1.8, 0, Math.PI * 2)
    ctx.fill()

    ctx.fillStyle = node.color
    ctx.beginPath()
    ctx.arc(node.x, node.y, node.r, 0, Math.PI * 2)
    ctx.fill()

    ctx.strokeStyle = resolveThemeColor(props.selectedNodeId === node.id ? '#0f172a' : '#ffffff')
    ctx.lineWidth = props.selectedNodeId === node.id ? 3 : 2
    ctx.stroke()

    if (node.status === 'active') {
      ctx.beginPath()
      ctx.arc(node.x + node.r * 0.62, node.y - node.r * 0.62, 5, 0, Math.PI * 2)
      ctx.fillStyle = '#22c55e'
      ctx.fill()
      ctx.strokeStyle = '#ffffff'
      ctx.lineWidth = 1.5
      ctx.stroke()
    }

    ctx.font = '600 12px sans-serif'
    const labelWidth = Math.max(76, ctx.measureText(node.name).width + 18)
    ctx.fillStyle = resolveThemeColor('rgba(255, 255, 255, 0.98)', 'surface')
    ctx.beginPath()
    ctx.roundRect(node.x - labelWidth / 2, node.y + node.r + 10, labelWidth, 24, 10)
    ctx.fill()
    ctx.strokeStyle = resolveThemeColor('rgba(148, 163, 184, 0.24)', 'border')
    ctx.lineWidth = 1
    ctx.stroke()

    ctx.fillStyle = resolveThemeColor('#0f172a')
    ctx.textAlign = 'center'
    ctx.fillText(node.name, node.x, node.y + node.r + 26)
    ctx.restore()
  })


  layoutState.value.laneLabels.forEach(label => {
    ctx.save()

    if (label.type === 'business') {
      ctx.fillStyle = resolveThemeColor('rgba(255, 255, 255, 0.98)', 'surface')
      ctx.beginPath()
      ctx.roundRect(label.x, label.y, label.width, label.height, 14)
      ctx.fill()
      ctx.strokeStyle = resolveThemeColor('rgba(59, 130, 246, 0.28)', 'border')
      ctx.stroke()
      ctx.fillStyle = resolveThemeColor('#0f172a')
      ctx.font = '600 15px sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText(label.text, label.x + label.width / 2, label.y + 22)
      ctx.restore()
      return
    }

    if (label.type === 'environment') {
      const badgeWidth = Math.max(42, ctx.measureText(label.text).width + 12)
      ctx.fillStyle = resolveThemeColor('rgba(255, 255, 255, 0.9)', 'surface')
      ctx.beginPath()
      ctx.roundRect(label.x - 6, label.y - 12, badgeWidth, 18, 8)
      ctx.fill()
      ctx.fillStyle = resolveThemeColor('#475569')
      ctx.font = '600 12px sans-serif'
      ctx.textAlign = 'left'
      ctx.fillText(label.text, label.x, label.y)
      ctx.restore()
      return
    }

    const groupWidth = Math.max(40, ctx.measureText(label.text).width + 12)
    ctx.fillStyle = resolveThemeColor('rgba(248, 250, 252, 0.92)', 'surface')
    ctx.beginPath()
    ctx.roundRect(label.x - 6, label.y - 10, groupWidth, 16, 8)
    ctx.fill()
    ctx.fillStyle = resolveThemeColor('#64748b')
    ctx.font = '11px sans-serif'
    ctx.textAlign = 'left'
    ctx.fillText(label.text, label.x, label.y)
    ctx.restore()
  })

  ctx.restore()
}

function updateHover(event) {
  const localPoint = clientToLocalPoint(event)
  const worldPoint = localToWorld(localPoint)
  const node = getNodeAt(worldPoint)
  hoveredNode.value = node
  if (node) {
    tooltipPos.value = {
      x: Math.min(localPoint.x + 16, canvasSize.value.width - 220),
      y: Math.max(localPoint.y - 10, 16),
    }
  }

  const edge = node ? null : getEdgeAt(worldPoint)
  if (canvasRef.value) {
    canvasRef.value.style.cursor = dragState.value.active ? 'grabbing' : (node || edge ? 'pointer' : 'grab')
  }
}

function handleMouseDown(event) {
  if (event.button !== 0) return
  const localPoint = clientToLocalPoint(event)
  dragState.value = {
    active: true,
    moved: false,
    start: localPoint,
    viewport: { ...viewport.value },
  }
}

function handleMouseMove(event) {
  if (dragState.value.active && dragState.value.start) {
    const localPoint = clientToLocalPoint(event)
    const deltaX = localPoint.x - dragState.value.start.x
    const deltaY = localPoint.y - dragState.value.start.y
    if (Math.abs(deltaX) > 2 || Math.abs(deltaY) > 2) {
      dragState.value.moved = true
      viewport.value = {
        ...viewport.value,
        x: dragState.value.viewport.x + deltaX,
        y: dragState.value.viewport.y + deltaY,
      }
      scheduleDraw()
    }
  }
  updateHover(event)
}

function handleMouseUp(event) {
  if (!dragState.value.active) return
  if (!dragState.value.moved) {
    const localPoint = clientToLocalPoint(event)
    const worldPoint = localToWorld(localPoint)
    const node = getNodeAt(worldPoint)
    const edge = node ? null : getEdgeAt(worldPoint)
    if (node) emit('select-node', node.id)
    else if (edge) emit('select-edge', edge.id)
    else emit('clear-selection')
  }
  dragState.value = { active: false, moved: false, start: null, viewport: null }
}

function handleMouseLeave() {
  hoveredNode.value = null
  dragState.value = { active: false, moved: false, start: null, viewport: null }
  if (canvasRef.value) canvasRef.value.style.cursor = 'grab'
}

function handleWheel(event) {
  const localPoint = clientToLocalPoint(event)
  const worldPoint = localToWorld(localPoint)
  const factor = event.deltaY < 0 ? 1.08 : 0.92
  const nextScale = Math.min(1.8, Math.max(0.45, viewport.value.scale * factor))

  viewport.value = {
    scale: nextScale,
    x: localPoint.x - worldPoint.x * nextScale,
    y: localPoint.y - worldPoint.y * nextScale,
  }
  scheduleDraw()
  updateHover(event)
}

function handleDoubleClick(event) {
  if (!props.editable) return
  const localPoint = clientToLocalPoint(event)
  const worldPoint = localToWorld(localPoint)
  const node = getNodeAt(worldPoint)
  if (node) emit('edit-node', node.id)
}

watch(
  () => [props.nodes, props.resourceTree],
  () => rebuildGraph({ fit: true }),
  { deep: true, immediate: true },
)

watch(
  () => [props.edges, props.selectedNodeId, props.selectedEdgeId, props.matchedNodeIds],
  () => scheduleDraw(),
  { deep: true },
)

watch(
  () => props.resetToken,
  () => fitView(),
)

watch(theme, scheduleDraw)

onMounted(() => {
  resizeObserver = new ResizeObserver(() => {
    rebuildGraph({ fit: true })
  })
  if (containerRef.value) resizeObserver.observe(containerRef.value)
  rebuildGraph({ fit: true })
})

onBeforeUnmount(() => {
  if (resizeObserver && containerRef.value) resizeObserver.unobserve(containerRef.value)
  resizeObserver = null
  if (frameHandle) cancelAnimationFrame(frameHandle)
})

defineExpose({ fitView })
</script>

<style scoped>
.topology-stage {
  position: relative;
  min-height: 620px;
  height: 100%;
  border-radius: 20px;
  overflow: hidden;
  background:
    radial-gradient(circle at top left, rgba(59, 130, 246, 0.08), transparent 28%),
    radial-gradient(circle at bottom right, rgba(16, 185, 129, 0.08), transparent 30%),
    linear-gradient(180deg, #f8fbff 0%, #f1f7fd 100%);
}

.topology-canvas {
  display: block;
  width: 100%;
  height: 100%;
}

.topology-tooltip {
  position: absolute;
  z-index: 6;
  min-width: 190px;
  max-width: 240px;
  padding: 10px 12px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.98);
  color: #0f172a;
  pointer-events: none;
  box-shadow: 0 18px 30px rgba(15, 23, 42, 0.12);
}

.tooltip-title {
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 700;
}

.tooltip-row {
  color: #475569;
  font-size: 12px;
  line-height: 1.5;
}

.topology-fit-btn {
  position: absolute;
  top: 14px;
  left: 14px;
  z-index: 5;
  padding: 8px 12px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.94);
  color: #0f172a;
  cursor: pointer;
}

.topology-legend {
  position: absolute;
  top: 14px;
  right: 14px;
  z-index: 5;
  min-width: 132px;
  padding: 12px 14px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.96);
  color: #334155;
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
}

.legend-title,
.minimap-title {
  margin-bottom: 8px;
  color: #0f172a;
  font-size: 12px;
  font-weight: 700;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 12px;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.legend-line {
  display: inline-block;
  width: 22px;
  border-top: 2px solid #94a3b8;
}

.legend-runs {
  border-top-style: solid;
  box-shadow: inset 0 0 0 999px rgba(14, 165, 233, 0.22);
}

.legend-solid {
  border-color: #8b5cf6;
}

.legend-dashed {
  border-style: dashed;
}

.legend-divider {
  height: 1px;
  margin: 10px 0;
  background: rgba(148, 163, 184, 0.2);
}

.topology-minimap {
  position: absolute;
  right: 14px;
  bottom: 14px;
  z-index: 5;
  padding: 10px 12px 12px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
}

.minimap-body {
  position: relative;
  width: 166px;
  height: 108px;
  border-radius: 10px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  border: 1px solid rgba(148, 163, 184, 0.16);
  overflow: hidden;
}

.minimap-node {
  position: absolute;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  transform: translate(-50%, -50%);
}

.minimap-viewport {
  position: absolute;
  border: 1px solid rgba(15, 23, 42, 0.65);
  border-radius: 8px;
  background: rgba(59, 130, 246, 0.08);
}
</style>






