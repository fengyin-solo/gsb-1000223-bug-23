<template>
  <section class="page" data-module="power_data">
    <header class="page-head">
      <div>
        <h2>发电量监测</h2>
        <p class="page-desc">
          按日汇总、时段明细与结果文件共用同一套采集状态口径：缺测、异常的时段不计数值，任何出口都不会写成 0。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记发电记录</button>
        <button class="btn" type="button" @click="exportResultFile">导出结果文件</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reloadSummary">
      <label class="filter-item">
        <span>电站编号</span>
        <input v-model="summaryFilters.station" placeholder="按电站编号检索" />
      </label>
      <label class="filter-item">
        <span>日期</span>
        <input v-model="summaryFilters.date" type="date" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetSummaryFilters">重置条件</button>
    </form>

    <h3 class="section-title">按日汇总</h3>
    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in summaryColumns" :key="column">{{ column }}</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in summaryRows" :key="`${row['电站编号']}-${row['日期']}`">
          <td v-for="column in summaryColumns" :key="column">
            <span v-if="column === '日发电量'" :class="{ 'value-missing': row['日发电量'] === null }">
              {{ formatDayValue(row) }}
            </span>
            <span v-else-if="column === '采集状态'" class="status-pill" :class="dayStatusClass(row)">
              {{ row['采集状态'] }}
            </span>
            <span v-else>{{ row[column] || '—' }}</span>
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">时段明细</button>
          </td>
        </tr>
        <tr v-if="!summaryRows.length">
          <td :colspan="summaryColumns.length + 1" class="empty-state">
            暂无按日汇总数据，可调整筛选条件或先登记发电记录
          </td>
        </tr>
      </tbody>
    </table>

    <section v-if="detail" class="detail-panel">
      <header class="detail-head">
        <strong>{{ detail.summary['电站编号'] }} · {{ detail.summary['日期'] }} 时段明细</strong>
        <span class="detail-meta">
          日发电量：{{ formatDayValue(detail.summary) }}
          <span class="status-pill" :class="dayStatusClass(detail.summary)">{{ detail.summary['采集状态'] }}</span>
        </span>
        <button class="btn ghost" type="button" @click="closeDetail">收起</button>
      </header>
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in detailColumns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in detail.items" :key="String(item['时段'])" :class="periodRowClass(item)">
            <td>{{ item['时段'] }}</td>
            <td :class="{ 'value-missing': item['发电量'] === null }">{{ formatPeriodValue(item) }}</td>
            <td>
              <span class="status-pill" :class="periodRowClass(item)">{{ item['采集状态'] }}</span>
            </td>
            <td>{{ reasonText(item) }}</td>
            <td>{{ item['记录编号'] ?? '—' }}</td>
          </tr>
          <tr v-if="!detail.items.length">
            <td :colspan="detailColumns.length" class="empty-state">该日没有应报时段</td>
          </tr>
        </tbody>
      </table>
      <p v-if="detail.summary['备注']" class="detail-remark">备注：{{ detail.summary['备注'] }}</p>
    </section>

    <h3 class="section-title">发电记录</h3>
    <form class="filter-bar" @submit.prevent="reloadRecords">
      <label class="filter-item">
        <span>记录编号</span>
        <input v-model="recordFilters.keyword" placeholder="按记录编号检索" />
      </label>
      <label class="filter-item">
        <span>采集状态</span>
        <select v-model="recordFilters.collect">
          <option value="">全部</option>
          <option v-for="option in collectStatuses" :key="option" :value="option">{{ option }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetRecordFilters">重置条件</button>
    </form>
    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in recordColumns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in recordRows" :key="String(row.id)" :class="periodRowClass(row)">
          <td v-for="column in recordColumns" :key="column">
            <span v-if="column === '发电量'" :class="{ 'value-missing': row['发电量'] === null }">
              {{ formatPeriodValue(row) }}
            </span>
            <span v-else-if="column === '原因说明'">{{ reasonText(row) }}</span>
            <span v-else-if="column === '处理状态'">{{ row.status ?? '—' }}</span>
            <span v-else>{{ row[column] ?? '—' }}</span>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!recordRows.length">
          <td :colspan="recordColumns.length + 1" class="empty-state">暂无发电记录，可先登记发电记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ summaryTotal }} 个电站日汇总 · {{ recordTotal }} 条发电记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type DayDetail = { summary: Row; items: Row[] }

const ENDPOINT = '/api/power_data'
const summaryColumns = ['电站编号', '日期', '日发电量', '应报时段数', '有效时段数', '缺测时段数', '异常时段数', '采集状态', '备注']
const detailColumns = ['时段', '发电量', '采集状态', '原因说明', '记录编号']
const recordColumns = ['记录编号', '电站编号', '记录时间', '发电量', '采集状态', '原因说明', '处理状态']
const collectStatuses = ['已采集', '缺测', '异常', '补录']
const actions = ['标记偏低', '确认异常', '数据补录']

const summaryRows = ref<Row[]>([])
const summaryTotal = ref(0)
const recordRows = ref<Row[]>([])
const recordTotal = ref(0)
const detail = ref<DayDetail | null>(null)
const errorMessage = ref('')
const summaryFilters = ref({ station: '', date: '' })
const recordFilters = ref({ keyword: '', collect: '' })

// 统一零值口径的页面侧表达：有数值（含真实 0）照常显示；缺测、异常显示状态而不是 0。
function formatDayValue(row: Row): string {
  const value = row['日发电量']
  return value === null || value === undefined ? '—（无有效数据）' : String(value)
}

