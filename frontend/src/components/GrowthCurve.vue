<script setup lang="ts">
/**
 * @file: src/components/GrowthCurve.vue
 * @description: 生长曲线 SVG 折线图组件：实测点连线 + WHO P3/P50/P97 参考线（自绘，无图表库）。
 */
import { computed } from 'vue'
import type { CurvePoint, GrowthCurve, WhoReferencePoint } from '@/types/api'

/** 组件属性定义 */
const props = defineProps<{
  /** 生长曲线数据（含 WHO 参考线，可能为 null） */
  curve: GrowthCurve | null
  /** 绘制维度：height 身长 / weight 体重 */
  metric: 'height' | 'weight'
}>()

/** SVG viewBox 尺寸 */
const VB_W = 640
const VB_H = 320
/** 内边距 */
const PAD = { left: 44, right: 14, top: 14, bottom: 30 }

/** 单位文案 */
const unit = computed(() => (props.metric === 'height' ? 'cm' : 'kg'))

/**
 * 取单点在当前维度的测量值。
 *
 * @param p: 曲线数据点
 * @returns 测量值，未填写为 null
 */
function measureOf(p: CurvePoint): number | null {
  return props.metric === 'height' ? p.height_cm : p.weight_kg
}

/** 当前维度的 WHO 参考线点集 */
const whoPoints = computed<WhoReferencePoint[]>(() => {
  if (!props.curve?.who_reference) return []
  return props.metric === 'height'
    ? props.curve.who_reference.height
    : props.curve.who_reference.weight
})

/** 当前维度的实测点（过滤未填写该维度的记录） */
const measured = computed<CurvePoint[]>(() => {
  if (!props.curve) return []
  const series =
    props.metric === 'height'
      ? props.curve.height_series
      : props.metric === 'weight'
        ? props.curve.weight_series
        : props.curve.head_circumference_series
  return series.filter((p) => measureOf(p) !== null)
})

/** X 轴最大月龄（WHO 范围 0-24，实测点超出时扩展） */
const maxMonth = computed(() => {
  let m = 24
  for (const p of measured.value) m = Math.max(m, Math.ceil(p.age_months))
  for (const w of whoPoints.value) m = Math.max(m, w.month)
  return m
})

/** Y 轴值域（min/max），综合实测点与 WHO P3/P97 */
const yRange = computed<{ min: number; max: number }>(() => {
  const values: number[] = []
  for (const p of measured.value) {
    const v = measureOf(p)
    if (v !== null) values.push(v)
  }
  for (const w of whoPoints.value) values.push(w.p3, w.p97)
  if (values.length === 0) return { min: 0, max: 1 }
  let min = Math.min(...values)
  let max = Math.max(...values)
  // 上下各留 10% 余量
  const span = Math.max(max - min, 1)
  min = Math.max(0, min - span * 0.1)
  max = max + span * 0.1
  return { min, max }
})

/**
 * 月龄映射为 SVG X 坐标。
 *
 * @param month: 月龄
 * @returns X 坐标
 */
function xOf(month: number): number {
  const innerW = VB_W - PAD.left - PAD.right
  return PAD.left + (month / maxMonth.value) * innerW
}

/**
 * 测量值映射为 SVG Y 坐标。
 *
 * @param value: 测量值
 * @returns Y 坐标
 */
function yOf(value: number): number {
  const innerH = VB_H - PAD.top - PAD.bottom
  const { min, max } = yRange.value
  return PAD.top + (1 - (value - min) / (max - min)) * innerH
}

/**
 * 将点集转为 SVG polyline 的 points 字符串。
 *
 * @param pts: 坐标点数组
 * @returns points 属性字符串
 */
function toPointsAttr(pts: Array<[number, number]>): string {
  return pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
}

/** WHO P3/P50/P97 折线坐标集 */
const whoLines = computed(() => {
  const keys = ['p3', 'p50', 'p97'] as const
  return keys.map((key) => ({
    key,
    label: key.toUpperCase(),
    points: toPointsAttr(whoPoints.value.map((w) => [xOf(w.month), yOf(w[key])] as [number, number]))
  }))
})

/** 实测值折线坐标集 */
const measuredLine = computed(() =>
  toPointsAttr(measured.value.map((p) => [xOf(p.age_months), yOf(measureOf(p) as number)] as [number, number]))
)

/** 实测点圆点坐标集 */
const measuredDots = computed(() =>
  measured.value.map((p) => ({
    x: xOf(p.age_months),
    y: yOf(measureOf(p) as number),
    value: measureOf(p) as number,
    month: p.age_months,
    date: p.record_date
  }))
)

