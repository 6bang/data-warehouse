<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { isDemoAssetUrl } from '@/demo/catalog'

const props = withDefaults(defineProps<{
  src?: string | null
  alt?: string
  size?: number | string
}>(), { size: 48, alt: '商品图片' })

const failed = ref(false)
const renderKey = ref(0)
const validSrc = computed(() => {
  const value = String(props.src || '').trim()
  if (!value) return ''
  if (isDemoAssetUrl(value)) return value
  try {
    const url = new URL(value)
    return /^https?:$/.test(url.protocol) ? value : ''
  } catch { return '' }
})
watch(validSrc, () => { failed.value = false; renderKey.value += 1 })
const boxSize = computed(() => typeof props.size === 'number' ? `${props.size}px` : props.size)
</script>

<template>
  <span class="product-image" :style="{ width: boxSize, height: boxSize }" :aria-label="alt">
    <el-image
      v-if="validSrc && !failed"
      :key="renderKey"
      :src="validSrc"
      :alt="alt"
      fit="contain"
      lazy
      loading="lazy"
      preview-teleported
      :preview-src-list="[validSrc]"
      crossorigin="anonymous"
      referrerpolicy="no-referrer"
      @error="failed = true"
    >
      <template #placeholder><span class="product-image-placeholder">⌛</span></template>
      <template #error><span class="product-image-placeholder">暂无图</span></template>
    </el-image>
    <span v-else class="product-image-placeholder">暂无图</span>
  </span>
</template>

<style scoped>
.product-image{display:inline-flex;flex:0 0 auto;align-items:center;justify-content:center;overflow:hidden;border-radius:7px;background:var(--app-hover,#f2f3f5);border:1px solid var(--app-border,#e5e7eb);color:var(--app-text-muted,#9299a6);font-size:10px;line-height:1;text-align:center}.product-image :deep(.el-image),.product-image :deep(.el-image__inner){display:block;width:100%;height:100%}.product-image-placeholder{display:inline-flex;width:100%;height:100%;align-items:center;justify-content:center;color:inherit;background:color-mix(in srgb,var(--app-hover,#f2f3f5) 78%,transparent)}
</style>
