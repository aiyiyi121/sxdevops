import * as echarts from 'echarts/core'
import { BarChart, GraphChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { LabelLayout, UniversalTransition } from 'echarts/features'
import { CanvasRenderer } from 'echarts/renderers'
import { colorScheme, resolveThemeColor, THEME_CHANGE_EVENT, theme } from '@/theme'
import { parseColor, themePalette } from '@/theme/palette'

echarts.use([
  BarChart,
  GraphChart,
  LineChart,
  PieChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  LabelLayout,
  UniversalTransition,
  CanvasRenderer,
])

const themedCharts = new Map()

function mapChartColors(value, path = '', fillRole = 'surface') {
  if (Array.isArray(value)) return value.map(item => mapChartColors(item, path, fillRole))
  if (!value || typeof value !== 'object' || Object.getPrototypeOf(value) !== Object.prototype) {
    if (typeof value !== 'string' || !/(color|\.fill|\.stroke)$/i.test(path)) return value
    const role = /backgroundColor/i.test(path) ? 'surface'
      : /borderColor|\.stroke$|(?:splitLine|axisLine)\.lineStyle\.color/i.test(path) ? 'border'
      : /shadowColor/i.test(path) ? 'shadow'
      : /\.fill$/i.test(path) ? fillRole : 'text'
    const decorativeText = role === 'text' && /\.fill$/i.test(path) && parseColor(value)?.alpha < 0.3
    return resolveThemeColor(value, decorativeText ? 'surface' : role)
  }
  const childFillRole = value.type === 'text' ? 'text' : fillRole
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, mapChartColors(item, `${path}.${key}`, childFillRole)]))
}

function chartOption(option) {
  if (colorScheme.value === 'light') return echarts.util.clone(option)
  const palette = themePalette(theme.value)
  const foreground = palette.secondary
  const border = palette.fillDarker
  const mapped = mapChartColors(option)
  const result = {
    backgroundColor: 'transparent',
    textStyle: { color: foreground },
    ...mapped,
  }
  if (mapped.tooltip) {
    result.tooltip = {
      backgroundColor: palette.overlay,
      borderColor: palette.border,
      ...mapped.tooltip,
      textStyle: { color: palette.primary, ...mapped.tooltip.textStyle },
    }
  }
  if (mapped.legend) result.legend = { ...mapped.legend, textStyle: { color: foreground, ...mapped.legend.textStyle } }
  for (const axisName of ['xAxis', 'yAxis']) {
    if (!mapped[axisName]) continue
    const axisOption = axis => ({
      ...axis,
      axisLabel: { color: foreground, ...axis.axisLabel },
      axisLine: { ...axis.axisLine, lineStyle: { color: border, ...axis.axisLine?.lineStyle } },
      splitLine: { ...axis.splitLine, lineStyle: { color: border, ...axis.splitLine?.lineStyle } },
    })
    result[axisName] = Array.isArray(mapped[axisName]) ? mapped[axisName].map(axisOption) : axisOption(mapped[axisName])
  }
  return result
}

function init(element, chartTheme, options) {
  const chart = echarts.init(element, chartTheme, options)
  if (themedCharts.has(chart)) return chart
  const setOption = chart.setOption.bind(chart)
  const clear = chart.clear.bind(chart)
  const dispose = chart.dispose.bind(chart)
  const record = { raw: {}, render: setOption }
  themedCharts.set(chart, record)
  chart.setOption = (option, settings, lazyUpdate) => {
    const notMerge = settings === true || settings?.notMerge
    record.raw = notMerge ? echarts.util.clone(option) : echarts.util.merge(record.raw, echarts.util.clone(option), true)
    setOption(chartOption(record.raw), settings, lazyUpdate)
  }
  chart.clear = () => {
    record.raw = {}
    clear()
  }
  chart.dispose = () => {
    themedCharts.delete(chart)
    dispose()
  }
  return chart
}

window.addEventListener(THEME_CHANGE_EVENT, () => {
  for (const [chart, record] of themedCharts) {
    if (chart.isDisposed()) {
      themedCharts.delete(chart)
      continue
    }
    if (!Object.keys(record.raw).length) continue
    const current = chart.getOption()
    const option = chartOption(record.raw)
    if (current.legend && option.legend) {
      const legends = Array.isArray(option.legend) ? option.legend : [option.legend]
      legends.forEach((legend, index) => {
        legend.selected = { ...legend.selected, ...current.legend[index]?.selected }
      })
    }
    record.render(option, { notMerge: true })
  }
})

export default { ...echarts, init }
