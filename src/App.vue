<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";
import { request, tokenStore } from "./api";
import Pagination from "./Pagination.vue";
import { usePagination } from "./usePagination";
import { createRuleDefaults } from "./ruleDefaults";

const authenticated = ref(false);
const restoring = ref(Boolean(tokenStore.get()));
const loading = ref(false);
const currentView = ref("businesses");
const sidebarOpen = ref(false);
const userMenuOpen = ref(false);
const userMenu = ref(null);
const userMenuButton = ref(null);
const globalSearch = ref("");
const businesses = ref([]);
const rules = ref([]);
const records = ref([]);
const dashboardStats = reactive({ businesses: 0, enabledBusinesses: 0, todayAlerts: 0 });

const loginForm = reactive({ username: "", password: "" });
const loginError = ref("");
const loginBusy = ref(false);
const passwordVisible = ref(false);

const businessSearch = ref("");
const businessStatus = ref("all");
const selectedBusinessIds = ref([]);
const businessModalOpen = ref(false);
const editingBusinessId = ref(null);
const businessForm = reactive({ code: "", name: "", tag: "", description: "", enabled: true, tone: "green" });

const ruleSearch = ref("");
const ruleBusinessFilter = ref("全部");
const ruleProviderFilter = ref("全部");
const ruleModalOpen = ref(false);
const editingRuleCode = ref("");
const ruleForm = reactive({ code: "", parent: "", business: "", provider: "", account: "", threshold: "", fluctuation: 0, debounce: "10m", purpose: "", tag: "", enabled: true });

const recordSearch = ref("");
const recordBusinessFilter = ref("全部业务");
const recordPeriod = ref("today");
const recordModalOpen = ref(false);
const editingRecord = ref(null);
const recordStatus = ref("待处理");

const toastText = ref("");
const toastVisible = ref(false);
let toastTimer;

const navItems = [
  { id: "businesses", icon: "⌘", label: "告警业务" },
  { id: "rules", icon: "≋", label: "告警设置" },
  { id: "records", icon: "◴", label: "告警记录" },
];

const statCards = computed(() => [
  { icon: "⌘", label: "接入业务总数", value: dashboardStats.businesses, note: "个" },
  { icon: "♢", label: "开启通知业务", value: dashboardStats.enabledBusinesses, note: `/ ${dashboardStats.businesses}` },
  { icon: "◴", label: "今日触发总次", value: dashboardStats.todayAlerts, note: "次" },
]);

const filteredBusinesses = computed(() => {
  const query = businessSearch.value.trim().toLowerCase();
  return businesses.value.filter((row) => {
    const matchesQuery = !query || `${row.code} ${row.name} ${row.tag || ""} ${row.description || ""}`.toLowerCase().includes(query);
    const matchesStatus = businessStatus.value === "all" || (businessStatus.value === "enabled") === Boolean(row.enabled);
    return matchesQuery && matchesStatus;
  });
});

const businessPagination = usePagination(filteredBusinesses, [businessSearch, businessStatus]);

const allBusinessesSelected = computed({
  get() {
    return businessPagination.items.length > 0 && businessPagination.items.every((row) => selectedBusinessIds.value.includes(row.id));
  },
  set(checked) {
    const visibleIds = businessPagination.items.map((row) => row.id);
    selectedBusinessIds.value = checked
      ? [...new Set([...selectedBusinessIds.value, ...visibleIds])]
      : selectedBusinessIds.value.filter((id) => !visibleIds.includes(id));
  },
});

const ruleBusinesses = computed(() => [...new Set(rules.value.map((row) => row.business).filter(Boolean))]);
const ruleProviders = computed(() => [...new Set(rules.value.map((row) => row.provider).filter(Boolean))]);
const filteredRules = computed(() => {
  const query = ruleSearch.value.trim().toLowerCase();
  return rules.value.filter((row) => {
    const matchesQuery = !query || Object.values(row).join(" ").toLowerCase().includes(query);
    const matchesBusiness = ruleBusinessFilter.value === "全部" || row.business === ruleBusinessFilter.value;
    const matchesProvider = ruleProviderFilter.value === "全部" || row.provider === ruleProviderFilter.value;
    return matchesQuery && matchesBusiness && matchesProvider;
  });
});

const rulePagination = usePagination(filteredRules, [ruleSearch, ruleBusinessFilter, ruleProviderFilter]);

const activeRuleCount = computed(() => rules.value.filter((row) => row.enabled).length);
const sensitiveRuleCount = computed(() => rules.value.filter((row) => Number(row.fluctuation) >= 40).length);
const minimumDebounce = computed(() => {
  if (!rules.value.length) return "--";
  return [...rules.value].sort((a, b) => debounceToMinutes(a.debounce) - debounceToMinutes(b.debounce))[0]?.debounce || "--";
});

