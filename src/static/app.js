const SNAPSHOT_DEPTH = 30;
const fmt = (n) =>
  n == null ? "—" : Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const fmtQty = (n) => (n == null ? "" : String(n));

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : res.statusText);
  }
  return data;
}

let pendingSubmit = null;
let selectedOrderId = null;
let newestOrderId = null;
let lastSnapshot = null;
let lastRenderedSnapshot = null;

const SIDE_PANEL_MIN = 260;
const SIDE_PANEL_MAX = 520;
const SIDE_PANEL_STORAGE_KEY = "orderbook-side-panel-width";

function setSidePanelWidth(width) {
  const nextWidth = Math.min(SIDE_PANEL_MAX, Math.max(SIDE_PANEL_MIN, Math.round(width)));
  document.documentElement.style.setProperty("--side-panel-width", `${nextWidth}px`);
  document.getElementById("panel-resizer").setAttribute("aria-valuenow", String(nextWidth));
  return nextWidth;
}

function initializePanelResizer() {
  const resizer = document.getElementById("panel-resizer");
  const savedWidth = Number.parseFloat(localStorage.getItem(SIDE_PANEL_STORAGE_KEY));
  if (Number.isFinite(savedWidth) && savedWidth > 0) setSidePanelWidth(savedWidth);

  resizer.addEventListener("pointerdown", (event) => {
    if (window.innerWidth <= 960) return;
    const startX = event.clientX;
    const startWidth = document.querySelector(".side-panel").getBoundingClientRect().width;
    resizer.setPointerCapture(event.pointerId);
    resizer.classList.add("is-resizing");
    document.body.classList.add("is-resizing-panel");

    const onMove = (moveEvent) => {
      setSidePanelWidth(startWidth + startX - moveEvent.clientX);
    };
    const onEnd = () => {
      resizer.removeEventListener("pointermove", onMove);
      resizer.removeEventListener("pointerup", onEnd);
      resizer.removeEventListener("pointercancel", onEnd);
      resizer.classList.remove("is-resizing");
      document.body.classList.remove("is-resizing-panel");
      const finalWidth = Number.parseFloat(
        getComputedStyle(document.documentElement).getPropertyValue("--side-panel-width")
      );
      localStorage.setItem(SIDE_PANEL_STORAGE_KEY, String(finalWidth));
      if (lastSnapshot) drawDepthChart(lastSnapshot.book, lastSnapshot.top, lastSnapshot.my_active_orders || []);
    };

    resizer.addEventListener("pointermove", onMove);
    resizer.addEventListener("pointerup", onEnd);
    resizer.addEventListener("pointercancel", onEnd);
  });

  resizer.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const currentWidth = document.querySelector(".side-panel").getBoundingClientRect().width;
    const direction = event.key === "ArrowLeft" ? 1 : -1;
    const nextWidth = setSidePanelWidth(currentWidth + direction * 20);
    localStorage.setItem(SIDE_PANEL_STORAGE_KEY, String(nextWidth));
  });
}

function setStatus(msg, isError = false) {
  const el = document.getElementById("order-status");
  if (!msg) {
    el.hidden = true;
    el.textContent = "";
    return;
  }
  el.hidden = false;
  el.textContent = msg;
  el.classList.toggle("error", isError);
}

function renderDom(book, top, myOrders) {
  const tbody = document.querySelector("#dom tbody");
  tbody.innerHTML = "";

  const asks = [...(book?.asks || [])].reverse();
  const bids = book?.bids || [];
  const myQuantityAt = new Map();
  for (const order of myOrders || []) {
    const key = `${order.side}:${order.price}`;
    myQuantityAt.set(key, (myQuantityAt.get(key) || 0) + order.quantity);
  }

  const spreadVal = top?.spread;
  const mid = top?.mid;
  const last = top?.last_print ?? top?.best_ask ?? top?.best_bid;

  for (const level of asks) {
    const tr = document.createElement("tr");
    tr.className = "ask";
    const myQty = myQuantityAt.get(`ask:${level.price}`);
    if (myQty) tr.classList.add("mine-level");
    tr.innerHTML = `
      <td class="bid-qty"></td>
      <td class="price">${fmt(level.price)}${myQty ? `<span class="mine-badge">YOU · ${fmtQty(myQty)}</span>` : ""}</td>
      <td class="ask-qty">${fmtQty(level.quantity)}</td>`;
    tbody.appendChild(tr);
  }

  const spreadTr = document.createElement("tr");
  spreadTr.className = "spread";
  const spreadLabel =
    spreadVal != null ? `— ${fmt(spreadVal)} —` : last != null ? fmt(last) : "—";
  spreadTr.innerHTML = `<td colspan="3">${spreadLabel}</td>`;
  tbody.appendChild(spreadTr);

  for (const level of bids) {
    const tr = document.createElement("tr");
    tr.className = "bid";
    const myQty = myQuantityAt.get(`bid:${level.price}`);
    if (myQty) tr.classList.add("mine-level");
    tr.innerHTML = `
      <td class="bid-qty">${fmtQty(level.quantity)}</td>
      <td class="price">${fmt(level.price)}${myQty ? `<span class="mine-badge">YOU · ${fmtQty(myQty)}</span>` : ""}</td>
      <td class="ask-qty"></td>`;
    tbody.appendChild(tr);
  }

  document.getElementById("last-print").textContent = fmt(last ?? mid);
}

