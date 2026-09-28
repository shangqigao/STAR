const state = {
  userId: localStorage.getItem("star_user_id") || "",
  task: null,
  imageId: null,
};

const el = {
  summary: document.querySelector("#summary"),
  activeUser: document.querySelector("#activeUser"),
  loginPanel: document.querySelector("#loginPanel"),
  workspace: document.querySelector("#workspace"),
  userId: document.querySelector("#userId"),
  userType: document.querySelector("#userType"),
  modelName: document.querySelector("#modelName"),
  startBtn: document.querySelector("#startBtn"),
  knownUsers: document.querySelector("#knownUsers"),
  assignmentAvailability: document.querySelector("#assignmentAvailability"),
  assignmentLabel: document.querySelector("#assignmentLabel"),
  phaseLabel: document.querySelector("#phaseLabel"),
  overallProgressLabel: document.querySelector("#overallProgressLabel"),
  imageCounter: document.querySelector("#imageCounter"),
  datasetBadge: document.querySelector("#datasetBadge"),
  taskImage: document.querySelector("#taskImage"),
  progressLabel: document.querySelector("#progressLabel"),
  progressBar: document.querySelector("#progressBar"),
  tabQ1: document.querySelector("#tabQ1"),
  tabQ2: document.querySelector("#tabQ2"),
  tabQSite: document.querySelector("#tabQSite"),
  tabQ4: document.querySelector("#tabQ4"),
  accuracyPanel: document.querySelector("#accuracyPanel"),
  accuracySummary: document.querySelector("#accuracySummary"),
  q1Chart: document.querySelector("#q1Chart"),
  qLymphChart: document.querySelector("#qLymphChart"),
  q2Chart: document.querySelector("#q2Chart"),
  q1ChartBlock: document.querySelector("#q1ChartBlock"),
  qLymphChartBlock: document.querySelector("#qLymphChartBlock"),
  q2ChartBlock: document.querySelector("#q2ChartBlock"),
  q1ChartLabel: document.querySelector("#q1ChartLabel"),
  qLymphChartLabel: document.querySelector("#qLymphChartLabel"),
  q2ChartLabel: document.querySelector("#q2ChartLabel"),
  answerForm: document.querySelector("#answerForm"),
  questionTitle: document.querySelector("#questionTitle"),
  questionText: document.querySelector("#questionText"),
  choiceList: document.querySelector("#choiceList"),
  submitBtn: document.querySelector("#submitBtn"),
  status: document.querySelector("#status"),
};

