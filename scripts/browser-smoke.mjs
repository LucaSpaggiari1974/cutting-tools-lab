import { chromium } from "playwright";

const failures = [];
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
page.on("pageerror", error => failures.push("pageerror: " + error.message));

const fixture = {
  updatedAt: "2026-10-22T00:00:00.000Z",
  items: [
    { code: "CTLAB-SMOKE-CNMG120408", maker: "Sandvik Coromant", category: "Tornitura finitura", material: "Acciai", vc: 180, f: 0.2, ap: 1, family: "CNMG", source: "smoke-test" },
    { code: "CTLAB-SMOKE-APKT1604", maker: "ISCAR", category: "Fresatura", material: "Acciai", vc: 160, f: 0.12, ap: 0.8, family: "APKT", source: "smoke-test" }
  ]
};

try {
  await page.route("**/catalog.json**", route => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(fixture) }));
  await page.route("**/complete-tools.json**", route => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [] }) }));
  await page.route("**/update-status.json**", route => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ updatedAt: fixture.updatedAt }) }));
  await page.route("**/manufacturers.json", route => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ groups: [{ name: "Produttore test", type: "Inserti", catalogScope: "Test automatico", drawings: "N/D" }] }) }));
  await page.route("**/gear-parameters.json**", route => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ coltello: [], creatore: [] }) }));

  const response = await page.goto("http://127.0.0.1:8765/index.html", { waitUntil: "domcontentloaded", timeout: 30000 });
  if (!response || !response.ok()) throw new Error("Homepage non caricata correttamente");
  await page.waitForFunction(() => document.querySelectorAll("tr.data").length >= 2, null, { timeout: 15000 });
  console.log("PASS: homepage e caricamento catalogo di prova");

  const search = page.locator("#q");
  await search.fill("CTLAB-SMOKE-CNMG120408");
  await page.waitForFunction(() => document.querySelectorAll("tr.data").length === 1, null, { timeout: 10000 });
  if (!(await page.locator("tr.data").innerText()).includes("CTLAB-SMOKE-CNMG120408")) throw new Error("Filtro ricerca non restituisce il codice atteso");
  await search.fill("");
  await page.waitForFunction(() => document.querySelectorAll("tr.data").length >= 2, null, { timeout: 10000 });
  console.log("PASS: ricerca e ripristino elenco");

  await page.locator('.navtab[data-page="formule"]').click();
  if (!(await page.locator('.navtab[data-page="formule"]').getAttribute("class")).includes("active")) throw new Error("Navigazione alla pagina Formule non attivata");
  const gearInput = page.locator("#ls500_z");
  if (await gearInput.count()) {
    await gearInput.fill("80");
    const output = (await page.locator("#ls500_dout").innerText()).trim();
    if (!output || output === "—" || output.includes("Inserire denti")) throw new Error("Calcolatore LS500 non aggiorna l'output con dati validi: " + output);
    console.log("PASS: navigazione e calcolatore LS500");
  } else {
    throw new Error("Campo ls500_z non trovato nella pagina Formule");
  }

  await page.locator('.navtab[data-page="produttori"]').click();
  await page.waitForTimeout(250);
  if (!(await page.locator("#manufacturerList").innerText()).includes("Produttore test")) throw new Error("Elenco produttori non viene renderizzato");
  console.log("PASS: elenco produttori");

  if (failures.length) throw new Error(failures.join("\n"));
  console.log("PASS: nessun errore JavaScript runtime non gestito");
} catch (error) {
  console.error("BROWSER SMOKE TEST FAILED:", error.stack || error.message);
  process.exitCode = 1;
} finally {
  await browser.close();
}