function drawDepthChart(book, top, myOrders) {
  const canvas = document.getElementById("depth-chart");
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const w = Math.max(rect.width, 320);
  const h = Math.max(rect.height, 280);
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  ctx.fillStyle = "#0a0e14";
  ctx.fillRect(0, 0, w, h);

  const bids = book?.bids || [];
  const asks = book?.asks || [];
  if (!bids.length && !asks.length) return;

  const mid =
    top?.mid ??
    (bids[0] && asks[0] ? (bids[0].price + asks[0].price) / 2 : bids[0]?.price ?? asks[0]?.price ?? 100);

  const bidPrices = [...bids].reverse();
  let cum = 0;
  const bidCurve = bidPrices.map((l) => {
    cum += l.quantity;
    return { price: l.price, cum };
  });

  cum = 0;
  const askCurve = asks.map((l) => {
    cum += l.quantity;
    return { price: l.price, cum };
  });

  const allPrices = [...bidPrices.map((l) => l.price), ...asks.map((l) => l.price), mid];
  const minP = Math.min(...allPrices);
  const maxP = Math.max(...allPrices);
  const pad = (maxP - minP) * 0.08 || 0.05;
  const xMin = minP - pad;
  const xMax = maxP + pad;
  const maxCum = Math.max(cum, ...bidCurve.map((b) => b.cum), ...askCurve.map((a) => a.cum), 1);

  const padL = 36;
  const padR = 12;
  const padT = 16;
  const padB = 28;
  const plotW = w - padL - padR;
  const plotH = h - padT - padB;

  const xScale = (p) => padL + ((p - xMin) / (xMax - xMin)) * plotW;
  const yScale = (c) => padT + plotH - (c / maxCum) * plotH;

  ctx.strokeStyle = "#21262d";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = padT + (plotH * i) / 4;
    ctx.beginPath();
    ctx.moveTo(padL, y);
    ctx.lineTo(w - padR, y);
    ctx.stroke();
  }

  const midX = xScale(mid);
  ctx.setLineDash([4, 4]);
  ctx.strokeStyle = "#d4a72c";
  ctx.beginPath();
  ctx.moveTo(midX, padT);
  ctx.lineTo(midX, padT + plotH);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = "#d4a72c";
  ctx.font = "11px ui-monospace, monospace";
  ctx.fillText(`mid ${fmt(mid)}`, midX + 4, padT + 12);

  if (bidCurve.length) {
    ctx.fillStyle = "rgba(63, 185, 80, 0.35)";
    ctx.strokeStyle = "rgba(63, 185, 80, 0.9)";
    ctx.beginPath();
    ctx.moveTo(xScale(bidCurve[0].price), yScale(0));
    let prevC = 0;
    for (const pt of bidCurve) {
      ctx.lineTo(xScale(pt.price), yScale(prevC));
      ctx.lineTo(xScale(pt.price), yScale(pt.cum));
      prevC = pt.cum;
    }
    ctx.lineTo(xScale(bidCurve[bidCurve.length - 1].price), yScale(bidCurve[bidCurve.length - 1].cum));
    ctx.lineTo(xScale(bidCurve[0].price), yScale(bidCurve[bidCurve.length - 1].cum));
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
  }

  if (askCurve.length) {
    ctx.fillStyle = "rgba(248, 81, 73, 0.35)";
    ctx.strokeStyle = "rgba(248, 81, 73, 0.9)";
    ctx.beginPath();
    ctx.moveTo(xScale(askCurve[0].price), yScale(0));
    let prevC = 0;
    for (const pt of askCurve) {
      ctx.lineTo(xScale(pt.price), yScale(prevC));
      ctx.lineTo(xScale(pt.price), yScale(pt.cum));
      prevC = pt.cum;
    }
    ctx.lineTo(xScale(askCurve[askCurve.length - 1].price), yScale(askCurve[askCurve.length - 1].cum));
    ctx.lineTo(xScale(askCurve[0].price), yScale(askCurve[askCurve.length - 1].cum));
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
  }

  for (const o of myOrders || []) {
    if (o.price == null) continue;
    const x = xScale(o.price);
    ctx.strokeStyle = "#58a6ff";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x, padT);
    ctx.lineTo(x, padT + plotH);
    ctx.stroke();
    const label = `YOU ${o.side === "bid" ? "BUY" : "SELL"} ${o.quantity}`;
    ctx.font = "bold 10px ui-monospace, monospace";
    const labelWidth = ctx.measureText(label).width + 8;
    const labelX = Math.min(Math.max(x + 4, padL), w - padR - labelWidth);
    const labelY = o.side === "bid" ? padT + plotH - 18 : padT + 6;
    ctx.fillStyle = "#58a6ff";
    ctx.fillRect(labelX, labelY, labelWidth, 16);
    ctx.fillStyle = "#07111f";
    ctx.fillText(label, labelX + 4, labelY + 11);
    ctx.lineWidth = 1;
  }
}

