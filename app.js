const rows = [
  { id: 1, code: "534784", name: "短信商", tag: "SMS-GATEWAY", rules: 14, enabled: true, time: "2024-03-01 10:24", tone: "green" },
  { id: 2, code: "882190", name: "支付网关", tag: "CORE-FIN", rules: 32, enabled: true, time: "2024-03-02 14:10", tone: "orange" },
  { id: 3, code: "319024", name: "物流推送", tag: "EXPRESS", rules: 6, enabled: false, time: "2024-03-05 09:12", tone: "gray" },
  { id: 4, code: "671042", name: "邮件服务", tag: "SMTP-RELAY", rules: 8, enabled: true, time: "2024-03-08 16:55", tone: "green" },
  { id: 5, code: "920411", name: "身份认证通道", tag: "OAUTH-IAM", rules: 21, enabled: true, time: "2024-03-12 11:30", tone: "orange" },
];

const stats = [
  { icon: "⌘", label: "接入业务总数", value: "28", note: "+3 个月" },
  { icon: "♢", label: "开启通知业务", value: "24", note: "/ 28" },
  { icon: "◴", label: "今日触发总次", value: "1,409", note: "次" },
];
const viewTitles = { overview: "控制台总览", rules: "告警设置", records: "告警记录", channels: "推送通道", settings: "系统配置" };
const ruleRows = [
  { code:"664851", parent:"534784", business:"短信商", provider:"阿里云", account:"123alibab", threshold:"< ¥1,000", fluctuation:50, debounce:"1d", purpose:"银行卡", tag:"关联业务为B", enabled:true },
  { code:"379465", parent:"534784", business:"短信商", provider:"华为云", account:"333alibab", threshold:"< ¥1,000", fluctuation:40, debounce:"1h", purpose:"备用专线", tag:"暂停充值", enabled:true },
  { code:"725076", parent:"534784", business:"短信商", provider:"阿里云", account:"222alibab", threshold:"< ¥1,000", fluctuation:20, debounce:"10m", purpose:"高敏通道", tag:"暂停充值-用完截至", enabled:true },
  { code:"164534", parent:"534784", business:"短信商", provider:"阿里云", account:"443alibab", threshold:"< ¥1,000", fluctuation:10, debounce:"1d", purpose:"兜底通道", tag:"暂停充值-用完截至", enabled:true },
];
const recordRows = [
  { id:1,time:"13:00:24",date:"2024-05-18",code:"664851",business:"短信商",provider:"阿里云",account:"123alibab",type:"余额低于阈值",value:"当前余额: ¥84.20",detail:"可用额度不足最低配置预警线(¥500.00)，预计15分钟内短信分发将阻断",status:"待处理",level:"warning" },
  { id:2,time:"13:00:10",date:"2024-05-18",code:"664851",business:"短信商",provider:"阿里云",account:"222alibab",type:"浮动百分比超出预设",value:"瞬时消耗环比 +340%",detail:"5分钟内验证码发送激增，单IP突发速率偏离常规业务基线",status:"处理中",level:"processing" },
  { id:3,time:"12:58:45",date:"2024-05-18",code:"781290",business:"支付网关",provider:"华为云",account:"333alibab",type:"接口调用超时",value:"Gateway Timeout: 504 (8200ms)",detail:"微信与银联代扣回调出现丢包，核心账本服务已自动切入熔断旁路",status:"待处理",level:"danger" },
  { id:4,time:"12:45:02",date:"2024-05-18",code:"550219",business:"实名认证 OCR",provider:"阿里云",account:"889alibab",type:"调用配额不足 10%",value:"剩余调用: 12,400 次",detail:"每日包年包月调用包消耗加速，运维建议及时增购扩容",status:"已确认",level:"confirmed" },
  { id:5,time:"12:15:30",date:"2024-05-18",code:"901432",business:"动态 CDN",provider:"华为云",account:"hw-cdn-edge01",type:"边缘节点回源重试",value:"Retry Count: 3",detail:"华南区域部分节点解析抖动，已触发自愈路由自动解析切换",status:"已忽略",level:"ignored" },
];

document.querySelector("#stats").innerHTML = stats.map(item => `<article class="stat-card"><span class="stat-icon">${item.icon}</span><div><small>${item.label}</small><strong>${item.value}<span>${item.note}</span></strong></div></article>`).join("");

