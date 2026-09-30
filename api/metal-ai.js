const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "Content-Type",
  "Access-Control-Allow-Methods": "POST, GET, OPTIONS"
};

function sendJson(res, status, data) {
  res.status(status).setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  res.setHeader("Access-Control-Allow-Methods", "POST, GET, OPTIONS");
  res.end(JSON.stringify(data));
}

function getBody(req) {
  return new Promise((resolve, reject) => {
    if (req.body && typeof req.body === "object") return resolve(req.body);
    let raw = "";
    req.on("data", chunk => {
      raw += chunk;
      if (raw.length > 1000000) {
        reject(new Error("Richiesta troppo grande."));
        req.destroy();
      }
    });
    req.on("end", () => {
      if (!raw.trim()) return resolve({});
      try { resolve(JSON.parse(raw)); }
      catch { reject(new Error("JSON della richiesta non valido.")); }
    });
    req.on("error", reject);
  });
}

export default async function handler(req, res) {
  if (req.method === "OPTIONS") {
    res.statusCode = 204;
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type");
    res.setHeader("Access-Control-Allow-Methods", "POST, GET, OPTIONS");
    return res.end();
  }

  if (req.method === "GET") {
    return sendJson(res, 200, {
      ok: true,
      service: "Metal AI",
      openaiConfigured: Boolean(process.env.OPENAI_API_KEY),
      gatewayConfigured: Boolean(process.env.AI_GATEWAY_API_KEY || process.env.VERCEL_OIDC_TOKEN),
      model,
      endpoint: "/api/metal-ai",
      methods: ["GET", "POST", "OPTIONS"]
    });
  }

  if (req.method !== "POST") {
    return sendJson(res, 405, {
      error: "Metodo non consentito.",
      method: req.method,
      allowed: ["GET", "POST", "OPTIONS"]
    });
  }

  const useGateway = Boolean(process.env.AI_GATEWAY_API_KEY || process.env.VERCEL_OIDC_TOKEN);
  const apiKey = process.env.AI_GATEWAY_API_KEY || process.env.VERCEL_OIDC_TOKEN || process.env.OPENAI_API_KEY;
  const baseUrl = useGateway ? "https://ai-gateway.vercel.sh/v1" : "https://api.openai.com/v1";
  const model = process.env.METAL_AI_MODEL || (useGateway ? "openai/gpt-5.6-luna" : "gpt-5.6-luna");

  if (!apiKey) {
    return sendJson(res, 503, {
      error: "Metal AI non ha una credenziale disponibile. Configurare AI Gateway/OIDC o OPENAI_API_KEY sul progetto Vercel."
    });
  }

  try {
    const body = await getBody(req);
    const question = String(body?.question || "");
    const catalogContext = String(body?.catalogContext || "");
    const systemInstruction = String(body?.systemInstruction || "");
    const localCalculations = body?.localCalculations || [];

    if (!question.trim()) {
      return sendJson(res, 400, { error: "Richiesta vuota." });
    }

    const prompt = `${systemInstruction.slice(0, 6000)}

Sei Metal AI, assistente tecnico specializzato in metalmeccanica.
Rispondi in italiano. Per ogni risposta distingui chiaramente:
- dati verificati da fonti esterne;
- dati del catalogo locale;
- calcoli matematici;
- ipotesi diagnostiche.

Per problemi di lavorazione devi analizzare sintomo, cause possibili, controlli e correzioni in ordine operativo.
Per problemi tecnici concreti DEVI usare la ricerca web disponibile prima di formulare la soluzione, privilegiando fonti tecniche primarie.
Per utensili, materiali, gradi, rivestimenti, parametri, norme, produttori e tecnologie recenti cerca fonti affidabili, soprattutto produttori, enti normativi e documentazione tecnica primaria.
Non inventare parametri. Se mancano dati necessari, dichiaralo e chiedili.
Se le fonti divergono, mostra l'intervallo e spiega da cosa dipende.
Per rettifica considera, quando pertinente, rettifica diametri, rettifica fori, rettifica evolvente e mole a vite.
Cita le fonti effettivamente consultate.

CATALOGO LOCALE:
${catalogContext.slice(0, 12000)}

CALCOLI LOCALI:
${JSON.stringify(localCalculations).slice(0, 8000)}

RICHIESTA OPERATORE:
${question.slice(0, 8000)}`;

    const openaiResponse = await fetch(`${baseUrl}/responses`, {
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

    const raw = await openaiResponse.text();
    let data = {};
    try {
      data = raw ? JSON.parse(raw) : {};
    } catch {
      return sendJson(res, 502, {
        error: "OpenAI ha restituito una risposta non JSON.",
        openai_status: openaiResponse.status,
        response_preview: raw.slice(0, 1000)
      });
    }

    if (!openaiResponse.ok) {
      return sendJson(res, openaiResponse.status, {
        error: data?.error?.message || "Errore del motore IA.",
        openai_status: openaiResponse.status,
        openai_type: data?.error?.type || null,
        openai_code: data?.error?.code || null
      });
    }

    const sources = [];
    for (const item of data.output || []) {
      for (const c of item.content || []) {
        for (const a of c.annotations || []) {
          if (a.type === "url_citation" && a.url) {
            sources.push({ title: a.title || a.url, url: a.url });
          }
        }
      }
    }

    return sendJson(res, 200, {
      answer: data.output_text || "Nessuna risposta restituita.",
      sources: sources
        .filter((x, i, a) => a.findIndex(y => y.url === x.url) === i)
        .slice(0, 12),
      response_id: data.id || null
    });
  } catch (e) {
    return sendJson(res, 500, {
      error: e?.message || "Errore durante la ricerca tecnica."
    });
  }
}