function renderPrintsTicker(prints) {
  const el = document.getElementById("prints-ticker");
  const lines = (prints || []).slice(0, 8);
  if (!lines.length) {
    el.textContent = "No prints yet";
    return;
  }
  el.innerHTML = lines
    .map(
      (p) =>
        `<div class="print-line ${p.taker}">${p.at} · ${fmt(p.price)} · ${p.quantity} · ${p.taker}</div>`
    )
    .join("");
}

function renderMyOrders(orders) {
  const tbody = document.querySelector("#my-orders tbody");
  tbody.innerHTML = "";
  const activeIds = new Set(orders.map((order) => order.order_id));
  if (!activeIds.has(selectedOrderId)) selectedOrderId = null;
  document.getElementById("cancel-selected").disabled = selectedOrderId == null;

  if (!orders.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="6" class="empty-row">No resting orders</td>`;
    tbody.appendChild(tr);
    return;
  }

  for (const o of orders) {
    const tr = document.createElement("tr");
    if (o.order_id === newestOrderId) tr.classList.add("newest-order");
    const sideClass = o.side === "bid" ? "side-bid" : "side-ask";
    tr.innerHTML = `
      <td><input type="radio" name="sel-order" value="${o.order_id}" aria-label="Select order ${o.order_id}" ${o.order_id === selectedOrderId ? "checked" : ""} /></td>
      <td>${o.order_id}</td>
      <td class="${sideClass}">${o.side === "bid" ? "Buy" : "Sell"}</td>
      <td>${fmt(o.price)}</td>
      <td>${o.open_quantity ?? o.quantity}</td>
      <td><span class="order-status status-${o.status}">${o.status}</span></td>`;
    tbody.appendChild(tr);
  }

  tbody.querySelectorAll('input[name="sel-order"]').forEach((radio) => {
    radio.addEventListener("change", () => {
      selectedOrderId = Number(radio.value);
      document.getElementById("cancel-selected").disabled = false;
    });
  });

}

function renderFinishedOrders(orders) {
  const tbody = document.querySelector("#finished-orders tbody");
  tbody.innerHTML = "";

  if (!orders.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="6" class="empty-row">No finished orders</td>`;
    tbody.appendChild(tr);
    return;
  }

  for (const o of [...orders].sort((a, b) => b.order_id - a.order_id)) {
    const tr = document.createElement("tr");
    const sideClass = o.side === "bid" ? "side-bid" : "side-ask";
    const type = o.order_type || (o.price == null ? "market" : "limit");
    const status = String(o.status || "unknown");
    tr.innerHTML = `
      <td>${o.order_id}</td>
      <td class="${sideClass}">${o.side === "bid" ? "Buy" : "Sell"}</td>
      <td class="text-capitalize">${type}</td>
      <td>${fmt(o.price)}</td>
      <td>${o.filled_quantity ?? 0}</td>
      <td><span class="order-status status-${status}">${status}</span></td>`;
    tbody.appendChild(tr);
  }
}

function syncControls(s) {
  const live = !!s.live;
  document.getElementById("toggle-flow").textContent = live ? "Pause Flow" : "Resume Flow";
  document.getElementById("toggle-flow").classList.toggle("primary", live);

  document.getElementById("tempo").value = s.tempo ?? 4;
  document.getElementById("tempo-val").textContent = s.tempo ?? 4;
  const urg = Math.round(Number(s.urgency) || 0);
  document.getElementById("urgency").value = urg;
  document.getElementById("urgency-val").textContent = urg;
}

