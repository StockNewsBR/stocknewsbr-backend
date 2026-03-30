from app.services.help_center_service import get_help_center_blueprint
from app.services.legal_service import get_public_bootstrap
from app.services.media_service import get_media_status
from app.services.push_service import get_push_status
from app.services.storage_service import get_storage_status


def get_marketing_site():
    bootstrap = get_public_bootstrap()
    help_center = get_help_center_blueprint()
    media = get_media_status()
    push = get_push_status()
    storage = get_storage_status()

    ai_modules = bootstrap.get("ai_modules", [])
    social_features = bootstrap.get("social_features", {})
    guides = help_center.get("guides", [])[:4]
    pricing = bootstrap.get("pricing", {})
    social_items = [
        key.replace("_", " ").title()
        for key, enabled in social_features.items()
        if enabled
    ]

    feature_cards = "".join(
        f"""
        <article class="feature-card">
          <span class="eyebrow">IA</span>
          <h3>{module}</h3>
          <p>Scanner institucional ligado ao ranking, grafico, feed e alertas.</p>
        </article>
        """
        for module in ai_modules[:8]
    )

    social_cards = "".join(
        f"""
        <article class="mini-card">
          <h3>{item}</h3>
          <p>Construido para manter o trader operando dentro do ecossistema.</p>
        </article>
        """
        for item in social_items[:6]
    )

    guide_cards = "".join(
        f"""
        <article class="guide-card">
          <span class="eyebrow">Ajuda</span>
          <h3>{guide['title']}</h3>
          <p>{guide.get('tagline', '')}</p>
          <a href="{guide.get('demo_video_url', '#')}">Ver demo</a>
        </article>
        """
        for guide in guides
    )

    return f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>StockNewsBR</title>
