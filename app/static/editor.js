// Редактор кампании. Сервер считает доли и возвращает кампанию целиком; UI обновляет узлы по ключу
// (data-stream-id, data-so-id), чтобы не терять фокус, прокрутку и текст в поиске, и анимирует разницу.
"use strict";

const CID = JSON.parse($("#page-data").textContent).campaignId;
const ACTIVE = "active", REMOVED = "removed";

let state = null; // последняя кампания с сервера
const cards = new Map(); // stream id → {el, ...}
const busyStreams = new Set();

const streamsEl = $("#streams");
const fetchBtn = $("#fetch");

/* ---------- Загрузка ---------- */

async function load() {
  $("#load-error").hidden = true;
  try {
    render(await api("GET", `/api/campaigns/${CID}`));
  } catch (e) {
    streamsEl.replaceChildren();
    streamsEl.removeAttribute("aria-busy");
    if (e.status === 404) return void ($("#empty").hidden = false);
    $(".notice-body", $("#load-error")).textContent = e.message;
    $("#load-error").hidden = false;
  }
}
$("#load-retry").addEventListener("click", load);

async function doFetch(btn = fetchBtn) {
  if (isBlocked(btn)) return;
  const dirty = state ? state.streams.filter((s) => s.dirty).length : 0;
  if (dirty) {
    const ok = await confirmDialog({
      title: "Загрузить заново из Keitaro?",
      body: h("p", { text: `Неопубликованные правки в ${dirty} ${plural(dirty, "потоке", "потоках", "потоках")} будут сброшены.` }),
      confirmLabel: "Fetch streams from KT",
      danger: true,
    });
    if (!ok) return;
  }
  setBusy(btn, true);
  let c;
  try {
    c = await api("POST", `/api/campaigns/${CID}/fetch`);
  } catch (e) {
    toast(e.message, { type: "error", action: e.status === 502 || e.status === 0 ? { label: "Повторить", run: () => doFetch(btn) } : null });
  } finally {
    setBusy(btn, false);
  }
  if (!c) return;
  $("#empty").hidden = true;
  $("#load-error").hidden = true;
  render(c);
  if (!document.activeElement || document.activeElement === document.body) fetchBtn.focus(); // кнопка в плашке исчезла
  toast("Загружено из Keitaro");
}
fetchBtn.addEventListener("click", () => doFetch());
$("#empty-fetch").addEventListener("click", (e) => doFetch(e.currentTarget));

/* ---------- Рендер ---------- */

function render(c) {
  const first = state === null;
  state = c;
  document.title = c.name;
  $("#title").textContent = c.name;
  $("#readonly-badge").hidden = c.editable;
  $("#readonly").hidden = c.editable;
  if (c.keitaro_url) $("#kt").href = c.keitaro_url;
  streamsEl.removeAttribute("aria-busy");
  if (first) streamsEl.replaceChildren();

  const ids = new Set(c.streams.map((s) => s.id));
  for (const [id, card] of cards) if (!ids.has(id)) { card.el.remove(); cards.delete(id); }
  c.streams.forEach((s, i) => {
    let card = cards.get(s.id);
    if (!card || card.hasOffers !== s.has_offers) {
      card?.el.remove();
      card = s.has_offers ? offersCard(s) : plainCard(s);
      cards.set(s.id, card);
    }
    if (streamsEl.children[i] !== card.el) streamsEl.insertBefore(card.el, streamsEl.children[i] || null);
    card.update(s, c.editable, first);
  });
  if (!c.streams.length) {
    streamsEl.replaceChildren(h("div.card.empty", {}, h("h2", { text: "В кампании нет потоков" }), h("p", { text: "В Keitaro у этой кампании нет ни одного потока." })));
  }
}

function plainCard(s) {
  const pos = h("span.mono.stream-pos");
  const name = h("h2.stream-name");
  const el = h("section.stream.stream-plain", { dataset: { streamId: s.id } }, pos, name, h("span.small.muted", { text: "Поток без офферов" }));
  return {
    el, hasOffers: false,
    update(s) { pos.textContent = `#${s.position}`; name.textContent = s.name; },
  };
}

const changesOf = (s) => s.offers.filter((o) => o.state !== o.pub_state || o.share !== o.pub_share).length;