const CHINESE_LABELS = {
  "Chest": "胸部",
  "Abdomen": "腹部",
  "Pelvis": "盆腔",
  "Others": "其他",
  "Lung": "肺",
  "Pleura": "胸膜",
  "Mediastinum": "纵隔",
  "Mediastinal lymph node": "纵隔淋巴结",
  "Cardiophrenic lymph node": "心膈角淋巴结",
  "Subcarinal lymph node": "隆突下淋巴结",
  "Hilar lymph node": "肺门淋巴结",
  "Axillary lymph node": "腋窝淋巴结",
  "Supraclavicular lymph node": "锁骨上淋巴结",
  "Infraclavicular lymph node": "锁骨下淋巴结",
  "Internal mammary lymph node": "内乳淋巴结",
  "Paratracheal lymph node": "气管旁淋巴结",
  "Pericardial lymph node": "心包淋巴结",
  "Chest wall": "胸壁",
  "Breast": "乳腺",
  "Esophagus": "食管",
  "Paraesophageal lymph node": "食管旁淋巴结",
  "Heart / pericardium": "心脏 / 心包",
  "Thymus": "胸腺",
  "Thyroid": "甲状腺",
  "Cervical lymph node": "颈部淋巴结",
  "Neck": "颈部",
  "Diaphragm": "膈肌",
  "Diaphragmatic lymph node": "膈肌淋巴结",
  "Lymph node": "淋巴结",
  "Abdomen": "腹部",
  "Liver": "肝脏",
  "Pancreas": "胰腺",
  "Pancreatic duct": "胰管",
  "Peripancreatic lymph node": "胰周淋巴结",
  "Kidney": "肾脏",
  "Adrenal": "肾上腺",
  "Spleen": "脾脏",
  "Stomach": "胃",
  "Colon": "结肠",
  "Small bowel": "小肠",
  "Gallbladder / biliary tract": "胆囊 / 胆道",
  "Peritoneum": "腹膜",
  "Omentum": "网膜",
  "Abdominal wall": "腹壁",
  "Retroperitoneum": "腹膜后",
  "Retroperitoneal lymph node": "腹膜后淋巴结",
  "Para-aortic lymph node": "主动脉旁淋巴结",
  "Aortocaval lymph node": "主动脉腔静脉间淋巴结",
  "Paracaval lymph node": "腔静脉旁淋巴结",
  "Portacaval lymph node": "门腔间淋巴结",
  "Celiac lymph node": "腹腔干淋巴结",
  "Mesenteric lymph node": "肠系膜淋巴结",
  "Mesentery": "肠系膜",
  "Hepatic lymph node": "肝区淋巴结",
  "Perigastric lymph node": "胃周淋巴结",
  "Porta hepatis lymph node": "肝门淋巴结",
  "Retrocrural lymph node": "膈脚后淋巴结",
  "Retrocaval lymph node": "腔静脉后淋巴结",
  "Inferior vena cava": "下腔静脉",
  "Renal vein": "肾静脉",
  "Ureter": "输尿管",
  "Psoas": "腰大肌",
  "Periportal lymph node": "门静脉周围淋巴结",
  "Abdominal lymph node": "腹部淋巴结",
  "Gastroesophageal junction": "胃食管交界",
  "Gastroesophageal lymph node": "胃食管交界淋巴结",
  "Pelvic lymph node": "盆腔淋巴结",
  "Iliac lymph node": "髂血管旁淋巴结",
  "Inguinal lymph node": "腹股沟淋巴结",
  "Uterus": "子宫",
  "Cervix": "宫颈",
  "Ovary / adnexa": "卵巢 / 附件",
  "Bladder": "膀胱",
  "Prostate": "前列腺",
  "Rectum": "直肠",
  "Perirectal lymph node": "直肠周围淋巴结",
  "Vagina": "阴道",
  "Vulva": "外阴",
  "Anus": "肛门",
  "Gluteal": "臀部",
  "Pubic bone": "耻骨",
  "Pelvic bone": "骨盆骨",
  "Sacrum": "骶骨",
  "Bone": "骨",
  "Soft tissue": "软组织",
  "Other": "其他",
  "Unsure": "不确定",
  "Yes": "是",
  "No": "否",
  "No issue": "无问题",
  "Multiple acquisitions visible": "可见多个采集序列",
  "Slice misalignment or discontinuity": "切片错位或不连续",
  "Limited field of view / anatomical context": "视野 / 解剖背景有限",
  "Red overlay appears mismatched with tumor": "红色叠加区域似乎与肿瘤不匹配",
  "Other issue": "其他问题",
};

function displayChoice(value) {
  const translated = CHINESE_LABELS[value];
  return translated ? `${value} (${translated})` : value;
}

function setStatus(message, isError = false) {
  el.status.textContent = message || "";
  el.status.classList.toggle("error", isError);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || `Request failed: ${response.status}`);
    error.code = data.code;
    throw error;
  }
  return data;
}

function choice(name, value) {
  const id = `${name}_${value.replace(/[^A-Za-z0-9]+/g, "_")}`;
  const label = document.createElement("label");
  label.className = "choice";
  label.innerHTML = `
    <input type="radio" name="${name}" id="${id}" value="${value}">
    <span>${displayChoice(value)}</span>
  `;
  return label;
}

function setStage(stage) {
  for (const [name, node] of [
    ["q1", el.tabQ1],
    ["q_lymph_node", el.tabQ2],
    ["q2", el.tabQSite],
    ["q4", el.tabQ4],
  ]) {
    node.classList.toggle("active", name === stage);
  }
}

