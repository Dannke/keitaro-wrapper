// Страница New campaign: живой предпросмотр имени, Geo чипами, комбобокс оффера, Create без перезагрузки.
"use strict";

const PAGE = JSON.parse($("#page-data").textContent);
const COUNTRIES = new Set(PAGE.countries); // тот же список, что services.COUNTRIES на бэкенде
const regionNames = (() => { try { return new Intl.DisplayNames(["ru"], { type: "region" }); } catch { return null; } })();
const countryName = (code) => { try { return regionNames?.of(code) ?? ""; } catch { return ""; } };
const dateFmt = new Intl.DateTimeFormat("ru", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

const form = $("#create");
const submit = $("#submit");
const fields = {
  name: { input: $("#name"), hint: $("#name-hint") },
  geo: { input: $("#geo-input"), hint: $("#geo-hint"), box: $("#geo-box") },
  offer: { input: $("#offer"), hint: $("#offer-hint") },
};
const hintDefault = new Map(Object.values(fields).map((f) => [f.hint, f.hint.innerHTML]));

function setFieldError(key, message) {
  const f = fields[key];
  f.hint.classList.toggle("error", !!message);
  if (message) f.hint.textContent = message;
  else f.hint.innerHTML = hintDefault.get(f.hint);
  f.input.setAttribute("aria-invalid", message ? "true" : "false");
  f.box?.classList.toggle("invalid", !!message);
  if (key === "name") updatePreview();
}

/* ---------- Name ---------- */

function updatePreview() {
  const el = $("#name-preview-value");
  if (!el) return;
  let v = fields.name.input.value.trim();
  if (v.startsWith(PAGE.prefix)) v = v.slice(PAGE.prefix.length); // бэкенд не дублирует префикс
  el.textContent = v || "name";
  el.classList.toggle("placeholder", !v);
}
fields.name.input.addEventListener("input", () => {
  if (fields.name.hint.classList.contains("error")) setFieldError("name", null);
  updatePreview();
  updateSubmit();
});

/* ---------- Geo ---------- */

const geo = []; // [{code, ok}]

function geoProblem() {
  const bad = geo.filter((c) => !c.ok).map((c) => c.code);
  if (!bad.length) return null;
  if (bad.includes("UK")) return "Кода UK нет в ISO 3166-1: Великобритания — GB";
  return `Нет в ISO 3166-1: ${bad.join(", ")}`;
}

function renderGeo() {
  $$(".chip", fields.geo.box).forEach((c) => c.remove());
  for (const c of geo) {
    const name = c.ok ? countryName(c.code) : c.code === "UK" ? "нужен GB" : "неизвестный код";
    fields.geo.input.before(
      h(
        `span.chip${c.ok ? "" : ".bad"}`,
        { title: c.ok ? name : undefined },
        h("span.mono", { text: c.code }),
        name && h("span", { text: name }),
        h("button", { type: "button", "aria-label": `Убрать ${c.code}`, onclick: () => removeCode(c.code) }, icon("x")),
      ),
    );
  }
  fields.geo.input.placeholder = geo.length ? "" : "MX, AU, RO";
  setFieldError("geo", geoProblem());
  updateSubmit();
}

function addCodes(text) {
  for (const raw of text.split(/[\s,;]+/)) {
    const code = raw.trim().toUpperCase();
    if (code && !geo.some((c) => c.code === code)) geo.push({ code, ok: COUNTRIES.has(code) });
  }
  renderGeo();
}

function removeCode(code) {
  geo.splice(geo.findIndex((c) => c.code === code), 1);
  renderGeo();
  fields.geo.input.focus();
}

function commitGeoInput() {
  const v = fields.geo.input.value;
  fields.geo.input.value = "";
  if (v.trim()) addCodes(v);
}

fields.geo.input.addEventListener("keydown", (e) => {
  if (e.key === "," || e.key === " " || e.key === ";" || (e.key === "Enter" && fields.geo.input.value.trim())) {
    e.preventDefault();
    commitGeoInput();
  } else if (e.key === "Backspace" && !fields.geo.input.value && geo.length) {
    e.preventDefault();
    geo.pop();
    renderGeo();
  }
});
fields.geo.input.addEventListener("input", () => {
  if (/[\s,;]/.test(fields.geo.input.value)) commitGeoInput(); // вставка «MX,AU,RO»
  updateSubmit();
});
fields.geo.input.addEventListener("blur", commitGeoInput);
fields.geo.box.addEventListener("click", (e) => { if (e.target === fields.geo.box) fields.geo.input.focus(); });

/* ---------- Offer ---------- */

const picked = $("#offer-picked");
const offerCombo = Combobox(fields.offer.input, {
  onSelect(o) {
    setFieldError("offer", null);
    if (o) {
      $("#offer-picked-id").textContent = o.id;
      $("#offer-picked-name").textContent = o.name;
      $("#offer-picked-name").title = o.name;
      $("#offer-combo").hidden = true;
      picked.hidden = false;
    }
    updateSubmit();
  },
});
$("#offer-change").addEventListener("click", () => {
  picked.hidden = true;
  $("#offer-combo").hidden = false;
  offerCombo.clear();
  fields.offer.input.focus();
});

/* ---------- Create ---------- */

function missing() {
  const m = [];
  if (!fields.name.input.value.trim()) m.push("Name");
  if (!geo.length && !fields.geo.input.value.trim()) m.push("Geo");
  if (!offerCombo.selected) m.push("Offer");
  return m;
}

function updateSubmit() {
  if (submit.getAttribute("aria-busy")) return;
  const m = missing();
  const reason = m.length ? `Заполните: ${m.join(", ")}` : geoProblem() ? "Исправьте коды в Geo" : "";
  submit.setAttribute("aria-disabled", reason ? "true" : "false");
  $("#submit-hint").textContent = reason;
}

const errorBox = $("#create-error");
function showFormError(message) {
  $(".notice-body", errorBox).textContent = message;
  errorBox.hidden = !message;
}

function fieldOfError(e) {
  if (e.field && e.field in fields) return e.field;
  if (e.field === "offer_id") return "offer";
  if (e.status !== 422) return null;
  if (e.message.startsWith("Geo")) return "geo";
  if (/имя/i.test(e.message)) return "name";
  if (/Оффер/.test(e.message)) return "offer";
  return null;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  commitGeoInput();
  if (isBlocked(submit)) {
    // подсказываем, чего не хватает, и ведём к первому пустому полю
    const m = missing();
    if (m.length) fields[m[0].toLowerCase()].input.focus();
    else if (geoProblem()) fields.geo.input.focus();
    return;
  }
  showFormError("");
  setBusy(submit, true);
  $(".btn-label", submit).textContent = "Создаю кампанию…";
  $("#submit-hint").textContent = "";
  try {
    const data = await api("POST", "/api/campaigns", {
      name: fields.name.input.value,
      geo: geo.map((c) => c.code).join(","),
      offer_id: offerCombo.selected.id,
    });
    showResult(data);
    addCampaignRow(data);
    fields.name.input.value = ""; // Geo и Offer оставляем: следующую кампанию часто создают с теми же
    updatePreview();
  } catch (err) {
    const key = fieldOfError(err);
    if (key) {
      setFieldError(key, err.message);
      fields[key].input.focus();
    } else showFormError(err.message);
  } finally {
    setBusy(submit, false);
    $(".btn-label", submit).textContent = "Create";
    updateSubmit();
  }
});