const recordBusinesses = computed(() => [...new Set(records.value.map((row) => row.business).filter(Boolean))]);
const filteredRecords = computed(() => {
  const query = recordSearch.value.trim().toLowerCase();
  return records.value.filter((row) => {
    const matchesQuery = !query || Object.values(row).join(" ").toLowerCase().includes(query);
    const matchesBusiness = recordBusinessFilter.value === "全部业务" || row.business === recordBusinessFilter.value;
    return matchesQuery && matchesBusiness;
  });
});
const recordPagination = usePagination(filteredRecords, [recordSearch, recordBusinessFilter, recordPeriod]);

const pendingRecordCount = computed(() => records.value.filter((row) => row.status === "待处理").length);
const confirmedRecordCount = computed(() => records.value.filter((row) => row.status === "已确认").length);
const statusTypeCount = computed(() => new Set(records.value.map((row) => row.status)).size);
const todayLabel = computed(() => new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date()).replaceAll("/", "-"));

function showToast(message) {
  toastText.value = message;
  toastVisible.value = true;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (toastVisible.value = false), 2400);
}

function logout() {
  tokenStore.set("");
  authenticated.value = false;
  userMenuOpen.value = false;
  sidebarOpen.value = false;
  currentView.value = "businesses";
  loginForm.password = "";
  passwordVisible.value = false;
  loginError.value = "";
  businessModalOpen.value = false;
  ruleModalOpen.value = false;
  recordModalOpen.value = false;
  selectedBusinessIds.value = [];
  globalSearch.value = "";
  businessSearch.value = "";
  businessStatus.value = "all";
  ruleSearch.value = "";
  ruleBusinessFilter.value = "全部";
  ruleProviderFilter.value = "全部";
  recordSearch.value = "";
  recordBusinessFilter.value = "全部业务";
  recordPeriod.value = "today";
  businesses.value = [];
  rules.value = [];
  records.value = [];
  clearTimeout(toastTimer);
  toastVisible.value = false;
  toastText.value = "";
}

function closeUserMenu(event) {
  if (!userMenu.value?.contains(event.target)) userMenuOpen.value = false;
}

function dismissUserMenu() {
  userMenuOpen.value = false;
  userMenuButton.value?.focus();
}

async function api(path, options = {}) {
  try {
    return await request(path, options);
  } catch (error) {
    if (error.status === 401 && path !== "/auth/login") logout();
    throw error;
  }
}

async function loadData({ quiet = false } = {}) {
  if (!quiet) loading.value = true;
  try {
    const [businessData, ruleData, recordData, statsData] = await Promise.all([
      api("/businesses"),
      api("/rules"),
      api("/records"),
      api("/stats"),
    ]);
    businesses.value = Array.isArray(businessData) ? businessData : [];
    rules.value = Array.isArray(ruleData) ? ruleData : [];
    records.value = Array.isArray(recordData) ? recordData : [];
    Object.assign(dashboardStats, statsData || {});
    selectedBusinessIds.value = selectedBusinessIds.value.filter((id) => businesses.value.some((row) => row.id === id));
  } catch (error) {
    showToast(error.message);
  } finally {
    loading.value = false;
  }
}

async function submitLogin() {
  loginError.value = "";
  if (!loginForm.username.trim() || !loginForm.password) {
    loginError.value = "请输入完整的登录账号和密码";
    return;
  }
  loginBusy.value = true;
  try {
    const result = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username: loginForm.username.trim(), password: loginForm.password }),
    });
    tokenStore.set(result.token);
    authenticated.value = true;
    await loadData();
    showToast("认证成功，已进入监控工作台");
  } catch (error) {
    loginError.value = error.message;
  } finally {
    loginBusy.value = false;
  }
}

function switchView(view) {
  currentView.value = view;
  sidebarOpen.value = false;
  globalSearch.value = view === "businesses" ? businessSearch.value : view === "rules" ? ruleSearch.value : recordSearch.value;
}

function applyGlobalSearch() {
  if (currentView.value === "businesses") businessSearch.value = globalSearch.value;
  if (currentView.value === "rules") ruleSearch.value = globalSearch.value;
  if (currentView.value === "records") recordSearch.value = globalSearch.value;
}

async function refreshData() {
  await loadData();
  showToast("数据已刷新");
}

function resetBusinessForm() {
  Object.assign(businessForm, { code: "", name: "", tag: "", description: "", enabled: true, tone: "green" });
}

function openBusinessModal(row = null) {
  editingBusinessId.value = row?.id ?? null;
  Object.assign(businessForm, row
    ? { code: row.code, name: row.name, tag: row.tag || "", description: row.description || "", enabled: Boolean(row.enabled), tone: row.tone || "green" }
    : { code: "", name: "", tag: "", description: "", enabled: true, tone: "green" });
  businessModalOpen.value = true;
}