function formatPeriodValue(row: Row): string {
  const value = row['发电量']
  if (value !== null && value !== undefined && value !== '') {
    return String(value)
  }
  const status = String(row['采集状态'] ?? '')
  return status === '缺测' || status === '异常' ? status : '—'
}

// 异常、缺测行必须说明原因；原因缺失时给出空态提示，不留无声空白。
function reasonText(row: Row): string {
  const reason = String(row['异常原因'] ?? row['缺测原因'] ?? row['原因说明'] ?? '').trim()
  if (reason) {
    return reason
  }
  const status = String(row['采集状态'] ?? '')
  return status === '缺测' || status === '异常' ? '原因未填写，请补充说明' : '—'
}

function periodRowClass(row: Row): string {
  const status = String(row['采集状态'] ?? '')
  if (status === '缺测') return 'is-gap'
  if (status === '异常') return 'is-abnormal'
  if (status === '补录') return 'is-backfill'
  return ''
}

function dayStatusClass(row: Row): string {
  const status = String(row['采集状态'] ?? '')
  if (status === '存在异常') return 'is-abnormal'
  if (status === '全日缺测') return 'is-gap'
  if (status === '部分缺测') return 'is-backfill'
  return 'is-ok'
}

const stats = computed(() => {
  const rows = summaryRows.value
  const hasValue = rows.some((row) => typeof row['日发电量'] === 'number')
  const total = rows.reduce((acc, row) => acc + (typeof row['日发电量'] === 'number' ? Number(row['日发电量']) : 0), 0)
  const missing = rows.reduce((acc, row) => acc + Number(row['缺测时段数'] ?? 0), 0)
  const abnormal = rows.reduce((acc, row) => acc + Number(row['异常时段数'] ?? 0), 0)
  return [
    { label: '日发电量合计(kWh)', value: hasValue ? total.toFixed(1) : '—' },
    { label: '缺测时段', value: missing },
    { label: '异常时段', value: abnormal },
  ]
})

function summaryQuery(): string {
  const params = new URLSearchParams()
  if (summaryFilters.value.station) params.set('station', summaryFilters.value.station)
  if (summaryFilters.value.date) params.set('date', summaryFilters.value.date)
  return params.toString()
}

function resetSummaryFilters() {
  summaryFilters.value = { station: '', date: '' }
  void reloadSummary()
}

function resetRecordFilters() {
  recordFilters.value = { keyword: '', collect: '' }
  void reloadRecords()
}

function exportResultFile() {
  const query = summaryQuery()
  window.open(`${ENDPOINT}/daily/export${query ? `?${query}` : ''}`, '_blank')
}

function openCreate() {
  errorMessage.value = '发电记录登记入口尚未接入审批流'
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  const params = new URLSearchParams({ station: String(row['电站编号']), date: String(row['日期']) })
  try {
    const response = await request(`${ENDPOINT}/daily/detail?${params}`)
    if (!response.ok) {
      throw new Error('时段明细读取失败，请稍后重试')
    }
    detail.value = (await response.json()) as DayDetail
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '时段明细读取失败'
  }
}

function closeDetail() {
  detail.value = null
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('发电监测动作未生效，请稍后重试')
    }
    await Promise.all([reloadRecords(), reloadSummary()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '发电监测操作失败'
  }
}

async function reloadSummary() {
  errorMessage.value = ''
  const query = summaryQuery()
  try {
    const response = await request(`${ENDPOINT}/daily?size=200${query ? `&${query}` : ''}`)
    if (!response.ok) {
      throw new Error('按日汇总读取失败')
    }
    const payload = await response.json()
    summaryRows.value = payload.items ?? []
    summaryTotal.value = payload.total ?? summaryRows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '按日汇总读取失败'
  }
}

async function reloadRecords() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  if (recordFilters.value.keyword) params.set('keyword', recordFilters.value.keyword)
  if (recordFilters.value.collect) params.set('collect', recordFilters.value.collect)
  try {
    const response = await request(`${ENDPOINT}?${params}`)
    if (!response.ok) {
      throw new Error('发电记录列表读取失败')
    }
    const payload = await response.json()
    recordRows.value = payload.items ?? []
    recordTotal.value = payload.total ?? recordRows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '发电记录列表读取失败'
  }
}

onMounted(() => {
  void reloadSummary()
  void reloadRecords()
})
</script>

<style scoped>
.section-title {
  font-size: 14px;
  margin: 16px 0 8px;
}
.value-missing {
  color: var(--muted);
}
.status-pill {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 12px;
  background: #eef2f7;
  color: var(--muted);
}
.status-pill.is-ok {
  background: #e7f6ec;
  color: #18794e;
}
.status-pill.is-gap {
  background: #fdf0e5;
  color: #b4540a;
}
.status-pill.is-abnormal {
  background: #fdeceb;
  color: #b42318;
}
.status-pill.is-backfill {
  background: #e8f0fe;
  color: #1f6feb;
}
tr.is-gap td {
  background: #fffaf5;
}
tr.is-abnormal td {
  background: #fff5f5;
}
.detail-panel {
  margin-top: 12px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fff;
}
.detail-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.detail-meta {
  color: var(--muted);
  font-size: 13px;
}
.detail-head .btn {
  margin-left: auto;
}
.detail-remark {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--muted);
}
</style>
