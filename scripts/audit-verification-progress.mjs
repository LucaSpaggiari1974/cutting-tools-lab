#!/usr/bin/env node
// Verifica strutturale del registro: NON certifica parametri o pubblicazione.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve, dirname } from "node:path";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const progress = JSON.parse(readFileSync(resolve(root, "technical-verification-progress.json"), "utf8"));
const errors = [];
const records = progress.verifiedSourceRecords ?? [];
const seen = new Set();
for (const [index, record] of records.entries()) {
  const label = `record ${index + 1}`;
  if (!record.code || !record.grade) errors.push(`${label}: codice/grado mancante`);
  const key = [record.code, record.grade].map(v => String(v ?? "").replace(/[^A-Z0-9]/gi, "").toUpperCase()).join("|");
  if (seen.has(key)) errors.push(`${label}: duplicato codice/grado ${key}`);
  seen.add(key);
  for (const field of ["source", "product", "speedSource", "gradeSource", "materialSource", "geometrySource"]) {
    if (!record[field]) continue;
    try {
      const url = new URL(record[field]);
      if (url.protocol !== "https:" || !/(^|\.)ingersoll-imc\.com$/i.test(url.hostname))
        errors.push(`${label}: fonte non ufficiale in ${field}`);
    } catch { errors.push(`${label}: URL non valido in ${field}`); }
  }
  if (record.geometry) {
    for (const field of ["includedAngleDeg", "indexes", "inscribedCircleIn", "cornerRadiusIn", "cuttingEdgeLengthIn", "thicknessIn"]) {
      if (record.geometry[field] !== undefined && (!Number.isFinite(record.geometry[field]) || record.geometry[field] <= 0))
        errors.push(`${label}: geometria ${field} non valida`);
    }
  }
  for (const field of ["fnMmRev", "apMm"]) {
    if (record[field] === undefined) continue;
    const range = record[field];
    if (!Array.isArray(range) || range.length !== 2 || !range.every(v => Number.isFinite(v) && v > 0) || range[0] > range[1])
      errors.push(`${label}: intervallo ${field} non valido`);
  }
  if (record.caseStudies) for (const study of record.caseStudies) {
    if (!study.scope || !study.material) errors.push(`${label}: caso studio senza ambito/materiale`);
    try {
      const url = new URL(study.source);
      if (url.protocol !== "https:" || !/(^|\.)ingersoll-imc\.com$/i.test(url.hostname)) errors.push(`${label}: fonte caso studio non ufficiale`);
    } catch { errors.push(`${label}: URL caso studio non valido`); }
    for (const field of ["vcMMin", "fnMmRev"]) {
      const value = study[field];
      if (value === undefined) continue;
      const values = Array.isArray(value) ? value : [value];
      if (!values.length || !values.every(v => Number.isFinite(v) && v > 0)) errors.push(`${label}: ${field} caso studio non valido`);
    }
  }
}
// Una verifica strutturale non deve accettare un falso completamento globale.
// Il conteggio di 50 riguarda soltanto un blocco, non l'intero catalogo.
if (progress.status === "complete") {
  if (progress.manufacturer !== "ALL" || progress.catalogCoverage?.allExistingRecordsVerified !== true ||
      progress.catalogCoverage?.unresolvedGapsDocumented !== true ||
      progress.catalogCoverage?.regressionsPassed !== true ||
      progress.catalogCoverage?.windowsPublicationVerified !== true)
    errors.push("completamento globale privo di copertura catalogo, lacune, regressioni o verifica Windows esplicite");
}
if (progress.batchTarget !== 50) errors.push("batchTarget diverso da 50");
if (progress.status === "complete") {
  if (records.length < progress.batchTarget) errors.push("stato completo senza 50 combinazioni documentate");
  if (records.some(record => record.publication !== "verified")) errors.push("stato completo con pubblicazione di singoli record non verificata");
  if (progress.publication !== "verified") errors.push("stato completo senza pubblicazione globale verificata");
}
for (const [index, record] of records.entries()) {
  if (record.snapshotAudit?.identity && /candidata|non certificazione/i.test(record.snapshotAudit.identity) && record.publication === "verified")
    errors.push(`record ${index + 1}: pubblicazione certificata nonostante corrispondenza solo candidata`);
}
// Inventario lacune: un record documentato non equivale a parametri completi.
// Non trasformare una VC di grado o una prova di sistema in VC dell'articolo.
const gaps = { noMaterial: [], noSpecificVc: [], noFeed: [], noDepth: [], candidateSnapshot: [] };
for (const record of records) {
  const id = `${record.code} / ${record.grade}`;
  if (!record.material) gaps.noMaterial.push(id);
  if (!Number.isFinite(record.vcMMin) && !record.itemVcMMin) gaps.noSpecificVc.push(id);
  if (!record.fnMmRev && !record.fzMmTooth) gaps.noFeed.push(id);
  if (!record.apMm && !/foratura|drilling/i.test(String(record.ap ?? ""))) gaps.noDepth.push(id);
  if (/candidata|non certificazione/i.test(String(record.snapshotAudit?.identity ?? ""))) gaps.candidateSnapshot.push(id);
}
console.log("Lacune per verifica successiva (non errori strutturali):", JSON.stringify(gaps));
console.log(`Registro: ${records.length} combinazioni distinte su obiettivo blocco ${progress.batchTarget}; controlli strutturali: ${errors.length ? "FAIL" : "PASS"}.`);
console.log("ATTENZIONE: PASS non significa verifica ufficiale dei valori né certificazione Cloudflare/Windows.");
if (errors.length) { for (const error of errors) console.error(error); process.exitCode = 1; }
