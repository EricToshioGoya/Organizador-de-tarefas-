// "Quem está usando?" (RF23–RF25, RF28): escolher conta existente ou criar uma só com o nome.
import { html } from "../lib/html.js";
import { useState } from "preact/hooks";
import { useStore } from "../lib/store.js";
import { Icon } from "../ui/icons.js";
import { Avatar, Button } from "../ui/core.js";
import { createAccount, selectAccount } from "../actions.js";

export function AccountPicker() {
  const accounts = useStore((s) => s.accounts);
  const online = useStore((s) => s.online);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    const clean = name.trim();
    if (!clean) {
      setError("Informe seu nome.");
      return;
    }
    if ((accounts || []).some((a) => a.name.toLocaleLowerCase("pt-BR") === clean.toLocaleLowerCase("pt-BR"))) {
      setError("Já existe uma conta com esse nome.");
      return;
    }
    setBusy(true);
    try {
      await createAccount(clean);
    } catch (err) {
      setError(err.message || "Não foi possível criar a conta.");
    } finally {
      setBusy(false);
    }
  };

  return html`<main class="picker" id="main">
    <div class="glass picker-card">
      <div class="brand" style="justify-content:center;font-size:var(--text-lg)">
        <span class="brand-mark"><${Icon} name="logo" size=${18} strokeWidth=${2.4} /></span>
        <span class="brand-name">Organizador de Tarefas</span>
      </div>
      <h1 class="picker-title">Quem está <span>usando?</span></h1>
      <p class="muted">Escolha sua conta. Não há senha: a identificação é só pelo nome.</p>

      ${accounts === null
        ? html`<div class="picker-grid">${[1, 2, 3].map((i) => html`<div key=${i} class="skeleton" style="height:150px;border-radius:16px"></div>`)}</div>`
        : html`<div class="picker-grid" role="list">
            ${accounts.map(
              (account) => html`<button key=${account.id} type="button" role="listitem" class="picker-account" onClick=${() => selectAccount(account.id)}>
                <${Avatar} account=${account} size="xl" />
                <span class="name">${account.name}</span>
                ${account.role === "gestor" ? html`<span class="role"><${Icon} name="crown" size=${12} />Gestor</span>` : html`<span class="role">Membro</span>`}
              </button>`,
            )}
            ${!creating
              ? html`<button type="button" role="listitem" class="picker-account picker-new" onClick=${() => setCreating(true)} disabled=${!online}>
                  <span class="avatar-new"><${Icon} name="plus" size=${30} /></span>
                  <span class="name">Nova conta</span>
                  <span class="role">${online ? "apenas o nome" : "requer conexão"}</span>
                </button>`
              : null}
          </div>`}

      ${creating
        ? html`<form class="stack" style="max-width:420px;margin:28px auto 0;gap:10px" onSubmit=${submit}>
            <label class="field-label" for="new-account-name" style="justify-content:center">Seu nome</label>
            <input
              id="new-account-name"
              class="input"
              maxLength="60"
              placeholder="Ex.: Pedro Silva"
              value=${name}
              ref=${(el) => el && !name && el.focus()}
              aria-invalid=${error ? "true" : undefined}
              onInput=${(e) => {
                setName(e.currentTarget.value);
                setError(null);
              }}
            />
            ${error ? html`<div class="field-error" role="alert"><${Icon} name="alert" size=${13} />${error}</div>` : null}
            <div class="row" style="justify-content:center">
              <${Button} variant="ghost" onClick=${() => (setCreating(false), setName(""), setError(null))}>Cancelar<//>
              <${Button} type="submit" variant="primary" icon="check" loading=${busy}>Criar conta<//>
            </div>
          </form>`
        : null}
      ${accounts && !accounts.length && !creating
        ? html`<p class="small muted" style="margin-top:20px">Ainda não há contas. Crie a primeira para começar.</p>`
        : null}
    </div>
  </main>`;
}