function renderTask(task) {
  state.task = task;
  el.accuracyPanel.classList.toggle("hidden", task.show_accuracy === false);
  const assignmentName = task.assignment_group
    ? (task.assignment_label || task.assignment_group.replaceAll("_", " "))
    : "";
  el.assignmentLabel.textContent = assignmentName ? `Assignment: ${assignmentName}` : "";
  el.assignmentLabel.classList.toggle("hidden", !assignmentName);
  const isPhased = Boolean(task.study_phase);
  const phaseNumber = task.study_phase === "phase_3" ? 3 : task.study_phase === "phase_2" ? 2 : 1;
  el.phaseLabel.textContent = isPhased ? `Phase ${phaseNumber}` : "";
  el.phaseLabel.classList.toggle("hidden", !isPhased);
  el.overallProgressLabel.textContent = isPhased
    ? `${task.overall_completed} / ${task.overall_total} overall`
    : "";
  el.overallProgressLabel.classList.toggle("hidden", !isPhased);
  if (task.done) {
    el.workspace.classList.remove("hidden");
    el.taskImage.removeAttribute("src");
    el.imageCounter.textContent = "Complete";
    el.datasetBadge.textContent = "Done";
    el.progressLabel.textContent = `${task.completed} / ${task.total} complete`;
    el.progressBar.style.width = "100%";
    el.questionTitle.textContent = isPhased ? "Study complete" : "All images complete";
    el.questionText.textContent = task.message;
    el.choiceList.innerHTML = "";
    el.submitBtn.disabled = true;
    setStatus("");
    return;
  }

  el.workspace.classList.remove("hidden");
  if (state.imageId !== task.image_id) {
    state.imageId = task.image_id;
    el.taskImage.src = task.image_url;
  }
  el.imageCounter.textContent = isPhased
    ? `Phase ${phaseNumber} · Image ${task.phase_completed + 1} / ${task.phase_total}`
    : `Image ${task.completed + 1} / ${task.total}`;
  el.datasetBadge.textContent = task.dataset;
  el.progressLabel.textContent = isPhased
    ? `${task.phase_completed} / ${task.phase_total} in this phase`
    : `${task.completed} / ${task.total} complete`;
  el.progressBar.style.width = `${task.total ? (task.completed / task.total) * 100 : 0}%`;
  el.submitBtn.disabled = false;
  setStage(task.stage);
  setAccuracyVisibility(task.stage);
  el.choiceList.innerHTML = "";

  if (task.stage === "q1") {
    el.questionTitle.textContent = "Q1. Region";
    el.questionText.textContent = "Which region is the tumor highlighted in red located in? Choose only one.";
    for (const region of task.regions) {
      el.choiceList.appendChild(choice("answer", region));
    }
  } else if (task.stage === "q_lymph_node") {
    el.questionTitle.textContent = "Q2. Lymph node";
    el.questionText.textContent = "Is the tumor highlighted in red located in a lymph node? Choose only one.";
    for (const answer of task.lymph_node_choices || []) {
      el.choiceList.appendChild(choice("answer", answer));
    }
  } else if (task.stage === "q2") {
    el.questionTitle.textContent = "Q3. Site";
    el.questionText.textContent = `Which site is the tumor highlighted in red located in? Region: ${task.answers.q1_region}; lymph node: ${task.answers.q_lymph_node}. Choose only one.`;
    for (const site of task.q2_choices || []) {
      el.choiceList.appendChild(choice("answer", site));
    }
  } else if (task.stage === "q4") {
    el.questionTitle.textContent = "Q4. Image quality check";
    el.questionText.textContent = "Does this image contain any visual issue that could make anatomical interpretation unreliable? Choose only one.";
    for (const issue of task.q4_choices || []) {
      el.choiceList.appendChild(choice("answer", issue));
    }
  }
  setStatus(task.phase_transition
    ? "Phase 1 complete. Continuing automatically to Phase 2."
    : "Autosave is active after every submission.");
  if (task.show_accuracy !== false) {
    loadStats().catch((error) => setStatus(error.message, true));
  }
}

