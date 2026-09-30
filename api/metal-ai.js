export default async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  if (req.method === "OPTIONS") return res.status(204).end();
  if (req.method !== "POST") return res.status(405).json({ error: "Metodo non consentito" });
  if (!process.env.OPENAI_API_KEY) return res.status(503).json({ error: "OPENAI_API_KEY non configurata sul server." });

  try {
    const { question = "", catalogContext = "" } = req.body || {};
    if (!String(question).trim()) return res.status(400).json({ error: "Richiesta vuota." });

    const prompt = `Sei Metal AI, assistente tecnico specializzato in metalmeccanica.
Devi rispondere in italiano e distinguere sempre:
- dati verificati da fonti esterne;
- dati presenti nel catalogo locale;
- calcoli eseguiti matematicamente;
- ipotesi diagnostiche.
Per problemi di lavorazione, analizza il sintomo, le cause possibili, i controlli da fare e le correzioni in ordine operativo.
Per utensili, materiali, gradi, rivestimenti, parametri, norme, produttori e tecnologie recenti, cerca sul web fonti tecniche affidabili, privilegiando produttori, enti normativi e documentazione tecnica primaria. Non dichiarare di aver consultato "tutto internet": usa le fonti effettivamente trovate e cita i riferimenti.
Non inventare parametri. Se le fonti divergono, mostra l'intervallo e spiega da cosa dipende.
Per rettifica includi, quando pertinente, rettifica diametri, rettifica fori, rettifica evolvente e mole a vite.
Contesto del catalogo locale:
${String(catalogContext).slice(0,12000)}

Richiesta dell'operatore:
${String(question).slice(0,8000)}`;

    const r = await fetch("https://api.openai.com/v1/responses", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${process.env.OPENAI_API_KEY}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        model: process.env.METAL_AI_MODEL || "gpt-5.6-luna",
        tools: [{ type: "web_search" }],
        input: prompt
      })
    });

    const data = await r.json();
    if (!r.ok) return res.status(r.status).json({ error: data?.error?.message || "Errore del motore IA." });

    const sources = [];
    for (const item of (data.output || [])) {
      for (const c of (item.content || [])) {
        for (const a of (c.annotations || [])) {
          if (a.type === "url_citation" && a.url) sources.push({ title: a.title || a.url, url: a.url });
        }
      }
    }
    return res.status(200).json({
      answer: data.output_text || "Nessuna risposta restituita.",
      sources: sources.filter((x,i,a)=>a.findIndex(y=>y.url===x.url)===i).slice(0,12),
      response_id: data.id || null
    });
  } catch (e) {
    return res.status(500).json({ error: "Errore durante la ricerca tecnica." });
  }
}