function showResult(c) {
  const box = $("#result");
  const ktUrl = PAGE.ktCampaignUrl.replace("{id}", c.id);
  box.replaceChildren(
    h(
      "div.result-head",
      {},
      icon("check"),
      h("h2", { text: "Кампания создана" }),
      h("button.btn.btn-sm.btn-ghost.icon-btn", { type: "button", "aria-label": "Скрыть", onclick: () => (box.hidden = true) }, icon("x")),
    ),
    h(
      "dl.result-grid",
      {},
      h("dt", { text: "Имя" }), h("dd", {}, h("span.result-name", { text: c.name })),
      h("dt", { text: "id" }), h("dd", {}, copyButton(c.id, `Скопировать id ${c.id}`)),
      h("dt", { text: "alias" }), h("dd", {}, copyButton(c.alias, `Скопировать alias ${c.alias}`)),
      h("dt", { text: "Geo" }), h("dd", {}, h("span.chips", {}, c.geo.split(",").map((g) => h("span.chip.chip-static", { title: countryName(g) }, h("span.mono", { text: g }))))),
      h("dt", { text: "Offer" }), h("dd", {}, h("span.result-offer", {}, offerLabel(c.offer))),
    ),
    h(
      "div.result-actions",
      {},
      h("a.btn.btn-secondary.btn-sm", { href: `/campaigns/${c.id}` }, "Открыть в редакторе", icon("arrow")),
      h("a.btn.btn-ghost.btn-sm", { href: ktUrl, target: "_blank", rel: "noopener" }, "View in KT", icon("external")),
    ),
  );
  box.hidden = false;
  box.classList.remove("enter");
  void box.offsetWidth;
  box.classList.add("enter");
  box.focus({ preventScroll: true });
  box.scrollIntoView({ block: "nearest", behavior: reducedMotion.matches ? "auto" : "smooth" });
}

function addCampaignRow(c) {
  const list = $("#camp-list");
  const li = h(
    "li.enter",
    {},
    h(
      "a.camp-row",
      { href: `/campaigns/${c.id}` },
      h("span.mono.camp-id", { text: String(c.id) }),
      h(
        "span.camp-main",
        {},
        h("span.camp-name", { text: c.name }),
        h("span.chips", {}, c.geo.split(",").map((g) => h("span.chip.chip-static", { title: countryName(g) }, h("span.mono", { text: g })))),
      ),
      h("span.camp-meta", {}, h("time.small.muted.num", { datetime: new Date().toISOString(), text: dateFmt.format(new Date()) })),
    ),
  );
  list.prepend(li);
  list.hidden = false;
  $("#camp-empty").hidden = true;
  $("#campaigns-count").textContent = list.children.length;
}

/* ---------- Список и «Открыть по id» ---------- */

for (const t of $$("#camp-list time")) {
  const d = new Date(t.getAttribute("datetime"));
  if (!isNaN(d)) t.textContent = dateFmt.format(d);
}
for (const chip of $$("[data-country]")) chip.title = countryName(chip.dataset.country);

const openId = $("#open-id");
openId.addEventListener("input", () => {
  const digits = openId.value.replace(/\D/g, "");
  if (digits !== openId.value) openId.value = digits; // нечисловой ввод не принимаем
  openId.removeAttribute("aria-invalid");
  $("#open-hint").classList.remove("error");
  $("#open-hint").textContent = "Чужие кампании открываются только на просмотр";
});
$("#open").addEventListener("submit", (e) => {
  e.preventDefault();
  const id = parseInt(openId.value, 10);
  if (!id) {
    openId.setAttribute("aria-invalid", "true");
    $("#open-hint").classList.add("error");
    $("#open-hint").textContent = "Введите числовой id кампании";
    return openId.focus();
  }
  location.href = `/campaigns/${id}`;
});

updatePreview();
updateSubmit();