function drawChart(canvas, values, totalCount = values.length) {
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  const padLeft = 34;
  const padRight = 8;
  const padTop = 8;
  const padBottom = 18;
  const plotWidth = width - padLeft - padRight;
  const plotHeight = height - padTop - padBottom;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);
  ctx.font = "11px system-ui, sans-serif";
  ctx.fillStyle = "#637083";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  ctx.strokeStyle = "#d8dee7";
  ctx.lineWidth = 1;
  for (const [value, label] of [[1, "100%"], [0.75, "75%"], [0.5, "50%"], [0.25, "25%"], [0, "0%"]]) {
    const py = padTop + (1 - value) * plotHeight;
    ctx.fillText(label, padLeft - 6, py);
    ctx.beginPath();
    ctx.moveTo(padLeft, py);
    ctx.lineTo(width - padRight, py);
    ctx.stroke();
  }
  ctx.beginPath();
  ctx.moveTo(padLeft, padTop);
  ctx.lineTo(padLeft, padTop + plotHeight);
  ctx.lineTo(width - padRight, padTop + plotHeight);
  ctx.stroke();
  if (!values.length) {
    ctx.fillStyle = "#637083";
    ctx.textAlign = "left";
    ctx.fillText("No data yet", padLeft + 8, padTop + plotHeight / 2);
    return;
  }
  ctx.strokeStyle = "#0d7c66";
  ctx.lineWidth = 2;
  ctx.beginPath();
  values.forEach((value, index) => {
    const x = values.length === 1 ? width - padRight : padLeft + (index / (values.length - 1)) * plotWidth;
    const y = padTop + (1 - value) * plotHeight;
    if (index === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  });
  ctx.stroke();
  ctx.fillStyle = "#637083";
  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
  ctx.fillText("1", padLeft, height - 4);
  ctx.textAlign = "right";
  ctx.fillText(String(totalCount || values.length), width - padRight, height - 4);
}

function percent(value) {
  return value === null || value === undefined ? "--" : `${Math.round(value * 100)}%`;
}

async function loadStats() {
  if (state.task?.show_accuracy === false) {
    return;
  }
  if (state.task?.stage === "q4") {
    el.accuracySummary.textContent = "Accuracy hidden for this question";
    return;
  }
  if (!state.userId) {
    drawChart(el.q1Chart, []);
    drawChart(el.qLymphChart, []);
    drawChart(el.q2Chart, []);
    return;
  }
  const stats = await api(`/api/stats?user_id=${encodeURIComponent(state.userId)}`);
  const completedText = stats.completed ? `${stats.completed} complete` : "No completed images";
  if (state.task?.stage === "q1") {
    el.accuracySummary.textContent = `${completedText} · Q1 region curve`;
  } else if (state.task?.stage === "q_lymph_node") {
    el.accuracySummary.textContent = `${completedText} · Q2 lymph-node curve`;
  } else if (state.task?.stage === "q2") {
    el.accuracySummary.textContent = `${completedText} · Q3 site curve`;
  } else {
    el.accuracySummary.textContent = `${completedText} · accuracy hidden for this question`;
  }
  el.q1ChartLabel.textContent = `Q1 region ${percent(stats.q1_accuracy)}`;
  el.qLymphChartLabel.textContent = `Q2 lymph node ${percent(stats.q_lymph_node_accuracy)}`;
  el.q2ChartLabel.textContent = `Q3 site ${percent(stats.q2_accuracy)}`;
  const totalCount = stats.completed || 0;
  drawChart(el.q1Chart, stats.q1_curve || [], totalCount);
  drawChart(el.qLymphChart, stats.q_lymph_node_curve || [], totalCount);
  drawChart(el.q2Chart, stats.q2_curve || [], totalCount);
}

