# ADR 0002: Privacidade do mamutômetro

## Status

Aceita — 2026-08-13. Implementada na CS-18.

## Contexto

A CS-18 pediu uma forma de o assinante "sinalizar em quem votou". O desenho
original fazia isso literalmente: uma estrela "votei nele", protegida por
cifra AES-256-GCM com o par (projeto, político) reduzido a um HMAC salgado.

Dois problemas. **Jurídico:** "em quem votei" é convicção política, dado
sensível pela LGPD (art. 5º, II), somado ao voto secreto. **De produto:**
estrelas comunicam avaliação, e este produto não avalia políticos.

## Decisão

Substituir a declaração de voto pelo **mamutômetro**: escala de 1 a N cujo
significado é definido por cada assinante e nunca informado ao sistema. Um
usuário usa "3 = votei"; outro, "3 = desconfio". O produto não pergunta, não
sugere e não registra a regra.

Quatro consequências que só fazem sentido juntas:

1. **Sem cifra.** A pergunta que ela bloqueava — "quem votou no político X" —
   deixa de ser respondível por construção. E o par (conta, político) já existe
   em claro em `projetos_parliamentarian` e nas tags: cifrar só aqui protegeria
   metade do que as tabelas vizinhas expõem inteiro.
2. **Sem consentimento formal.** Um modal sobre "tratamento da sua convicção
   política" declararia a semântica que o desenho acabou de remover. Existe um
   aviso neutro e dispensável na primeira utilização, sem registro de aceite.
3. **Sem agregado por político**, em nenhuma superfície, nem no admin. Com a
   base atual qualquer recorte desanonimiza, e um agregado seria engenharia
   reversa da semântica de cada um. Precedente: `_swaps_by_project` já mostra
   quantas trocas o usuário fez, nunca quais políticos.
4. **Neutralidade da interface é requisito.** Nenhum texto pode sugerir o que um
   nível significa — inclusive nome de coluna, que é documentação. O campo se
   chama `level`, não `afinidade`.

## Consequências

Continuam valendo, e são elas que sustentam a promessa: escopo pelo JWT, zero
visibilidade no admin, `DELETE` de verdade, e nenhum `usage_event` com id de
político.

**Limite honesto:** remover a semântica reduz muito a exposição, não a zera. Um
vazamento ainda revela que a conta X marcou o político Y em nível alto, e a
maioria tende à leitura óbvia da escala.

**Dívida criada:** a garantia passa a depender de copy, que muda sem revisão
técnica. Mitigação: teste lê `ui/src/components/selecao/Mamutometro.tsx` e falha
se sobrar "voto", "apoio", "afinidade" ou "prefer" em texto de tela. Se ele
falhar, ou a copy voltou atrás, ou esta ADR precisa mudar.

**A pergunta que vai voltar:** "por que não um top-10 dos mais marcados?" A
resposta é o item 3, e precisa estar escrita antes de a pergunta chegar com
pressa em cima.
