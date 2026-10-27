<script setup lang="ts">
import type { UploadFile } from 'element-plus'
import { ElMessage } from 'element-plus'
import { computed, reactive, ref, watch } from 'vue'
import http from '@/api/http'

interface MCPSource { id: number; name: string; organization_name: string; connection_status: string; last_synced_at: string | null; last_error: string }
interface MCPStore { store_id: string; store_name: string; platform_type: string; platform_name: string }

const props = withDefaults(defineProps<{ modelValue: boolean; initialTab?: 'file' | 'feishu' | 'mcp' }>(), { initialTab: 'file' })
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; imported: [] }>()
const active = ref('file')
const loading = ref(false)
const selectedFile = ref<File>()
const form = reactive({ data_type: 'product', shop: '演示旗舰店', url: '', run_detection: true })
const mcpSources = ref<MCPSource[]>([])
const mcpStores = ref<MCPStore[]>([])
const mcp = reactive<{ source_id?: number; organization_name: string; month: string; store_ids: string[] }>({
  source_id: undefined, organization_name: '', month: new Date().toISOString().slice(0, 7), store_ids: [],
})
const selectedSource = computed(() => mcpSources.value.find(item => item.id === mcp.source_id))

watch(() => props.modelValue, async (visible) => {
  if (!visible) return
  active.value = props.initialTab
  if (props.initialTab === 'feishu' && !form.url) {
    try {
      const { data } = await http.get('/configuration/summary/')
      form.url = data.feishu?.default_base_url || ''
    } catch { /* 非管理员或未配置时保持为空 */ }
  }
  if (props.initialTab === 'mcp') await loadMcpSources()
})

function onFileChange(uploadFile: UploadFile) { selectedFile.value = uploadFile.raw }

async function loadMcpSources() {
  try {
    const { data } = await http.get('/data-sync/mcp/')
    mcpSources.value = data.sources || []
    if (!mcpSources.value.length) return
    if (!mcpSources.value.some(item => item.id === mcp.source_id)) mcp.source_id = mcpSources.value[0].id
    mcp.organization_name = selectedSource.value?.organization_name || ''
    await loadMcpStores()
  } catch (error: any) { ElMessage.error(error.response?.data?.detail || '读取经营数据源失败') }
}

async function loadMcpStores() {
  if (!mcp.source_id) return
  mcpStores.value = []
  mcp.store_ids = []
  try {
    const { data } = await http.post('/data-sync/mcp/', { action: 'stores', source_id: mcp.source_id })
    mcpStores.value = data.stores || []
    mcp.store_ids = mcpStores.value.map(item => item.store_id)
    mcp.organization_name = selectedSource.value?.organization_name || mcp.organization_name
  } catch (error: any) { ElMessage.error(error.response?.data?.detail || '读取授权店铺失败') }
}

async function submit() {
  loading.value = true
  try {
    if (active.value === 'file') {
      if (!selectedFile.value) throw new Error('请选择 Excel 或 CSV 文件')
      const payload = new FormData()
      payload.append('file', selectedFile.value)
      payload.append('data_type', form.data_type)
      payload.append('shop', form.shop)
      payload.append('run_detection', String(form.run_detection))
      await http.post('/imports/file/', payload)
    } else if (active.value === 'feishu') {
      if (!form.url) throw new Error('请输入飞书 Base 链接')
      await http.post('/imports/feishu/', form)
    } else {
      if (!mcp.source_id) throw new Error('尚未配置经营数据服务')
      if (!mcp.organization_name.trim()) throw new Error('请填写数据归属企业')
      if (!mcp.month) throw new Error('请选择同步月份')
      const { data } = await http.post('/data-sync/mcp/', {
        action: 'sync', source_id: mcp.source_id, organization_name: mcp.organization_name,
        month: mcp.month, store_ids: mcp.store_ids,
      })
      ElMessage.success(`${data.message}：${data.summary.products} 个商品、${data.summary.shops} 个店铺`)
      emit('update:modelValue', false)
      emit('imported')
      return
    }
    ElMessage.success('导入完成，经营指标与异常已更新')
    emit('update:modelValue', false)
    emit('imported')
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || error.message || '导入失败')
  } finally { loading.value = false }
}
</script>

<template>
  <el-dialog :model-value="props.modelValue" :title="active==='file'?'导入经营数据':'同步经营数据'" width="min(720px, 92vw)" @close="emit('update:modelValue', false)">
    <el-tabs v-model="active">
      <el-tab-pane label="Excel / CSV" name="file">
        <el-upload drag :auto-upload="false" :limit="1" accept=".xlsx,.xls,.csv" :on-change="onFileChange">
          <div>拖拽或点击选择 Excel / CSV</div><template #tip><div class="el-upload__tip">支持中文字段自动映射，重复数据会幂等更新</div></template>
        </el-upload>
      </el-tab-pane>
      <el-tab-pane label="飞书多维表格" name="feishu">
        <el-form-item label="Base 链接"><el-input v-model="form.url" placeholder="粘贴包含 table 参数的飞书 Base 链接" /></el-form-item>
      </el-tab-pane>
      <el-tab-pane label="经营数据一键同步" name="mcp">
        <el-alert v-if="!mcpSources.length" type="warning" :closable="false" title="尚未配置经营数据服务，请由管理员先在“配置中心 → MCP 服务”完成连接。" />
        <el-form v-else label-position="top" class="mcp-sync-form">
          <div class="mcp-grid">
            <el-form-item label="数据源"><el-select v-model="mcp.source_id" class="full-width" @change="loadMcpStores"><el-option v-for="item in mcpSources" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item>
            <el-form-item label="同步月份"><el-date-picker v-model="mcp.month" type="month" value-format="YYYY-MM" class="full-width" /></el-form-item>
          </div>
          <el-form-item label="数据归属企业"><el-input v-model="mcp.organization_name" /></el-form-item>
          <el-form-item label="授权店铺">
            <el-select v-model="mcp.store_ids" multiple collapse-tags collapse-tags-tooltip class="full-width" placeholder="选择店铺；不选表示全部授权店铺">
              <el-option v-for="item in mcpStores" :key="item.store_id" :label="`${item.store_name}（${item.platform_name}）`" :value="item.store_id" />
            </el-select>
          </el-form-item>
          <el-alert type="info" :closable="false" title="将通过只读 MCP 分页拉取商品月度数据，并原子更新同企业、同月份、同店铺的数据快照。" />
        </el-form>
      </el-tab-pane>
    </el-tabs>
    <el-form v-if="active!=='mcp'" label-position="top">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <el-form-item label="数据类型"><el-select v-model="form.data_type" class="full-width"><el-option label="商品经营数据" value="product" /><el-option label="付费推广数据" value="paid" /><el-option label="店铺每日汇总" value="shop" /></el-select></el-form-item>
        <el-form-item label="默认店铺"><el-input v-model="form.shop" /></el-form-item>
      </div>
      <el-checkbox v-model="form.run_detection">导入完成后自动检测异常</el-checkbox>
    </el-form>
    <template #footer><el-button @click="emit('update:modelValue', false)">取消</el-button><el-button type="primary" :loading="loading" :disabled="active==='mcp'&&!mcpSources.length" @click="submit">{{ active==='file'?'开始导入':'开始同步' }}</el-button></template>
  </el-dialog>
</template>

<style scoped>
.mcp-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.mcp-sync-form{padding-top:4px}@media(max-width:640px){.mcp-grid{grid-template-columns:1fr}}
</style>
