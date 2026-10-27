<script setup lang="ts">
import * as echarts from 'echarts/core'
import type { ECharts, EChartsCoreOption } from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{ option: EChartsCoreOption; height?: string }>()
const element = ref<HTMLDivElement>()
echarts.use([BarChart, LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])
let chart: ECharts | undefined
let observer: ResizeObserver | undefined

onMounted(() => {
  if (!element.value) return
  chart = echarts.init(element.value)
  chart.setOption(props.option)
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(element.value)
})

watch(() => props.option, (option) => chart?.setOption(option, true), { deep: true })
onBeforeUnmount(() => { observer?.disconnect(); chart?.dispose() })
</script>

<template><div ref="element" :style="{ height: height || '300px', width: '100%' }" /></template>
