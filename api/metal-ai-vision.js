export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== "POST") return res.status(405).json({ error: "Metodo non consentito" });
  if (!process.env.OPENAI_API_KEY) return res.status(503).json({ error: "OPENAI_API_KEY non configurata sul server." });

  try {
    const { image, question = "" } = req.body || {};
    if (!image || typeof image !== "string" || !image.startsWith("data:image/")) {
      return res.status(400).json({ error: "Immagine non valida." });
    }
    if (image.length > 7_000_000) return res.status(413).json({ error: "Immagine troppo grande." });

    const prompt = `Sei Metal AI, specializzata in lavorazioni meccaniche.
Analizza questa foto come un tecnico esperto di officina. Identifica SOLO ciò che è visibile e separa:
1) osservazioni certe dalla foto;
2) problema/i probabili;
3) cause possibili, ordinate per verifica pratica;
4) correzioni/azioni consigliate;
5) quali misure o parametri servono per confermare la diagnosi.
Considera tornitura, fresatura, foratura, alesatura, rettifica diametri, rettifica fori, rettifica evolvente e mole a vite quando pertinenti.
Non inventare materiale, grado inserto, tolleranza, geometria o parametro di taglio se non sono leggibili. Se un dato non è leggibile, dichiaralo.
Quando servono dati aggiornati di utensili, materiali o produttori, usa la ricerca web e cita le fonti nella risposta.
Se la foto mostra un difetto di pezzo, truciolo, utensile, mola, superficie, usura o rottura, descrivi gli indizi visivi che sostengono la diagnosi.
Rispondi in italiano, in modo operativo e tecnico.
Richiesta dell'operatore: ${String(question).slice(0,4000)}`;

    const r = await fetch("https://api.openai.com/v1/responses", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${process.env.OPENAI_API_KEY}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        model: process.env.METAL_AI_MODEL || "gpt-5.6-luna",
        tools: [{ type: "web_search" }],
        input: [{
          role: "user",
          content: [
            { type: "input_text", text: prompt },
            { type: "input_image", image_url: image, detail: "high" }
          ]
        }]
      })
    });

    const data = await r.json();
    if (!r.ok) return res.status(r.status).json({ error: data?.error?.message || "Errore del motore IA." });
    return res.status(200).json({ answer: data.output_text || "Nessuna analisi testuale restituita.", response_id: data.id || null });
  } catch (e) {
    return res.status(500).json({ error: "Errore durante l'analisi dell'immagine." });
  }
}
