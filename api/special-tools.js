const { put, get, del, issueSignedToken, presignUrl } = require("@vercel/blob");

const ARCHIVE_PATH = "allison/special-tools.json";
const MEDIA_PREFIX = "allison/media/";

function emptyArchive() {
  return { version: 1, category: "Utensili speciali Allison", updatedAt: null, items: [] };
}

async function readBlobText(path) {
  const result = await get(path, { access: "private", useCache: false });
  if (!result) return null;
  const ab = await new Response(result.stream).arrayBuffer();
  return Buffer.from(ab).toString("utf8");
}

async function getArchive() {
  try {
    const text = await readBlobText(ARCHIVE_PATH);
    if (!text) return emptyArchive();
    const json = JSON.parse(text);
    if (!Array.isArray(json.items)) json.items = [];
    return json;
  } catch (_) {
    return emptyArchive();
  }
}

async function signedFileUrl(path) {
  if (!path || !String(path).startsWith(MEDIA_PREFIX)) return "";
  const token = await issueSignedToken({ operations: ["get"] });
  const { presignedUrl } = await presignUrl(token, {
    pathname: String(path),
    operation: "get",
    validUntil: Date.now() + 10 * 60 * 1000
  });
  return presignedUrl;
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

function setCors(res) {
  res.setHeader("Access-Control-Allow-Origin", "https://cutting-tools-lab.vercel.app");
  res.setHeader("Vary", "Origin");
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
}