function setAccuracyVisibility(stage) {
  el.q1ChartBlock.classList.toggle("hidden", stage !== "q1");
  el.qLymphChartBlock.classList.toggle("hidden", stage !== "q_lymph_node");
  el.q2ChartBlock.classList.toggle("hidden", stage !== "q2");
  el.accuracySummary.textContent = stage === "q1"
    ? "Q1 region curve"
    : stage === "q_lymph_node"
      ? "Q2 lymph-node curve"
    : stage === "q2"
      ? "Q3 site curve"
      : "Accuracy hidden for this question";
}

async function loadSummary() {
  const data = await api("/api/manifest-summary");
  const parts = Object.entries(data.datasets).map(([name, count]) => `${name}: ${count}`);
  el.summary.textContent = `${data.total} images loaded (${parts.join(", ")})`;
}

async function loadAssignmentAvailability() {
  const data = await api("/api/assignment-summary");
  el.assignmentAvailability.innerHTML = "";
  for (const summary of Object.values(data.roles)) {
    const item = document.createElement("span");
    item.textContent = `Radiologist groups: ${summary.available} of ${summary.total} available`;
    item.classList.toggle("unavailable", summary.available === 0);
    el.assignmentAvailability.appendChild(item);
  }
}

async function loadKnownUsers() {
  const data = await api("/api/users");
  el.knownUsers.innerHTML = "";
  if (!data.users.length) {
    return;
  }
  for (const user of data.users) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = `${user.user_id} (${user.user_type || "human"})`;
    btn.addEventListener("click", () => {
      el.userId.value = user.user_id;
      el.userType.value = user.user_type || "human";
      el.modelName.value = user.model || "";
      startUser();
    });
    el.knownUsers.appendChild(btn);
  }
}

async function startUser() {
  const userId = el.userId.value.trim();
  if (!userId) {
    setStatus("Enter a user ID first.", true);
    return;
  }
  setStatus("Starting session...");
  try {
    const data = await api("/api/users", {
      method: "POST",
      body: JSON.stringify({
        user_id: userId,
        user_type: el.userType.value,
        model: el.modelName.value.trim(),
      }),
    });
    state.userId = data.user.user_id;
    localStorage.setItem("star_user_id", state.userId);
    const assignment = data.user.assignment_group
      ? ` · ${data.user.assignment_group.replaceAll("_", " ")}`
      : "";
    el.activeUser.textContent = `${data.user.user_id} · ${data.user.user_type.replaceAll("_", " ")}${assignment}`;
    el.loginPanel.classList.add("hidden");
    renderTask(data.task);
    await loadKnownUsers();
    await loadAssignmentAvailability();
  } catch (error) {
    setStatus(error.message, true);
    await loadAssignmentAvailability();
  }
}

async function refreshCurrent() {
  if (!state.userId) return;
  const task = await api(`/api/current?user_id=${encodeURIComponent(state.userId)}`);
  renderTask(task);
}

async function submitAnswer(event) {
  event.preventDefault();
  if (!state.task || state.task.done) return;
  const selected = el.answerForm.querySelector("input[name='answer']:checked");
  if (!selected) {
    setStatus("Choose one answer before submitting.", true);
    return;
  }

  const payload = {
    user_id: state.userId,
    image_id: state.task.image_id,
    stage: state.task.stage,
  };
  if (state.task.stage === "q1") {
    payload.q1_region = selected.value;
  } else if (state.task.stage === "q_lymph_node") {
    payload.q_lymph_node = selected.value;
  } else if (state.task.stage === "q2") {
    payload.q2_site = selected.value;
  } else if (state.task.stage === "q4") {
    payload.q4_quality_issue = selected.value;
  }

  el.submitBtn.disabled = true;
  setStatus("Saving...");
  try {
    const data = await api("/api/answer", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    renderTask(data.task);
  } catch (error) {
    el.submitBtn.disabled = false;
    setStatus(error.message, true);
  }
}

el.startBtn.addEventListener("click", startUser);
el.answerForm.addEventListener("submit", submitAnswer);

async function init() {
  try {
    await loadSummary();
    await loadAssignmentAvailability();
    await loadKnownUsers();
    if (state.userId) {
      el.userId.value = state.userId;
    }
    await loadStats();
  } catch (error) {
    el.summary.textContent = error.message;
  }
}

init();
