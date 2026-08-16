# Mamute Político - UI

Tecnologias utilizadas:

- Vite
- TypeScript
- React
- shadcn-ui
- Tailwind CSS


## Interface web (ui)

A pasta `ui/` contém uma **SPA** em **React** (Vite, TypeScript, shadcn/ui, Tailwind CSS) que:

- Consome a API REST em **`{VITE_BASE_URL}/api`** (por exemplo, parlamentares, proposições, votações).
- Usa **Ghost Members** para login e token: URLs de sessão, JWKS e links do portal são derivados de **`VITE_BASE_URL`** (mesma origem base configurada no build).
- Chama o chatbot por **mesma origem** em **`POST /chat/chatbot/stream`** (sem variável de ambiente extra; o proxy — por exemplo Caddy em `environments/*` — encaminha `/chat` ao serviço do chatbot).

### Variáveis de ambiente

Veja o modelo em [`ui/.env.example`](ui/.env.example). As principais:

| Variável | Função |
|----------|--------|
| `VITE_BASE_URL` | Origem sem barra final. A aplicação monta a API em `{VITE_BASE_URL}/api` e as rotas Ghost em `{VITE_BASE_URL}`. |
| `VITE_GHOST_JWKS` | (Opcional) JWKS do Ghost em JSON; se omitido, o fluxo de token pode seguir sem verificação no cliente. |

No **Docker**, as variáveis `VITE_*` são injetadas no **build** (ver [`ui/Dockerfile`](ui/Dockerfile)). No stack de **produção**, o serviço `ui` é definido em [`environments/production/docker-compose.yml`](environments/production/docker-compose.yml). O **Caddy** nos diretórios `environments/development` e `environments/production` encaminha tráfego para API, chatbot e arquivos estáticos conforme cada `Caddyfile`.

### Desenvolvimento local

```bash
cd ui
npm ci   # ou npm install
npm run dev
```

O servidor de desenvolvimento do Vite usa a **porta 8080** (ver `vite.config.ts`). Ajuste `VITE_BASE_URL` para coincidir com onde a API e o Ghost estão expostos no navegador.

## Marcações pessoais (CS-18)

Ficam na tela de seleção, sobre a lista de parlamentares monitorados:

- **Ordem pessoal** — setas ↑ ↓ e "mover para o topo". Sem drag-and-drop de
  propósito: funciona no toque e no teclado, e não exige biblioteca nova.
- **Tags livres** — chips no card, editor com buscar/criar, e filtro por tag.
  Enquanto há filtro ativo os controles de ordem somem: ordenar uma lista
  filtrada enviaria a lista parcial e a API recusaria.
- **Mamutômetro** — escala de N mamutes. Clicar no nível atual limpa a marcação.

Tudo isso está atrás de feature flag (`marcacoes_pessoais` e `mamutometro`).
**Com as flags desligadas a tela é idêntica à de antes da feature**, ordem
alfabética inclusive — há teste travando isso.

### A regra que não pode ser quebrada

O mamutômetro **não pode ter legenda**. O significado de cada nível é de quem
usa, e o dia em que a interface disser o que 3 significa, o sistema passa a
guardar aquilo. Por isso os rótulos de acessibilidade são posicionais
("marcar 2 de 3"), nunca semânticos, e há teste que lê o componente e falha se
encontrar "voto", "apoio", "afinidade" ou "prefer" em texto de tela.

Antes de mexer na copy dessa área, leia
[`docs/adr/0002-privacidade-do-mamutometro.md`](../docs/adr/0002-privacidade-do-mamutometro.md).

O tamanho da régua, os escopos e o texto do aviso são configurados em
**Admin → Configurações**; quais planos têm a feature, no painel de
funcionalidades.
