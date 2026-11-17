// Общие компоненты: иконки, api(), кнопки с загрузкой, тосты, диалог подтверждения, комбобокс офферов, копирование.
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");

/** h("button.btn.btn-sm", {type: "button", onclick}, "Текст", child) — маленький конструктор DOM без innerHTML. */
function h(tag, attrs = {}, ...children) {
  const [name, ...classes] = tag.split(".");
  const el = document.createElement(name);
  if (classes.length) el.className = classes.join(" ");
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (k === "text") el.textContent = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  el.append(...children.flat().filter((c) => c != null && c !== false));
  return el;
}

// Пути Lucide (ISC), 24×24, обводка задаётся в CSS
const ICONS = {
  refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
  external: '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
  plus: '<path d="M5 12h14"/><path d="M12 5v14"/>',
  pin: '<path d="M12 17v5"/><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/>',
  undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11"/>',
  alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  copy: '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
  x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  arrow: '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
};

function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "icon");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = ICONS[name];
  return svg;
}

// <span data-icon="refresh"></span> в шаблонах
function hydrateIcons(root = document) {
  for (const el of $$("[data-icon]", root)) el.replaceWith(icon(el.dataset.icon));
}

/* ---------- api() ---------- */

class ApiError extends Error {
  constructor(status, message, detail) {
    super(message);
    this.status = status; // 0 — сеть
    this.detail = detail;
  }
  /** Поле формы, к которому относится ошибка валидации (из loc pydantic или по тексту). */
  get field() {
    if (Array.isArray(this.detail)) return this.detail[0]?.loc?.at(-1);
    return null;
  }
}

function detailText(detail, status) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // ошибка валидации pydantic: [{loc: ["body", "offer_id"], msg: "..."}]
    return detail.map((d) => `${(d.loc || []).filter((p) => p !== "body").join(".") || "запрос"}: ${d.msg}`).join("; ");
  }
  return `Ошибка ${status}`;
}

async function api(method, url, body) {
  let r;
  try {
    r = await fetch(url, {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Нет связи с приложением: проверьте, что сервер запущен, и повторите", null);
  }
  const data = await r.json().catch(() => null);
  if (!r.ok) throw new ApiError(r.status, detailText(data?.detail, r.status), data?.detail);
  return data;
}

/* ---------- Кнопки ---------- */

/** Состояние загрузки: спиннер поверх подписи, ширина не меняется, повторный клик игнорируется. */
function setBusy(btn, busy) {
  if (!btn) return;
  if (busy) {
    btn.setAttribute("aria-busy", "true");
    btn.dataset.wasDisabled = btn.getAttribute("aria-disabled") || "";
    btn.setAttribute("aria-disabled", "true");
    btn.append(h("span.spinner", { "aria-hidden": "true" }));
  } else {
    btn.removeAttribute("aria-busy");
    $(".spinner", btn)?.remove();
    if (btn.dataset.wasDisabled === "true") btn.setAttribute("aria-disabled", "true");
    else btn.removeAttribute("aria-disabled");
  }
}

const isBlocked = (btn) => btn.disabled || btn.getAttribute("aria-disabled") === "true";

/* ---------- Тосты ---------- */

function toast(message, { type = "success", action } = {}) {
  const region = $("#toasts");
  const close = () => {
    el.classList.add("leaving");
    setTimeout(() => el.remove(), reducedMotion.matches ? 0 : 150);
  };
  const el = h(
    `div.toast.toast-${type}`,
    type === "error" ? { role: "alert" } : {},
    icon(type === "error" ? "alert" : "check"),
    h("div.toast-body", { text: message }),
    action && h("button.btn.btn-sm.btn-secondary", { type: "button", onclick: () => { close(); action.run(); } }, action.label),
    h("button.btn.btn-sm.btn-ghost.icon-btn", { type: "button", "aria-label": "Закрыть", onclick: close }, icon("x")),
  );
  region.append(el);
  if (type !== "error") setTimeout(close, 4000); // ошибка висит до закрытия
  return el;
}

/* ---------- Диалог подтверждения ---------- */

/** Нативный <dialog>: showModal даёт фокус-ловушку и Esc. Фокус возвращается на кнопку, открывшую диалог. */
function confirmDialog({ title, body, confirmLabel, cancelLabel = "Отмена", danger = false }) {
  const opener = document.activeElement;
  return new Promise((resolve) => {
    const ok = h(`button.btn.${danger ? "btn-danger" : "btn-primary"}`, { type: "submit", value: "ok" }, confirmLabel);
    const dlg = h(
      "dialog",
      { "aria-labelledby": "dlg-title" },
      h(
        "form",
        { method: "dialog" },
        h("div.dialog-body", {}, h("h2", { id: "dlg-title", text: title }), body),
        h("div.dialog-actions", {}, h("button.btn.btn-secondary", { type: "submit", value: "cancel" }, cancelLabel), ok),
      ),
    );
    dlg.addEventListener("close", () => {
      resolve(dlg.returnValue === "ok");
      dlg.remove();
      if (opener?.isConnected) opener.focus();
    });
    document.body.append(dlg);
    dlg.showModal();
    ok.focus();
  });
}

/* ---------- Копирование ---------- */

document.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-copy]");
  if (!btn) return;
  try {
    await navigator.clipboard.writeText(btn.dataset.copy);
  } catch {
    return toast("Не удалось скопировать: браузер не дал доступ к буферу обмена", { type: "error" });
  }
  const label = $(".copy-label", btn);
  const prev = label?.textContent;
  btn.dataset.copied = "";
  btn.replaceChild(icon("check"), $("svg", btn));
  if (label) label.textContent = "Скопировано";
  $("#sr-status").textContent = "Скопировано";
  setTimeout(() => {
    delete btn.dataset.copied;
    btn.replaceChild(icon("copy"), $("svg", btn));
    if (label) label.textContent = prev;
  }, 1200);
});