/** X 轴刻度（每 3 个月） */
const xTicks = computed(() => {
  const step = maxMonth.value <= 12 ? 2 : 4
  const ticks: number[] = []
  for (let m = 0; m <= maxMonth.value; m += step) ticks.push(m)
  return ticks
})

/** Y 轴刻度（5 等分） */
const yTicks = computed(() => {
  const { min, max } = yRange.value
  const ticks: number[] = []
  for (let i = 0; i <= 4; i++) {
    ticks.push(min + ((max - min) * i) / 4)
  }
  return ticks
})
</script>

<template>
  <div class="curve-wrap">
    <svg
      class="curve-svg"
      :viewBox="`0 0 ${VB_W} ${VB_H}`"
      role="img"
      :aria-label="`${metric === 'height' ? '身长' : '体重'}生长曲线`"
    >
      <!-- Y 轴网格与刻度 -->
      <g v-for="(t, i) in yTicks" :key="`y${i}`">
        <line :x1="PAD.left" :x2="VB_W - PAD.right" :y1="yOf(t)" :y2="yOf(t)" class="grid-line" />
        <text :x="PAD.left - 6" :y="yOf(t) + 4" class="tick-text" text-anchor="end">
          {{ t.toFixed(1) }}
        </text>
      </g>
      <!-- X 轴刻度 -->
      <g v-for="m in xTicks" :key="`x${m}`">
        <text :x="xOf(m)" :y="VB_H - 10" class="tick-text" text-anchor="middle">{{ m }}</text>
      </g>
      <text :x="VB_W - PAD.right" :y="VB_H - 10" class="tick-text axis-unit" text-anchor="end">
        月龄
      </text>
      <text :x="8" :y="PAD.top + 2" class="tick-text axis-unit">({{ unit }})</text>

      <!-- WHO 参考线：P3 / P50 / P97 -->
      <polyline
        v-for="line in whoLines"
        :key="line.key"
        :points="line.points"
        class="who-line"
        :class="`who-${line.key}`"
      />

      <!-- 实测值折线与数据点 -->
      <polyline v-if="measured.length > 1" :points="measuredLine" class="measured-line" />
      <circle
        v-for="(dot, i) in measuredDots"
        :key="`d${i}`"
        :cx="dot.x"
        :cy="dot.y"
        r="4"
        class="measured-dot"
      >
        <title>{{ dot.date }} · {{ dot.month }}月龄 · {{ dot.value }}{{ unit }}</title>
      </circle>
    </svg>

    <!-- 图例 -->
    <div class="legend">
      <span class="legend-item"><i class="swatch measured"></i>实测值</span>
      <span class="legend-item"><i class="swatch p3"></i>WHO P3</span>
      <span class="legend-item"><i class="swatch p50"></i>WHO P50</span>
      <span class="legend-item"><i class="swatch p97"></i>WHO P97</span>
    </div>
    <p v-if="!curve?.who_reference" class="who-tip">WHO 参考线仅覆盖 0-24 月龄宝宝</p>
  </div>
</template>

<style scoped>
.curve-wrap {
  width: 100%;
}

.curve-svg {
  width: 100%;
  height: auto;
  display: block;
}

.grid-line {
  stroke: var(--color-border);
  stroke-width: 1;
  stroke-dasharray: 3 4;
}

.tick-text {
  fill: var(--color-text-muted);
  font-size: 11px;
}

.axis-unit {
  font-style: normal;
}

.who-line {
  fill: none;
  stroke-width: 1.5;
  stroke-dasharray: 5 4;
  opacity: 0.85;
}

.who-p3 {
  stroke: var(--color-info);
}

.who-p50 {
  stroke: var(--color-tertiary);
}

.who-p97 {
  stroke: var(--color-purple);
}

.measured-line {
  fill: none;
  stroke: var(--color-primary-strong);
  stroke-width: 2.5;
  stroke-linejoin: round;
  stroke-linecap: round;
}

.measured-dot {
  fill: var(--color-primary);
  stroke: var(--color-on-primary);
  stroke-width: 1;
}

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-md);
  margin-top: var(--space-sm);
  font-size: 12px;
  color: var(--color-text-secondary);
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.swatch {
  display: inline-block;
  width: 14px;
  height: 3px;
  border-radius: 2px;
}

.swatch.measured {
  background: var(--color-primary-strong);
  height: 4px;
}

.swatch.p3 {
  background: var(--color-info);
}

.swatch.p50 {
  background: var(--color-tertiary);
}

.swatch.p97 {
  background: var(--color-purple);
}

.who-tip {
  margin: var(--space-xs) 0 0;
  font-size: 12px;
  color: var(--color-text-muted);
}
</style>
