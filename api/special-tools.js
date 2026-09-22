const { put, get, del } = require("@vercel/blob");
const crypto = require("crypto");


const ARCHIVE_PATH = "allison/special-tools.json";
const MEDIA_PREFIX = "allison/media/";

function emptyArchive() {
  return { version: 1, category: "Gestione utensili interni", updatedAt: null, items: [] };
}

async function readBlobText(path) {
  const result = await get(path, { access: "private", useCache: false });
  if (!result) return null;
  const ab = await new Response(result.stream).arrayBuffer();
  return Buffer.from(ab).toString("utf8");
}

async function getArchive() {
  const text = await readBlobText(ARCHIVE_PATH);
  if (!text) return emptyArchive();
  const json = JSON.parse(text);
  if (!Array.isArray(json.items)) json.items = [];
  return json;
}

function mediaViewToken(path, expiresAt) {
  const secret = String(process.env.SPECIAL_TOOLS_PASSWORD || "");
  const payload = String(path) + "|" + String(expiresAt);
  const sig = crypto.createHmac("sha256", secret).update(payload).digest("base64url");
  return Buffer.from(payload).toString("base64url") + "." + sig;
}

function verifyMediaViewToken(token, expectedPath) {
  try {
    const parts = String(token || "").split(".");
    if (parts.length !== 2) return false;
    const payload = Buffer.from(parts[0], "base64url").toString("utf8");
    const sig = parts[1];
    const sep = payload.lastIndexOf("|");
    if (sep < 1) return false;
    const path = payload.slice(0, sep);
    const expiresAt = Number(payload.slice(sep + 1));
    if (path !== expectedPath || !Number.isFinite(expiresAt) || Date.now() > expiresAt) return false;
    const expected = crypto.createHmac("sha256", String(process.env.SPECIAL_TOOLS_PASSWORD || "")).update(payload).digest("base64url");
    return crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(expected));
  } catch (_) {
    return false;
  }
}

function signedFileUrl(path) {
  if (!path || !String(path).startsWith(MEDIA_PREFIX)) return "";
  const expiresAt = Date.now() + 24 * 60 * 60 * 1000;
  const token = mediaViewToken(String(path), expiresAt);
  return "/api/special-tools?file=" + encodeURIComponent(String(path)) + "&view=1&token=" + encodeURIComponent(token);
}

async function publicArchive(json) {
  const items = await Promise.all((json.items || []).map(async (item) => ({
    ...item,
    fileUrl: item.filePath ? await signedFileUrl(item.filePath) : ""
  })));
  return { ...json, items };
}

async function saveArchive(json) {
  json.updatedAt = new Date().toISOString();
  await put(ARCHIVE_PATH, JSON.stringify(json, null, 2) + "\n", {
    access: "private",
    addRandomSuffix: false,
    allowOverwrite: true,
    contentType: "application/json"
  });
  return json;
}

async function uploadMedia(item) {
  const data = String(item.fileData || "");
  if (!data || !data.startsWith("data:")) {
    return { filePath: String(item.filePath || ""), fileName: String(item.fileName || ""), fileType: String(item.fileType || "") };
  }
  const match = data.match(/^data:([^;]+);base64,(.+)$/s);
  if (!match) throw new Error("File allegato non valido.");
  const mime = match[1];
  const base64 = match[2];
  if (base64.length > 3 * 1024 * 1024 * 1.4) throw new Error("File troppo grande. Usa un file fino a 3 MB.");
  const ext = mime === "application/pdf" ? "pdf" : (mime.split("/")[1] || "bin").replace(/[^a-z0-9]/gi, "") || "bin";
  const path = MEDIA_PREFIX + item.id + "-" + Date.now() + "." + ext;
  await put(path, Buffer.from(base64, "base64"), {
    access: "private",
    addRandomSuffix: false,
    contentType: mime
  });
  return { filePath: path, fileName: String(item.fileName || ("allegato." + ext)), fileType: mime };
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
    filePath: String(x.filePath || "").trim(),
    fileUrl: String(x.fileUrl || "").trim(),
    fileName: String(x.fileName || "").trim(),
    fileType: String(x.fileType || "").trim(),
    createdAt: x.createdAt || new Date().toISOString()
  };
}

function requireSpecialPassword(req) {
  const expected = String(process.env.SPECIAL_TOOLS_PASSWORD || "");
  const received = String(req.headers["x-special-tools-password"] || "");
  if (!expected) return { ok:false, status:503, error:"Password Gestione utensili interni non configurata su Vercel." };
  if (!received || received !== expected) return { ok:false, status:401, error:"Password Gestione utensili interni non valida." };
  return { ok:true };
}