function renderSnapshot(s) {
  const snapshotKey = JSON.stringify(s);
  if (snapshotKey === lastRenderedSnapshot) return;
  lastRenderedSnapshot = snapshotKey;
  lastSnapshot = s;
  const top = s.top || {};
  const book = s.book || {};
  const allOrders = s.my_orders || [];
  const activeOrders = s.my_active_orders || allOrders.filter((order) =>
    order.status === "resting" || order.status === "partial"
  );
  const finishedOrders = s.my_finished_orders || allOrders.filter((order) =>
    order.status !== "resting" && order.status !== "partial"
  );
  renderDom(book, top, activeOrders);
  drawDepthChart(book, top, activeOrders);
  renderPrintsTicker(s.prints);
  renderMyOrders(activeOrders);
  renderFinishedOrders(finishedOrders);
  syncControls(s);
}

async function fetchSnapshot() {
  return api(`/api/snapshot?depth=${SNAPSHOT_DEPTH}`);
}

async function refresh() {
  try {
    renderSnapshot(await fetchSnapshot());
  } catch (e) {
    setStatus(`Refresh error: ${e.message}`, true);
  }
}

async function configure(partial) {
  await api("/api/configure", { method: "POST", body: JSON.stringify(partial) });
  await refresh();
}

async function submitOrder(body) {
  const result = await api("/api/submit", { method: "POST", body: JSON.stringify(body) });

  if (result.outcome === "needs_acknowledgement") {
    pendingSubmit = { ...body, acknowledged: true };
    document.getElementById("ack-message").textContent = result.reason || "Price needs confirmation.";
    document.getElementById("ack-dialog").showModal();
    return;
  }

  pendingSubmit = null;
  if (result.outcome === "rejected") {
    setStatus(result.reason || "Rejected", true);
  } else {
    newestOrderId = result.open > 0 ? result.order_id : null;
    setStatus(`Order ${result.order_id}: ${result.status}, filled ${result.filled}, open ${result.open}`);
  }
  await refresh();
}

async function cancelOrder(orderId) {
  const button = document.getElementById("cancel-selected");
  button.disabled = true;
  button.textContent = "Cancelling…";
  try {
    await api(`/api/orders/${orderId}`, { method: "DELETE" });
    selectedOrderId = null;
    setStatus(`Cancelled order ${orderId}`);
    await refresh();
  } finally {
    button.textContent = "Cancel Selected";
  }
}

document.getElementById("order-form").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const fd = new FormData(ev.target);
  const order_type = fd.get("order_type");
  const body = {
    side: fd.get("side"),
    order_type,
    quantity: Number(fd.get("quantity")),
    acknowledged: false,
  };
  if (order_type === "limit") {
    body.price = Number(fd.get("price"));
  }
  submitOrder(body).catch((e) => setStatus(e.message, true));
});

document.getElementById("ack-dialog").addEventListener("close", () => {
  if (document.getElementById("ack-dialog").returnValue !== "confirm" || !pendingSubmit) {
    pendingSubmit = null;
    return;
  }
  const body = pendingSubmit;
  pendingSubmit = null;
  submitOrder(body).catch((e) => setStatus(e.message, true));
});

document.getElementById("toggle-flow").addEventListener("click", () => {
  const next = !(lastSnapshot?.live);
  configure({ live: next }).catch((e) => setStatus(e.message, true));
});

document.getElementById("tempo").addEventListener("input", (ev) => {
  document.getElementById("tempo-val").textContent = ev.target.value;
});
document.getElementById("tempo").addEventListener("change", (ev) => {
  configure({ tempo: Number(ev.target.value) }).catch((e) => setStatus(e.message, true));
});

document.getElementById("urgency").addEventListener("input", (ev) => {
  document.getElementById("urgency-val").textContent = ev.target.value;
});
document.getElementById("urgency").addEventListener("change", (ev) => {
  configure({ urgency: Number(ev.target.value) }).catch((e) => setStatus(e.message, true));
});

document.getElementById("restart").addEventListener("click", () => {
  api("/api/restart", { method: "POST" })
    .then(() => {
      setStatus("Session reset");
      return refresh();
    })
    .catch((e) => setStatus(e.message, true));
});

document.getElementById("cancel-selected").addEventListener("click", () => {
  if (selectedOrderId == null) return;
  cancelOrder(selectedOrderId).catch((e) => setStatus(e.message, true));
});

let pollTimer = null;

async function poll() {
  try {
    let snap = await fetchSnapshot();
    if (snap.live) {
      await api("/api/advance", { method: "POST", body: JSON.stringify({ ticks: snap.tempo || 1 }) });
      snap = await fetchSnapshot();
    }
    renderSnapshot(snap);
  } catch (e) {
    console.error(e);
  }
}

window.addEventListener("resize", () => {
  if (lastSnapshot) drawDepthChart(lastSnapshot.book, lastSnapshot.top, lastSnapshot.my_orders);
});

function startPoll() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(poll, 800);
}

initializePanelResizer();
refresh().then(startPoll);
