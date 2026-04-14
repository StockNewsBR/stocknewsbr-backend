import json

from app.Frontend.layout import get_layout


def get_terminal(focused_tab: str | None = None, token: str | None = None):
    tabs = get_layout()["tabs"]
    initial_tab = focused_tab or "home"
    embedded_tabs = json.dumps(tabs)
    embedded_token = json.dumps(token or "")

    return f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>StockNewsBR Workspace</title>
<style>
:root {{
  --bg:#07111b;
  --bg-soft:#0d1b28;
  --panel:#112233;
  --panel-alt:#13283d;
  --text:#ecf3fb;
  --muted:#8fa3b8;
  --green:#1fd38a;
  --gold:#f4b942;
  --red:#ff6b6b;
  --cyan:#67d4ff;
  --line:rgba(255,255,255,.08);
  --glow:0 18px 60px rgba(0,0,0,.35);
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0;
  font-family:Segoe UI, Arial, sans-serif;
  background:
    radial-gradient(circle at top left, rgba(31,211,138,.12), transparent 28%),
    radial-gradient(circle at top right, rgba(244,185,66,.12), transparent 22%),
    linear-gradient(180deg, #08131f 0%, #061019 100%);
  color:var(--text);
}}
button, input, textarea {{
  font:inherit;
}}
.shell {{
  min-height:100vh;
  display:grid;
  grid-template-rows:auto auto 1fr;
}}
.topbar {{
  display:flex;
  justify-content:space-between;
  align-items:center;
  gap:16px;
  padding:18px 22px;
  border-bottom:1px solid var(--line);
  background:rgba(7,17,27,.82);
  backdrop-filter:blur(16px);
  position:sticky;
  top:0;
  z-index:5;
}}
.brand h1 {{
  margin:0;
  font-size:22px;
  letter-spacing:.03em;
}}
.brand p {{
  margin:4px 0 0;
  color:var(--muted);
  font-size:13px;
}}
.statusbar {{
  display:flex;
  gap:12px;
  flex-wrap:wrap;
  justify-content:flex-end;
}}
.pill {{
  padding:8px 12px;
  border-radius:999px;
  background:rgba(255,255,255,.06);
  color:var(--text);
  font-size:12px;
}}
.tabs {{
  display:flex;
  gap:10px;
  padding:14px 20px;
  border-bottom:1px solid var(--line);
  overflow:auto;
}}
.tab {{
  border:1px solid rgba(255,255,255,.08);
  background:rgba(255,255,255,.04);
  color:var(--text);
  border-radius:16px;
  padding:12px 14px;
  min-width:214px;
  cursor:pointer;
  transition:.2s ease;
}}
.tab:hover,.tab.active {{
  border-color:rgba(31,211,138,.55);
  background:linear-gradient(180deg, rgba(31,211,138,.14), rgba(255,255,255,.05));
  transform:translateY(-1px);
}}
.tab.dragging {{
  opacity:.55;
}}
.tab strong {{
  display:block;
  font-size:13px;
}}
.tab span {{
  display:block;
  margin-top:5px;
  color:var(--muted);
  font-size:11px;
}}
.workspace {{
  display:grid;
  grid-template-columns:2fr 1fr;
  gap:18px;
  padding:18px;
}}
.stack {{
  display:grid;
  gap:18px;
}}
.panel {{
  background:linear-gradient(180deg, rgba(17,34,51,.96), rgba(10,24,38,.96));
  border:1px solid var(--line);
  border-radius:22px;
  padding:18px;
  box-shadow:var(--glow);
}}
.panel h2 {{
  margin:0 0 12px;
  font-size:18px;
}}
.panel h3 {{
  margin:0 0 10px;
  font-size:14px;
  color:#dce7f4;
}}
.hero {{
  display:grid;
  grid-template-columns:1.35fr 1fr;
  gap:18px;
}}
.metric-grid,.mini-grid,.feature-grid {{
  display:grid;
  grid-template-columns:repeat(3, 1fr);
  gap:12px;
}}
.feature-grid {{
  grid-template-columns:repeat(2, 1fr);
}}
.metric,.mini-card,.feature-card {{
  background:rgba(255,255,255,.04);
  border:1px solid rgba(255,255,255,.06);
  border-radius:16px;
  padding:14px;
}}
.metric b,.mini-card b {{
  display:block;
  margin-bottom:6px;
  font-size:20px;
}}
.muted {{ color:var(--muted); }}
.list {{
  display:grid;
  gap:10px;
}}
.row {{
  display:flex;
  justify-content:space-between;
  gap:12px;
  padding:11px 12px;
  border-radius:14px;
  background:rgba(255,255,255,.04);
}}
.row .left {{
  display:grid;
  gap:4px;
}}
.score.up {{ color:var(--green); }}
.score.mid {{ color:var(--gold); }}
.score.down {{ color:var(--red); }}
.chart-wrap {{
  background:rgba(255,255,255,.03);
  border-radius:16px;
  padding:10px;
}}
.chart-meta {{
  display:flex;
  gap:10px;
  flex-wrap:wrap;
  margin-top:12px;
}}
.badge {{
  padding:7px 10px;
  border-radius:999px;
  background:rgba(255,255,255,.06);
  font-size:12px;
}}
.actions {{
  display:flex;
  gap:10px;
  flex-wrap:wrap;
  margin-top:12px;
}}
button.action {{
  border:none;
  border-radius:12px;
  padding:11px 14px;
  cursor:pointer;
  color:#061019;
  font-weight:700;
  background:linear-gradient(90deg, var(--green), #6ee7b7);
}}
button.secondary {{
  color:var(--text);
  background:rgba(255,255,255,.08);
}}
.guide {{
  border:1px solid rgba(255,255,255,.08);
  border-radius:18px;
  padding:14px;
  background:rgba(255,255,255,.03);
}}
.guide p, .guide li {{
  color:var(--muted);
  line-height:1.45;
}}
.guide ul {{
  margin:10px 0 0 18px;
  padding:0;
}}
.feed {{
  display:grid;
  gap:10px;
}}
.post {{
  padding:12px;
  border-radius:16px;
  background:rgba(255,255,255,.04);
}}
.room-composer {{
  display:grid;
  gap:10px;
}}
.field-row {{
  display:flex;
  gap:10px;
  flex-wrap:wrap;
  align-items:center;
}}
.input, .textarea {{
  width:100%;
  border-radius:14px;
  border:1px solid rgba(255,255,255,.08);
  background:rgba(255,255,255,.04);
  color:var(--text);
  padding:12px 14px;
}}
.textarea {{
  min-height:96px;
  resize:vertical;
}}
.empty {{
  padding:18px;
  border-radius:16px;
  background:rgba(255,255,255,.03);
  color:var(--muted);
}}
.hint {{
  font-size:12px;
  color:var(--muted);
}}
.image-preview {{
  margin-top:8px;
  max-width:100%;
  border-radius:14px;
  border:1px solid rgba(255,255,255,.06);
}}
@media (max-width: 1100px) {{
  .workspace,.hero {{
    grid-template-columns:1fr;
  }}
  .metric-grid,.mini-grid,.feature-grid {{
    grid-template-columns:1fr;
  }}
}}
</style>
</head>
<body>
<div class="shell">
  <div class="topbar">
    <div class="brand">
      <h1>StockNewsBR Workspace</h1>
      <p>Google app + website + Telegram como uma mesa operacional unica.</p>
    </div>
    <div class="statusbar" id="statusbar"></div>
  </div>
  <div class="tabs" id="tabs"></div>
  <div class="workspace">
    <div class="stack" id="main-column"></div>
    <div class="stack" id="side-column"></div>
  </div>
</div>
<script>
const FALLBACK_TABS = {embedded_tabs};
const FOCUSED_TAB = {json.dumps(initial_tab)};
const AUTH_TOKEN = {embedded_token};
const IS_POPOUT = Boolean(FOCUSED_TAB);
let WORKSPACE = null;
let CHART = null;
let ACTIVE_TAB = FOCUSED_TAB || "home";
let ACTIVE_TICKER = "PETR4";
let ROOM_MESSAGES = [];
let ROOM_SOCKET = null;
let OPENED_POPOUTS = [];
let DRAG_INDEX = null;

function escapeHtml(value) {{
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}}

function scoreClass(score) {{
  if (score >= 80) return "up";
  if (score >= 50) return "mid";
  return "down";
}}

function authHeaders(base = {{}}) {{
  if (!AUTH_TOKEN) return base;
  return {{ ...base, Authorization: `Bearer ${{AUTH_TOKEN}}` }};
}}

async function apiFetch(url, options = {{}}) {{
  const headers = authHeaders(options.headers || {{}});
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  if (options.body && !isFormData && !headers["Content-Type"]) {{
    headers["Content-Type"] = "application/json";
  }}
  const response = await fetch(url, {{ ...options, headers }});
  if (!response.ok) {{
    let detail = response.statusText;
    try {{
      const payload = await response.json();
      detail = payload.detail || JSON.stringify(payload);
    }} catch (error) {{
      detail = response.statusText || String(error);
    }}
    throw new Error(detail);
  }}
  return response;
}}

function openDetached(tabId) {{
  if (!OPENED_POPOUTS.includes(tabId)) {{
    OPENED_POPOUTS.push(tabId);
    persistLayout();
  }}
  const tokenQuery = AUTH_TOKEN ? `?token=${{encodeURIComponent(AUTH_TOKEN)}}` : "";
  const url = `/web/terminal/popout/${{tabId}}${{tokenQuery}}`;
  window.open(url, `stocknewsbr_${{tabId}}`, "width=1480,height=920,resizable=yes,scrollbars=yes");
}}

function setActiveTab(tabId) {{
  if (IS_POPOUT) return;
  ACTIVE_TAB = tabId;
  renderWorkspace();
}}

function onTabDragStart(index) {{
  if (IS_POPOUT) return;
  DRAG_INDEX = index;
}}

function onTabDragOver(event) {{
  if (IS_POPOUT) return;
  event.preventDefault();
}}

function onTabDrop(index) {{
  if (IS_POPOUT || DRAG_INDEX === null || !WORKSPACE?.tabs?.length) return;
  const tabs = [...WORKSPACE.tabs];
  const moved = tabs.splice(DRAG_INDEX, 1)[0];
  tabs.splice(index, 0, moved);
  DRAG_INDEX = null;
  WORKSPACE.tabs = tabs;
  renderTabs();
  persistLayout();
}}

function renderTabs() {{
  const host = document.getElementById("tabs");
  const tabs = (WORKSPACE?.tabs || FALLBACK_TABS).filter(tab => !IS_POPOUT || tab.id === ACTIVE_TAB);

  host.innerHTML = tabs.map((tab, index) => `
    <div
      class="tab ${{tab.id === ACTIVE_TAB ? "active" : ""}}"
      draggable="${{IS_POPOUT ? "false" : "true"}}"
      ondragstart="onTabDragStart(${{index}})"
      ondragover="onTabDragOver(event)"
      ondrop="onTabDrop(${{index}})"
      onclick="setActiveTab('${{tab.id}}')"
    >
      <strong>${{escapeHtml(tab.title)}}</strong>
      <span>${{tab.detachable ? "Aba arrastavel e destacavel para workspace multi-monitor" : "Modulo principal da mesa"}} </span>
      <div class="actions">
        <button class="action secondary" onclick="event.stopPropagation(); openDetached('${{tab.id}}')">Desacoplar</button>
      </div>
    </div>
  `).join("");
}}

function renderStatus() {{
  const status = WORKSPACE?.status || {{}};
  const authHint = AUTH_TOKEN ? "token conectado" : "adicione ?token=SEU_TOKEN";
  document.getElementById("statusbar").innerHTML = `
    <div class="pill">Ciclos: ${{status.engine_cycles ?? 0}}</div>
    <div class="pill">Sinais: ${{status.signals_generated ?? 0}}</div>
    <div class="pill">HTTP: ${{status.http_requests ?? 0}}</div>
    <div class="pill">WS: ${{status.ws_connections ?? 0}}</div>
    <div class="pill">${{escapeHtml(authHint)}}</div>
  `;
}}

function renderHome() {{
  const pricing = WORKSPACE?.pricing || {{}};
  const roadmap = WORKSPACE?.launch_roadmap || {{}};
  const topSignals = WORKSPACE?.top_signals || [];
  const ranking = WORKSPACE?.ranking || [];

  return `
    <div class="panel">
      <div class="hero">
        <div>
          <h2>Lancamento principal Android + Web + Telegram</h2>
          <p class="muted">O ecossistema premium ja nasce orientado a workspace profissional, social por ticker, videos de ajuda e IA aplicada ao fluxo.</p>
          <div class="metric-grid">
            <div class="metric"><span class="muted">Trial</span><b>${{pricing.trial_days || 90}} dias</b><span class="muted">Acesso inicial ao ecossistema</span></div>
            <div class="metric"><span class="muted">Premium mensal</span><b>R$ ${{pricing.premium_monthly?.price_brl || 49}}</b><span class="muted">App + Web + Telegram</span></div>
            <div class="metric"><span class="muted">Premium anual</span><b>R$ ${{pricing.premium_annual?.price_brl || 500}}</b><span class="muted">Google app primeiro, Apple depois</span></div>
          </div>
          <div class="actions">
            <button class="action" onclick="setActiveTab('grafico')">Abrir grafico</button>
            <button class="action secondary" onclick="setActiveTab('ticker-rooms')">Ir para Ticker Room</button>
          </div>
        </div>
        <div class="panel" style="padding:16px;">
          <h3>Workspace salvo por usuario</h3>
          <div class="mini-grid">
            <div class="mini-card"><span class="muted">Fase atual</span><b>${{escapeHtml(roadmap.current || "google_app")}}</b></div>
            <div class="mini-card"><span class="muted">Proxima fase</span><b>${{escapeHtml(roadmap.next || "apple_app")}}</b></div>
            <div class="mini-card"><span class="muted">Ticker fixado</span><b>${{escapeHtml(ACTIVE_TICKER)}}</b></div>
          </div>
          <p class="hint" style="margin-top:12px;">Arraste as abas para reorganizar, destaque paineis em outra tela e seu layout fica salvo para a proxima sessao.</p>
        </div>
      </div>
    </div>
    <div class="panel">
      <h2>Radar principal da mesa</h2>
      <div class="list">
        ${{topSignals.slice(0, 8).map(item => `
          <div class="row">
            <div class="left">
              <strong>${{escapeHtml(item.ticker || item.symbol || "-")}}</strong>
              <span class="muted">Trend: ${{escapeHtml(item.trend ?? "n/a")}} | Breakout: ${{item.breakout ? "sim" : "nao"}}</span>
            </div>
            <div class="score ${{scoreClass(Number(item.score || 0))}}">${{Number(item.score || 0).toFixed(2)}}</div>
          </div>
        `).join("") || `<div class="empty">Sem sinais no snapshot ainda.</div>`}}
      </div>
    </div>
    <div class="panel">
      <h2>Ranking geral</h2>
      <div class="list">
        ${{ranking.slice(0, 8).map(item => `
          <div class="row">
            <div class="left">
              <strong>${{escapeHtml(item.symbol || "-")}}</strong>
              <span class="muted">Tendencia: ${{escapeHtml(item.trend ?? "n/a")}} | RSI: ${{escapeHtml(item.rsi ?? "n/a")}}</span>
            </div>
            <div class="score ${{scoreClass(Number(item.score || 0))}}">${{Number(item.score || 0).toFixed(2)}}</div>
          </div>
        `).join("") || `<div class="empty">Ranking indisponivel.</div>`}}
      </div>
    </div>
  `;
}}

function renderChartPanel() {{
  const chart = CHART || {{}};
  const summary = chart.summary || {{}};
  const markers = chart.markers || [];
  const zones = chart.zones || [];

  return `
    <div class="panel">
      <h2>IA Grafico com overlays</h2>
      <div class="field-row">
        <input class="input" id="ticker-input" value="${{escapeHtml(ACTIVE_TICKER)}}" maxlength="16" placeholder="Digite PETR4, VALE3, BTCUSD..." />
        <button class="action" onclick="updateTicker()">Atualizar ticker</button>
      </div>
      <div class="chart-wrap" style="margin-top:12px;">
        <canvas id="chart-canvas" width="920" height="300"></canvas>
      </div>
      <div class="chart-meta">
        <div class="badge">Ticker: ${{escapeHtml(summary.ticker || ACTIVE_TICKER)}}</div>
        <div class="badge">Fechamento: ${{escapeHtml(summary.latest_close ?? "n/a")}}</div>
        <div class="badge">Bias: ${{escapeHtml(summary.trend_bias || "n/a")}}</div>
        <div class="badge">Marcadores: ${{markers.length}}</div>
      </div>
      <div class="actions">
        ${{zones.map(zone => `<span class="badge">${{escapeHtml(zone.label)}}: ${{escapeHtml(zone.price)}}</span>`).join("")}}
      </div>
      <div class="list" style="margin-top:14px;">
        ${{markers.map(marker => `
          <div class="row">
            <div class="left">
              <strong>${{escapeHtml(marker.type)}}</strong>
              <span class="muted">Preco: ${{escapeHtml(marker.price ?? "n/a")}} | Tempo: ${{escapeHtml(marker.time ?? "snapshot")}}</span>
            </div>
            <div class="score ${{marker.side === "buy" ? "up" : marker.side === "sell" ? "down" : "mid"}}">${{escapeHtml(marker.side)}}</div>
          </div>
        `).join("") || `<div class="empty">Nenhum marcador operacional ainda.</div>`}}
      </div>
    </div>
  `;
}}

function renderFeatureList(title, items) {{
  return `
    <div class="panel">
      <h2>${{escapeHtml(title)}}</h2>
      <div class="feature-grid">
        ${{items.map(item => `
          <div class="feature-card">
            <strong>${{escapeHtml(item.title || item)}}</strong>
            <p>${{escapeHtml(item.tagline || "Modulo institucional da plataforma")}}</p>
          </div>
        `).join("")}}
      </div>
    </div>
  `;
}}

function renderAiToolList(title, items, fallbackTagline) {{
  const safeItems = Array.isArray(items) ? items : [];
  const rows = safeItems.length
    ? safeItems.map(item => ({{
        title: `${{item.ticker || "ATIVO"}} • ${{item.signal || "NEUTRAL"}} • ${{Number(item.score || 0).toFixed(1)}}`,
        tagline: item.ai_comment || item.trigger || fallbackTagline || "Leitura operacional da IA.",
      }}))
    : [{{ title, tagline: fallbackTagline || "Sem leituras especificas no snapshot atual." }}];

  return renderFeatureList(title, rows);
}}

function renderHelp() {{
  const guides = WORKSPACE?.help_center?.guides || [];
  const videoStatus = WORKSPACE?.help_center?.video_status || {{}};
  return `
    <div class="panel">
      <h2>Ajuda educacional para o trader</h2>
      <p class="muted">Videos disponiveis: ${{videoStatus.available_videos ?? 0}} / ${{videoStatus.planned_videos ?? guides.length}}</p>
      <div class="list">
        ${{guides.map(guide => `
          <div class="guide">
            <h3>${{escapeHtml(guide.title)}}</h3>
            <p>${{escapeHtml(guide.tagline || guide.description || "")}}</p>
            <ul>
              ${{(guide.how_to_use || []).map(step => `<li>${{escapeHtml(step)}}</li>`).join("")}}
            </ul>
            <div class="actions">
              <button class="action secondary" onclick="window.open('${{guide.demo_video_url}}','_blank')">Abrir demo</button>
              <span class="badge">Video: ${{escapeHtml(guide.video_status || "preview")}}</span>
            </div>
          </div>
        `).join("") || `<div class="empty">Guias em preparacao.</div>`}}
      </div>
    </div>
  `;
}}

function renderTickerRoom() {{
  const messages = ROOM_MESSAGES || [];
  return `
    <div class="panel">
      <h2>Ticker Room em tempo real - ${{escapeHtml(ACTIVE_TICKER)}}</h2>
      <div class="field-row">
        <input class="input" id="chat-ticker-input" value="${{escapeHtml(ACTIVE_TICKER)}}" maxlength="16" placeholder="Ticker da sala" />
        <button class="action" onclick="updateTicker(true)">Trocar sala</button>
      </div>
      <div class="room-composer" style="margin-top:12px;">
        <textarea class="textarea" id="chat-message-input" placeholder="Compartilhe sua leitura do ativo, emoji, tese, noticia ou plano."></textarea>
        <input class="input" id="chat-image-input" placeholder="URL da imagem opcional" />
        <div class="field-row">
          <button class="action" onclick="sendRoomMessage()">Publicar</button>
          <button class="action secondary" onclick="connectChatSocket()">Reconectar realtime</button>
        </div>
      </div>
      <div class="feed" style="margin-top:14px;">
        ${{messages.map(item => `
          <div class="post">
            <strong>${{escapeHtml(item.user_name || "Trader")}}</strong>
            <p class="muted">${{escapeHtml(item.text || "")}}</p>
            ${{item.image_url ? `<img class="image-preview" src="${{escapeHtml(item.image_url)}}" alt="midia" />` : ""}}
          </div>
        `).join("") || `<div class="empty">Ainda sem mensagens. Esta sala ja esta pronta para realtime por ticker.</div>`}}
      </div>
    </div>
  `;
}}

function renderFeedPreview() {{
  const posts = WORKSPACE?.featured_posts || [];
  return `
    <div class="panel">
      <h2>Feed social em destaque</h2>
      <div class="feed">
        ${{posts.map(post => `
          <div class="post">
            <strong>${{escapeHtml(post.user || "Trader")}} ${{post.ticker ? `em ${{escapeHtml(post.ticker)}}` : ""}}</strong>
            <p class="muted">${{escapeHtml(post.text || "")}}</p>
            ${{post.image_url ? `<img class="image-preview" src="${{escapeHtml(post.image_url)}}" alt="midia" />` : ""}}
          </div>
        `).join("") || `<div class="empty">Sem posts destacados por enquanto.</div>`}}
      </div>
    </div>
  `;
}}

function renderInfra() {{
  const media = WORKSPACE?.media || {{}};
  const push = WORKSPACE?.push || {{}};
  const layout = WORKSPACE?.layout || {{}};
  const roomPreview = WORKSPACE?.ticker_room_preview || {{}};

  return `
    <div class="panel">
      <h2>Infra e operacao</h2>
      <div class="mini-grid">
        <div class="mini-card"><span class="muted">Media provider</span><b>${{escapeHtml(media.provider || "local")}}</b></div>
        <div class="mini-card"><span class="muted">CDN pronto</span><b>${{media.cdn_ready ? "sim" : "nao"}}</b></div>
        <div class="mini-card"><span class="muted">Push Android</span><b>${{push.android_ready ? "sim" : "nao"}}</b></div>
      </div>
      <p class="muted" style="margin-top:12px;">${{escapeHtml(media.next_step || "")}}</p>
      <p class="muted">${{escapeHtml(push.next_step || "")}}</p>
      <div class="actions">
        <span class="badge">Popouts: ${{(layout.opened_popouts || []).length}}</span>
        <span class="badge">Sala fixa: ${{escapeHtml(roomPreview.symbol || ACTIVE_TICKER)}}</span>
      </div>
    </div>
    <div class="panel">
      <h2>Preview da sala</h2>
      <div class="feed">
        ${{(roomPreview.messages || []).slice(-4).map(item => `
          <div class="post">
            <strong>${{escapeHtml(item.user_name || "Trader")}}</strong>
            <p class="muted">${{escapeHtml(item.text || "")}}</p>
          </div>
        `).join("") || `<div class="empty">Sem historico recente na sala selecionada.</div>`}}
      </div>
    </div>
  `;
}}

function drawChart() {{
  const canvas = document.getElementById("chart-canvas");
  if (!canvas || !CHART?.series?.length) return;

  const ctx = canvas.getContext("2d");
  const series = CHART.series;
  const closes = series.map(item => Number(item.close || 0));
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const width = canvas.width;
  const height = canvas.height;

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#08131f";
  ctx.fillRect(0, 0, width, height);

  function drawLine(values, color, lineWidth = 2) {{
    if (!values.length) return;
    ctx.beginPath();
    values.forEach((value, index) => {{
      const x = index * (width / Math.max(values.length - 1, 1));
      const y = height - ((value - min) / Math.max(max - min, 1e-9)) * (height - 20) - 10;
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }});
    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth;
    ctx.stroke();
  }}

  drawLine(closes, "#f4b942", 2.5);
  drawLine(series.map(item => Number(item.ema9 || item.close || 0)), "#1fd38a");
  drawLine(series.map(item => Number(item.ema21 || item.close || 0)), "#56a3ff");

  (CHART.markers || []).forEach((marker, index) => {{
    const x = width - 18 - (index * 16);
    const y = marker.side === "buy" ? 22 : marker.side === "sell" ? 42 : 62;
    ctx.fillStyle = marker.side === "buy" ? "#1fd38a" : marker.side === "sell" ? "#ff6b6b" : "#f4b942";
    ctx.beginPath();
    ctx.arc(x, y, 5, 0, Math.PI * 2);
    ctx.fill();
  }});
}}

async function persistLayout() {{
  if (!WORKSPACE || IS_POPOUT) return;

  try {{
    await apiFetch("/web/workspace/layout", {{
      method: "PUT",
      body: JSON.stringify({{
        tabs: (WORKSPACE.tabs || FALLBACK_TABS).map(tab => tab.id),
        pinned_ticker: ACTIVE_TICKER,
        opened_popouts: OPENED_POPOUTS,
      }}),
    }});
  }} catch (error) {{
    console.warn("Falha ao salvar layout", error);
  }}
}}

async function refreshSymbolContext() {{
  const [chartResponse, roomResponse] = await Promise.all([
    apiFetch(`/web/chart/${{encodeURIComponent(ACTIVE_TICKER)}}?interval=1D`),
    apiFetch(`/chat/${{encodeURIComponent(ACTIVE_TICKER)}}/history?limit=60`),
  ]);

  CHART = await chartResponse.json();
  const roomPayload = await roomResponse.json();
  ROOM_MESSAGES = roomPayload.items || [];
}}

async function updateTicker(focusRoom = false) {{
  const input = document.getElementById(focusRoom ? "chat-ticker-input" : "ticker-input");
  const nextTicker = String(input?.value || ACTIVE_TICKER).trim().toUpperCase();
  if (!nextTicker) return;
  ACTIVE_TICKER = nextTicker;
  await persistLayout();
  await refreshSymbolContext();
  if (focusRoom) {{
    ACTIVE_TAB = "ticker-rooms";
    connectChatSocket();
  }}
  renderWorkspace();
}}

function connectChatSocket() {{
  if (ROOM_SOCKET) {{
    try {{
      ROOM_SOCKET.close();
    }} catch (error) {{
      console.warn(error);
    }}
  }}

  if (!AUTH_TOKEN) return;

  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  ROOM_SOCKET = new WebSocket(
    `${{protocol}}://${{window.location.host}}/ws/chat/${{encodeURIComponent(ACTIVE_TICKER)}}?token=${{encodeURIComponent(AUTH_TOKEN)}}`
  );

  ROOM_SOCKET.onmessage = event => {{
    const payload = JSON.parse(event.data);
    if (payload.type === "history") {{
      ROOM_MESSAGES = payload.items || [];
    }} else if (payload.type === "message" && payload.item) {{
      ROOM_MESSAGES = [...ROOM_MESSAGES, payload.item].slice(-60);
    }}
    if (ACTIVE_TAB === "ticker-rooms") {{
      renderWorkspace();
    }}
  }};
}}

async function sendRoomMessage() {{
  const textInput = document.getElementById("chat-message-input");
  const imageInput = document.getElementById("chat-image-input");
  const text = String(textInput?.value || "").trim();
  const imageUrl = String(imageInput?.value || "").trim();
  if (!text) return;

  try {{
    if (ROOM_SOCKET && ROOM_SOCKET.readyState === WebSocket.OPEN) {{
      ROOM_SOCKET.send(JSON.stringify({{
        type: "message",
        text,
        image_url: imageUrl || null,
      }}));
    }} else {{
      const response = await apiFetch(`/chat/${{encodeURIComponent(ACTIVE_TICKER)}}/message`, {{
        method: "POST",
        body: JSON.stringify({{
          text,
          image_url: imageUrl || null,
        }}),
      }});
      const created = await response.json();
      ROOM_MESSAGES = [...ROOM_MESSAGES, created].slice(-60);
    }}

    if (textInput) textInput.value = "";
    if (imageInput) imageInput.value = "";
    renderWorkspace();
  }} catch (error) {{
    alert(`Falha ao publicar: ${{error.message}}`);
  }}
}}

function renderWorkspace() {{
  renderTabs();
  renderStatus();

  const main = document.getElementById("main-column");
  const side = document.getElementById("side-column");

  const panels = {{
    "home": renderHome(),
    "heatmap": renderAiToolList("IA Heat Map", WORKSPACE?.ai_tools?.heat_map || [], "Mapa de calor institucional por ativo e setor."),
    "radar": renderHome(),
    "breakout-probability": renderAiToolList("IA Breakout Probability", WORKSPACE?.ai_tools?.breakout_probability || [], "Scanner para rompimentos com contexto de fluxo e score."),
    "volatility-squeeze": renderAiToolList("IA Volatility Squeeze", WORKSPACE?.ai_tools?.volatility_squeeze || [], "Busca compressoes antes de expansao direcional."),
    "institutional-flow": renderAiToolList("IA Institutional Flow", WORKSPACE?.ai_tools?.institutional_flow || [], "Leitura de pressao institucional, smart money e acumulacao."),
    "smart-money": renderAiToolList("IA Smart Money", WORKSPACE?.ai_tools?.smart_money || [], "Rastreamento de volume anormal e presenca de player forte."),
    "accumulation": renderAiToolList("IA Accumulation", WORKSPACE?.ai_tools?.accumulation || [], "Base para identificar absorcao e construcao de posicao."),
    "liquidity-sweep": renderAiToolList("IA Liquidity Sweep", WORKSPACE?.ai_tools?.liquidity_sweep || [], "Mapeia varredura de liquidez e possiveis traps."),
    "liquidity-map": renderAiToolList("IA Liquidity Map", WORKSPACE?.ai_tools?.liquidity_map || [], "Zonas de liquidez para decisao de trade e gerenciamento."),
    "market-regime": renderAiToolList("IA Market Regime", WORKSPACE?.ai_tools?.market_regime || [], "Define se o mercado esta em momentum, rotacao ou defesa."),
    "master-score": renderAiToolList("IA Master Score", WORKSPACE?.ai_tools?.master_score || [], "Ranking consolidado do ecossistema institucional da plataforma."),
    "grafico": renderChartPanel(),
    "ticker-rooms": renderTickerRoom(),
    "education": renderHelp(),
  }};

  main.innerHTML = panels[ACTIVE_TAB] || renderHome();
  side.innerHTML = `${{renderInfra()}}${{renderFeedPreview()}}`;

  if (ACTIVE_TAB === "grafico") drawChart();
  if (ACTIVE_TAB === "ticker-rooms") connectChatSocket();
}}

async function loadWorkspace() {{
  const workspaceResponse = await apiFetch("/web/workspace/data");
  WORKSPACE = await workspaceResponse.json();
  ACTIVE_TICKER = WORKSPACE?.layout?.pinned_ticker || "PETR4";
  OPENED_POPOUTS = [...(WORKSPACE?.layout?.opened_popouts || [])];

  if (IS_POPOUT) {{
    ACTIVE_TAB = FOCUSED_TAB;
  }} else {{
    const allowedTabs = new Set((WORKSPACE?.tabs || []).map(tab => tab.id));
    if (!allowedTabs.has(ACTIVE_TAB)) {{
      ACTIVE_TAB = (WORKSPACE?.tabs?.[0]?.id) || "home";
    }}
  }}

  await refreshSymbolContext();
  renderWorkspace();
}}

loadWorkspace().catch(error => {{
  document.getElementById("main-column").innerHTML = `<div class="panel"><h2>Workspace indisponivel</h2><p class="muted">${{escapeHtml(error.message || "Erro ao carregar os dados.")}}</p><p class="hint">Se voce estiver testando no navegador, abra esta pagina com ?token=SEU_ACCESS_TOKEN para liberar as chamadas autenticadas do workspace.</p></div>`;
}});
</script>
</body>
</html>
"""
