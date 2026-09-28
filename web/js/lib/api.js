// Cliente HTTP da API REST (RNF21). Envia fuso, conta em uso, horário da ação e chave de idempotência.
import { TIMEZONE } from "./format.js";

export class ApiError extends Error {
  constructor(status, message, code, data) {
    super(message);
    this.status = status;
    this.code = code;
    this.data = data;
  }
}

/** Falhas de rede (offline, servidor fora do ar) chegam como TypeError do fetch. */
export const isNetworkError = (error) => !(error instanceof ApiError);

export async function request(method, path, { body, account, time, key, signal } = {}) {
  const headers = { "X-Timezone": TIMEZONE, Accept: "application/json" };
  if (account) headers["X-Account-Id"] = account;
  if (time) headers["X-Client-Time"] = time;
  if (key) headers["Idempotency-Key"] = key;
  let payload;
  if (body instanceof FormData) {
    payload = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const response = await fetch(path, { method, headers, body: payload, signal, credentials: "same-origin", cache: "no-store" });
  if (response.status === 204) return null;
  const type = response.headers.get("content-type") || "";
  const data = type.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const message = (data && data.detail) || `Erro ${response.status} no servidor.`;
    throw new ApiError(response.status, typeof message === "string" ? message : "Dados inválidos.", data && data.code, data);
  }
  return data;
}

export const api = {
  get: (path, options) => request("GET", path, options),
  post: (path, body, options) => request("POST", path, { ...options, body }),
  patch: (path, body, options) => request("PATCH", path, { ...options, body }),
  put: (path, body, options) => request("PUT", path, { ...options, body }),
  delete: (path, options) => request("DELETE", path, options),
};
