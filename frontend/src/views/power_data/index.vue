<template>
  <section class="page" data-module="power_data">
    <header class="page-head">
      <div>
        <h2>发电监测管理</h2>
        <p class="page-desc">按电站编号、上报时段维护发电记录。缺测时段统一标为「缺测」，发电量留空不计零；夜间真实零值仍显示 0。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="showCreate = !showCreate">登记发电记录</button>
        <button class="btn" type="button" @click="exportRows">导出结果文件</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form v-if="showCreate" class="create-form" @submit.prevent="submitCreate">
      <label class="filter-item"><span>记录编号 *</span><input v-model="createForm.记录编号" placeholder="如 POWE-0011" /></label>
      <label class="filter-item"><span>电站编号 *</span><input v-model="createForm.电站编号" placeholder="如 PLAN-0001" /></label>
      <label class="filter-item"><span>记录时间</span><input v-model="createForm.记录时间" type="date" /></label>
      <label class="filter-item"><span>上报时段</span><input v-model="createForm.上报时段" placeholder="如 10:00" /></label>
      <label class="filter-item"><span>发电量（kWh）</span><input v-model="createForm.发电量" type="number" placeholder="未采集请留空" /></label>
      <button class="btn primary" type="submit" :disabled="submitting">{{ submitting ? '提交中…' : '提交' }}</button>
      <button class="btn ghost" type="button" @click="showCreate = false">取消</button>
      <span class="form-hint">发电量留空表示该时段缺测，会带上缺测原因进入列表，不会记成 0；重复提交同一记录编号不会产生重复行。</span>
    </form>

    <h3 class="section-title">按日汇总</h3>
    <table class="data-table summary-table">
      <thead>
        <tr>
          <th>电站编号</th><th>日期</th><th>应报时段</th><th>已采集</th><th>缺测时段</th><th>日发电量(kWh)</th><th>完整性</th><th>缺口原因</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in dailyRows" :key="`${item.电站编号}-${item.日期}`">
          <td>{{ item.电站编号 }}</td>
          <td>{{ item.日期 }}</td>
          <td>{{ item.应报时段数 }}</td>
          <td>{{ item.已采集时段数 }}</td>
          <td :class="{ 'missing-text': item.缺测时段数 > 0 }">{{ item.缺测时段数 }}</td>
          <td>{{ item.日发电量 }}</td>
          <td>
            <span class="tag" :class="item.完整性 === '完整' ? 'tag-collected' : 'tag-missing'">{{ item.完整性 }}</span>
          </td>
          <td class="reason-text">{{ item.缺测原因.length ? item.缺测原因.join('；') : '—' }}</td>
        </tr>
        <tr v-if="!dailyRows.length">
          <td colspan="8" class="empty-state">暂无可汇总的发电记录</td>
        </tr>
      </tbody>
    </table>

    <h3 class="section-title">发电记录明细</h3>
    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>记录编号</span>
        <input v-model="filters.keyword" placeholder="按记录编号检索" />
      </label>
      <label class="filter-item">
        <span>采集状态</span>
        <select v-model="filters.collection">
          <option value="">全部</option>
          <option v-for="s in collectionStatuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>数据状态</span>
        <select v-model="filters.status">
          <option value="">全部</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="String(row.id)"
          :class="{ 'row-missing': row.采集状态 === '缺测', 'row-abnormal': row.abnormal }"
        >
          <template v-for="column in columns" :key="column">
            <td v-if="column === '发电量'">
              <span v-if="row.发电量 === null" class="missing-text">—（缺测）</span>
              <span v-else>{{ row.发电量 }}</span>
            </td>
            <td v-else-if="column === '采集状态'">
              <span class="tag" :class="row.采集状态 === '缺测' ? 'tag-missing' : 'tag-collected'">{{ row.采集状态 }}</span>
            </td>
            <td v-else-if="column === '状态说明'">
              <span v-if="row.采集状态 === '缺测'" class="reason-text">缺口：{{ row.缺测原因 }}</span>
              <span v-else-if="row.abnormal" class="reason-text">{{ row.异常说明 || '异常原因待确认' }}</span>
              <span v-else>—</span>
            </td>
            <td v-else>{{ row[column] ?? '—' }}</td>
          </template>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :disabled="actingId === row.id"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">
            {{ message || '当前筛选条件下没有发电记录，可登记一条记录或调整查询条件' }}
          </td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条发电记录；口径：缺测时段发电量留空、不计零</span>
      <span v-if="message" :class="messageOk ? 'success-text' : 'error-text'">{{ message }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

interface PowerRow {
  id: number
  status: string
  abnormal: boolean
  记录编号: string
  电站编号: string
  记录时间: string
  上报时段: string
  发电量: number | null
  辐照度: number | null
  组件温度: number | null
  环境温度: number | null
  采集状态: '已采集' | '缺测'
  是否缺口: boolean
  缺测原因: string
  异常说明: string
  [key: string]: string | number | boolean | null
}

interface DailySummary {
  电站编号: string
  日期: string
  应报时段数: number
  已采集时段数: number
  缺测时段数: number
  日发电量: number
  完整性: '完整' | '有缺口'
  缺测原因: string[]
}

const ENDPOINT = '/api/power_data'
const columns = ["记录编号", "电站编号", "记录时间", "上报时段", "发电量", "辐照度", "组件温度", "环境温度", "采集状态", "状态说明"]
const actions = ["标记偏低", "确认异常", "数据补录"]
const statuses = ["正常", "偏低", "异常", "补录"]
const collectionStatuses = ["已采集", "缺测"]

const rows = ref<PowerRow[]>([])
const dailyRows = ref<DailySummary[]>([])
const total = ref(0)
const message = ref('')
const messageOk = ref(true)
const filters = ref<{ keyword: string; status: string; collection: string }>({ keyword: '', status: '', collection: '' })
const showCreate = ref(false)
const submitting = ref(false)
const actingId = ref<number | null>(null)
const stats = ref<{ label: string; value: string | number }[]>([
  { label: '最新日发电量(kWh)', value: '—' },
  { label: '缺测时段数', value: '—' },
  { label: '异常记录数', value: '—' },
])
const createForm = ref({ 记录编号: '', 电站编号: '', 记录时间: '', 上报时段: '', 发电量: '' })

function notify(text: string, ok = true) {
  message.value = text
  messageOk.value = ok
}

function dedupe(items: PowerRow[]): PowerRow[] {
  // 接口重试可能回吐重复行，这里按 id 再去一道，避免空白行重复显示。
  const seen = new Set<number>()
  return items.filter((row) => {
    if (seen.has(row.id)) return false
    seen.add(row.id)
    return true
  })
}

function resetFilters() {
  filters.value = { keyword: '', status: '', collection: '' }
  void reload()
}

function exportRows() {
  // 结果文件里缺测时段发电量为空值，由后端按统一口径导出。
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function submitCreate() {
  if (submitting.value) return
  submitting.value = true
  notify('')
  try {
    const values: Record<string, string> = {
      记录编号: createForm.value.记录编号.trim(),
      电站编号: createForm.value.电站编号.trim(),
      记录时间: createForm.value.记录时间,
      上报时段: createForm.value.上报时段.trim(),
    }
    // 发电量留空不参与提交：后端据此标记缺测，绝不是提交 0。
    if (createForm.value.发电量.trim() !== '') values.发电量 = createForm.value.发电量.trim()
    const response = await request(ENDPOINT, { method: 'POST', body: JSON.stringify({ values }) })
    const payload = await response.json()
    notify(payload.message ?? (response.ok ? '发电记录已登记' : '登记失败'), response.ok)
    if (response.ok) {
      createForm.value = { 记录编号: '', 电站编号: '', 记录时间: '', 上报时段: '', 发电量: '' }
      showCreate.value = false
      await Promise.all([reload(), reloadDaily()])
    }
  } catch (error) {
    notify(error instanceof Error ? error.message : '发电记录登记失败', false)
  } finally {
    submitting.value = false
  }
}

async function runAction(action: string, row: PowerRow) {
  const values: Record<string, string> = { action }
  if (action === '数据补录') {
    const input = window.prompt(`为 ${row.记录编号} 补录发电量（kWh），缺测时段必须补真实读数：`)
    if (input === null) return
    if (input.trim() === '') {
      notify('数据补录需要提供发电量数值，缺测时段不能直接置零', false)
      return
    }
    values.发电量 = input.trim()
  }
  if (action === '确认异常') {
    const input = window.prompt(`确认 ${row.记录编号} 为异常，请填写原因（可留空使用默认说明）：`)
    if (input === null) return
    values.异常说明 = input.trim()
  }
  actingId.value = row.id
  notify('')
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json()
    notify(payload.message ?? '发电监测动作未生效', response.ok)
    if (response.ok) await Promise.all([reload(), reloadDaily()])
  } catch (error) {
    notify(error instanceof Error ? error.message : '发电监测操作失败', false)
  } finally {
    actingId.value = null
  }
}

async function reload() {
  message.value = ''
  const params = new URLSearchParams()
  if (filters.value.keyword) params.set('keyword', filters.value.keyword.trim())
  if (filters.value.status) params.set('status', filters.value.status)
  if (filters.value.collection) params.set('collection', filters.value.collection)
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) throw new Error('发电记录列表读取失败')
    const payload = await response.json()
    rows.value = dedupe(payload.items ?? [])
    total.value = payload.total ?? rows.value.length
    await reloadCounts()
  } catch (error) {
    notify(error instanceof Error ? error.message : '发电监测列表读取失败', false)
  }
}