function renderRows() {
  const query = document.querySelector("#searchInput").value.trim().toLowerCase();
  const status = document.querySelector("#statusFilter").value;
  const filtered = rows.filter(row => (!query || `${row.code}${row.name}${row.tag}`.toLowerCase().includes(query)) && (status === "all" || (status === "enabled") === row.enabled));
  document.querySelector("#billingTable").innerHTML = filtered.length ? filtered.map(row => `<tr data-id="${row.id}">
    <td><input class="row-check" type="checkbox" /></td><td class="metric">${row.id}</td><td><span class="code">${row.code}</span></td>
    <td><div class="account-cell"><i class="tone-${row.tone}"></i><b>${row.name}</b><small class="business-tag tone-${row.tone}">${row.tag}</small></div></td>
    <td class="metric">${row.rules} 条监控流</td>
    <td><label class="switch"><input type="checkbox" ${row.enabled ? "checked" : ""} data-toggle="${row.id}"/><i></i><span>${row.enabled ? "开启" : "暂停"}</span></label></td><td class="metric time-cell">${row.time}</td>
    <td><div class="row-actions"><button data-action="detail">详情</button><button data-action="edit">编辑</button><button data-action="delete">删除</button></div></td></tr>`).join("") : `<tr><td colspan="8" style="text-align:center;color:#89959f">没有符合条件的告警业务</td></tr>`;
  document.querySelector("#totalCount").textContent = filtered.length === rows.length ? "28" : filtered.length;
  bindRowEvents();
}

function renderRules() {
  const query = document.querySelector("#ruleSearch")?.value.trim().toLowerCase() || "";
  const list = ruleRows.filter(row => !query || Object.values(row).join(" ").toLowerCase().includes(query));
  document.querySelector("#rulesTable").innerHTML = list.map(row => `<tr><td><b class="rule-code">#${row.code}</b><small>（父ID: ${row.parent}）</small></td><td><span class="dot green"></span>${row.business}</td><td><b>${row.provider}</b><small class="block">${row.account}</small></td><td><span class="threshold">${row.threshold}</span></td><td><div class="percent-cell"><i><b style="width:${row.fluctuation}%"></b></i><span>${row.fluctuation}%</span></div></td><td><span class="debounce">${row.debounce}</span></td><td><b>${row.purpose}</b><small class="block muted-copy">${row.tag}</small></td><td><label class="switch"><input type="checkbox" ${row.enabled?"checked":""} data-rule-toggle="${row.code}"/><i></i></label></td><td><div class="rule-actions"><button data-rule-action="test" data-code="${row.code}">♧ 测试</button><button data-rule-action="edit" data-code="${row.code}">编辑</button><button data-rule-action="delete" data-code="${row.code}">删除</button></div></td></tr>`).join("");
  bindRuleEvents();
}

function bindRuleEvents() {
  document.querySelectorAll("[data-rule-toggle]").forEach(input => input.addEventListener("change", event => {
    const row = ruleRows.find(item => item.code === event.target.dataset.ruleToggle);
    row.enabled = event.target.checked; toast(`规则 #${row.code} 通知已${row.enabled ? "开启" : "关闭"}`);
  }));
  document.querySelectorAll("[data-rule-action]").forEach(button => button.addEventListener("click", event => {
    const code = event.currentTarget.dataset.code;
    const row = ruleRows.find(item => item.code === code);
    const action = event.currentTarget.dataset.ruleAction;
    if (action === "test") return toast(`规则 #${code} 测试告警已触发`);
    if (action === "edit") return openRuleModal(row);
    if (action === "delete" && window.confirm(`确认删除告警规则 #${code}？`)) {
      ruleRows.splice(ruleRows.indexOf(row), 1); renderRules(); toast(`规则 #${code} 已删除`);
    }
  }));
}

function openRuleModal(row) {
  document.querySelector("#editingRuleCode").value = row.code;
  document.querySelector("#editRuleCode").value = row.code;
  document.querySelector("#editRuleParent").value = row.parent;
  document.querySelector("#editRuleBusiness").value = row.business;
  document.querySelector("#editRuleProvider").value = row.provider;
  document.querySelector("#editRuleAccount").value = row.account;
  document.querySelector("#editRuleThreshold").value = row.threshold.replace(/[^\d.]/g, "");
  document.querySelector("#editRuleFluctuation").value = row.fluctuation;
  document.querySelector("#editRuleDebounce").value = row.debounce;
  document.querySelector("#editRulePurpose").value = row.purpose;
  document.querySelector("#editRuleTag").value = row.tag;
  document.querySelector("#editRuleEnabled").checked = row.enabled;
  document.querySelector("#editRuleEnabledText").textContent = row.enabled ? "开启" : "关闭";
  document.querySelector("#ruleModal").hidden = false;
}

function closeRuleModal() { document.querySelector("#ruleModal").hidden = true; }