/** Кнопка «скопировать»: показывает значение моноширинным, клик копирует. */
function copyButton(value, ariaLabel) {
  return h(
    "button.copy",
    { type: "button", "data-copy": String(value), "aria-label": ariaLabel, title: "Скопировать" },
    h("span.mono.copy-label", { text: String(value) }),
    icon("copy"),
  );
}

/* ---------- Офферы ---------- */

const nameHasId = (o) => new RegExp(`^${o.id}(?!\\d)`).test(o.name);
/** Название без ведущего id («25327 Mixflow AU» → «Mixflow AU»): id и так стоит в своей колонке. */
const bareName = (o) => (nameHasId(o) && o.name.slice(String(o.id).length).replace(/^[\s\-–—:|#.]+/, "")) || o.name;

function offerLabel(o, { query } = {}) {
  const name = h("span.name", { title: o.name });
  highlight(name, bareName(o), query);
  return [h("span.mono", { text: String(o.id) }), name];
}

function highlight(el, text, query) {
  const q = (query || "").trim().toLowerCase();
  const i = q ? text.toLowerCase().indexOf(q) : -1;
  if (i < 0) return (el.textContent = text);
  el.append(text.slice(0, i), h("mark", { text: text.slice(i, i + q.length) }), text.slice(i + q.length));
}

/* ---------- Комбобокс (ARIA 1.2, список с автодополнением) ---------- */

let comboSeq = 0;

/**
 * Поиск оффера в Keitaro. Выбранный оффер хранится явно: input.dataset.offerId и combo.selected.
 * onSelect(offer|null) вызывается при выборе и при сбросе; onEnter(offer) — Enter при уже выбранном оффере.
 */
function Combobox(input, { onSelect = () => {}, onEnter } = {}) {
  const id = `combo-${++comboSeq}`;
  const list = h("ul.combo-list", { role: "listbox", id: `${id}-list`, "aria-label": "Офферы" });
  const status = h("div.combo-status", { role: "status" });
  const pop = h("div.combo-pop", { hidden: true }, list, status);
  input.after(pop);
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-expanded", "false");
  input.setAttribute("aria-controls", list.id);
  input.autocomplete = "off";
  input.spellcheck = false;

  const self = { selected: null, select, clear, input };
  let items = [], active = -1, timer, ctrl;

  function open() { pop.hidden = false; input.setAttribute("aria-expanded", "true"); }
  function close() {
    pop.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    active = -1;
  }
  function setActive(i) {
    if (!items.length) return;
    active = (i + items.length) % items.length;
    $$(".combo-opt", list).forEach((li, j) => li.setAttribute("aria-selected", String(j === active)));
    const li = list.children[active];
    input.setAttribute("aria-activedescendant", li.id);
    li.scrollIntoView({ block: "nearest" });
  }
  function showStatus(text, { error = false, retry = false, spinner = false } = {}) {
    status.className = "combo-status" + (error ? " error" : "");
    status.replaceChildren(
      ...[
        spinner ? h("span.spinner", { "aria-hidden": "true" }) : error ? icon("alert") : null,
        h("span", { text }),
        retry ? h("button.btn.btn-sm.btn-secondary", { type: "button", onmousedown: (e) => e.preventDefault(), onclick: () => search(true) }, "Повторить") : null,
      ].filter(Boolean),
    );
    status.hidden = !text;
  }
  function renderItems(q) {
    list.replaceChildren(
      ...items.map((o, i) =>
        h(
          "li.combo-opt",
          {
            role: "option", id: `${id}-opt-${o.id}`, "aria-selected": "false",
            onmousedown: (e) => e.preventDefault(), // фокус остаётся в поле
            onclick: () => select(items[i]),
          },
          offerLabel(o, { query: q }),
        ),
      ),
    );
  }

  function select(o) {
    self.selected = o;
    if (o) {
      input.dataset.offerId = o.id;
      input.value = nameHasId(o) ? o.name : `${o.id} ${o.name}`;
    } else delete input.dataset.offerId;
    close();
    onSelect(o);
  }
  function clear() { input.value = ""; select(null); }

  async function search(now = false) {
    clearTimeout(timer);
    const q = input.value.trim();
    timer = setTimeout(async () => {
      ctrl?.abort(); // поздний ответ не затрёт свежий
      ctrl = new AbortController();
      list.replaceChildren();
      items = [];
      showStatus("Ищу…", { spinner: true });
      open();
      try {
        const r = await fetch(`/api/offers?q=${encodeURIComponent(q)}`, { signal: ctrl.signal });
        const data = await r.json().catch(() => null);
        if (!r.ok) throw new ApiError(r.status, detailText(data?.detail, r.status), data?.detail);
        items = data;
        renderItems(q);
        showStatus(items.length ? "" : "Ничего не найдено");
        if (items.length) setActive(0);
      } catch (e) {
        if (e.name === "AbortError") return;
        showStatus(e instanceof ApiError ? e.message : "Нет связи с приложением", { error: true, retry: true });
      }
    }, now ? 0 : 250);
  }

  input.addEventListener("input", () => {
    if (self.selected) { self.selected = null; delete input.dataset.offerId; onSelect(null); }
    search();
  });
  input.addEventListener("focus", () => { if (!self.selected && !items.length) search(true); });
  input.addEventListener("blur", () => setTimeout(close, 0));
  input.addEventListener("keydown", (e) => {
    const isOpen = !pop.hidden;
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        if (!isOpen) { open(); if (!items.length) search(true); }
        setActive(active + 1);
        break;
      case "ArrowUp":
        e.preventDefault();
        if (!isOpen) open();
        setActive(active - 1);
        break;
      case "Home":
      case "End":
        if (isOpen && items.length) { e.preventDefault(); setActive(e.key === "Home" ? 0 : items.length - 1); }
        break;
      case "Enter":
        e.preventDefault();
        if (isOpen && active >= 0) select(items[active]);
        else if (isOpen && status.classList.contains("error")) search(true);
        else if (self.selected && onEnter) onEnter(self.selected);
        break;
      case "Escape":
        if (isOpen) { e.preventDefault(); close(); }
        else if (input.value) { e.preventDefault(); clear(); }
        break;
    }
  });
  return self;
}

/* ---------- Числа ---------- */

/** Плавно перетекает число от старого значения к новому (200 мс), без движения при reduced-motion. */
function tweenNumber(el, from, to, suffix = "%") {
  if (from === to || reducedMotion.matches) return void (el.textContent = to + suffix);
  const t0 = performance.now(), dur = 200;
  const ease = (t) => 1 - Math.pow(1 - t, 3);
  const step = (now) => {
    const t = Math.min(1, (now - t0) / dur);
    el.textContent = Math.round(from + (to - from) * ease(t)) + suffix;
    if (t < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

const plural = (n, one, few, many) => {
  const m10 = n % 10, m100 = n % 100;
  return m10 === 1 && m100 !== 11 ? one : m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? few : many;
};

document.addEventListener("DOMContentLoaded", () => hydrateIcons());
