Configuracao Ghost

## Redirecionamento da home para o app

- Visite https://meu-endereco-aqui.com/ghost/#/settings/code-injection
- Em code injection, clique em open, copie e cole em `header` o codigo abaixo, que redireciona o Ghost para o app:

```
<script>
(function () {
  if (window.location.pathname === "/" && !window.location.hash) {
    window.location.replace("/app/");
  }
})();
</script>
```

- Salve e volte para a pagina inicial https://meu-endereco-aqui.com

## Webhooks de membros para sincronizar usuarios

O Mamute sincroniza membros do Ghost com projetos locais pela API. O endpoint
que recebe os eventos e:

```
https://mamute.voltdata.info/api/webhooks/ghost/members
```

Em outro dominio, troque apenas a origem. O caminho deve continuar:

```
/api/webhooks/ghost/members
```

### Variavel de ambiente da API

Crie `GHOST_WEBHOOK_SECRET` no app/container da API no CapRover:

```
mamute-api
```

Nao configure essa variavel em `mamute-ghost`, `mamute-scrappers` ou `mamute-ui`.
O valor deve ser um segredo forte e deve ser o mesmo usado no campo `Secret` dos
webhooks criados no Ghost.

Depois de salvar a variavel no CapRover, redeploy/restart o app `mamute-api`
caso o CapRover nao reinicie automaticamente.

### Criar a integracao no Ghost

Referencia oficial: https://docs.ghost.org/webhooks

1. Acesse o Ghost Admin:

   ```
   https://mamute.voltdata.info/ghost/
   ```

2. Va em `Settings` > `Advanced` > `Integrations`.

3. Clique em `Add custom integration`.

4. De um nome claro para a integracao, por exemplo:

   ```
   Mamute API - member sync
   ```

5. Dentro da integracao, crie um webhook para cada evento abaixo, todos usando
   a mesma URL e o mesmo segredo:

   | Event | Target URL | Secret |
   | --- | --- | --- |
   | `member.added` | `https://mamute.voltdata.info/api/webhooks/ghost/members` | mesmo valor de `GHOST_WEBHOOK_SECRET` |
   | `member.edited` | `https://mamute.voltdata.info/api/webhooks/ghost/members` | mesmo valor de `GHOST_WEBHOOK_SECRET` |
   | `member.deleted` | `https://mamute.voltdata.info/api/webhooks/ghost/members` | mesmo valor de `GHOST_WEBHOOK_SECRET` |

O Ghost considera a entrega bem-sucedida quando o endpoint responde com HTTP
`2xx`. Respostas `401` indicam assinatura/segredo invalido. Respostas `5xx`
indicam erro na API ou no banco.

### Testar a integracao

O Ghost pode nao exibir um botao de teste para webhooks. Nesse caso, teste com
um membro real temporario:

1. Crie um membro no Ghost com e-mail unico, por exemplo:

   ```
   webhook-real-test-20260602@voltdata.info
   ```

2. Aguarde alguns segundos e confira no Postgres:

   ```sql
   select id, email, cliente, tier_id, qtd_termos, tag_ghost, deleted_at, updated_at
   from projetos
   where email = 'webhook-real-test-20260602@voltdata.info'
   order by id desc;
   ```

   Resultado esperado: uma linha com `deleted_at is null`.

3. Exclua o membro temporario no Ghost.

4. Rode a consulta de novo.

   Resultado esperado: a mesma linha com `deleted_at` preenchido.

### Backfill manual

O webhook cobre eventos futuros. Para reconciliar membros ja existentes ou
recuperar evento perdido, rode o backfill manual dos scrappers:

```bash
python -m mamute_scrappers.scripts.create_users
```

Esse comando continua usando `GHOST_API_KEY` e `GHOST_ADMIN_URL`.
