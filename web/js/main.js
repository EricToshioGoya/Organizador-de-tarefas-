// Ponto de entrada: registra o service worker (PWA — RNF20), inicializa o estado e renderiza o app.
import { html, render } from "./lib/html.js";
import { App } from "./views/App.js";
import { init } from "./actions.js";

render(html`<${App} />`, document.getElementById("app"));
init();

if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost" || location.hostname === "127.0.0.1")) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {
      /* sem service worker: o app segue funcionando online */
    });
  });
}