async function reloadDaily() {
  try {
    const response = await request(`${ENDPOINT}/daily`)
    if (!response.ok) return
    const payload = await response.json()
    dailyRows.value = payload.items ?? []
    const latest = dailyRows.value.reduce((max, item) => item.日期 > max ? item.日期 : max, '')
    const latestTotal = dailyRows.value
      .filter((item) => item.日期 === latest)
      .reduce((sum, item) => sum + item.日发电量, 0)
    stats.value[0].value = latest ? latestTotal.toFixed(1) : '—'
    stats.value[1].value = dailyRows.value.reduce((sum, item) => sum + item.缺测时段数, 0)
  } catch {
    // 汇总取不到时卡片保留占位，不阻断明细列表
  }
}

async function reloadCounts() {
  // 异常记录数取过滤口径之外的全量统计，避免分页后数不准。
  try {
    const [missingResp, abnormalResp] = await Promise.all([
      request(`${ENDPOINT}?collection=${encodeURIComponent('缺测')}&size=1`),
      request(`${ENDPOINT}?status=${encodeURIComponent('异常')}&size=1`),
    ])
    const missingPayload = missingResp.ok ? await missingResp.json() : null
    const abnormalPayload = abnormalResp.ok ? await abnormalResp.json() : null
    if (missingPayload) stats.value[1].value = missingPayload.total ?? 0
    if (abnormalPayload) stats.value[2].value = abnormalPayload.total ?? 0
  } catch {
    stats.value[2].value = 0
  }
}

onMounted(() => {
  void reload()
  void reloadDaily()
})
</script>

<style scoped>
.section-title { font-size: 15px; margin: 18px 0 8px; }
.summary-table td, .summary-table th { font-size: 12.5px; }
.create-form {
  display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end;
  background: #fff; border: 1px solid var(--border); border-radius: 8px;
  padding: 12px; margin-bottom: 12px;
}
.form-hint { flex-basis: 100%; font-size: 12px; color: var(--muted); }
.tag { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 12px; }
.tag-collected { background: #e7f6ec; color: #1a7f37; }
.tag-missing { background: #fdecec; color: #b42318; }
.missing-text { color: #b42318; font-weight: 600; }
.reason-text { color: var(--muted); font-size: 12px; }
.row-missing { background: #fff8f8; }
.row-abnormal { background: #fffaf0; }
.row-missing.row-abnormal { background: #fdf6ef; }
.success-text { color: #1a7f37; }
button:disabled { cursor: not-allowed; opacity: 0.6; }
</style>
