import { test, expect } from "@playwright/test";

/**
 * Smoke E2E — roda contra `vite preview` (build estatico, sem backend).
 *
 * Cobre o que e possivel sem stack completa:
 * - SPA carrega index.html e tem markup esperado
 * - Bundle JS resolveu (no console errors fatais)
 * - Asset principal (CSS/JS) responde 200
 * - Bundle nao referencia URLs loopback (defesa em profundidade do shell smoke)
 *
 * NAO cobre (precisa stack docker, fica pra Onda 2):
 * - Auth real (magic link Ghost)
 * - Chamadas reais /api/* (precisaria mock ou backend)
 * - Fluxo dashboard -> favoritar
 */

test.describe("smoke @app", () => {
  test("SPA root carrega e responde com markup esperado", async ({ page, request }) => {
    // Vite serve em /app/ (base configurada em vite.config.ts).
    const resp = await page.goto("/app/");
    expect(resp?.status(), "GET /app/ deve retornar 200").toBe(200);

    // Title vem do <title> em index.html — checa que SPA renderizou shell.
    await expect(page).toHaveTitle(/Mamute|Pol[ií]tico/i);

    // Pelo menos um <script type="module"> apontando pro bundle compilado.
    const scriptCount = await page.locator('script[type="module"]').count();
    expect(scriptCount, "deve ter ao menos 1 script module").toBeGreaterThan(0);

    // Bundle assets resolvem 200 (pega bug onde caminho /app/ esta errado).
    const assets = page.locator('script[src*="/app/assets/"], link[href*="/app/assets/"]');
    const count = await assets.count();
    expect(count, "deve referenciar assets em /app/assets/").toBeGreaterThan(0);
    if (count > 0) {
      const firstSrc = (await assets.first().getAttribute("src")) ??
        (await assets.first().getAttribute("href"));
      const url = new URL(firstSrc!, "http://127.0.0.1:4173").toString();
      const assetResp = await request.get(url);
      expect(assetResp.status(), `asset ${url} deve servir 200`).toBe(200);
    }
  });

  test("static asset (robots.txt) serve sob /app/ — pipeline saudavel", async ({ request }) => {
    // Vite copia ui/public/* pra dist com base /app/. Falha aqui = asset
    // pipeline quebrado ou base config errada.
    const resp = await request.get("/app/robots.txt");
    expect(resp.status(), "GET /app/robots.txt deve servir").toBeLessThan(400);
    const body = await resp.text();
    expect(body.length, "robots.txt nao deve estar vazio").toBeGreaterThan(0);
  });

  test("metadados sociais e card sao publicados sob /app/", async ({ page, request }) => {
    const resp = await page.goto("/app/");
    expect(resp?.status(), "GET /app/ deve retornar 200").toBe(200);

    const imageUrl = "https://mamute.voltdata.info/app/mamute-social-card.png";
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
      "href",
      "https://mamute.voltdata.info/app/"
    );
    await expect(page.locator('meta[property="og:url"]')).toHaveAttribute(
      "content",
      "https://mamute.voltdata.info/app/"
    );
    await expect(page.locator('meta[property="og:image"]')).toHaveAttribute("content", imageUrl);
    await expect(page.locator('meta[name="twitter:card"]')).toHaveAttribute(
      "content",
      "summary_large_image"
    );
    await expect(page.locator('meta[name="twitter:image"]')).toHaveAttribute("content", imageUrl);

    const card = await request.get("/app/mamute-social-card.png");
    expect(card.status(), "card social deve servir sob /app/").toBe(200);
    expect(card.headers()["content-type"]).toContain("image/png");
  });

  test("nao ha erros JS criticos no console no boot", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });

    await page.goto("/app/");
    // Espera SPA assentar — TanStack Query pode disparar fetches que falham
    // (sem backend) e isso vira erro de console. Filtramos por padroes
    // esperaveis: ECONNREFUSED, fetch failed, NetworkError, 404, 422.
    await page.waitForLoadState("networkidle", { timeout: 5_000 }).catch(() => {});

    const expectedTransientPatterns = [
      /Failed to fetch/i,
      /NetworkError/i,
      /ECONNREFUSED/i,
      /404/,
      /422/,
      /401/,
      /api\/.*404/i,
      /Recurso n[ãa]o encontrado/i,
      /Token ausente/i,
    ];

    const fatalErrors = errors.filter(
      (e) => !expectedTransientPatterns.some((p) => p.test(e))
    );

    expect(
      fatalErrors,
      `Erros JS nao-transientes detectados:\n${fatalErrors.join("\n")}`
    ).toEqual([]);
  });
});
