export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/product-image") {
      const targetRaw = url.searchParams.get("url");
      if (!targetRaw) return new Response("Missing url", { status: 400 });

      let target;
      try { target = new URL(targetRaw); } catch {
        return new Response("Invalid url", { status: 400 });
      }

      if (target.protocol !== "https:") {
        return new Response("HTTPS only", { status: 400 });
      }

      const allowedHosts = [
        "i.ebayimg.com",
        "cdn.mscdirect.com",
        "industrybuying.com",
        "insertcarbide.com",
        "rinaldi-tools.com",
        "artykulytechniczne.pl",
        "cdn.turnersupply.com",
        "epublications.sandvik.coromant.com",
        "www.bwintools.com",
        "www.cutwel.co.uk",
        "webshop.iscaritalia.it",
        "ssl.ingersoll-imc.com",
        "ntkcuttingtools.com",
        "tool-global.kyocera.com",
        "tungaloy.com",
        "www.kennametal.com",
        "static1.industrybuying.com",
        "c.cdnmp.net",
        "images.nexusapp.co",
        "darxton.ru",
        "img2.tradewheel.com",
        "cdn.dgisupply.ca",
        "cdn11.bigcommerce.com",
        "gen3industrial.com",
        "www.maxodeals.com",
        "ssl.ingersoll-imc.com",
        "ingersoll-imc.com"
      ];

      const allowed = allowedHosts.some(
        host => target.hostname === host || target.hostname.endsWith("." + host)
      );
      if (!allowed) return new Response("Image host not allowed", { status: 403 });

      const candidates = [targetRaw]
        .concat(url.searchParams.getAll("fallback"))
        .filter(Boolean)
        .slice(0, 4);

      for (const candidateRaw of candidates) {
        let candidate;
        try { candidate = new URL(candidateRaw); } catch { continue; }
        if (candidate.protocol !== "https:") continue;

        const candidateAllowed = allowedHosts.some(
          host => candidate.hostname === host || candidate.hostname.endsWith("." + host)
        );
        if (!candidateAllowed) continue;

        const headerSets = [
          {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Referer": candidate.origin + "/"
          },
          {
            "User-Agent": "Mozilla/5.0",
            "Accept": "image/avif,image/webp,image/*,*/*;q=0.7"
          }
        ];

        for (const requestHeaders of headerSets) {
          try {
            const upstream = await fetch(candidate.toString(), { headers: requestHeaders });
            if (!upstream.ok) continue;

            const contentType = upstream.headers.get("content-type") || "";
            if (!contentType.toLowerCase().startsWith("image/")) continue;

            const headers = new Headers();
            headers.set("Content-Type", contentType);
            headers.set("Cache-Control", "public, max-age=86400, s-maxage=604800, stale-while-revalidate=2592000");
            headers.set("Access-Control-Allow-Origin", "*");
            headers.set("X-Image-Source", candidate.hostname);

            return new Response(upstream.body, { status: 200, headers });
          } catch {}
        }
      }

      return new Response("Image unavailable", { status: 502 });
    }

    return env.ASSETS.fetch(request);
  }
};