function renderRecords() {
  const query = document.querySelector("#recordSearch")?.value.trim().toLowerCase() || "";
  const list = recordRows.filter(row => !query || Object.values(row).join(" ").toLowerCase().includes(query));
  document.querySelector("#recordsTable").innerHTML = list.length ? list.map(row => `<tr><td><input type="checkbox" /></td><td class="metric">#${row.id}</td><td><b class="record-time">${row.time}</b><small class="block">${row.date}</small></td><td><b class="rule-code">${row.code}</b></td><td><span class="dot ${row.id===2?"orange":"green"}"></span>${row.business}</td><td><span class="provider-badge">${row.provider}</span><small class="block">${row.account}</small></td><td><div class="alert-copy"><b class="${row.level}">${row.type}</b><strong>${row.value}</strong><small>${row.detail}</small></div></td><td><span class="status-badge ${row.level}">${row.status}</span></td><td><div class="record-actions"><button data-record-action="status" data-id="${row.id}">修改状态</button><button data-record-action="delete" data-id="${row.id}">删除</button></div></td></tr>`).join("") : `<tr><td colspan="9" style="text-align:center;color:#89959f">没有符合条件的告警记录</td></tr>`;
  bindRecordEvents();
}

function bindRecordEvents() {
  document.querySelectorAll("[data-record-action]").forEach(button => button.addEventListener("click", event => {
    const row = recordRows.find(item => item.id === Number(event.currentTarget.dataset.id));
    if (event.currentTarget.dataset.recordAction === "status") return openRecordStatusModal(row);
    if (window.confirm(`确认删除告警记录 #${row.id}？`)) {
      recordRows.splice(recordRows.indexOf(row), 1); renderRecords(); toast(`告警记录 #${row.id} 已删除`);
    }
  }));
}

function openRecordStatusModal(row) {
  document.querySelector("#editingRecordId").value = row.id;
  document.querySelector("#editRecordStatus").value = row.status;
  document.querySelector("#recordStatusDescription").textContent = `告警 #${row.id} · ${row.business} · ${row.code}`;
  document.querySelector("#recordStatusModal").hidden = false;
}

function closeRecordStatusModal() { document.querySelector("#recordStatusModal").hidden = true; }
function statusLevel(status) { return { "待处理":"warning", "处理中":"processing", "已确认":"confirmed", "已忽略":"ignored" }[status]; }

function bindRowEvents() {
  document.querySelectorAll("[data-toggle]").forEach(input => input.addEventListener("change", event => {
    const row = rows.find(item => item.id === Number(event.target.dataset.toggle)); row.enabled = event.target.checked; renderRows(); toast(`${row.name}通知已${row.enabled ? "开启" : "暂停"}`);
  }));
  document.querySelectorAll("[data-action]").forEach(button => button.addEventListener("click", event => {
    const tr = event.target.closest("tr"); const row = rows.find(item => item.id === Number(tr.dataset.id));
    if (event.target.dataset.action === "delete") return toast(`演示模式：未删除 ${row.name}`);
    if (event.target.dataset.action === "edit") return openModal(row);
    toast(`${row.name}：${row.rules} 条监控流，接入时间 ${row.time}`);
  }));
}

function selectedRows() { return [...document.querySelectorAll(".row-check:checked")].map(box => Number(box.closest("tr").dataset.id)); }
function batchSet(enabled) { const selected = selectedRows(); if (!selected.length) return toast("请先选择告警业务"); rows.filter(row => selected.includes(row.id)).forEach(row => row.enabled = enabled); renderRows(); toast(`已批量${enabled ? "启用" : "停用"} ${selected.length} 个业务`); }

function openModal(row) {
  document.querySelector("#accountModal").hidden = false;
  document.querySelector("#formName").value = row?.name || ""; document.querySelector("#formCode").value = row?.code || ""; document.querySelector("#formPrice").value = "";
}
function closeModal() { document.querySelector("#accountModal").hidden = true; document.querySelector("#accountForm").reset(); }
function toast(message) { const el = document.querySelector("#toast"); el.textContent = `✓　${message}`; el.classList.add("show"); clearTimeout(toast.timer); toast.timer = setTimeout(() => el.classList.remove("show"), 2200); }

