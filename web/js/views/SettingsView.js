// Configurações da conta: nome e exclusão (RF27), perfil Membro/Gestor (RF61), tarefa parada (RN22),
// feed de calendário (RF55) e resumo diário por e-mail/Telegram (RF56, RN29).
import { html } from "../lib/html.js";
import { useEffect, useState } from "preact/hooks";
import { useStore } from "../lib/store.js";
import { Icon } from "../ui/icons.js";
import { Avatar, Button, Checkbox, Segmented } from "../ui/core.js";
import { Field, useFieldId } from "../ui/forms.js";
import { api } from "../lib/api.js";
import { TIMEZONE } from "../lib/format.js";
import { confirmDialog, deleteAccount, toast, updateAccount } from "../actions.js";

function Section({ title, icon, children, description }) {
  return html`<section class="panel stack" style="gap:14px">
    <div>
      <h2 class="panel-title"><${Icon} name=${icon} />${title}</h2>
      ${description ? html`<p class="small muted" style="margin-top:4px">${description}</p>` : null}
    </div>
    ${children}
  </section>`;
}

export function SettingsView() {
  const me = useStore((s) => (s.accounts || []).find((a) => a.id === s.meId));
  const board = useStore((s) => s.boards[s.meId]);
  const meta = useStore((s) => s.meta);
  const settings = board?.account?.settings || me?.settings || {};
  const ids = { name: useFieldId("name"), stale: useFieldId("stale"), email: useFieldId("email"), tg: useFieldId("tg"), time: useFieldId("time") };
  const [name, setName] = useState(me?.name || "");
  const [stale, setStale] = useState(settings.stale_days || 5);
  const [email, setEmail] = useState(settings.email || "");
  const [telegram, setTelegram] = useState(settings.telegram_chat_id || "");
  const [time, setTime] = useState(settings.digest_time || "08:00");
  const [channels, setChannels] = useState(settings.digest_channels || []);
  const [enabled, setEnabled] = useState(!!settings.digest_enabled);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(null);

  useEffect(() => {
    setStale(settings.stale_days || 5);
    setEmail(settings.email || "");
    setTelegram(settings.telegram_chat_id || "");
    setTime(settings.digest_time || "08:00");
    setChannels(settings.digest_channels || []);
    setEnabled(!!settings.digest_enabled);
  }, [board?.account?.settings]);

  if (!me) return null;
  const calendarUrl = `${meta?.public_url || location.origin}/api/accounts/${me.id}/calendar.ics`;

  const saveName = async () => {
    if (!name.trim() || name.trim() === me.name) return;
    try {
      await updateAccount(me.id, { name: name.trim() }, { success: "Nome atualizado." });
    } catch (error) {
      toast(error.message, "error");
      setName(me.name);
    }
  };

  const saveRole = async (role) => {
    try {
      await updateAccount(me.id, { role }, { success: role === "gestor" ? "Perfil alterado para Gestor." : "Perfil alterado para Membro." });
    } catch (error) {
      toast(error.message, "error");
    }
  };

  const saveSettings = async (changes, message = "Configurações salvas.") => {
    setSaving(true);
    try {
      await updateAccount(me.id, { settings: changes }, { success: message });
    } catch (error) {
      toast(error.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const saveDigest = () =>
    saveSettings({ email: email.trim(), telegram_chat_id: telegram.trim(), digest_time: time, digest_channels: channels, digest_enabled: enabled, timezone: TIMEZONE }, "Resumo diário configurado.");

  const test = async (channel) => {
    setTesting(channel);
    try {
      await api.post(`/api/accounts/${me.id}/digest/test`, { channel }, { account: me.id });
      toast(channel === "email" ? "Resumo enviado por e-mail." : "Resumo enviado pelo Telegram.");
    } catch (error) {
      toast(error.message, "error");
    } finally {
      setTesting(null);
    }
  };

  const copy = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      toast("Endereço copiado.");
    } catch {
      toast(text, "info");
    }
  };

  const remove = async () => {
    const ok = await confirmDialog({
      title: `Excluir a conta “${me.name}”?`,
      text: "Todas as tarefas e metas desta conta serão excluídas definitivamente. Esta ação não pode ser desfeita.",
      confirmLabel: "Excluir conta",
      danger: true,
    });
    if (!ok) return;
    try {
      await deleteAccount(me.id);
    } catch (error) {
      toast(error.message, "error");
    }
  };

  const toggleChannel = (channel, on) => setChannels(on ? [...new Set([...channels, channel])] : channels.filter((c) => c !== channel));

  return html`<div class="stack" style="gap:18px;max-width:760px">
    <header class="page-head">
      <div class="row" style="gap:14px">
        <${Avatar} account=${me} size="lg" />
        <div>
          <h1 class="page-title">Configurações da conta</h1>
          <p class="page-subtitle">Identificação apenas pelo nome, sem senha. Use somente com dados não sensíveis.</p>
        </div>
      </div>
    </header>

    <${Section} title="Conta" icon="user">
      <${Field} label="Nome" id=${ids.name} hint="Único na equipe, sem distinção entre maiúsculas e minúsculas.">
        <div class="row">
          <input id=${ids.name} class="input" maxLength="60" value=${name} onInput=${(e) => setName(e.currentTarget.value)} onKeyDown=${(e) => e.key === "Enter" && saveName()} />
          <${Button} onClick=${saveName} disabled=${!name.trim() || name.trim() === me.name}>Salvar<//>
        </div>
      <//>
      <${Field} label="Perfil" hint="O Gestor acompanha toda a equipe, atribui tarefas e comenta; o restante é somente leitura.">
        <${Segmented}
          label="Perfil"
          value=${me.role}
          options=${[
            { value: "membro", label: "Membro" },
            { value: "gestor", label: "Gestor" },
          ]}
          onChange=${saveRole}
        />
      <//>
    <//>

    <${Section} title="Alertas" icon="pause" description="Tarefas pendentes sem criação, edição ou marcação de etapa nesse intervalo recebem o destaque de “parada”.">
      <${Field} label="Considerar parada após (dias)" id=${ids.stale}>
        <div class="row">
          <input id=${ids.stale} class="input" type="number" min="1" max="90" style="max-width:120px" value=${stale} onInput=${(e) => setStale(e.currentTarget.value)} />
          <${Button} loading=${saving} onClick=${() => saveSettings({ stale_days: Number(stale) })}>Salvar<//>
        </div>
      <//>
    <//>

    <${Section}
      title="Calendário (.ics)"
      icon="calendar"
      description="Assine no Google Agenda (Outras agendas → Do URL) ou no Outlook (Adicionar calendário → Da Internet). As datas de entrega aparecem como eventos de dia inteiro."
    >
      <div class="row">
        <input class="input mono" readOnly value=${calendarUrl} aria-label="Endereço do calendário" onFocus=${(e) => e.currentTarget.select()} />
        <${Button} icon="copy" onClick=${() => copy(calendarUrl)}>Copiar<//>
      </div>
      <p class="xsmall faint">O Google Agenda só consegue ler endereços acessíveis pela internet; em rede interna, use o Outlook ou publique o servidor com HTTPS.</p>
    <//>

    <${Section} title="Resumo diário" icon="mail" description="Atrasadas, vencimentos do dia e Top 3, no horário escolhido. E-mail e Telegram são opcionais.">
      <label class="row" style="cursor:pointer">
        <${Checkbox} checked=${enabled} onChange=${setEnabled} label="Ativar resumo diário" />
        <span>Enviar resumo diário</span>
      </label>
      <div class="form-grid">
        <${Field} label="Horário" id=${ids.time}>
          <input id=${ids.time} class="input" type="time" value=${time} onInput=${(e) => setTime(e.currentTarget.value)} />
        <//>
        <div></div>
        <${Field} label="E-mail" id=${ids.email} hint=${meta?.email_enabled ? null : "O servidor ainda não tem SMTP configurado."}>
          <div class="row">
            <${Checkbox} checked=${channels.includes("email")} onChange=${(on) => toggleChannel("email", on)} label="Receber por e-mail" />
            <input id=${ids.email} class="input" type="email" placeholder="voce@empresa.com" value=${email} onInput=${(e) => setEmail(e.currentTarget.value)} />
          </div>
        <//>
        <${Field} label="Telegram (ID do chat)" id=${ids.tg} hint=${meta?.telegram_enabled ? "Inicie conversa com o bot da equipe e informe o ID do chat." : "O servidor ainda não tem bot do Telegram configurado."}>
          <div class="row">
            <${Checkbox} checked=${channels.includes("telegram")} onChange=${(on) => toggleChannel("telegram", on)} label="Receber pelo Telegram" />
            <input id=${ids.tg} class="input" placeholder="123456789" value=${telegram} onInput=${(e) => setTelegram(e.currentTarget.value)} />
          </div>
        <//>
      </div>
      <div class="row-wrap">
        <${Button} variant="primary" loading=${saving} onClick=${saveDigest}>Salvar resumo diário<//>
        <${Button} variant="ghost" icon="send" loading=${testing === "email"} disabled=${!meta?.email_enabled || !settings.email} onClick=${() => test("email")}>Testar e-mail<//>
        <${Button} variant="ghost" icon="send" loading=${testing === "telegram"} disabled=${!meta?.telegram_enabled || !settings.telegram_chat_id} onClick=${() => test("telegram")}>Testar Telegram<//>
      </div>
      <p class="xsmall faint">Fuso usado no envio: ${settings.timezone || TIMEZONE}.</p>
    <//>

    <section class="panel danger-zone stack" style="gap:12px">
      <h2 class="panel-title"><${Icon} name="alert" />Zona de perigo</h2>
      <p class="small muted">Excluir a conta remove definitivamente as tarefas e metas dela.</p>
      <div><${Button} variant="danger" icon="trash" onClick=${remove}>Excluir conta<//></div>
    </section>
  </div>`;
}
