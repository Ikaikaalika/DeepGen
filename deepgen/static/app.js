const state = {
  sessionId: null,
  livingPeople: [],
};

async function request(url, options = {}) {
  const res = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed (${res.status})`);
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res.text();
}

function setText(id, value) {
  document.getElementById(id).textContent = value;
}

function renderLivingPeople() {
  const tbody = document.querySelector("#living-table tbody");
  tbody.innerHTML = "";
  for (const person of state.livingPeople) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${person.name}</td>
      <td>${person.xref}</td>
      <td>${person.birth_date || ""}</td>
      <td><input type="checkbox" data-field="can_use_data" data-id="${person.id}" ${person.can_use_data ? "checked" : ""}></td>
      <td><input type="checkbox" data-field="can_llm_research" data-id="${person.id}" ${person.can_llm_research ? "checked" : ""}></td>
    `;
    tbody.appendChild(tr);
  }
}

async function loadProviderConfig() {
  const configs = await request("/api/providers/config");
  const byProvider = Object.fromEntries(configs.map((c) => [c.provider, c.values]));
  document.getElementById("llm-backend").value = (byProvider.llm?.backend || "openai");
  document.getElementById("openai-model").value = (byProvider.openai?.model || "gpt-4.1-mini");
  document.getElementById("mlx-model").value = (byProvider.mlx?.model || "mlx-community/Llama-3.2-3B-Instruct-4bit");
}

async function saveProviderConfig() {
  const llmBackend = document.getElementById("llm-backend").value;
  const openaiApiKey = document.getElementById("openai-api-key").value.trim();
  const openaiModel = document.getElementById("openai-model").value.trim();
  const mlxModel = document.getElementById("mlx-model").value.trim();
  const familyClientId = document.getElementById("family-client-id").value.trim();
  const familyClientSecret = document.getElementById("family-client-secret").value.trim();
  const naraApiKey = document.getElementById("nara-api-key").value.trim();

  await request("/api/providers/config/llm", {
    method: "PUT",
    body: JSON.stringify({ values: { backend: llmBackend } }),
  });
  await request("/api/providers/config/openai", {
    method: "PUT",
    body: JSON.stringify({ values: { api_key: openaiApiKey, model: openaiModel } }),
  });
  await request("/api/providers/config/mlx", {
    method: "PUT",
    body: JSON.stringify({ values: { model: mlxModel, enabled: "true" } }),
  });
  await request("/api/providers/config/familysearch", {
    method: "PUT",
    body: JSON.stringify({ values: { client_id: familyClientId, client_secret: familyClientSecret } }),
  });
  await request("/api/providers/config/nara", {
    method: "PUT",
    body: JSON.stringify({ values: { api_key: naraApiKey } }),
  });
}

async function uploadGedcom() {
  const input = document.getElementById("gedcom-file");
  if (!input.files.length) throw new Error("Select a GEDCOM file first.");
  const form = new FormData();
  form.append("file", input.files[0]);
  const res = await fetch("/api/sessions/upload", { method: "POST", body: form });
  if (!res.ok) {
    throw new Error(await res.text());
  }
  const data = await res.json();
  state.sessionId = data.session_id;
  setText(
    "upload-status",
    `Session ${data.session_id} | Version ${data.gedcom_version} | People ${data.person_count} | Living ${data.living_count}`
  );
  await loadLivingPeople();
}

async function loadLivingPeople() {
  if (!state.sessionId) return;
  state.livingPeople = await request(`/api/sessions/${state.sessionId}/living-people`);
  renderLivingPeople();
}

async function saveConsent(markAll = false) {
  if (!state.sessionId) throw new Error("Upload GEDCOM first.");
  let payload = { updates: [] };
  if (markAll) {
    payload = {
      updates: [],
      mark_all: {
        can_use_data: document.getElementById("mark-all-data").checked,
        can_llm_research: document.getElementById("mark-all-llm").checked,
      },
    };
  } else {
    const rows = [...document.querySelectorAll("#living-table tbody tr")];
    payload.updates = rows.map((row) => {
      const dataInput = row.querySelector('input[data-field="can_use_data"]');
      const llmInput = row.querySelector('input[data-field="can_llm_research"]');
      return {
        person_id: Number(dataInput.getAttribute("data-id")),
        can_use_data: dataInput.checked,
        can_llm_research: llmInput.checked,
      };
    });
  }
  state.livingPeople = await request(`/api/sessions/${state.sessionId}/living-consent`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  renderLivingPeople();
}

async function loadGaps() {
  if (!state.sessionId) throw new Error("Upload GEDCOM first.");
  const gaps = await request(`/api/sessions/${state.sessionId}/gaps`);
  const list = document.getElementById("gap-list");
  list.innerHTML = "";
  for (const gap of gaps) {
    const li = document.createElement("li");
    li.textContent = `${gap.name} (${gap.xref}) | missing father: ${gap.missing_father} | missing mother: ${gap.missing_mother}`;
    list.appendChild(li);
  }
}

async function runResearch() {
  if (!state.sessionId) throw new Error("Upload GEDCOM first.");
  const payload = { max_people: 10 };
  const result = await request(`/api/sessions/${state.sessionId}/research/run`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  document.getElementById("research-output").textContent = JSON.stringify(result, null, 2);
}

async function exportGedcom() {
  if (!state.sessionId) throw new Error("Upload GEDCOM first.");
  const version = document.getElementById("export-version").value;
  const text = await request(`/api/sessions/${state.sessionId}/export?version=${version}`, {
    headers: {},
  });
  const blob = new Blob([text], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const link = document.getElementById("download-link");
  link.href = url;
  link.download = `deepgen_${state.sessionId}_${version}.ged`;
  link.textContent = "Download Export (ready)";
}

document.getElementById("save-config").addEventListener("click", async () => {
  try {
    await saveProviderConfig();
    setText("config-status", "Provider config saved.");
  } catch (err) {
    setText("config-status", `Error: ${err.message}`);
  }
});

document.getElementById("upload-btn").addEventListener("click", async () => {
  try {
    await uploadGedcom();
  } catch (err) {
    setText("upload-status", `Error: ${err.message}`);
  }
});

document.getElementById("mark-all-btn").addEventListener("click", async () => {
  try {
    await saveConsent(true);
  } catch (err) {
    setText("upload-status", `Error: ${err.message}`);
  }
});

document.getElementById("save-consent").addEventListener("click", async () => {
  try {
    await saveConsent(false);
  } catch (err) {
    setText("upload-status", `Error: ${err.message}`);
  }
});

document.getElementById("load-gaps").addEventListener("click", async () => {
  try {
    await loadGaps();
  } catch (err) {
    setText("upload-status", `Error: ${err.message}`);
  }
});

document.getElementById("run-research").addEventListener("click", async () => {
  try {
    await runResearch();
  } catch (err) {
    document.getElementById("research-output").textContent = `Error: ${err.message}`;
  }
});

document.getElementById("export-btn").addEventListener("click", async () => {
  try {
    await exportGedcom();
  } catch (err) {
    setText("upload-status", `Error: ${err.message}`);
  }
});

loadProviderConfig().catch((err) => {
  setText("config-status", `Error: ${err.message}`);
});