function offersCard(s) {
  const sid = s.id;
  const pos = h("span.mono.stream-pos");
  const name = h("h2.stream-name", { id: `stream-${sid}-name` });
  const badge = h("span.badge.badge-draft", { hidden: true });
  const draftHint = h("span.small.draft-hint", { hidden: true, text: "Черновик сохранён, в Keitaro ещё не отправлен" });
  const alert = h("div.notice.notice-danger.stream-alert", { role: "alert", hidden: true });
  const tbody = h("tbody");
  const totalNum = h("span.num");
  const totalNote = h("span.total-note.small");
  const totalCell = h("td.right.total", {}, totalNum);
  const table = h(
    "table.table.offers",
    { "aria-labelledby": name.id },
    h("thead", {}, h("tr", {},
      h("th.col-offer", { scope: "col", text: "Offer" }),
      h("th.right.col-share", { scope: "col", text: "Share" }),
      h("th.col-state", { scope: "col", text: "State" }),
      h("th.col-pin", { scope: "col", text: "Pin" }),
      h("th.col-act", { scope: "col", text: "Actions" }),
    )),
    tbody,
    h("tfoot", {}, h("tr", {}, h("td.total-label", { text: "Итого" }), totalCell, h("td.total-note-cell", { colspan: 3 }, totalNote))),
  );

  // Низ карточки: поиск и Add offer слева, Cancel и Push справа. Узлы живут между рендерами: текст поиска не теряется
  const input = h("input.input", { placeholder: "Оффер: id или название", "aria-label": "Оффер для добавления", "aria-describedby": `add-${sid}-hint` });
  const comboWrap = h("div.combo", {}, input);
  const addHint = h("div.hint", { id: `add-${sid}-hint` });
  const addBtn = h("button.btn.btn-secondary", { type: "button", onclick: () => addOffer() }, icon("plus"), h("span", { text: "Add offer" }));
  const combo = Combobox(input, {
    onSelect: () => setAddError(""),
    onEnter: () => addOffer(),
  });
  const cancelBtn = h("button.btn.btn-secondary", { type: "button", onclick: () => cancel() }, h("span", { text: "Cancel" }));
  const pushBtn = h("button.btn.btn-primary", { type: "button", "aria-describedby": `push-${sid}-reason`, onclick: () => push() }, h("span", { text: "Push" }));
  const pushReason = h("div.hint.push-reason", { id: `push-${sid}-reason` });
  const foot = h(
    "div.stream-foot",
    {},
    h("div.add", {}, h("div.add-row", {}, comboWrap, addBtn), addHint),
    h("div.publish", {}, h("div.publish-row", {}, cancelBtn, pushBtn), pushReason),
  );

  const el = h(
    "section.stream",
    { dataset: { streamId: sid }, "aria-labelledby": name.id },
    h("header.stream-head", {}, pos, name, badge, draftHint),
    alert,
    h("div.table-wrap", {}, table),
    foot,
  );
  const rows = new Map(); // so id → row
  let current = s;

  function setAddError(msg) {
    addHint.textContent = msg;
    addHint.classList.toggle("error", !!msg);
    input.setAttribute("aria-invalid", msg ? "true" : "false");
  }

  function showAlert(err, retry) {
    const actions = [];
    if (err.status === 409) actions.push(h("button.btn.btn-sm.btn-secondary", { type: "button", onclick: () => doFetch() }, icon("refresh"), h("span", { text: "Fetch streams from KT" })));
    else if (retry && (err.status === 502 || err.status === 0)) actions.push(h("button.btn.btn-sm.btn-secondary", { type: "button", onclick: retry }, "Повторить"));
    alert.replaceChildren(icon("alert"), h("div.notice-body", { text: err.message }), ...actions);
    alert.hidden = false;
  }

  /** Операция над потоком: пока идёт запрос, остальные кнопки потока не срабатывают. */
  async function run(btn, method, url, body, { ok, onError } = {}) {
    if (busyStreams.has(sid) || isBlocked(btn)) return;
    busyStreams.add(sid);
    el.classList.add("is-busy");
    setBusy(btn, true);
    alert.hidden = true;
    let c, err;
    try {
      c = await api(method, url, body);
    } catch (e) {
      err = e;
    } finally {
      busyStreams.delete(sid);
      el.classList.remove("is-busy");
      setBusy(btn, false);
    }
    if (c) {
      render(c);
      ok?.(c);
      return;
    }
    if (err.status === 403) {
      state.editable = false; // свежее имя в Keitaro без префикса: дальше только просмотр
      toast(err.message, { type: "error" });
    } else if (!onError?.(err)) showAlert(err, () => run(btn, method, url, body, { ok, onError }));
    render(state); // откат к серверному состоянию (например, Pin)
  }

  function addOffer() {
    const o = combo.selected;
    if (!o) {
      setAddError("Выберите оффер из списка");
      return input.focus();
    }
    run(addBtn, "POST", `/api/streams/${sid}/offers`, { offer_id: o.id }, {
      ok: () => { combo.clear(); setAddError(""); input.focus(); announce("Оффер добавлен, доли пересчитаны"); },
      onError: (e) => (e.status === 409 || e.status === 422 ? (setAddError(e.message), true) : false),
    });
  }

  function cancel() {
    run(cancelBtn, "POST", `/api/streams/${sid}/cancel`, null, { ok: () => toast("Правки потока отменены") });
  }

  async function push() {
    if (isBlocked(pushBtn) || busyStreams.has(sid)) return;
    const s = current;
    const active = s.offers.filter((o) => o.state === ACTIVE);
    const leaving = s.offers.filter((o) => o.state === REMOVED && o.pub_state === ACTIVE);
    const line = (o, share) => h("li", {}, h("span.name", { title: o.name }, offerText(o)), share);
    const ok = await confirmDialog({
      title: `Push потока «${s.name}» в Keitaro`,
      body: h(
        "div.push-summary",
        {},
        h("p.small.secondary", { text: "Keitaro заменит список офферов потока ровно этим списком." }),
        active.length
          ? h("div", {}, h("div.summary-title", { text: "Уйдут в Keitaro" }), h("ul.summary", {}, active.map((o) => line(o, h("span.share.num.mono", { text: shareChange(o) })))))
          : h("div.notice.notice-danger", {}, icon("alert"), h("div.notice-body", { text: "Поток останется без офферов" })),
        leaving.length > 0 && h("div", {}, h("div.summary-title", { text: "Будут убраны из Keitaro" }), h("ul.summary.leaving", {}, leaving.map((o) => line(o, h("span.share.num.mono", { text: `${o.pub_share}% → 0%` }))))),
      ),
      confirmLabel: "Push",
      danger: !active.length,
    });
    if (ok) run(pushBtn, "POST", `/api/streams/${sid}/push`, null, { ok: () => toast("Опубликовано в Keitaro") });
  }

  function update(s, editable, first) {
    current = s;
    pos.textContent = `#${s.position}`;
    name.textContent = s.name;
    const n = changesOf(s);
    el.classList.toggle("dirty", s.dirty);
    el.classList.toggle("readonly", !editable);
    badge.hidden = !s.dirty;
    badge.textContent = `Не опубликовано · ${n} ${plural(n, "изменение", "изменения", "изменений")}`;
    draftHint.hidden = !s.dirty || !editable;
    foot.hidden = !editable;

    const seen = new Set();
    s.offers.forEach((o, i) => {
      let row = rows.get(o.id);
      const isNew = !row;
      if (isNew) rows.set(o.id, (row = offerRow(o, run)));
      if (tbody.children[i] !== row.tr) tbody.insertBefore(row.tr, tbody.children[i] || null);
      row.update(o, { animate: !first && !isNew });
      if (isNew && !first) row.tr.classList.add("enter");
      seen.add(o.id);
    });
    for (const [id, row] of rows) if (!seen.has(id)) { row.tr.remove(); rows.delete(id); }
    if (!s.offers.length) {
      tbody.replaceChildren(h("tr.no-offers", {}, h("td", { colspan: 5, text: "В потоке нет офферов. Добавьте оффер через поиск ниже." })));
    } else $(".no-offers", tbody)?.remove();

    const hasActive = s.offers.some((o) => o.state === ACTIVE);
    const bad = hasActive && s.total !== 100;
    const pinned = s.offers.filter((o) => o.state === ACTIVE && o.pinned).reduce((a, o) => a + o.share, 0);
    totalNum.textContent = `${s.total}%`;
    totalCell.classList.toggle("bad", bad);
    totalNote.textContent = bad ? `закреплено ${pinned}%` : !hasActive && s.offers.length ? "нет активных офферов" : "";
    totalNote.classList.toggle("bad", bad);

    const noChanges = !s.dirty;
    const reason = noChanges ? "" : bad ? `Сумма долей ${s.total}%, для Push нужно ровно 100%` : "";
    cancelBtn.setAttribute("aria-disabled", String(noChanges));
    pushBtn.setAttribute("aria-disabled", String(noChanges || bad));
    cancelBtn.title = pushBtn.title = noChanges ? "Нет неопубликованных правок" : "";
    if (bad) pushBtn.title = reason;
    pushReason.textContent = reason;
    pushReason.classList.toggle("error", !!reason);
  }

  return { el, hasOffers: true, update };
}

