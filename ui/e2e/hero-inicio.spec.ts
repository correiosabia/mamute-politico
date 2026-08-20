import { test, expect } from "@playwright/test";

/**
 * Regressao de layout do heroi da home (CS-35).
 *
 * O incomodo reportado pelo designer era dependente de resolucao: a ilustracao
 * do Congresso e renderizada com `w-full`, entao sua altura cresce junto com a
 * largura da viewport, enquanto a altura do heroi vinha de min-heights fixos
 * (560px / 800px no 2xl). Resultado: entre ~1440 e 1535px os CTAs encostavam no
 * gramado, e de 1536px pra cima sobrava um vazio de ~250px acima do chapeu.
 *
 * A correcao amarra a altura do heroi ao conteudo + uma faixa reservada com a
 * mesma proporcao do gramado, o que deve manter as duas metricas abaixo estaveis
 * em qualquer largura.
 */

// Asset: 1440x401. O gramado (primeira faixa opaca no lado esquerdo, onde o
// texto vive) comeca em y=258 — ou seja, os ultimos 143px da imagem.
const FAIXA_GRAMADO = 143 / 401;

// Folga minima entre o CTA e o gramado, e teto pro espaco acima do chapeu.
const FOLGA_MINIMA_PX = 24;
const ESPACO_TOPO_MAXIMO_PX = 96;

const LARGURAS = [1280, 1600, 1920];

for (const width of LARGURAS) {
  test(`heroi da home mantem conteudo na faixa amarela em ${width}px @app`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/app/");

    const hero = page.getByTestId("hero-inicio");
    const ilustracao = page.getByTestId("hero-congresso-desktop");
    const cta = page.getByRole("link", { name: "EXPLORAR DASHBOARD" });
    const chapeu = page.getByText("TEMPO REAL", { exact: false }).first();

    await expect(cta).toBeVisible();
    await expect(ilustracao).toBeVisible();

    const [heroBox, imgBox, ctaBox, chapeuBox] = await Promise.all([
      hero.boundingBox(),
      ilustracao.boundingBox(),
      cta.boundingBox(),
      chapeu.boundingBox(),
    ]);
    const headerBox = await page.locator("header").first().boundingBox();

    expect(heroBox && imgBox && ctaBox && chapeuBox && headerBox).toBeTruthy();

    // 1. Nenhum CTA sobre a ilustracao: o botao mais baixo fica acima do gramado.
    const topoGramado = imgBox!.y + imgBox!.height * (1 - FAIXA_GRAMADO);
    const folga = topoGramado - (ctaBox!.y + ctaBox!.height);
    expect(
      folga,
      `CTA deve ficar ao menos ${FOLGA_MINIMA_PX}px acima do gramado (folga=${Math.round(folga)}px)`
    ).toBeGreaterThanOrEqual(FOLGA_MINIMA_PX);

    // 2. Sem vazio no topo: o chapeu segue logo abaixo do header.
    const espacoTopo = chapeuBox!.y - (headerBox!.y + headerBox!.height);
    expect(
      espacoTopo,
      `espaco acima do chapeu deve ficar <= ${ESPACO_TOPO_MAXIMO_PX}px (atual=${Math.round(espacoTopo)}px)`
    ).toBeLessThanOrEqual(ESPACO_TOPO_MAXIMO_PX);

    // 3. A ilustracao nao e cortada no topo (as torres ficam nos ~6% de cima).
    expect(
      Math.round(heroBox!.y - imgBox!.y),
      "topo da ilustracao nao deve ser cortado pelo overflow-hidden do heroi"
    ).toBeLessThanOrEqual(0);
  });
}