function setCors(res) {
  res.setHeader("Access-Control-Allow-Origin", "https://lucaspaggiari1974.github.io");
  res.setHeader("Vary", "Origin");
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, x-special-tools-password");
}


module.exports = async (req, res) => {
  setCors(res);
  if (req.method === "OPTIONS") return res.status(204).end();

  const auth = requireSpecialPassword(req);
  if (!auth.ok) return res.status(auth.status).json({ error: auth.error });

  try {
    if (req.method === "GET" && req.query?.file) {
      const path = String(req.query.file || "");
      if (!path.startsWith(MEDIA_PREFIX) || path.includes("..") || path.includes("\\") || path.includes("\0")) {
        return res.status(400).json({ error: "File allegato non valido." });
      }
      const viewToken = String(req.query?.token || "");
      if (!viewToken || !verifyMediaViewToken(viewToken, path)) {
        return res.status(401).json({ error: "Link allegato non valido o scaduto." });
      }
      const result = await get(path, { access: "private", useCache: false });
      if (!result) return res.status(404).json({ error: "File allegato non trovato." });
      const contentType = result.blob?.contentType || "application/octet-stream";
      res.setHeader("Content-Type", contentType);
      res.setHeader("Cache-Control", "private, no-store, max-age=0");
      return res.status(200).send(Buffer.from(await new Response(result.stream).arrayBuffer()));
    }

    if (req.method === "GET") {
      return res.status(200).json(await publicArchive(await getArchive()));
    }

    if (req.method === "POST") {
      const raw = req.body || {};
      const incoming = cleanItem(raw);
      if (!incoming.code || !incoming.machine || !incoming.pieceType) {
        return res.status(400).json({ error: "Codice, macchina e tipologia di pezzo sono obbligatori." });
      }

      if (raw.fileData) {
        const media = await uploadMedia({ ...incoming, fileData: raw.fileData, fileName: raw.fileName, fileType: raw.fileType });
        incoming.filePath = media.filePath;
        incoming.fileName = media.fileName;
        incoming.fileType = media.fileType;
        incoming.fileUrl = "";
      }

      const json = await getArchive();

      // Salvataggio in modalità UPSERT:
      // - se arriva lo stesso ID, aggiorna quella scheda;
      // - se lo stesso codice + macchina + tipologia pezzo esiste già,
      //   sovrascrive la scheda esistente invece di creare un duplicato.
      // Se non viene scelto un nuovo file, conserva l'eventuale allegato già presente.
      let index = json.items.findIndex(x => String(x.id) === String(incoming.id));
      if (index < 0) {
        index = json.items.findIndex(x =>
          String(x.code || "").trim().toLowerCase() === incoming.code.toLowerCase() &&
          String(x.machine || "").trim().toLowerCase() === incoming.machine.toLowerCase() &&
          String(x.pieceType || "").trim().toLowerCase() === incoming.pieceType.toLowerCase()
        );
      }
      let action = "created";
      if (index >= 0) {
        action = "updated";
        const previous = json.items[index];
        incoming.id = previous.id;
        if (!raw.fileData) {
          incoming.filePath = previous.filePath || "";
          incoming.fileName = previous.fileName || "";
          incoming.fileType = previous.fileType || "";
          incoming.fileUrl = "";
        }
        incoming.createdAt = previous.createdAt || incoming.createdAt;
        json.items[index] = incoming;
      } else {
        json.items.push(incoming);
      }
      await saveArchive(json);
      return res.status(200).json({ ok: true, action, item: incoming, updatedAt: json.updatedAt });
    }

    if (req.method === "DELETE") {
      const id = String((req.body || {}).id || req.query?.id || "");
      if (!id) return res.status(400).json({ error: "ID mancante." });
      const json = await getArchive();
      const item = json.items.find(x => String(x.id) === id);
      if (!item) return res.status(404).json({ error: "Utensile non trovato." });
      json.items = json.items.filter(x => String(x.id) !== id);
      if (item.filePath && item.filePath.startsWith(MEDIA_PREFIX)) {
        try { await del(item.filePath, { access: "private" }); } catch (_) {}
      }
      await saveArchive(json);
      return res.status(200).json({ ok: true, updatedAt: json.updatedAt });
    }

    return res.status(405).json({ error: "Metodo non supportato." });
  } catch (e) {
    const message = e && e.message ? e.message : "Errore server.";
    if (/BLOB|token|store|configured/i.test(message)) {
      return res.status(503).json({ error: "Archivio cloud Gestione utensili interni non configurato su Vercel. Collega un Vercel Blob Store al progetto." });
    }
    return res.status(500).json({ error: message });
  }
};