const offerText = (o) => (nameHasId({ id: o.offer_id, name: o.name }) ? o.name : `${o.offer_id} ${o.name}`);
const shareChange = (o) => (o.pub_state !== null && o.pub_share !== o.share ? `${o.pub_share}% → ${o.share}%` : `${o.share}%`);

function stateBadge(o) {
  if (o.pub_state === null) return ["badge-new", "Новый"];
  if (o.state === REMOVED) return o.pub_state === ACTIVE ? ["badge-leaving", "Будет убран из Keitaro"] : ["badge-removed", "Удалён"];
  return ["badge-active", "Активен"];
}

function offerRow(o, run) {
  const idEl = h("span.mono.offer-id");
  const nameEl = h("span.offer-name");
  const was = h("span.share-was.num");
  const now = h("span.share-now.num");
  const fill = h("i");
  const shareCell = h("td.right.col-share", {}, h("div.share", {}, h("div.share-nums", {}, was, now), h("div.share-bar", { "aria-hidden": "true" }, fill)));
  const badge = h("span.badge");
  const pinBtn = h("button.btn.btn-sm.btn-ghost.pin", { type: "button", "aria-pressed": "false" }, icon("pin"), h("span", { text: "Pin" }));
  const actLabel = h("span");
  const actIcon = h("span.act-icon");
  const actBtn = h("button.btn.btn-sm", { type: "button" }, actIcon, actLabel);
  const tr = h(
    "tr",
    {},
    h("td.col-offer", {}, h("div.offer-cell", {}, idEl, nameEl)),
    shareCell,
    h("td.col-state", {}, badge),
    h("td.col-pin", {}, pinBtn),
    h("td.col-act", {}, actBtn),
  );
  let so = o, shown = o.share;

  pinBtn.addEventListener("click", () => run(pinBtn, "POST", `/api/stream_offers/${so.id}/pin`, { pinned: !so.pinned }, {
    ok: () => announce(so.pinned ? "Доля закреплена" : "Закрепление снято"),
  }));
  actBtn.addEventListener("click", () => {
    const removing = so.state === ACTIVE;
    run(actBtn, "POST", `/api/stream_offers/${so.id}/${removing ? "remove" : "restore"}`, null, {
      ok: () => announce(removing ? "Оффер убран, доли пересчитаны" : "Оффер возвращён, доли пересчитаны"),
    });
  });

  function update(o, { animate }) {
    so = o;
    tr.dataset.soId = o.id;
    const removed = o.state === REMOVED;
    tr.classList.toggle("removed", removed);
    idEl.textContent = o.offer_id;
    nameEl.textContent = bareName({ id: o.offer_id, name: o.name });
    nameEl.title = o.name;

    if (animate && shown !== o.share) {
      tweenNumber(now, shown, o.share);
      shareCell.classList.remove("flash");
      void shareCell.offsetWidth; // перезапуск вспышки
      shareCell.classList.add("flash");
    } else now.textContent = `${o.share}%`;
    shown = o.share;
    fill.style.transform = `scaleX(${o.share / 100})`;
    // было → стало: опубликованная доля приглушённо
    const changed = o.pub_state !== null && o.pub_share !== o.share; // и у вернувшегося из архива: 0% → 17%
    was.textContent = changed ? `${o.pub_share}% →` : "";
    was.hidden = !changed;

    const [cls, text] = stateBadge(o);
    badge.className = `badge ${cls}`;
    badge.textContent = text;

    pinBtn.setAttribute("aria-pressed", String(o.pinned));
    pinBtn.setAttribute("aria-label", `Pin ${o.name}`);
    pinBtn.setAttribute("aria-disabled", String(removed));
    pinBtn.title = removed ? "Закрепить можно только активный оффер" : o.pinned ? "Снять закрепление доли" : "Закрепить долю";

    actLabel.textContent = removed ? "Bring back" : "Remove";
    actIcon.replaceChildren(removed ? icon("undo") : "");
    actIcon.hidden = !removed;
    actBtn.className = `btn btn-sm ${removed ? "btn-secondary" : "btn-ghost"}`;
    actBtn.setAttribute("aria-label", `${removed ? "Bring back" : "Remove"} ${o.name}`);
  }
  return { tr, update };
}

function announce(text) {
  const el = $("#sr-status");
  el.textContent = "";
  setTimeout(() => (el.textContent = text), 50);
}

load();
