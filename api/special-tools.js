const REPO = process.env.GITHUB_REPO || "LucaSpaggiari1974/cutting-tools-lab";
const BRANCH = process.env.GITHUB_BRANCH || "main";
const TOKEN = process.env.GITHUB_TOKEN;
const API = "https://api.github.com";
const JSON_PATH = "special-tools.json";

function headers() {
  if (!TOKEN) throw new Error("GITHUB_TOKEN non configurato su Vercel");
  return {
    Authorization: `Bearer ${TOKEN}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "Content-Type": "application/json"
  };
}

async function github(path, options = {}) {
  const r = await fetch(API + path, { ...options, headers: { ...headers(), ...(options.headers || {}) } });
  const text = await r.text();
  let data;
  try { data = text ? JSON.parse(text) : {}; } catch { data = { message: text }; }
  if (!r.ok) throw new Error(data.message || `GitHub HTTP ${r.status}`);
  return data;
}

async function getArchive() {
  const d = await github(`/repos/${REPO}/contents/${JSON_PATH}?ref=${encodeURIComponent(BRANCH)}`);
  const content = Buffer.from(d.content.replace(/\n/g, ""), "base64").toString("utf8");
  const json = JSON.parse(content);
  return { json, sha: d.sha };
}

async function putArchive(json, sha, message) {
  json.updatedAt = new Date().toISOString();
  const content = Buffer.from(JSON.stringify(json, null, 2) + "\n").toString("base64");
  return github(`/repos/${REPO}/contents/${JSON_PATH}`, {
    method: "PUT",
    body: JSON.stringify({ message, content, sha, branch: BRANCH })
  });
}

function cleanItem(x) {
  return {
    id: x.id || Date.now(),
    code: String(x.code || "").trim(),
    name: String(x.name || "").trim(),
    type: String(x.type || "").trim(),
    machine: String(x.machine || "").trim(),
    pieceType: String(x.pieceType || "").trim(),
    material: String(x.material || "").trim(),
    geom: String(x.geom || "").trim(),
    params: String(x.params || "").trim(),
    notes: String(x.notes || "").trim(),
    fileUrl: String(x.fileUrl || "").trim(),
    fileName: String(x.fileName || "").trim(),
    fileType: String(x.fileType || "").trim(),
    createdAt: x.createdAt || new Date().toISOString()
  };
}

module.exports = async (req, res) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  if (req.method === "OPTIONS") return res.status(204).end();

  try {
    if (req.method === "GET") {
      const { json } = await getArchive();
      return res.status(200).json(json);
    }

    if (req.method === "POST") {
      const incoming = cleanItem(req.body || {});
      if (!incoming.code || !incoming.machine || !incoming.pieceType) {
        return res.status(400).json({ error: "Codice, macchina e tipologia di pezzo sono obbligatori." });
      }

      const { json, sha } = await getArchive();
      if (!Array.isArray(json.items)) json.items = [];
      const index = json.items.findIndex(x => String(x.id) === String(incoming.id));
      if (index >= 0) json.items[index] = incoming;
      else json.items.push(incoming);
      await putArchive(json, sha, `feat(allison): salva utensile ${incoming.code}`);
      return res.status(200).json({ ok: true, item: incoming, updatedAt: json.updatedAt });
    }

    if (req.method === "DELETE") {
      const id = String((req.body || {}).id || req.query?.id || "");
      if (!id) return res.status(400).json({ error: "ID mancante." });
      const { json, sha } = await getArchive();
      const before = json.items.length;
      json.items = json.items.filter(x => String(x.id) !== id);
      if (json.items.length === before) return res.status(404).json({ error: "Utensile non trovato." });
      await putArchive(json, sha, `feat(allison): elimina utensile ${id}`);
      return res.status(200).json({ ok: true, updatedAt: json.updatedAt });
    }

    return res.status(405).json({ error: "Metodo non supportato." });
  } catch (e) {
    return res.status(500).json({ error: e.message || "Errore server." });
  }
};