<style>
:root {{
  --bg:#061018;
  --bg-2:#0d1b28;
  --panel:rgba(16,31,46,.86);
  --line:rgba(255,255,255,.09);
  --text:#edf4fb;
  --muted:#95a9bd;
  --green:#1fd38a;
  --gold:#f4b942;
  --red:#ff6b6b;
  --cyan:#68d6ff;
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0;
  font-family:Segoe UI, Arial, sans-serif;
  color:var(--text);
  background:
    radial-gradient(circle at 0% 0%, rgba(31,211,138,.16), transparent 26%),
    radial-gradient(circle at 100% 0%, rgba(244,185,66,.14), transparent 24%),
    linear-gradient(180deg, #060f17 0%, #091421 100%);
}}
a {{ color:inherit; text-decoration:none; }}
.shell {{ width:min(1320px, calc(100vw - 32px)); margin:0 auto; }}
.nav {{
  display:flex; justify-content:space-between; align-items:center; gap:16px;
  padding:18px 0; position:sticky; top:0; z-index:5;
  backdrop-filter:blur(18px);
}}
.nav-links {{ display:flex; gap:14px; flex-wrap:wrap; }}
.nav-links a {{
  padding:10px 14px; border-radius:999px; background:rgba(255,255,255,.04); color:var(--muted);
}}
.hero {{
  padding:34px 0 24px;
  display:grid; grid-template-columns:1.3fr .9fr; gap:22px;
}}
.hero-card,.panel {{
  border:1px solid var(--line);
  background:linear-gradient(180deg, rgba(17,32,47,.9), rgba(10,22,34,.88));
  border-radius:28px;
  box-shadow:0 24px 80px rgba(0,0,0,.34);
}}
.hero-main {{ padding:30px; }}
.hero-main h1 {{ margin:0; font-size:58px; line-height:1.02; letter-spacing:-.03em; }}
.hero-main p {{ font-size:18px; color:var(--muted); max-width:720px; }}
.eyebrow {{
  display:inline-flex; align-items:center; gap:8px;
  padding:8px 12px; border-radius:999px; background:rgba(31,211,138,.12); color:var(--green); font-size:12px;
  text-transform:uppercase; letter-spacing:.08em;
}}
.cta-row {{ display:flex; gap:12px; flex-wrap:wrap; margin-top:18px; }}
.cta {{
  display:inline-flex; align-items:center; justify-content:center;
  min-height:48px; padding:0 18px; border-radius:16px; font-weight:700;
}}
.cta.primary {{ background:linear-gradient(90deg, var(--green), #70ebb8); color:#041017; }}
.cta.secondary {{ background:rgba(255,255,255,.06); border:1px solid var(--line); }}
.hero-side {{ padding:24px; display:grid; gap:14px; }}
.metric-grid, .feature-grid, .social-grid, .guides-grid, .ops-grid {{
  display:grid; gap:14px;
}}
.metric-grid {{ grid-template-columns:repeat(3, 1fr); }}
.feature-grid {{ grid-template-columns:repeat(4, 1fr); }}
.social-grid, .guides-grid, .ops-grid {{ grid-template-columns:repeat(3, 1fr); }}
.metric, .feature-card, .mini-card, .guide-card, .ops-card {{
  border:1px solid rgba(255,255,255,.06);
  background:rgba(255,255,255,.04);
  border-radius:22px;
  padding:18px;
}}
.metric strong {{ display:block; font-size:30px; margin:6px 0; }}
.metric span, .feature-card p, .mini-card p, .guide-card p, .ops-card p {{ color:var(--muted); line-height:1.45; }}
.section {{ padding:12px 0 18px; }}
.section h2 {{ margin:0 0 8px; font-size:34px; }}
.section p.lead {{ margin:0 0 18px; color:var(--muted); max-width:840px; }}
.feature-card h3, .mini-card h3, .guide-card h3, .ops-card h3 {{ margin:12px 0 8px; font-size:18px; }}
.workspace-preview {{
  display:grid; grid-template-columns:220px 1fr 320px; gap:14px; padding:18px;
}}
.rail, .center, .right {{
  border:1px solid rgba(255,255,255,.06);
  background:rgba(255,255,255,.03);
  border-radius:22px;
  padding:16px;
}}
.chip {{ display:inline-flex; padding:8px 12px; border-radius:999px; background:rgba(255,255,255,.06); color:var(--muted); margin:0 8px 8px 0; }}
.list-item {{
  display:flex; justify-content:space-between; gap:12px; padding:12px 0; border-bottom:1px solid rgba(255,255,255,.06);
}}
.list-item:last-child {{ border-bottom:none; }}
.score-up {{ color:var(--green); }}
.score-mid {{ color:var(--gold); }}
.ops-grid .ops-card strong {{ display:block; font-size:24px; margin:8px 0; }}
.footer {{
  padding:24px 0 44px; color:var(--muted); display:flex; justify-content:space-between; gap:16px; flex-wrap:wrap;
}}
@media (max-width: 1080px) {{
  .hero, .workspace-preview, .feature-grid, .metric-grid, .social-grid, .guides-grid, .ops-grid {{
    grid-template-columns:1fr;
  }}
  .hero-main h1 {{ font-size:42px; }}
}}
</style>
</head>
<body>
  <div class="shell">
    <nav class="nav">
      <div>
        <span class="eyebrow">StockNewsBR</span>
      </div>
      <div class="nav-links">
        <a href="/public/pricing">Precos</a>
        <a href="/public/help-center">Ajuda</a>
        <a href="/public/disclosure">Disclosure</a>
        <a href="/web/terminal/ui">Workspace</a>
      </div>
    </nav>

    <section class="hero">
      <div class="hero-card hero-main">
        <span class="eyebrow">Google App + Web + Telegram</span>
        <h1>Ferramenta institucional para traders que querem IA, comunidade e execucao no mesmo lugar.</h1>
        <p>StockNewsBR junta radar, heat map, ticker rooms, grafico com overlays de compra e venda, polls semanais, feed social e alertas em um ecossistema premium desenhado para o trader brasileiro.</p>
        <div class="cta-row">
          <a class="cta primary" href="/public/pricing">Assinar Premium</a>
          <a class="cta secondary" href="/site/workspace">Explorar o website</a>
        </div>
        <div class="metric-grid" style="margin-top:22px;">
          <div class="metric"><span>Trial inicial</span><strong>{pricing.get('trial_days', 90)} dias</strong><span>Depois vai automaticamente para a conta basica/free.</span></div>
          <div class="metric"><span>Mensal Premium</span><strong>R$ {pricing.get('premium_monthly', {}).get('price_brl', 49)}</strong><span>App Google + website + Telegram.</span></div>
          <div class="metric"><span>Anual Premium</span><strong>R$ {pricing.get('premium_annual', {}).get('price_brl', 500)}</strong><span>Desenhado para retention e uso diario.</span></div>
        </div>
      </div>
      <aside class="hero-card hero-side">
        <div class="metric"><span>Roadmap atual</span><strong>{bootstrap.get('launch_roadmap', {}).get('current', 'google_app')}</strong><span>{bootstrap.get('launch_roadmap', {}).get('summary', 'Android primeiro, Apple depois.')}</span></div>
        <div class="metric"><span>Videos de ajuda</span><strong>{help_center.get('video_status', {}).get('available_videos', 0)}/{help_center.get('video_status', {}).get('planned_videos', 0)}</strong><span>{help_center.get('video_status', {}).get('next_step', '')}</span></div>
        <div class="metric"><span>Infra</span><strong>{storage.get('provider', 'local').upper()}</strong><span>Upload/CDN: {'pronto' if media.get('cdn_ready') else 'em configuracao'} | Push Android: {'pronto' if push.get('android_ready') else 'pendente'}</span></div>
      </aside>
    </section>

    <section class="section">
      <h2>Mais util que Stocktwits porque a conversa nao vive separada da execucao.</h2>
      <p class="lead">Aqui o feed conversa com o ranking, o ranking conversa com o grafico, o grafico conversa com os alerts e a comunidade opera em ticker rooms com IA e contexto institucional.</p>
      <div class="workspace-preview panel">
        <div class="rail">
          <span class="eyebrow">Modulos</span>
          <div style="margin-top:12px;">
            <div class="chip">IA Heat Map</div>
            <div class="chip">IA Radar</div>
            <div class="chip">Master Score</div>
            <div class="chip">Grafico IA</div>
            <div class="chip">Ticker Rooms</div>
            <div class="chip">Ajuda Friendly</div>
          </div>
        </div>
        <div class="center">
          <div class="list-item"><div><strong>Workspace multi-monitor</strong><div style="color:var(--muted);">Arraste abas, desacople paines e salve seu layout.</div></div><div class="score-up">AO VIVO</div></div>
          <div class="list-item"><div><strong>Grafico com overlay</strong><div style="color:var(--muted);">Zonas, marcadores BUY/SELL e bias operacional.</div></div><div class="score-mid">PRONTO</div></div>
          <div class="list-item"><div><strong>Ticker room realtime</strong><div style="color:var(--muted);">Mensagens, imagem, like e comunidade por ativo.</div></div><div class="score-up">ATIVO</div></div>
        </div>
        <div class="right">
          <span class="eyebrow">Diferencial</span>
          <p style="color:var(--muted); margin-top:12px;">Nao e uma rede social vazia. E uma mesa operacional acessivel para todos, com IA, scan institucional e jornada completa de descoberta, estudo e execucao.</p>
        </div>
      </div>
    </section>

    <section class="section">
      <h2>Motor de IA institucional</h2>
      <p class="lead">Arquitetura pronta para mercado, eventos, fluxo, probabilidade de breakout, regime, liquidez e score mestre.</p>
      <div class="feature-grid">{feature_cards}</div>
    </section>

    <section class="section">
      <h2>Social que segura o trader dentro do produto</h2>
      <p class="lead">Comentarios por ticker, likes, bloqueio, moderacao, upload de imagem, polls semanais e rooms em tempo real.</p>
      <div class="social-grid">{social_cards}</div>
    </section>

    <section class="section">
      <h2>Ajuda amigavel com exemplos e videos</h2>
      <p class="lead">A plataforma nasce com onboarding em portugues, explicando cada ferramenta com passo a passo simples para o trader entender rapido.</p>
      <div class="guides-grid">{guide_cards}</div>
    </section>

    <section class="section">
      <h2>Operacao pronta para escala</h2>
      <p class="lead">Upload/CDN, push mobile, observabilidade, websocket e moderacao entram como parte do produto, nao como remendo.</p>
      <div class="ops-grid">
        <article class="ops-card"><span class="eyebrow">Upload</span><h3>Storage + CDN</h3><strong>{storage.get('provider', 'local').upper()}</strong><p>{media.get('next_step', '')}</p></article>
        <article class="ops-card"><span class="eyebrow">Push</span><h3>Android / Apple</h3><strong>{'Android pronto' if push.get('android_ready') else 'Configurar Firebase'}</strong><p>{push.get('next_step', '')}</p></article>
        <article class="ops-card"><span class="eyebrow">Ajuda</span><h3>Biblioteca de videos</h3><strong>{help_center.get('video_status', {}).get('available_videos', 0)} videos</strong><p>{help_center.get('video_status', {}).get('next_step', '')}</p></article>
      </div>
    </section>

    <footer class="footer">
      <span>www.stocknewsbr.com</span>
      <span>StockNewsBR 2026 | Android-first, Apple em seguida</span>
    </footer>
  </div>
</body>
</html>
"""