function closeBusinessModal() {
  businessModalOpen.value = false;
  editingBusinessId.value = null;
  resetBusinessForm();
}

async function saveBusiness() {
  const id = editingBusinessId.value;
  const payload = {
    code: businessForm.code.trim(),
    name: businessForm.name.trim(),
    tag: businessForm.tag.trim(),
    description: businessForm.description.trim(),
    enabled: Boolean(businessForm.enabled),
    tone: businessForm.tone || "green",
  };
  try {
    await api(id ? `/businesses/${id}` : "/businesses", { method: id ? "PUT" : "POST", body: JSON.stringify(payload) });
    closeBusinessModal();
    await loadData({ quiet: true });
    showToast(`告警业务“${payload.name}”已保存`);
  } catch (error) {
    showToast(error.message);
  }
}

async function toggleBusiness(row, enabled) {
  const previous = row.enabled;
  row.enabled = enabled;
  try {
    const saved = await api(`/businesses/${row.id}`, { method: "PATCH", body: JSON.stringify({ enabled }) });
    Object.assign(row, saved);
    await refreshStatsOnly();
    showToast(`${row.name}通知已${enabled ? "开启" : "暂停"}`);
  } catch (error) {
    row.enabled = previous;
    showToast(error.message);
  }
}

async function batchSetBusinesses(enabled) {
  const selected = businesses.value.filter((row) => selectedBusinessIds.value.includes(row.id));
  if (!selected.length) return showToast("请先选择告警业务");
  try {
    await Promise.all(selected.map((row) => api(`/businesses/${row.id}`, { method: "PATCH", body: JSON.stringify({ enabled }) })));
    await loadData({ quiet: true });
    showToast(`已批量${enabled ? "启用" : "停用"} ${selected.length} 个业务`);
  } catch (error) {
    showToast(error.message);
  }
}

async function deleteBusiness(row) {
  if (!window.confirm(`确认删除业务“${row.name}”？其关联规则也会一并删除。`)) return;
  try {
    await api(`/businesses/${row.id}`, { method: "DELETE" });
    await loadData({ quiet: true });
    showToast(`${row.name} 已删除`);
  } catch (error) {
    showToast(error.message);
  }
}

async function refreshStatsOnly() {
  try {
    Object.assign(dashboardStats, await api("/stats"));
  } catch (error) {
    showToast(error.message);
  }
}

function randomBusinessCode() {
  businessForm.code = String(Math.floor(100000 + Math.random() * 900000));
}

function resetRuleFilters() {
  ruleSearch.value = "";
  ruleBusinessFilter.value = "全部";
  ruleProviderFilter.value = "全部";
  if (currentView.value === "rules") globalSearch.value = "";
}

function syncRuleBusiness() {
  ruleForm.business = businesses.value.find((row) => row.code === ruleForm.parent)?.name || "";
}

function openRuleModal(row = null) {
  editingRuleCode.value = row?.code || "";
  const parent = row?.parent || businesses.value[0]?.code || "";
  Object.assign(ruleForm, row
    ? { code: row.code, parent: row.parent, business: row.business, provider: row.provider, account: row.account, threshold: row.threshold, fluctuation: row.fluctuation, debounce: row.debounce, purpose: row.purpose, tag: row.tag || "", enabled: Boolean(row.enabled) }
    : createRuleDefaults(parent, businesses.value.find((item) => item.code === parent)?.name || "", rules.value));
  ruleModalOpen.value = true;
}

function closeRuleModal() {
  ruleModalOpen.value = false;
  editingRuleCode.value = "";
}

