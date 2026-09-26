"use strict";

const tubeBody = document.querySelector("#tubeTable tbody");
const resultsEl = document.getElementById("results");
const formError = document.getElementById("formError");

function makeInput(cls, placeholder, value) {
  const input = document.createElement("input");
  input.type = "text";
  input.inputMode = "decimal";
  input.className = cls;
  input.placeholder = placeholder;
  input.value = value;
  return input;
}

function addRow(conc = "", retain = "", loss = "") {
  const tr = document.createElement("tr");

  const idxTd = document.createElement("td");
  idxTd.className = "idx";

  const concTd = document.createElement("td");
  concTd.appendChild(makeInput("conc", "如 10", conc));

  const retainTd = document.createElement("td");
  retainTd.appendChild(makeInput("retain", "如 500", retain));

  const lossTd = document.createElement("td");
  lossTd.appendChild(makeInput("loss", "如 50", loss));

  const delTd = document.createElement("td");
  const delBtn = document.createElement("button");
  delBtn.type = "button";
  delBtn.className = "del";
  delBtn.title = "删除该管";
  delBtn.textContent = "×";
  delBtn.addEventListener("click", () => {
    tr.remove();
    renumber();
  });
  delTd.appendChild(delBtn);

  tr.append(idxTd, concTd, retainTd, lossTd, delTd);
  tubeBody.appendChild(tr);
  renumber();
}

function renumber() {
  [...tubeBody.rows].forEach((tr, i) => {
    tr.cells[0].textContent = i + 1;
  });
}

function clearRows() {
  tubeBody.innerHTML = "";
}

function fillExample() {
  document.getElementById("stockConc").value = "100";
  document.getElementById("pipetteMin").value = "2";
  clearRows();
  ["10", "1", "0.1", "0.01"].forEach((c) => addRow(c, "500", "50"));
}

function fillBadExample() {
  document.getElementById("stockConc").value = "100";
  document.getElementById("pipetteMin").value = "100";
  clearRows();
  addRow("10", "500", "50");
  addRow("50", "500", "50"); // 浓度次序错误：50 未低于 10
  addRow("1", "500", "50"); // 取液量将低于移液下限 100
}

async function calculate() {
  formError.hidden = true;

  const tubes = [...tubeBody.rows].map((tr) => ({
    concentration: tr.querySelector(".conc").value.trim(),
    retain_volume: tr.querySelector(".retain").value.trim(),
    loss_volume: tr.querySelector(".loss").value.trim() || "0",
  }));
  const payload = {
    stock_concentration: document.getElementById("stockConc").value.trim(),
    pipette_min: document.getElementById("pipetteMin").value.trim(),
    tubes,
  };

  let data;
  try {
    const resp = await fetch("/api/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    data = await resp.json();
    if (!resp.ok) {
      const detail = data && data.detail;
      throw new Error(
        typeof detail === "string" ? detail : "请求参数有误，请检查输入。"
      );
    }
  } catch (err) {
    formError.textContent = err.message;
    formError.hidden = false;
    resultsEl.hidden = true;
    return;
  }
  render(data);
}

function render(data) {
  const concUnit = document.getElementById("concUnit").value.trim();
  const volUnit = document.getElementById("volUnit").value.trim() || "µL";
  const cu = concUnit ? ` ${concUnit}` : "";
  const vu = ` ${volUnit}`;

  // 汇总卡片
  const summary = document.getElementById("summaryCard");
  summary.className = "card " + (data.feasible ? "ok" : "bad");
  summary.innerHTML = "";
  const h2 = document.createElement("h2");
  h2.textContent = data.feasible ? "✔ 方案可行" : "✘ 方案存在不可行步骤";
  const p1 = document.createElement("p");
  const strong = document.createElement("strong");
  strong.textContent = data.total_stock_consumption;
  p1.append("母液总消耗：", strong, `${vu}　·　目标管数：${data.tube_count}`);
  const p2 = document.createElement("p");
  p2.className = "hint";
  p2.textContent = data.feasible
    ? "所有步骤的取液量与加液量均不低于移液下限，浓度逐级递减。"
    : "红色步骤不可行：请检查浓度次序，或调整保留体积 / 预留损耗 / 移液下限。";
  summary.append(h2, p1, p2);

  // 步骤表
  const tbody = document.querySelector("#stepTable tbody");
  tbody.innerHTML = "";
  for (const s of data.steps) {
    const tr = document.createElement("tr");
    if (!s.feasible) tr.className = "bad";
    const cells = [
      s.tube,
      s.target_concentration + cu,
      s.prepare_volume + vu,
      s.source,
      s.take_volume + vu,
      s.diluent_volume + vu,
      s.retain_volume + vu,
      s.loss_volume + vu,
    ];
    for (const c of cells) {
      const td = document.createElement("td");
      td.textContent = c;
      tr.appendChild(td);
    }
    const statusTd = document.createElement("td");
    statusTd.textContent = s.feasible ? "可行" : "不可行：" + s.issues.join("；");
    tr.appendChild(statusTd);
    tbody.appendChild(tr);
  }

  // 文字步骤
  const ol = document.getElementById("stepNarrative");
  ol.innerHTML = "";
  data.steps.forEach((s, i) => {
    const li = document.createElement("li");
    if (!s.feasible) li.className = "bad";
    let text =
      `第 ${s.tube} 管：从${s.source}取 ${s.take_volume}${vu}，` +
      `加入稀释液 ${s.diluent_volume}${vu}，混匀，共 ${s.prepare_volume}${vu}` +
      `（浓度 ${s.target_concentration}${cu}）；` +
      `保留 ${s.retain_volume}${vu}，预留损耗 ${s.loss_volume}${vu}`;
    const next = data.steps[i + 1];
    text += next ? `，其余供第 ${next.tube} 管取液。` : "，该管为末管。";
    if (!s.feasible) text += "　⚠ " + s.issues.join("；");
    li.textContent = text;
    ol.appendChild(li);
  });

  resultsEl.hidden = false;
  resultsEl.scrollIntoView({ behavior: "smooth", block: "start" });
}

document.getElementById("addTube").addEventListener("click", () => addRow());
document.getElementById("fillExample").addEventListener("click", fillExample);
document.getElementById("fillBadExample").addEventListener("click", fillBadExample);
document.getElementById("calc").addEventListener("click", calculate);

// 初始填入示例，打开页面即可直接计算
fillExample();
