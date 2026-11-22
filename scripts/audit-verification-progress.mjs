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
  for (const field of ["source", "product", "speedSource", "gradeSource", "materialSource"]) {
    if (!record[field]) continue;
    try {
      const url = new URL(record[field]);
      if (url.protocol !== "https:" || !/(^|\.)ingersoll-imc\.com$/i.test(url.hostname))
        errors.push(`${label}: fonte non ufficiale in ${field}`);
    } catch { errors.push(`${label}: URL non valido in ${field}`); }
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
      if (url.protocol !== "https:" || !/(^|\\.)ingersoll-imc\\.com$/i.test(url.hostname)) errors.push(`${label}: fonte caso studio non ufficiale`);
    } catch { errors.push(`${label}: URL caso studio non valido`); }
    for (const field of ["vcMMin", "fnMmRev"]) {
      const value = study[field];
      if (value === undefined) continue;
      const values = Array.isArray(value) ? value : [value];
      if (!values.length || !values.every(v => Number.isFinite(v) && v > 0)) errors.push(`${label}: ${field} caso studio non valido`);
    }
  }
}
if (progress.batchTarget !== 50) errors.push("batchTarget diverso da 50");
if (records.length > progress.batchTarget && progress.status === "complete") errors.push("stato completo incoerente con batch");
console.log(`Registro: ${records.length} combinazioni distinte su obiettivo blocco ${progress.batchTarget}; controlli strutturali: ${errors.length ? "FAIL" : "PASS"}.`);
console.log("ATTENZIONE: PASS non significa verifica ufficiale dei valori né certificazione Cloudflare/Windows.");
if (errors.length) { for (const error of errors) console.error(error); process.exitCode = 1; }