async function saveRule() {
  const debounce = ruleForm.debounce.trim().toLowerCase();
  if (!/^\d+(?:\.\d+)?[mhd]$/.test(debounce)) {
    showToast("防抖告警跨度请输入数字加 m、h 或 d，例如 10m、2h、1d");
    return;
  }
  const originalCode = editingRuleCode.value;
  const payload = {
    code: ruleForm.code.trim().replace(/^#/, ""),
    parent: ruleForm.parent.trim(),
    business: ruleForm.business.trim(),
    provider: ruleForm.provider.trim(),
    account: ruleForm.account.trim(),
    threshold: Number(ruleForm.threshold),
    fluctuation: Number(ruleForm.fluctuation),
    debounce,
    purpose: ruleForm.purpose.trim(),
    tag: ruleForm.tag.trim(),
    enabled: Boolean(ruleForm.enabled),
  };
  try {
    await api(originalCode ? `/rules/${encodeURIComponent(originalCode)}` : "/rules", { method: originalCode ? "PUT" : "POST", body: JSON.stringify(payload) });
    closeRuleModal();
    await loadData({ quiet: true });
    showToast(`规则 #${payload.code} 已保存`);
  } catch (error) {
    showToast(error.message);
  }
}

async function toggleRule(row, enabled) {
  const previous = row.enabled;
  row.enabled = enabled;
  try {
    const saved = await api(`/rules/${encodeURIComponent(row.code)}`, { method: "PATCH", body: JSON.stringify({ enabled }) });
    Object.assign(row, saved);
    showToast(`规则 #${row.code} 通知已${enabled ? "开启" : "关闭"}`);
  } catch (error) {
    row.enabled = previous;
    showToast(error.message);
  }
}

async function deleteRule(row) {
  if (!window.confirm(`确认删除告警规则 #${row.code}？`)) return;
  try {
    await api(`/rules/${encodeURIComponent(row.code)}`, { method: "DELETE" });
    await loadData({ quiet: true });
    showToast(`规则 #${row.code} 已删除`);
  } catch (error) {
    showToast(error.message);
  }
}

function resetRecordFilters() {
  recordSearch.value = "";
  recordBusinessFilter.value = "全部业务";
  recordPeriod.value = "today";
  if (currentView.value === "records") globalSearch.value = "";
}

function openRecordStatusModal(row) {
  editingRecord.value = row;
  recordStatus.value = row.status;
  recordModalOpen.value = true;
}

function closeRecordStatusModal() {
  recordModalOpen.value = false;
  editingRecord.value = null;
}

async function saveRecordStatus() {
  if (!editingRecord.value) return;
  try {
    const saved = await api(`/records/${editingRecord.value.id}`, { method: "PATCH", body: JSON.stringify({ status: recordStatus.value }) });
    const row = records.value.find((item) => item.id === saved.id);
    if (row) Object.assign(row, saved);
    closeRecordStatusModal();
    showToast(`告警记录 #${saved.id} 状态已修改为“${saved.status}”`);
  } catch (error) {
    showToast(error.message);
  }
}

async function deleteRecord(row) {
  if (!window.confirm(`确认删除告警记录 #${row.id}？`)) return;
  try {
    await api(`/records/${row.id}`, { method: "DELETE" });
    records.value = records.value.filter((item) => item.id !== row.id);
    await refreshStatsOnly();
    showToast(`告警记录 #${row.id} 已删除`);
  } catch (error) {
    showToast(error.message);
  }
}

function debounceToMinutes(value) {
  const match = String(value || "").trim().match(/^(\d+(?:\.\d+)?)([mhd])$/i);
  if (!match) return Number.POSITIVE_INFINITY;
  const factors = { m: 1, h: 60, d: 1440 };
  return Number(match[1]) * factors[match[2].toLowerCase()];
}

function statusClass(status) {
  return { 待处理: "warning", 处理中: "processing", 已确认: "confirmed", 已忽略: "ignored" }[status] || "warning";
}

function recordLevel(row) {
  return row.level || statusClass(row.status);
}

onMounted(async () => {
  document.addEventListener("pointerdown", closeUserMenu);
  if (!tokenStore.get()) {
    restoring.value = false;
    return;
  }
  try {
    await api("/auth/me");
    authenticated.value = true;
    await loadData();
  } catch {
    logout();
  } finally {
    restoring.value = false;
  }
});

onUnmounted(() => {
  document.removeEventListener("pointerdown", closeUserMenu);
  clearTimeout(toastTimer);
});
</script>

<template>
  <div v-if="restoring" class="boot-screen">
    <span class="boot-spinner"></span>
    <p>正在恢复登录状态...</p>
  </div>

  <section v-else-if="!authenticated" class="login-screen">
    <div class="ambient ambient-a"></div>
    <div class="ambient ambient-b"></div>
    <div class="ambient ambient-c"></div>
    <div class="login-card">
      <div class="login-visual">
        <div class="visual-brand">
          <span class="logo-box">◈</span>
          <div><strong>告警智能监控平台</strong><small>OPS TELEMETRY HUB</small></div>
        </div>
        <div class="telemetry-card">
          <div class="telemetry-scene">
            <img
              alt="蓝青色监控大屏连接服务器与云端网络节点"
              src="/monitoring-illustration.png"
              width="1536"
              height="1024"
            />
          </div>
          <div class="telemetry-status"><span><i></i>集群状态：巡检就绪</span><b>≋ 99.99%</b></div>
        </div>
      </div>
      <div class="login-form-wrap">
        <form class="login-form" @submit.prevent="submitLogin">
          <span class="login-tag">告警管理中心</span>
          <h1>系统登录</h1>
          <p class="login-subtitle">请输入您的凭证以访问监控工作台</p>
          <label for="username">账号</label>
          <div class="input-wrap"><span>♙</span><input id="username" v-model="loginForm.username" autocomplete="username" placeholder="请输入登录账号" required /></div>
          <label for="password">密码</label>
          <div class="input-wrap">
            <span>▣</span>
            <input id="password" v-model="loginForm.password" :type="passwordVisible ? 'text' : 'password'" autocomplete="current-password" placeholder="请输入密码" required />
            <button type="button" :aria-label="passwordVisible ? '隐藏密码' : '显示密码'" @click="passwordVisible = !passwordVisible">◉</button>
          </div>
          <p class="login-error">{{ loginError }}</p>
          <button class="login-button" type="submit" :disabled="loginBusy"><span>{{ loginBusy ? "认证中..." : "立即登录" }}</span><b>→</b></button>
        </form>
      </div>
    </div>
  </section>

  <div v-else class="app">
    <aside class="sidebar" :class="{ open: sidebarOpen }">
      <div class="brand"><span class="logo-box">♢</span><div><strong>云告警管理中心</strong><small>v2.4.0 · Enterprise</small></div></div>
      <div class="probe"><span>✓</span><small>全链路探针巡检正常</small><i></i></div>
      <nav>
        <p>监控工作台</p>
        <button v-for="item in navItems" :key="item.id" class="nav-item" :class="{ active: currentView === item.id }" @click="switchView(item.id)"><span>{{ item.icon }}</span>{{ item.label }}</button>
      </nav>
    </aside>

    <div v-if="sidebarOpen" class="sidebar-mask" @click="sidebarOpen = false"></div>

    <div class="workspace">
      <header class="topbar">
        <button class="mobile-menu" @click="sidebarOpen = !sidebarOpen">☰</button>
        <label class="global-search"><span>⌕</span><input v-model="globalSearch" placeholder="搜索业务、规则编码或告警流水号..." @input="applyGlobalSearch" /></label>
        <span class="instant-mode">ϟ 即时响应模式已开启</span>
        <div class="top-actions">
          <button title="刷新数据" :disabled="loading" @click="refreshData">↻</button>
          <div ref="userMenu" class="operator" @keydown.esc.stop.prevent="dismissUserMenu" @focusout="!$event.currentTarget.contains($event.relatedTarget) && (userMenuOpen = false)">
            <span><b>运维中心主控</b><small>ops-master@cloud.local</small></span>
            <button ref="userMenuButton" type="button" class="avatar-button" aria-label="用户菜单" :aria-expanded="userMenuOpen" aria-controls="user-menu" @click="userMenuOpen = !userMenuOpen">管</button>
            <div v-if="userMenuOpen" id="user-menu" class="user-menu">
              <button type="button" @click="logout">退出登录</button>
            </div>
          </div>
        </div>
      </header>

      <main class="main-content">
        <section v-if="currentView === 'businesses'">
          <div class="hero-row">
            <div class="title-block">
              <div class="breadcrumbs">控制台　›　业务管理　›　<span>告警业务</span></div>
              <div class="title-line"><h1>告警业务矩阵</h1><em>CLUSTER: AP-EAST-01</em></div>
            </div>
            <div class="stats">
              <article v-for="card in statCards" :key="card.label" class="stat-card">
                <span class="stat-icon">{{ card.icon }}</span>
                <div><small>{{ card.label }}</small><strong>{{ card.value }}<span>{{ card.note }}</span></strong></div>
              </article>
            </div>
          </div>

          <div class="toolbar">
            <div class="toolbar-left">
              <label class="table-search"><span>⌕</span><input v-model="businessSearch" placeholder="搜索业务编码或业务名称..." /></label>
              <label class="select-wrap"><select v-model="businessStatus"><option value="all">通知状态：全部</option><option value="enabled">已开启通知</option><option value="disabled">已暂停通知</option></select><span>⌄</span></label>
              <button class="soft-button" @click="batchSetBusinesses(true)">▷ 批量启用</button>
              <button class="soft-button muted" @click="batchSetBusinesses(false)">Ⅱ 批量停用</button>
            </div>
            <button class="add-button" @click="openBusinessModal()">＋ 新增业务</button>
          </div>

          <div class="data-panel">
            <div class="table-scroll">
              <table>
                <thead><tr><th><input v-model="allBusinessesSelected" type="checkbox" aria-label="选择当前全部业务" /></th><th>ID</th><th>唯一编码</th><th>业务名称</th><th>关联子规则</th><th>是否开启通知</th><th>接入时间</th><th>操作</th></tr></thead>
                <tbody>
                  <tr v-for="row in businessPagination.items" :key="row.id">
                    <td><input v-model="selectedBusinessIds" class="row-check" type="checkbox" :value="row.id" :aria-label="`选择业务 ${row.name}`" /></td>
                    <td class="metric">{{ row.id }}</td>
                    <td><span class="code">{{ row.code }}</span></td>
                    <td><div class="account-cell"><i :class="`tone-${row.tone || 'green'}`"></i><b>{{ row.name }}</b><small class="business-tag" :class="`tone-${row.tone || 'green'}`">{{ row.tag || "-" }}</small></div></td>
                    <td class="metric">{{ row.rules }} 条监控流</td>
                    <td><label class="switch"><input type="checkbox" :checked="row.enabled" @change="toggleBusiness(row, $event.target.checked)" /><i></i><span>{{ row.enabled ? "开启" : "暂停" }}</span></label></td>
                    <td class="metric time-cell">{{ row.time }}</td>
                    <td><div class="row-actions"><button @click="openBusinessModal(row)">编辑</button><button @click="deleteBusiness(row)">删除</button></div></td>
                  </tr>
                  <tr v-if="!filteredBusinesses.length"><td colspan="8" class="empty-cell">没有符合条件的告警业务</td></tr>
                </tbody>
              </table>
            </div>
            <Pagination :pagination="businessPagination" />
          </div>
        </section>

        <section v-else-if="currentView === 'rules'">
          <div class="section-heading">
            <div>
              <div class="breadcrumbs">控制台　/　告警业务　/　<span>告警设置</span></div>
              <div class="title-line"><h1>规则与阈值配置</h1><em>CONFIG-v2.4</em></div>
            </div>
            <div class="heading-buttons"><button class="blue-button" @click="openRuleModal()">⊕ 新增告警规则</button></div>
          </div>

          <div class="summary-grid rules-summary">
            <article><span>♢</span><div><small>生效中监控规则</small><strong>{{ activeRuleCount }} <i>/ {{ rules.length }} 条总计</i></strong><em>通知状态来自规则配置</em></div></article>
            <article><span>⌁</span><div><small>高浮动预警配置（≥40%）</small><strong>{{ sensitiveRuleCount }} <i>条高灵敏度策略</i></strong><em>依据预警浮动百分比统计</em></div></article>
            <article><span>◷</span><div><small>最短防抖告警跨度</small><strong>{{ minimumDebounce }} <i>m 分钟 · h 小时 · d 天</i></strong><em>用户可自由输入数值与单位</em></div></article>
            <article><span>☁</span><div><small>规则厂商分布</small><strong class="provider-count">{{ ruleProviders.length }} 家</strong><em>{{ ruleProviders.join("　") || "暂无厂商" }}</em></div></article>
          </div>

          <div class="rule-filters">
            <div><b>业务:</b><button class="chip" :class="{ active: ruleBusinessFilter === '全部' }" @click="ruleBusinessFilter = '全部'">全部</button><button v-for="name in ruleBusinesses" :key="name" class="chip" :class="{ active: ruleBusinessFilter === name }" @click="ruleBusinessFilter = name">{{ name }}</button></div>
            <div><b>厂商:</b><button class="chip" :class="{ active: ruleProviderFilter === '全部' }" @click="ruleProviderFilter = '全部'">全部</button><button v-for="provider in ruleProviders" :key="provider" class="chip" :class="{ active: ruleProviderFilter === provider }" @click="ruleProviderFilter = provider">{{ provider }}</button></div>
            <label class="mini-search">⌕ <input v-model="ruleSearch" placeholder="搜索详细唯一编码 / 账号 / 业务用途..." /></label>
            <button class="reset-button" @click="resetRuleFilters">⌁ 重置</button>
            <button class="icon-refresh" :disabled="loading" @click="refreshData">↻</button>
          </div>

          <div class="data-panel rules-panel">
            <div class="table-scroll">
              <table class="rules-table">
                <thead><tr><th>详细唯一编码</th><th>所属业务</th><th>厂商 / 账号</th><th>低于阈值预警</th><th>浮动百分比</th><th>防抖告警跨度</th><th>业务用途 / 标签</th><th>通知开关</th><th>操作</th></tr></thead>
                <tbody>
                  <tr v-for="row in rulePagination.items" :key="row.code">
                    <td><b class="rule-code">#{{ row.code }}</b><small>（父编码: {{ row.parent }}）</small></td>
                    <td><span class="dot green"></span>{{ row.business }}</td>
                    <td><b>{{ row.provider }}</b><small class="block">{{ row.account }}</small></td>
                    <td><span class="threshold">&lt; ¥{{ Number(row.threshold).toLocaleString("zh-CN") }}</span></td>
                    <td><div class="percent-cell"><i><b :style="{ width: `${Math.min(100, Math.max(0, Number(row.fluctuation)))}%` }"></b></i><span>{{ row.fluctuation }}%</span></div></td>
                    <td><span class="debounce">{{ row.debounce }}</span></td>
                    <td><b>{{ row.purpose }}</b><small class="block muted-copy">{{ row.tag || "-" }}</small></td>
                    <td><label class="switch"><input type="checkbox" :checked="row.enabled" @change="toggleRule(row, $event.target.checked)" /><i></i></label></td>
                    <td><div class="rule-actions"><button @click="openRuleModal(row)">编辑</button><button @click="deleteRule(row)">删除</button></div></td>
                  </tr>
                  <tr v-if="!filteredRules.length"><td colspan="9" class="empty-cell">没有符合条件的告警规则</td></tr>
                </tbody>
              </table>
            </div>
            <Pagination :pagination="rulePagination" />
          </div>
        </section>

        <section v-else>
          <div class="section-heading records-heading">
            <div><span class="live-label">LIVE LOGS</span><h1>告警通知记录总览</h1><p>全通道告警事件下发追踪与实时应急处置中心</p></div>
          </div>

          <div class="summary-grid record-summary">
            <article><span>♢</span><div><small>今日告警总触发</small><strong>{{ dashboardStats.todayAlerts }} <i class="green-note">数据库实时统计</i></strong><div class="summary-line blue"></div></div></article>
            <article><span>▲</span><div><small>待处理紧急预警</small><strong class="orange-text">{{ pendingRecordCount }} <i>需人工干预</i></strong><div class="summary-line orange"></div></div></article>
            <article><span>▣</span><div><small>已确认告警</small><strong>{{ confirmedRecordCount }} <i class="green-note">条</i></strong><div class="summary-line green"></div></div></article>
            <article><span>◷</span><div><small>告警记录总量</small><strong>{{ records.length }} <i>条 · {{ statusTypeCount }} 种状态</i></strong><em>按最新告警时间排序</em><div class="summary-line navy"></div></div></article>
          </div>

          <div class="record-filters">
            <div class="period-tabs"><button :class="{ active: recordPeriod === 'today' }" @click="recordPeriod = 'today'">今日</button><button :class="{ active: recordPeriod === '3d' }" @click="recordPeriod = '3d'">近3天</button><button :class="{ active: recordPeriod === '7d' }" @click="recordPeriod = '7d'">近7天</button></div>
            <div class="date-range">▣ {{ todayLabel }} 00:00 至 {{ todayLabel }} 23:59　≋</div>
            <div class="filter-grid record-filter-simple">
              <label>业务类型<select v-model="recordBusinessFilter"><option>全部业务</option><option v-for="name in recordBusinesses" :key="name">{{ name }}</option></select></label>
              <label>复合关键字搜索<input v-model="recordSearch" placeholder="输入编码 / 账号 / 告警摘要..." /></label>
              <button class="outline-button" @click="resetRecordFilters">↻ 重置</button>
              <button class="dark-button" @click="refreshData">≡ 查询记录</button>
            </div>
            <div class="selected-filters"><span>已选条件：</span><i>周期: {{ recordPeriod === "today" ? "今日" : recordPeriod === "3d" ? "近3天" : "近7天" }}　×</i><i v-if="recordBusinessFilter !== '全部业务'">业务: {{ recordBusinessFilter }}　×</i></div>
          </div>

          <div class="data-panel records-panel">
            <div class="table-scroll">
              <table class="records-table">
                <thead><tr><th><input type="checkbox" aria-label="选择全部告警记录" /></th><th>ID</th><th>告警时间</th><th>业务详细编码</th><th>业务名称</th><th>厂商与账号</th><th>告警内容及异常特征</th><th>状态</th><th>操作</th></tr></thead>
                <tbody>
                  <tr v-for="row in recordPagination.items" :key="row.id">
                    <td><input type="checkbox" :aria-label="`选择告警记录 ${row.id}`" /></td>
                    <td class="metric">#{{ row.id }}</td>
                    <td><b class="record-time">{{ row.time }}</b><small class="block">{{ row.date }}</small></td>
                    <td><b class="rule-code">{{ row.code }}</b></td>
                    <td><span class="dot" :class="row.status === '处理中' ? 'orange' : 'green'"></span>{{ row.business }}</td>
                    <td><span class="provider-badge">{{ row.provider }}</span><small class="block">{{ row.account }}</small></td>
                    <td><div class="alert-copy"><b :class="recordLevel(row)">{{ row.type }}</b><strong>{{ row.value }}</strong><small>{{ row.detail }}</small></div></td>
                    <td><span class="status-badge" :class="statusClass(row.status)">{{ row.status }}</span></td>
                    <td><div class="record-actions"><button @click="openRecordStatusModal(row)">修改状态</button><button @click="deleteRecord(row)">删除</button></div></td>
                  </tr>
                  <tr v-if="!filteredRecords.length"><td colspan="9" class="empty-cell">没有符合条件的告警记录</td></tr>
                </tbody>
              </table>
            </div>
            <Pagination :pagination="recordPagination" />
          </div>
        </section>
      </main>
    </div>
  </div>

  <div v-if="businessModalOpen" class="modal" @click.self="closeBusinessModal">
    <div class="modal-card business-modal-card">
      <header><div><h2>{{ editingBusinessId ? "编辑告警业务" : "新增告警业务" }}</h2><p>配置数据库中业务接入编码与通知状态</p></div><button aria-label="关闭" @click="closeBusinessModal">×</button></header>
      <form @submit.prevent="saveBusiness">
        <div class="form-grid">
          <label><span>业务名称 *</span><input v-model.trim="businessForm.name" placeholder="例：短信商" required /></label>
          <label><span>唯一编码 *</span><span class="code-row"><input v-model.trim="businessForm.code" placeholder="6 位数字或唯一标识" required /><button type="button" @click="randomBusinessCode">随机码</button></span></label>
          <label><span>业务标签</span><input v-model.trim="businessForm.tag" placeholder="例：SMS-GATEWAY" /></label>
          <label><span>标识色</span><select v-model="businessForm.tone"><option value="green">绿色</option><option value="orange">橙色</option><option value="gray">灰色</option></select></label>
          <label class="wide"><span>业务描述</span><input v-model.trim="businessForm.description" placeholder="填写业务职责边界或主要接口人" /></label>
          <label class="notify-field"><span>通知开关</span><span class="switch"><input v-model="businessForm.enabled" type="checkbox" /><i></i><strong>{{ businessForm.enabled ? "开启" : "暂停" }}</strong></span></label>
        </div>
        <footer><button type="button" @click="closeBusinessModal">取消</button><button type="submit">保存业务</button></footer>
      </form>
    </div>
  </div>

  <div v-if="ruleModalOpen" class="modal" @click.self="closeRuleModal">
    <div class="modal-card rule-modal-card">
      <header><div><h2>{{ editingRuleCode ? "编辑告警规则" : "新增告警规则" }}</h2><p>修改规则阈值、浮动比例、防抖周期及业务属性</p></div><button aria-label="关闭" @click="closeRuleModal">×</button></header>
      <form @submit.prevent="saveRule">
        <div class="form-grid">
          <label><span>详细唯一编码 *</span><input v-model.trim="ruleForm.code" required /></label>
          <label><span>父业务 *</span><select v-model="ruleForm.parent" required @change="syncRuleBusiness"><option disabled value="">请选择业务</option><option v-for="row in businesses" :key="row.id" :value="row.code">{{ row.code }} · {{ row.name }}</option></select></label>
          <label><span>所属业务 *</span><input v-model="ruleForm.business" readonly required /></label>
          <label><span>厂商 *</span><input v-model.trim="ruleForm.provider" required /></label>
          <label class="wide"><span>厂商账号 *</span><input v-model.trim="ruleForm.account" required /></label>
        </div>
        <div class="key-settings">
          <p><b>核心告警参数</b><small>以下三个字段直接影响规则触发行为</small></p>
          <div class="form-grid key-grid">
            <label>
              <span>低于阈值 *</span>
              <span class="unit-input"><input v-model="ruleForm.threshold" type="number" min="0" step="0.01" inputmode="decimal" placeholder="例：1000" required /><em>元</em></span>
            </label>
            <label>
              <span>预警浮动百分比 *</span>
              <span class="unit-input"><input v-model="ruleForm.fluctuation" type="number" min="0" max="100" step="1" required /><em>%</em></span>
            </label>
            <label><span>防抖告警跨度 *</span><input v-model.trim="ruleForm.debounce" placeholder="例：10m / 1h / 1d" pattern="[0-9]+(?:\.[0-9]+)?[mMhHdD]" title="请输入数字加单位：m 表示分钟、h 表示小时、d 表示天" required /><small class="time-help">m 分钟 · h 小时 · d 天</small></label>
          </div>
        </div>
        <div class="form-grid">
          <label><span>业务用途 *</span><input v-model.trim="ruleForm.purpose" required /></label>
          <label><span>标签 / 备注</span><input v-model.trim="ruleForm.tag" /></label>
          <label class="notify-field"><span>通知开关</span><span class="switch"><input v-model="ruleForm.enabled" type="checkbox" /><i></i><strong>{{ ruleForm.enabled ? "开启" : "关闭" }}</strong></span></label>
        </div>
        <footer><button type="button" @click="closeRuleModal">取消</button><button type="submit">保存修改</button></footer>
      </form>
    </div>
  </div>

  <div v-if="recordModalOpen" class="modal" @click.self="closeRecordStatusModal">
    <div class="modal-card status-modal-card">
      <header><div><h2>修改告警状态</h2><p v-if="editingRecord">告警 #{{ editingRecord.id }} · {{ editingRecord.business }} · {{ editingRecord.code }}</p></div><button aria-label="关闭" @click="closeRecordStatusModal">×</button></header>
      <form @submit.prevent="saveRecordStatus"><label for="recordStatus">处置状态</label><select id="recordStatus" v-model="recordStatus"><option>待处理</option><option>处理中</option><option>已确认</option><option>已忽略</option></select><footer><button type="button" @click="closeRecordStatusModal">取消</button><button type="submit">保存状态</button></footer></form>
    </div>
  </div>

  <div class="toast" :class="{ show: toastVisible }">✓　{{ toastText }}</div>
</template>
