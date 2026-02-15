const state = {
  sessionId: null,
  researchJobId: null,
  researchProposals: [],
  researchQuestions: [],
  livingPeople: [],
  people: [],
  peopleByXref: {},
  childrenByParent: new Map(),
  capabilities: {
    mlx_installed: false,
    vision_installed: false,
    ocr_installed: false,
  },
  tree: {
    rootXref: null,
    mode: "ancestors",
    generations: 4,
    transform: { x: 0, y: 0, k: 1 },
    bounds: null,
    didPan: false,
    _hasInteractions: false,
  },
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

const SVG_NS = "http://www.w3.org/2000/svg";
const TREE_NODE_W = 172;
const TREE_NODE_H = 56;
const TREE_GAP_X = 44;
const TREE_GAP_Y = 90;

function svgEl(name, attrs = {}) {
  const el = document.createElementNS(SVG_NS, name);
  for (const [k, v] of Object.entries(attrs)) {
    el.setAttribute(k, String(v));
  }
  return el;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function extractYear(value) {
  if (!value) return null;
  const m = String(value).match(/(\d{4})/g);
  if (!m || !m.length) return null;
  const year = Number(m[m.length - 1]);
  return Number.isFinite(year) ? year : null;
}

function truncate(value, max = 26) {
  const text = String(value || "");
  if (text.length <= max) return text;
  return `${text.slice(0, Math.max(0, max - 1))}…`;
}

function formatLifespan(person) {
  const by = person.birth_year ?? extractYear(person.birth_date);
  const dy = extractYear(person.death_date);
  if (by && dy) return `${by}\u2013${dy}`;
  if (by && !dy) return person.is_living ? `b. ${by} (living)` : `b. ${by}`;
  if (!by && dy) return `d. ${dy}`;
  return person.is_living ? "living" : "";
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
  document.getElementById("llm-backend").value = byProvider.llm?.backend || "openai";
  document.getElementById("openai-model").value = byProvider.openai?.model || "gpt-4.1-mini";
  document.getElementById("anthropic-model").value = byProvider.anthropic?.model || "claude-3-5-sonnet-latest";
  document.getElementById("mlx-model").value = byProvider.mlx?.model || "mlx-community/Llama-3.2-3B-Instruct-4bit";
  document.getElementById("family-client-id").value = byProvider.familysearch?.client_id || "";
  document.getElementById("family-access-token").value = byProvider.familysearch?.access_token || "";
  document.getElementById("nara-api-key").value = byProvider.nara?.api_key || "";
  document.getElementById("loc-api-key").value = byProvider.loc?.api_key || "";
  document.getElementById("census-enabled").value = byProvider.census?.enabled || "false";
  document.getElementById("census-api-key").value = byProvider.census?.api_key || "";
  document.getElementById("gnis-enabled").value = byProvider.gnis?.enabled || "false";
  document.getElementById("gnis-dataset-path").value = byProvider.gnis?.dataset_path || "";
  document.getElementById("geonames-enabled").value = byProvider.geonames?.enabled || "false";
  document.getElementById("geonames-username").value = byProvider.geonames?.username || "";
  document.getElementById("wikidata-enabled").value = byProvider.wikidata?.enabled || "true";
  document.getElementById("europeana-enabled").value = byProvider.europeana?.enabled || "false";
  document.getElementById("europeana-api-key").value = byProvider.europeana?.api_key || "";
  document.getElementById("openrefine-enabled").value = byProvider.openrefine?.enabled || "false";
  document.getElementById("openrefine-service-url").value = byProvider.openrefine?.service_url || "";
  document.getElementById("social-enabled").value = byProvider.social?.enabled || "false";
  document.getElementById("social-x-enabled").value = byProvider.social?.x_enabled || "true";
  document.getElementById("social-linkedin-enabled").value = byProvider.social?.linkedin_enabled || "true";
  document.getElementById("social-reddit-enabled").value = byProvider.social?.reddit_enabled || "true";
  document.getElementById("social-github-enabled").value = byProvider.social?.github_enabled || "true";
  document.getElementById("social-facebook-enabled").value = byProvider.social?.facebook_enabled || "false";
  document.getElementById("social-instagram-enabled").value = byProvider.social?.instagram_enabled || "false";
  document.getElementById("social-bluesky-enabled").value = byProvider.social?.bluesky_enabled || "false";
  document.getElementById("local-folder-path").value = byProvider.local?.folder_path || "";
  document.getElementById("local-enabled").value = byProvider.local?.enabled || "false";
  document.getElementById("face-threshold").value = byProvider.face?.threshold || "0.52";
}

async function refreshAppStatus() {
  const result = await request("/api/health", { headers: {} });
  state.capabilities.mlx_installed = Boolean(result.mlx_installed);
  state.capabilities.vision_installed = Boolean(result.vision_installed);
  state.capabilities.ocr_installed = Boolean(result.ocr_installed);
  applyCapabilityUI();
  document.getElementById("app-status-output").textContent = JSON.stringify(result, null, 2);
}

function applyCapabilityUI() {
  const mlxOk = state.capabilities.mlx_installed;
  const visionOk = state.capabilities.vision_installed;

  const backend = document.getElementById("llm-backend");
  if (backend) {
    const mlxOption = backend.querySelector('option[value="mlx"]');
    if (mlxOption) {
      mlxOption.disabled = !mlxOk;
      mlxOption.textContent = mlxOk ? "mlx" : "mlx (not bundled)";
    }
    if (!mlxOk && backend.value === "mlx") backend.value = "openai";
  }

  const faceBtn = document.getElementById("run-face-pair");
  if (faceBtn) {
    faceBtn.disabled = !visionOk;
    faceBtn.title = visionOk ? "" : "Face pairing is not bundled in this build.";
  }
}

async function checkUpdates() {
  const result = await request("/api/app/update-check", { headers: {} });
  document.getElementById("app-status-output").textContent = JSON.stringify(result, null, 2);
}

async function saveProviderConfig() {
  const llmBackend = document.getElementById("llm-backend").value;
  const openaiApiKey = document.getElementById("openai-api-key").value.trim();
  const openaiModel = document.getElementById("openai-model").value.trim() || "gpt-4.1-mini";
  const anthropicApiKey = document.getElementById("anthropic-api-key").value.trim();
  const anthropicModel = document.getElementById("anthropic-model").value.trim() || "claude-3-5-sonnet-latest";
  const mlxModel = document.getElementById("mlx-model").value.trim() || "mlx-community/Llama-3.2-3B-Instruct-4bit";
  const familyClientId = document.getElementById("family-client-id").value.trim();
  const familyClientSecret = document.getElementById("family-client-secret").value.trim();
  const familyAccessToken = document.getElementById("family-access-token").value.trim();
  const naraApiKey = document.getElementById("nara-api-key").value.trim();
  const locApiKey = document.getElementById("loc-api-key").value.trim();
  const censusEnabled = document.getElementById("census-enabled").value;
  const censusApiKey = document.getElementById("census-api-key").value.trim();
  const gnisEnabled = document.getElementById("gnis-enabled").value;
  const gnisDatasetPath = document.getElementById("gnis-dataset-path").value.trim();
  const geonamesEnabled = document.getElementById("geonames-enabled").value;
  const geonamesUsername = document.getElementById("geonames-username").value.trim();
  const wikidataEnabled = document.getElementById("wikidata-enabled").value;
  const europeanaEnabled = document.getElementById("europeana-enabled").value;
  const europeanaApiKey = document.getElementById("europeana-api-key").value.trim();
  const openrefineEnabled = document.getElementById("openrefine-enabled").value;
  const openrefineServiceUrl = document.getElementById("openrefine-service-url").value.trim();
  const socialEnabled = document.getElementById("social-enabled").value;
  const socialXEnabled = document.getElementById("social-x-enabled").value;
  const socialLinkedinEnabled = document.getElementById("social-linkedin-enabled").value;
  const socialRedditEnabled = document.getElementById("social-reddit-enabled").value;
  const socialGithubEnabled = document.getElementById("social-github-enabled").value;
  const socialFacebookEnabled = document.getElementById("social-facebook-enabled").value;
  const socialInstagramEnabled = document.getElementById("social-instagram-enabled").value;
  const socialBlueskyEnabled = document.getElementById("social-bluesky-enabled").value;
  const localFolderPath = document.getElementById("local-folder-path").value.trim();
  const localEnabled = document.getElementById("local-enabled").value;
  const faceThreshold = document.getElementById("face-threshold").value.trim() || "0.52";

  await request("/api/providers/config/llm", {
    method: "PUT",
    body: JSON.stringify({ values: { backend: llmBackend } }),
  });
  await request("/api/providers/config/openai", {
    method: "PUT",
    body: JSON.stringify({ values: { api_key: openaiApiKey, model: openaiModel } }),
  });
  await request("/api/providers/config/anthropic", {
    method: "PUT",
    body: JSON.stringify({ values: { api_key: anthropicApiKey, model: anthropicModel } }),
  });
  await request("/api/providers/config/mlx", {
    method: "PUT",
    body: JSON.stringify({ values: { model: mlxModel, enabled: "true" } }),
  });
  await request("/api/providers/config/familysearch", {
    method: "PUT",
    body: JSON.stringify({
      values: {
        client_id: familyClientId,
        client_secret: familyClientSecret,
        access_token: familyAccessToken,
      },
    }),
  });
  await request("/api/providers/config/nara", {
    method: "PUT",
    body: JSON.stringify({ values: { api_key: naraApiKey } }),
  });
  await request("/api/providers/config/loc", {
    method: "PUT",
    body: JSON.stringify({ values: { api_key: locApiKey } }),
  });
  await request("/api/providers/config/census", {
    method: "PUT",
    body: JSON.stringify({ values: { enabled: censusEnabled, api_key: censusApiKey } }),
  });
  await request("/api/providers/config/gnis", {
    method: "PUT",
    body: JSON.stringify({ values: { enabled: gnisEnabled, dataset_path: gnisDatasetPath } }),
  });
  await request("/api/providers/config/geonames", {
    method: "PUT",
    body: JSON.stringify({ values: { enabled: geonamesEnabled, username: geonamesUsername } }),
  });
  await request("/api/providers/config/wikidata", {
    method: "PUT",
    body: JSON.stringify({ values: { enabled: wikidataEnabled } }),
  });
  await request("/api/providers/config/europeana", {
    method: "PUT",
    body: JSON.stringify({ values: { enabled: europeanaEnabled, api_key: europeanaApiKey } }),
  });
  await request("/api/providers/config/openrefine", {
    method: "PUT",
    body: JSON.stringify({ values: { enabled: openrefineEnabled, service_url: openrefineServiceUrl } }),
  });
  await request("/api/providers/config/social", {
    method: "PUT",
    body: JSON.stringify({
      values: {
        enabled: socialEnabled,
        x_enabled: socialXEnabled,
        linkedin_enabled: socialLinkedinEnabled,
        reddit_enabled: socialRedditEnabled,
        github_enabled: socialGithubEnabled,
        facebook_enabled: socialFacebookEnabled,
        instagram_enabled: socialInstagramEnabled,
        bluesky_enabled: socialBlueskyEnabled,
      },
    }),
  });
  await request("/api/providers/config/local", {
    method: "PUT",
    body: JSON.stringify({ values: { folder_path: localFolderPath, enabled: localEnabled } }),
  });
  await request("/api/providers/config/face", {
    method: "PUT",
    body: JSON.stringify({ values: { enabled: "true", threshold: faceThreshold } }),
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
  state.researchJobId = null;
  state.researchProposals = [];
  state.researchQuestions = [];
  document.getElementById("research-job-status").textContent = "";
  document.getElementById("proposal-review").innerHTML = "";
  document.getElementById("question-review").innerHTML = "";
  setText(
    "upload-status",
    `Session ${data.session_id} | Version ${data.gedcom_version} | People ${data.person_count} | Living ${data.living_count}`
  );
  await loadLivingPeople();
  await loadPeople();
  initTreeDefaults();
  renderTree();
}

async function loadLivingPeople() {
  if (!state.sessionId) return;
  state.livingPeople = await request(`/api/sessions/${state.sessionId}/living-people`);
  renderLivingPeople();
}

async function loadPeople() {
  if (!state.sessionId) return;
  state.people = await request(`/api/sessions/${state.sessionId}/people`);
  state.peopleByXref = Object.fromEntries(state.people.map((p) => [p.xref, p]));
  rebuildRelationshipIndexes();
}

function rebuildRelationshipIndexes() {
  const map = new Map();
  for (const person of state.people) {
    if (person.father_xref) {
      if (!map.has(person.father_xref)) map.set(person.father_xref, []);
      map.get(person.father_xref).push(person.xref);
    }
    if (person.mother_xref) {
      if (!map.has(person.mother_xref)) map.set(person.mother_xref, []);
      map.get(person.mother_xref).push(person.xref);
    }
  }
  for (const [parentXref, children] of map.entries()) {
    children.sort((a, b) => {
      const pa = state.peopleByXref[a];
      const pb = state.peopleByXref[b];
      const ay = pa?.birth_year ?? extractYear(pa?.birth_date);
      const by = pb?.birth_year ?? extractYear(pb?.birth_date);
      if (ay && by && ay !== by) return ay - by;
      return String(pa?.name || a).localeCompare(String(pb?.name || b));
    });
    map.set(parentXref, children);
  }
  state.childrenByParent = map;
}

function initTreeDefaults() {
  const modeEl = document.getElementById("tree-mode");
  const genEl = document.getElementById("tree-depth");
  state.tree.mode = modeEl?.value || "ancestors";
  state.tree.generations = Number(genEl?.value || "4") || 4;
  if (!state.tree.rootXref && state.people.length) {
    state.tree.rootXref = state.people[0].xref;
  }
  syncTreeRootInput();
}

function syncTreeRootInput() {
  const input = document.getElementById("tree-root");
  if (!input) return;
  const person = state.peopleByXref[state.tree.rootXref];
  input.value = person ? `${person.name} (${person.xref})` : state.tree.rootXref || "";
}

function findPeople(query, limit = 10) {
  const q = String(query || "").trim().toLowerCase();
  if (!q) return [];
  const results = [];
  for (const person of state.people) {
    if (results.length >= limit) break;
    const hay = `${person.name} ${person.xref}`.toLowerCase();
    if (hay.includes(q)) results.push(person);
  }
  return results;
}

function showTreeSuggestions(people) {
  const box = document.getElementById("tree-suggestions");
  if (!box) return;
  box.innerHTML = "";
  if (!people.length) {
    box.hidden = true;
    return;
  }
  for (const person of people) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = `${person.name} (${person.xref})`;
    btn.addEventListener("click", () => {
      state.tree.rootXref = person.xref;
      syncTreeRootInput();
      box.hidden = true;
      renderTree();
    });
    box.appendChild(btn);
  }
  box.hidden = false;
}

function resolveTreeRootFromInput() {
  const input = document.getElementById("tree-root");
  const raw = String(input?.value || "").trim();
  if (!raw) return null;
  const xrefMatch = raw.match(/@[^@]+@/);
  if (xrefMatch) {
    const xref = xrefMatch[0];
    if (state.peopleByXref[xref]) return xref;
  }
  const results = findPeople(raw, 1);
  return results.length ? results[0].xref : null;
}

function buildAncestorsTree(rootXref, maxDepth) {
  const makeNode = (xref, depth, label, placeholder = false) => ({
    id: `${xref || "unknown"}:${label}:${depth}:${Math.random().toString(16).slice(2)}`,
    xref: xref || null,
    person: xref ? state.peopleByXref[xref] || null : null,
    depth,
    label,
    placeholder: placeholder || !xref || !state.peopleByXref[xref],
    children: [],
  });

  const walk = (xref, depth, label, path) => {
    if (!xref) return makeNode(null, depth, label, true);
    if (path.has(xref)) return makeNode(xref, depth, "cycle", true);
    const person = state.peopleByXref[xref];
    const node = makeNode(xref, depth, label, !person);
    if (!person || depth >= maxDepth) return node;
    const nextPath = new Set(path);
    nextPath.add(xref);
    node.children = [
      walk(person.father_xref, depth + 1, "father", nextPath),
      walk(person.mother_xref, depth + 1, "mother", nextPath),
    ];
    return node;
  };

  return walk(rootXref, 0, "root", new Set());
}

function buildDescendantsTree(rootXref, maxDepth) {
  const makeNode = (xref, depth) => ({
    id: `${xref || "unknown"}:${depth}:${Math.random().toString(16).slice(2)}`,
    xref: xref || null,
    person: xref ? state.peopleByXref[xref] || null : null,
    depth,
    label: depth === 0 ? "root" : "child",
    placeholder: !xref || !state.peopleByXref[xref],
    children: [],
  });

  const walk = (xref, depth, path) => {
    if (!xref) return makeNode(null, depth);
    if (path.has(xref)) return { ...makeNode(xref, depth), label: "cycle", placeholder: true };
    const person = state.peopleByXref[xref];
    const node = makeNode(xref, depth);
    if (!person || depth >= maxDepth) return node;
    const nextPath = new Set(path);
    nextPath.add(xref);
    const children = state.childrenByParent.get(xref) || [];
    node.children = children.map((childXref) => walk(childXref, depth + 1, nextPath));
    return node;
  };

  return walk(rootXref, 0, new Set());
}

function layoutTree(root, mode, maxDepth) {
  let nextX = 0;

  const assignX = (node) => {
    if (!node.children || node.children.length === 0) {
      node._x = nextX++;
      return node._x;
    }
    const xs = node.children.map(assignX);
    const avg = xs.reduce((a, b) => a + b, 0) / xs.length;
    node._x = avg;
    return avg;
  };

  assignX(root);

  const nodes = [];
  const links = [];
  const collect = (node) => {
    nodes.push(node);
    for (const child of node.children || []) {
      links.push({ from: node, to: child });
      collect(child);
    }
  };
  collect(root);

  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;

  for (const node of nodes) {
    const yIndex = mode === "ancestors" ? maxDepth - node.depth : node.depth;
    node.x = node._x * (TREE_NODE_W + TREE_GAP_X);
    node.y = yIndex * (TREE_NODE_H + TREE_GAP_Y);
    minX = Math.min(minX, node.x);
    minY = Math.min(minY, node.y);
    maxX = Math.max(maxX, node.x + TREE_NODE_W);
    maxY = Math.max(maxY, node.y + TREE_NODE_H);
  }

  return { nodes, links, bounds: { minX, minY, maxX, maxY } };
}

function applyTreeTransform() {
  const svg = document.getElementById("tree-svg");
  const group = svg?.querySelector("g[data-tree-group='1']");
  if (!svg || !group) return;
  const { x, y, k } = state.tree.transform;
  group.setAttribute("transform", `translate(${x} ${y}) scale(${k})`);
}

function centerTree() {
  const svg = document.getElementById("tree-svg");
  const bounds = state.tree.bounds;
  if (!svg || !bounds) return;

  const svgW = svg.clientWidth || 900;
  const svgH = svg.clientHeight || 560;
  const pad = 40;
  const contentW = (bounds.maxX - bounds.minX) + pad * 2;
  const contentH = (bounds.maxY - bounds.minY) + pad * 2;
  const fit = Math.min(svgW / contentW, svgH / contentH);
  const k = clamp(fit, 0.24, 2.2);
  const tx = (svgW - (bounds.maxX - bounds.minX) * k) / 2 - bounds.minX * k;
  const ty = (svgH - (bounds.maxY - bounds.minY) * k) / 2 - bounds.minY * k;
  state.tree.transform = { x: tx, y: ty, k };
  applyTreeTransform();
}

function renderTree() {
  const status = document.getElementById("tree-status");
  if (!state.sessionId) {
    if (status) status.textContent = "Upload a GEDCOM to view the tree.";
    return;
  }
  if (!state.people.length) {
    if (status) status.textContent = "No people loaded.";
    return;
  }

  const mode = document.getElementById("tree-mode")?.value || state.tree.mode;
  const generations = Number(document.getElementById("tree-depth")?.value || state.tree.generations) || 4;
  state.tree.mode = mode;
  state.tree.generations = generations;

  const inputRoot = resolveTreeRootFromInput();
  if (inputRoot) state.tree.rootXref = inputRoot;

  const rootPerson = state.peopleByXref[state.tree.rootXref];
  if (!rootPerson) {
    if (status) status.textContent = "Select a valid root person.";
    return;
  }

  const maxDepth = Math.max(0, generations - 1);
  const model =
    mode === "descendants"
      ? buildDescendantsTree(rootPerson.xref, maxDepth)
      : buildAncestorsTree(rootPerson.xref, maxDepth);

  const layout = layoutTree(model, mode, maxDepth);
  state.tree.bounds = layout.bounds;

  const svg = document.getElementById("tree-svg");
  svg.innerHTML = "";

  const group = svgEl("g", { "data-tree-group": "1" });
  const edges = svgEl("g", { "data-tree-edges": "1" });
  const nodes = svgEl("g", { "data-tree-nodes": "1" });
  group.appendChild(edges);
  group.appendChild(nodes);
  svg.appendChild(group);

  for (const link of layout.links) {
    const from = link.from;
    const to = link.to;
    const x1 = from.x + TREE_NODE_W / 2;
    const x2 = to.x + TREE_NODE_W / 2;
    let y1;
    let y2;
    if (mode === "ancestors") {
      y1 = from.y;
      y2 = to.y + TREE_NODE_H;
    } else {
      y1 = from.y + TREE_NODE_H;
      y2 = to.y;
    }
    const my = (y1 + y2) / 2;
    const d = `M ${x1} ${y1} C ${x1} ${my} ${x2} ${my} ${x2} ${y2}`;
    edges.appendChild(svgEl("path", { d, class: "tree-edge" }));
  }

  for (const node of layout.nodes) {
    const person = node.person;
    const isLiving = Boolean(person?.is_living);
    const classes = ["tree-node"];
    if (node.placeholder) classes.push("placeholder");
    if (isLiving) classes.push("living");

    const g = svgEl("g", {
      class: classes.join(" "),
      transform: `translate(${node.x} ${node.y})`,
      "data-xref": node.xref || "",
    });

    g.appendChild(svgEl("rect", { x: 0, y: 0, rx: 12, ry: 12, width: TREE_NODE_W, height: TREE_NODE_H }));

    const nameLine = person?.name ? truncate(person.name, 28) : node.label === "cycle" ? "Cycle detected" : "Unknown";
    const lifeLine = person ? formatLifespan(person) : node.label === "father" ? "unknown father" : node.label === "mother" ? "unknown mother" : "";
    const xrefLine = person?.xref ? person.xref : node.xref ? String(node.xref) : "";

    const text = svgEl("text", { x: 12, y: 18 });
    const t1 = svgEl("tspan", { x: 12, dy: 0 });
    t1.textContent = nameLine;
    text.appendChild(t1);
    const t2 = svgEl("tspan", { x: 12, dy: 16 });
    t2.textContent = truncate(lifeLine, 30);
    text.appendChild(t2);
    const t3 = svgEl("tspan", { x: 12, dy: 16 });
    t3.textContent = truncate(xrefLine, 30);
    text.appendChild(t3);
    g.appendChild(text);

    nodes.appendChild(g);
  }

  ensureTreeInteractions();
  // Center after the DOM has measured the SVG.
  requestAnimationFrame(centerTree);

  if (status) {
    status.textContent = `${rootPerson.name} (${rootPerson.xref}) | mode: ${mode} | generations: ${generations}`;
  }
}

function ensureTreeInteractions() {
  if (state.tree._hasInteractions) return;
  const svg = document.getElementById("tree-svg");
  if (!svg) return;
  state.tree._hasInteractions = true;

  let panning = false;
  let start = null;

  svg.addEventListener("pointerdown", (e) => {
    panning = true;
    state.tree.didPan = false;
    start = {
      x: e.clientX,
      y: e.clientY,
      tx: state.tree.transform.x,
      ty: state.tree.transform.y,
    };
    try {
      svg.setPointerCapture(e.pointerId);
    } catch {
      // no-op
    }
  });

  svg.addEventListener("pointermove", (e) => {
    if (!panning || !start) return;
    const dx = e.clientX - start.x;
    const dy = e.clientY - start.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) state.tree.didPan = true;
    state.tree.transform.x = start.tx + dx;
    state.tree.transform.y = start.ty + dy;
    applyTreeTransform();
  });

  svg.addEventListener("pointerup", () => {
    panning = false;
    start = null;
  });

  svg.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      const rect = svg.getBoundingClientRect();
      const sx = e.clientX - rect.left;
      const sy = e.clientY - rect.top;

      const { x, y, k } = state.tree.transform;
      const wx = (sx - x) / k;
      const wy = (sy - y) / k;
      const scale = e.deltaY < 0 ? 1.1 : 0.9;
      const nk = clamp(k * scale, 0.24, 2.8);
      state.tree.transform.k = nk;
      state.tree.transform.x = sx - wx * nk;
      state.tree.transform.y = sy - wy * nk;
      applyTreeTransform();
    },
    { passive: false }
  );

  svg.addEventListener("click", (e) => {
    if (state.tree.didPan) {
      state.tree.didPan = false;
      return;
    }
    const target = e.target;
    const node = target?.closest ? target.closest("g.tree-node") : null;
    const xref = node?.getAttribute ? node.getAttribute("data-xref") : "";
    if (xref && state.peopleByXref[xref]) {
      state.tree.rootXref = xref;
      syncTreeRootInput();
      renderTree();
    }
  });
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

async function indexLocalFolder() {
  if (!state.sessionId) throw new Error("Upload GEDCOM first.");
  const folderPath = document.getElementById("local-folder-path").value.trim();
  const result = await request(`/api/sessions/${state.sessionId}/research/local-index`, {
    method: "POST",
    body: JSON.stringify({ folder_path: folderPath, max_files: 2000 }),
  });
  document.getElementById("research-output").textContent = JSON.stringify(result, null, 2);
}

async function runFacePairing() {
  if (!state.sessionId) throw new Error("Upload GEDCOM first.");
  const folderPath = document.getElementById("local-folder-path").value.trim();
  const threshold = Number(document.getElementById("face-threshold").value || "0.52");
  const result = await request(`/api/sessions/${state.sessionId}/research/face-pair`, {
    method: "POST",
    body: JSON.stringify({ folder_path: folderPath, max_images: 400, threshold }),
  });
  document.getElementById("research-output").textContent = JSON.stringify(result, null, 2);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function loadJobStatus(jobId) {
  return request(`/api/research/jobs/${jobId}`, { headers: {} });
}

async function loadJobFindings(jobId) {
  return request(`/api/research/jobs/${jobId}/findings`, { headers: {} });
}

async function loadJobProposals(jobId) {
  return request(`/api/research/jobs/${jobId}/proposals?limit=250&offset=0`, { headers: {} });
}

async function loadJobQuestions(jobId) {
  return request(`/api/research/jobs/${jobId}/questions`, { headers: {} });
}

function renderProposalReview() {
  const root = document.getElementById("proposal-review");
  root.innerHTML = "";

  if (!state.researchProposals.length) {
    const empty = document.createElement("p");
    empty.textContent = "No proposals loaded.";
    root.appendChild(empty);
    return;
  }

  for (const proposal of state.researchProposals) {
    const card = document.createElement("article");
    card.className = "proposal-card";

    const personName = state.peopleByXref[proposal.person_xref]?.name || proposal.person_xref;
    card.innerHTML = `
      <h3>${personName} (${proposal.person_xref}) • ${proposal.relationship}</h3>
      <div class="proposal-meta">
        status=${proposal.status} | confidence=${proposal.confidence} | candidate=${proposal.candidate_name || "null"}<br/>
        evidence_ids=${(proposal.evidence_ids || []).join(", ") || "none"}<br/>
        flags=${(proposal.contradiction_flags || []).join(", ") || "none"}<br/>
        notes=${proposal.notes || ""}
      </div>
      <div class="proposal-actions">
        <button data-action="approve">Approve</button>
        <button data-action="reject">Reject</button>
        <button data-action="edit">Edit Name</button>
      </div>
    `;

    const actions = card.querySelectorAll("button[data-action]");
    for (const btn of actions) {
      btn.addEventListener("click", async () => {
        try {
          const action = btn.getAttribute("data-action");
          if (action === "edit") {
            const candidate = window.prompt("Edited candidate name", proposal.candidate_name || "");
            if (candidate === null) return;
            await decideProposal(proposal.proposal_id, {
              action: "edit",
              candidate_name: candidate,
              notes: "Edited in review UI",
            });
            return;
          }
          await decideProposal(proposal.proposal_id, { action });
        } catch (err) {
          document.getElementById("research-output").textContent = `Error: ${err.message}`;
        }
      });
    }

    root.appendChild(card);
  }
}

function renderQuestionReview() {
  const root = document.getElementById("question-review");
  root.innerHTML = "";

  if (!state.researchQuestions.length) {
    const empty = document.createElement("p");
    empty.textContent = "No open research questions.";
    root.appendChild(empty);
    return;
  }

  for (const item of state.researchQuestions) {
    const card = document.createElement("article");
    card.className = "question-card";
    const personName = state.peopleByXref[item.person_xref]?.name || item.person_xref;
    card.innerHTML = `
      <p><strong>${personName} (${item.person_xref}) • ${item.relationship}</strong></p>
      <p>status=${item.status}</p>
      <p>question=${item.question}</p>
      <p>rationale=${item.rationale}</p>
    `;

    if (item.status === "pending") {
      const actions = document.createElement("div");
      actions.className = "question-actions";
      actions.innerHTML = `
        <input type="text" placeholder="Your answer..." />
        <button data-action="answer">Submit Answer</button>
        <button data-action="skip">Skip</button>
      `;
      const input = actions.querySelector("input");
      const answerBtn = actions.querySelector('button[data-action="answer"]');
      const skipBtn = actions.querySelector('button[data-action="skip"]');

      answerBtn.addEventListener("click", async () => {
        try {
          const answer = (input.value || "").trim();
          if (!answer) throw new Error("Enter an answer first.");
          await answerQuestion(item.question_id, { status: "answered", answer });
        } catch (err) {
          document.getElementById("research-output").textContent = `Error: ${err.message}`;
        }
      });

      skipBtn.addEventListener("click", async () => {
        try {
          await answerQuestion(item.question_id, { status: "skipped" });
        } catch (err) {
          document.getElementById("research-output").textContent = `Error: ${err.message}`;
        }
      });

      card.appendChild(actions);
    } else if (item.answer) {
      const answer = document.createElement("p");
      answer.textContent = `answer=${item.answer}`;
      card.appendChild(answer);
    }

    root.appendChild(card);
  }
}

async function answerQuestion(questionId, payload) {
  await request(`/api/research/questions/${questionId}/answer`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (!state.researchJobId) return;
  const questionsRes = await loadJobQuestions(state.researchJobId);
  state.researchQuestions = questionsRes.questions || [];
  renderQuestionReview();
}

async function decideProposal(proposalId, payload) {
  await request(`/api/research/proposals/${proposalId}/decision`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (!state.researchJobId) return;
  const proposalRes = await loadJobProposals(state.researchJobId);
  state.researchProposals = proposalRes.proposals || [];
  renderProposalReview();
  const questionsRes = await loadJobQuestions(state.researchJobId);
  state.researchQuestions = questionsRes.questions || [];
  renderQuestionReview();
}

async function runResearch() {
  if (!state.sessionId) throw new Error("Upload GEDCOM first.");
  state.researchQuestions = [];
  document.getElementById("question-review").innerHTML = "";
  const payload = { max_people: 15 };
  const created = await request(`/api/sessions/${state.sessionId}/research/jobs`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  state.researchJobId = created.job_id;
  document.getElementById("research-job-status").textContent = JSON.stringify(created, null, 2);

  let status = null;
  for (let i = 0; i < 60; i++) {
    status = await loadJobStatus(state.researchJobId);
    document.getElementById("research-job-status").textContent = JSON.stringify(status, null, 2);
    if (status.status === "completed" || status.status === "failed") break;
    await sleep(350);
  }

  const findings = await loadJobFindings(state.researchJobId);
  document.getElementById("research-output").textContent = JSON.stringify(findings, null, 2);

  const proposalRes = await loadJobProposals(state.researchJobId);
  state.researchProposals = proposalRes.proposals || [];
  renderProposalReview();
}

async function applyApproved() {
  if (!state.sessionId) throw new Error("Upload GEDCOM first.");
  const result = await request(`/api/sessions/${state.sessionId}/research/apply-approved`, {
    method: "POST",
    body: JSON.stringify({ job_id: state.researchJobId }),
  });
  await loadPeople();
  renderTree();
  document.getElementById("research-output").textContent = JSON.stringify(result, null, 2);
  if (state.researchJobId) {
    const proposalRes = await loadJobProposals(state.researchJobId);
    state.researchProposals = proposalRes.proposals || [];
    renderProposalReview();
    const questionsRes = await loadJobQuestions(state.researchJobId);
    state.researchQuestions = questionsRes.questions || [];
    renderQuestionReview();
  }
}

async function uploadDocument() {
  if (!state.sessionId) throw new Error("Upload GEDCOM first.");
  const input = document.getElementById("doc-file");
  if (!input.files || !input.files.length) throw new Error("Choose a file first.");

  const form = new FormData();
  form.append("file", input.files[0]);
  const res = await fetch(`/api/sessions/${state.sessionId}/documents/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    throw new Error((await res.text()) || `Upload failed (${res.status})`);
  }
  const payload = await res.json();
  document.getElementById("doc-output").textContent = JSON.stringify(payload, null, 2);
}

async function listDocuments() {
  if (!state.sessionId) throw new Error("Upload GEDCOM first.");
  const payload = await request(`/api/sessions/${state.sessionId}/documents?limit=100&offset=0`, {
    headers: {},
  });
  document.getElementById("doc-output").textContent = JSON.stringify(payload, null, 2);
}

async function searchDocuments() {
  if (!state.sessionId) throw new Error("Upload GEDCOM first.");
  const query = document.getElementById("doc-search-query").value.trim();
  if (!query) throw new Error("Enter search text first.");
  const payload = await request(
    `/api/sessions/${state.sessionId}/documents/search?q=${encodeURIComponent(query)}&limit=50`,
    { headers: {} }
  );
  document.getElementById("doc-output").textContent = JSON.stringify(payload, null, 2);
}

async function reindexDocuments() {
  if (!state.sessionId) throw new Error("Upload GEDCOM first.");
  const payload = await request(`/api/sessions/${state.sessionId}/documents/reindex`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  document.getElementById("doc-output").textContent = JSON.stringify(payload, null, 2);
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

document.getElementById("refresh-app-status").addEventListener("click", async () => {
  try {
    await refreshAppStatus();
  } catch (err) {
    document.getElementById("app-status-output").textContent = `Error: ${err.message}`;
  }
});

document.getElementById("check-updates").addEventListener("click", async () => {
  try {
    await checkUpdates();
  } catch (err) {
    document.getElementById("app-status-output").textContent = `Error: ${err.message}`;
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

document.getElementById("tree-root").addEventListener("input", async (e) => {
  const value = e.target.value || "";
  if (!state.sessionId || !state.people.length) return;
  const results = value.trim().length >= 2 || value.includes("@") ? findPeople(value, 8) : [];
  showTreeSuggestions(results);
});

document.getElementById("tree-root").addEventListener("keydown", async (e) => {
  if (e.key !== "Enter") return;
  e.preventDefault();
  document.getElementById("tree-suggestions").hidden = true;
  renderTree();
});

document.getElementById("tree-render").addEventListener("click", async () => {
  try {
    document.getElementById("tree-suggestions").hidden = true;
    renderTree();
  } catch (err) {
    setText("tree-status", `Error: ${err.message}`);
  }
});

document.getElementById("tree-center").addEventListener("click", async () => {
  try {
    centerTree();
  } catch (err) {
    setText("tree-status", `Error: ${err.message}`);
  }
});

document.getElementById("index-local").addEventListener("click", async () => {
  try {
    await indexLocalFolder();
  } catch (err) {
    document.getElementById("research-output").textContent = `Error: ${err.message}`;
  }
});

document.getElementById("run-face-pair").addEventListener("click", async () => {
  try {
    await runFacePairing();
  } catch (err) {
    document.getElementById("research-output").textContent = `Error: ${err.message}`;
  }
});

document.getElementById("run-research").addEventListener("click", async () => {
  try {
    await runResearch();
  } catch (err) {
    document.getElementById("research-output").textContent = `Error: ${err.message}`;
  }
});

document.getElementById("apply-approved").addEventListener("click", async () => {
  try {
    await applyApproved();
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

document.getElementById("upload-doc-btn").addEventListener("click", async () => {
  try {
    await uploadDocument();
  } catch (err) {
    document.getElementById("doc-output").textContent = `Error: ${err.message}`;
  }
});

document.getElementById("list-docs-btn").addEventListener("click", async () => {
  try {
    await listDocuments();
  } catch (err) {
    document.getElementById("doc-output").textContent = `Error: ${err.message}`;
  }
});

document.getElementById("search-docs-btn").addEventListener("click", async () => {
  try {
    await searchDocuments();
  } catch (err) {
    document.getElementById("doc-output").textContent = `Error: ${err.message}`;
  }
});

document.getElementById("reindex-docs-btn").addEventListener("click", async () => {
  try {
    await reindexDocuments();
  } catch (err) {
    document.getElementById("doc-output").textContent = `Error: ${err.message}`;
  }
});

loadProviderConfig().catch((err) => {
  setText("config-status", `Error: ${err.message}`);
});

refreshAppStatus().catch((err) => {
  document.getElementById("app-status-output").textContent = `Error: ${err.message}`;
});
