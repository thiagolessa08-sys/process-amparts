# Gateway — roteamento por path de `www.processintelligence.com.br`

O Railway mapeia um domínio para **um** serviço e não roteia por path. Este
gateway existe para que vários projetos dividam o mesmo domínio:

```
www.processintelligence.com.br
         │
   [ gateway (este serviço) ]  ← o Custom Domain fica AQUI
         │
   ┌─────┴──────┬─────────────┐
/amparts    /cordeiro     /biolab
   │            │             │
front-am    front-cor    front-bio    (serviços Railway)
```

## Como funciona

Repasse puro, **sem reescrita de path**. Cada frontend é compilado com
`base: '/<prefixo>/'` no `vite.config.js` e servido a partir de `dist/<prefixo>`,
então já responde no próprio prefixo.

O `header_up Host` é obrigatório: a borda do Railway decide o serviço de destino
pelo cabeçalho `Host`. Sem ele, o upstream recebe `www.processintelligence.com.br`
e o Railway não sabe para onde entregar.

## Setup no Railway (uma vez)

1. Novo serviço no projeto, a partir deste repositório, com
   **Root Directory = `gateway`**.
2. Nesse serviço: **Settings → Custom Domain** → `www.processintelligence.com.br`.
   Crie no registrador o CNAME que o Railway indicar.
3. **Remova** o Custom Domain do serviço do frontend, se já tiver sido posto lá —
   o domínio pertence ao gateway agora.
4. Os serviços dos projetos continuam com suas URLs `*.up.railway.app`. Elas
   seguem funcionando e são o que o gateway chama por baixo.

## Adicionar um projeto

1. No `vite.config.js` do projeto novo:
   `base: '/<prefixo>/'` e `build: { outDir: 'dist/<prefixo>' }`.
2. No `Caddyfile`, descomente/copie um bloco:

```
@prefixo path /prefixo /prefixo/*
handle @prefixo {
	reverse_proxy https://SERVICO.up.railway.app {
		header_up Host SERVICO.up.railway.app
	}
}
```

3. Adicione o domínio ao regex de CORS do backend desse projeto.

## Verificação depois do deploy

```bash
curl -sS -o /dev/null -w '%{http_code} %{redirect_url}\n' https://www.processintelligence.com.br/health
```

Esperado por rota:

| Rota | Esperado |
|---|---|
| `/health` | `200 ok` (não depende de upstream) |
| `/` | `302` → `/amparts/` |
| `/amparts` | `200` HTML |
| `/amparts/` | `200` HTML |
| `/amparts/assets/index-*.js` | `200 application/javascript` |
| `/qualquer-outra-coisa` | `404` |

## Dívida conhecida

Este diretório vive no repositório do AM Parts por conveniência, mas é
**infraestrutura compartilhada**: ao adicionar o segundo projeto, o `Caddyfile`
passa a listar serviços que nada têm a ver com o AM Parts. Vale extrair para um
repositório próprio (`process-gateway`) nesse momento. O Root Directory do
serviço no Railway é a única coisa que precisa mudar.