document.querySelector("#loginForm").addEventListener("submit", event => {
  event.preventDefault(); const user = document.querySelector("#username").value.trim(); const pass = document.querySelector("#password").value;
  if (!user || !pass) { document.querySelector("#loginError").textContent = "请输入完整的登录账号和密码"; return; }
  document.querySelector("#loginScreen").hidden = true; document.querySelector("#app").hidden = false; toast("认证成功，已进入监控工作台");
});
document.querySelector("#togglePassword").addEventListener("click", () => { const input = document.querySelector("#password"); input.type = input.type === "password" ? "text" : "password"; });
document.querySelector("#searchInput").addEventListener("input", renderRows); document.querySelector("#statusFilter").addEventListener("change", renderRows);
document.querySelector("#ruleSearch").addEventListener("input", renderRules); document.querySelector("#recordSearch").addEventListener("input", renderRecords);
document.querySelector("#selectAll").addEventListener("change", event => document.querySelectorAll(".row-check").forEach(box => box.checked = event.target.checked));
document.querySelector("#batchEnable").addEventListener("click", () => batchSet(true)); document.querySelector("#batchDisable").addEventListener("click", () => batchSet(false));
document.querySelector("#addAccount").addEventListener("click", () => openModal()); document.querySelector("#closeModal").addEventListener("click", closeModal); document.querySelector("#cancelModal").addEventListener("click", closeModal);
document.querySelector("#randomCode").addEventListener("click", () => document.querySelector("#formCode").value = String(Math.floor(100000 + Math.random() * 900000)));
document.querySelector("#accountForm").addEventListener("submit", event => { event.preventDefault(); closeModal(); toast("告警业务已保存"); });
document.querySelector("#closeRuleModal").addEventListener("click", closeRuleModal);
document.querySelector("#cancelRuleModal").addEventListener("click", closeRuleModal);
document.querySelector("#editRuleEnabled").addEventListener("change", event => { document.querySelector("#editRuleEnabledText").textContent = event.target.checked ? "开启" : "关闭"; });
document.querySelector("#ruleForm").addEventListener("submit", event => {
  event.preventDefault();
  const originalCode = document.querySelector("#editingRuleCode").value;
  const row = ruleRows.find(item => item.code === originalCode);
  const nextCode = document.querySelector("#editRuleCode").value.trim().replace(/^#/, "");
  if (ruleRows.some(item => item !== row && item.code === nextCode)) return toast(`唯一编码 #${nextCode} 已存在`);
  const thresholdNumber = Number(document.querySelector("#editRuleThreshold").value.replace(/[^\d.]/g, ""));
  row.code = nextCode;
  row.parent = document.querySelector("#editRuleParent").value.trim();
  row.business = document.querySelector("#editRuleBusiness").value.trim();
  row.provider = document.querySelector("#editRuleProvider").value.trim();
  row.account = document.querySelector("#editRuleAccount").value.trim();
  row.threshold = `< ¥${thresholdNumber.toLocaleString("zh-CN")}`;
  row.fluctuation = Number(document.querySelector("#editRuleFluctuation").value);
  row.debounce = document.querySelector("#editRuleDebounce").value.trim().toLowerCase();
  row.purpose = document.querySelector("#editRulePurpose").value.trim();
  row.tag = document.querySelector("#editRuleTag").value.trim();
  row.enabled = document.querySelector("#editRuleEnabled").checked;
  closeRuleModal(); renderRules(); toast(`规则 #${row.code} 已保存`);
});
document.querySelector("#closeRecordStatusModal").addEventListener("click", closeRecordStatusModal);
document.querySelector("#cancelRecordStatusModal").addEventListener("click", closeRecordStatusModal);
document.querySelector("#recordStatusForm").addEventListener("submit", event => {
  event.preventDefault();
  const row = recordRows.find(item => item.id === Number(document.querySelector("#editingRecordId").value));
  row.status = document.querySelector("#editRecordStatus").value;
  row.level = statusLevel(row.status);
  closeRecordStatusModal(); renderRecords(); toast(`告警记录 #${row.id} 状态已修改为“${row.status}”`);
});
document.querySelector("#refreshBtn").addEventListener("click", () => { renderRows(); toast("业务数据已刷新"); });
document.querySelector("#mobileMenu").addEventListener("click", () => document.querySelector("#sidebar").classList.toggle("open"));
document.querySelectorAll("[data-view]").forEach(button => button.addEventListener("click", () => {
  const view = button.dataset.view;
  document.querySelectorAll(".nav-item").forEach(item => item.classList.toggle("active", item.dataset.view === view));
  document.querySelector("#billingView").hidden = view !== "billing";
  document.querySelector("#rulesView").hidden = view !== "rules";
  document.querySelector("#recordsView").hidden = view !== "records";
  document.querySelector("#emptyView").hidden = ["billing","rules","records"].includes(view);
  document.querySelector("#emptyTitle").textContent = viewTitles[view] || "告警业务";
  document.querySelector("#sidebar").classList.remove("open");
}));

renderRows(); renderRules(); renderRecords();
