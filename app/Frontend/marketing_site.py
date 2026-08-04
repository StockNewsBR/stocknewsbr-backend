from app.services.help_center_service import get_help_center_blueprint
from app.services.legal_service import get_public_bootstrap
from app.services.media_service import get_media_status
from app.services.push_service import get_push_status
from app.services.storage_service import get_storage_status
from app.system.system_metrics import get_metrics_snapshot


def _join(items):
    return "".join(items)


def _metric_cards(metrics):
    return _join(
        f"""
        <article class="stat">
          <span>{label}</span>
          <strong>{value}</strong>
          <p>{description}</p>
        </article>
        """
        for label, value, description in metrics
    )


def _feature_cards():
    cards = [
        ("Score Mestre", "Resumo operacional", "Transforma 9 IAs e o Auditor em uma leitura única para decidir mais rápido."),
        ("Auditor Institucional", "Filtro obrigatório", "Bloqueia conflitos e reduz o ruído antes que o cenário chegue ao trader."),
        ("Ranking", "Onde olhar", "Mostra as melhores oportunidades por leitura institucional, risco e contexto."),
        ("Radar", "O que vem antes", "Ajuda a perceber compressão, gatilho e preparação sem disparar trade sozinho."),
        ("Telegram", "Alerta direto", "Entrega o resumo do mercado no canal certo sem exigir abrir várias telas."),
    ]
    return _join(
        f"""
        <article class="feature">
          <div class="icon">{index + 1:02d}</div>
          <h3>{title}</h3>
          <strong>{headline}</strong>
          <p>{body}</p>
        </article>
        """
        for index, (title, headline, body) in enumerate(cards)
    )


def _faq_cards():
    faqs = [
        ("O que e o Score Mestre?", "E a sintese institucional do produto. Ele resume contexto, direcao, conviccao e risco em uma leitura unica."),
        ("O que e o Auditor?", "E a camada de protecao que impede conflito institucional e sinal ruim de virar decisao operacional."),
        ("O que significa NAO OPERAR AGORA?", "Significa que a leitura ainda nao tem contexto suficiente ou esta bloqueada por risco, qualidade de dados ou conflito."),
        ("Como funciona o Telegram?", "Ele recebe o resumo do mercado e os alertas institucionais sem depender de varias telas abertas."),
    ]
    return _join(
        f"""
        <details class="faq">
          <summary>{question}</summary>
          <p>{answer}</p>
        </details>
        """
        for question, answer in faqs
    )


def get_marketing_site():
    bootstrap = get_public_bootstrap()
    help_center = get_help_center_blueprint()
    media = get_media_status()
    push = get_push_status()
    storage = get_storage_status()
    metrics = get_metrics_snapshot()

    pricing = bootstrap.get("pricing", {})
    roadmap = bootstrap.get("launch_roadmap", {})
    help_guides = help_center.get("guides", [])[:3]

    stats = _metric_cards(
        [
            ("Sinais gerados", f"{metrics.get('signals_generated', 0)}", "Volume operacional do motor e do snapshot."),
            ("Ciclos executados", f"{metrics.get('engine_cycles', 0)}", "Ritmo de processamento do sistema."),
            ("Uptime", f"{round((metrics.get('uptime_seconds', 0) or 0) / 3600, 1)}h", "Tempo online da infraestrutura."),
            ("Scan médio", f"{metrics.get('scan_time', 0)}s", "Leitura média por ciclo do backend."),
        ]
    )

    feature_cards = _feature_cards()
    faq_cards = _faq_cards()
    help_cards = _join(
        f"""
        <article class="help-card">
          <span>Ajuda</span>
          <h3>{guide.get('title', '')}</h3>
          <p>{guide.get('tagline', '') or guide.get('description', '')}</p>
        </article>
        """
        for guide in help_guides
    )

    plan_cards = _join(
        f"""
        <article class="plan {class_name}">
          <span>{label}</span>
          <h3>{title}</h3>
          <strong>{price}</strong>
          <p>{description}</p>
        </article>
        """
        for class_name, label, title, price, description in [
            ("free", "Gratuito", "Gratuito", f"{pricing.get('trial_days', 30)} dias", "Entrada para conhecer a leitura institucional e o fluxo do produto."),
            ("pro", "Pro", "Pro", "Premium", "Para quem quer workspace completo, Telegram e continuidade diária."),
            ("institutional", "Institucional", "Institucional", "Futuro", "Estrutura preparada para times e uso avançado."),
        ]
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
  --bg:#071119;
  --bg-soft:#0d1822;
  --panel:#101f2d;
  --line:rgba(255,255,255,.08);
  --text:#edf5fb;
  --muted:#95a8ba;
  --green:#24d18a;
  --gold:#f0b84f;
  --cyan:#69c6ff;
  --red:#ff6f6f;
}}
* {{ box-sizing:border-box; }}
html {{ scroll-behavior:smooth; }}
body {{
  margin:0;
  color:var(--text);
  background:
    radial-gradient(circle at 15% 10%, rgba(36,209,138,.14), transparent 24%),
    radial-gradient(circle at 92% 0%, rgba(105,198,255,.12), transparent 22%),
    linear-gradient(180deg, #061019 0%, #08131e 100%);
  font-family: Inter, Segoe UI, Arial, sans-serif;
}}
a {{ color:inherit; text-decoration:none; }}
.shell {{ width:min(1220px, calc(100vw - 32px)); margin:0 auto; }}
.topbar {{
  position:sticky; top:0; z-index:5;
  display:flex; align-items:center; justify-content:space-between; gap:16px;
  padding:18px 0; backdrop-filter:blur(18px);
}}
.brand {{
  display:flex; flex-direction:column; gap:4px;
}}
.brand strong {{ font-size:18px; letter-spacing:.02em; }}
.brand span {{ color:var(--muted); font-size:13px; }}
.nav {{ display:flex; flex-wrap:wrap; gap:10px; }}
.nav a {{
  padding:10px 14px;
  border-radius:999px;
  background:rgba(255,255,255,.04);
  border:1px solid var(--line);
  color:var(--muted);
}}
.hero {{
  padding:24px 0 18px;
  display:grid;
  grid-template-columns:1.35fr .95fr;
  gap:18px;
}}
.panel {{
  border:1px solid var(--line);
  background:linear-gradient(180deg, rgba(17,33,48,.94), rgba(10,22,34,.94));
  border-radius:26px;
  box-shadow:0 24px 70px rgba(0,0,0,.28);
}}
.hero-main {{ padding:32px; }}
.eyebrow {{
  display:inline-flex; align-items:center; gap:8px;
  padding:8px 12px; border-radius:999px;
  background:rgba(36,209,138,.12);
  color:var(--green); font-size:12px; text-transform:uppercase; letter-spacing:.08em;
}}
.hero-main h1 {{
  margin:16px 0 12px;
  font-size:clamp(42px, 5vw, 68px);
  line-height:1.02;
  letter-spacing:-.03em;
}}
.hero-main p {{
  margin:0;
  color:var(--muted);
  font-size:18px;
  line-height:1.6;
  max-width:760px;
}}
.cta-row {{ display:flex; flex-wrap:wrap; gap:12px; margin-top:22px; }}
.cta {{
  display:inline-flex; align-items:center; justify-content:center;
  min-height:50px; padding:0 18px;
  border-radius:16px; font-weight:700;
  border:1px solid var(--line);
}}
.cta.primary {{ background:linear-gradient(90deg, var(--green), #71edbc); color:#041017; }}
.cta.secondary {{ background:rgba(255,255,255,.04); }}
.hero-side {{ padding:22px; display:grid; gap:12px; }}
.hero-side .stat strong {{ font-size:28px; }}
.section {{ padding:14px 0 18px; }}
.section h2 {{ margin:0 0 8px; font-size:34px; line-height:1.08; }}
.section p.lead {{ margin:0 0 18px; color:var(--muted); line-height:1.6; max-width:860px; }}
.grid {{ display:grid; gap:14px; }}
.stats {{ grid-template-columns:repeat(4, minmax(0,1fr)); }}
.features {{ grid-template-columns:repeat(5, minmax(0,1fr)); }}
.plans {{ grid-template-columns:repeat(3, minmax(0,1fr)); }}
.help {{ grid-template-columns:repeat(3, minmax(0,1fr)); }}
.stat, .feature, .plan, .help-card, .faq, .proof, .flow {{
  background:rgba(255,255,255,.04);
  border:1px solid rgba(255,255,255,.06);
  border-radius:22px;
  padding:18px;
}}
.stat span, .feature p, .plan p, .help-card p, .proof p, .flow p, .faq p {{
  color:var(--muted);
  line-height:1.5;
}}
.stat strong {{
  display:block;
  font-size:28px;
  margin:6px 0;
}}
.feature .icon {{
  width:38px; height:38px; border-radius:12px;
  display:flex; align-items:center; justify-content:center;
  background:rgba(36,209,138,.12); color:var(--green); font-weight:800;
}}
.feature h3, .plan h3, .help-card h3 {{
  margin:12px 0 8px;
  font-size:18px;
}}
.feature strong {{
  display:block;
  color:var(--text);
  font-size:15px;
  margin-bottom:8px;
  line-height:1.35;
}}
.flow-wrap {{
  display:grid;
  grid-template-columns:1fr auto 1fr;
  gap:12px;
  align-items:center;
}}
.flow {{
  text-align:center;
}}
.arrow {{
  font-size:28px;
  color:var(--muted);
  text-align:center;
}}
.proof-grid {{
  display:grid;
  grid-template-columns:repeat(4, minmax(0,1fr));
  gap:14px;
}}
.faq-wrap {{
  display:grid;
  gap:12px;
}}
.faq summary {{
  cursor:pointer;
  font-weight:700;
  list-style:none;
}}
.faq summary::-webkit-details-marker {{ display:none; }}
.footer {{
  padding:26px 0 40px;
  display:flex;
  flex-wrap:wrap;
  justify-content:space-between;
  gap:14px;
  color:var(--muted);
}}
@media (max-width: 1060px) {{
  .hero, .stats, .features, .plans, .help, .proof-grid, .flow-wrap {{
    grid-template-columns:1fr;
  }}
  .hero-main h1 {{ font-size:40px; }}
}}
</style>
</head>
<body>
  <div class="shell">
    <header class="topbar">
      <div class="brand">
        <strong>StockNewsBR</strong>
        <span>Transforme complexidade institucional em decisao simples.</span>
      </div>
      <nav class="nav" aria-label="Navegacao principal">
        <a href="#diferenciais">Diferenciais</a>
        <a href="#como-funciona">Como funciona</a>
        <a href="#planos">Planos</a>
        <a href="#faq">FAQ</a>
        <a href="/web/terminal/ui">Workspace</a>
      </nav>
    </header>

    <section class="hero">
      <div class="panel hero-main">
        <span class="eyebrow">Produto institucional para trader profissional</span>
        <h1>Transforme complexidade institucional em decisao simples.</h1>
        <p>Fluxo, liquidez, smart money, noticias e contexto de mercado analisados para voce, com Score Mestre, Auditor Institucional, Radar e Ranking unidos em uma leitura que cabe em poucos segundos.</p>
        <div class="cta-row">
          <a class="cta primary" href="/web/terminal/ui">Testar Gratuitamente</a>
          <a class="cta secondary" href="/web/terminal/ui#rankings">Ver Oportunidades</a>
          <a class="cta secondary" href="/web/terminal/ui#ticker-rooms">Entrar no Telegram</a>
        </div>
        <div class="grid stats" style="margin-top:22px;">
          {stats}
        </div>
      </div>
      <aside class="panel hero-side">
        <div class="stat">
          <span>Trial no lancamento</span>
          <strong>30 dias</strong>
          <p>Oferta inicial para a primeira onda de usuarios.</p>
        </div>
        <div class="stat">
          <span>Trial para novos usuarios</span>
          <strong>15 dias</strong>
          <p>Concede uma entrada rapida para novos cadastros apos o lancamento.</p>
        </div>
        <div class="stat">
          <span>Plano atual</span>
          <strong>{roadmap.get('current', 'google_app')}</strong>
          <p>{roadmap.get('summary', 'App, web e Telegram prontos para consumo.')}</p>
        </div>
      </aside>
    </section>

    <section class="section" id="diferenciais">
      <h2>Diferenciais que ajudam a vender o produto sem vender promessa vazia.</h2>
      <p class="lead">O visitante entende rapido o que e, para quem serve, qual problema resolve e por que o fluxo institucional e mais confiavel do que uma colecao de cards soltos.</p>
      <div class="grid features">
        {feature_cards}
      </div>
    </section>

    <section class="section" id="como-funciona">
      <h2>Como funciona</h2>
      <p class="lead">O fluxo visual deixa claro que a decisao nasce de leitura institucional e nao de indicadores isolados.</p>
      <div class="flow-wrap">
        <div class="flow"><strong>Mercado</strong><p>Preco, volume, contexto e noticia entram primeiro.</p></div>
        <div class="arrow">↓</div>
        <div class="flow"><strong>9 IAs + Auditor + Score Mestre + Painel</strong><p>O sistema sintetiza, bloqueia conflito e simplifica a leitura.</p></div>
        <div class="arrow">↓</div>
        <div class="flow"><strong>Radar / Ranking / Telegram</strong><p>O trader recebe o resumo do que merece atencao agora.</p></div>
      </div>
    </section>

    <section class="section" id="planos">
      <h2>Planos</h2>
      <p class="lead">Estrutura preparada para lancamento, sem cobrar aqui e sem esconder a hierarquia de acesso.</p>
      <div class="grid plans">
        {plan_cards}
      </div>
    </section>

    <section class="section">
      <h2>Prova social sem inventar numero</h2>
      <p class="lead">A vitrine pode usar metrica real do sistema quando existir. Se nao houver, o layout continua limpo e honesto.</p>
      <div class="grid proof-grid">
        <article class="proof"><span>Metrica real</span><strong>{metrics.get('signals_generated', 0)}</strong><p>Sinais gerados pelo motor.</p></article>
        <article class="proof"><span>Metrica real</span><strong>{metrics.get('engine_cycles', 0)}</strong><p>Ciclos executados pelo worker.</p></article>
        <article class="proof"><span>Metrica real</span><strong>{metrics.get('assets_scanned', 0)}</strong><p>Ativos processados no pipeline.</p></article>
        <article class="proof"><span>Metrica real</span><strong>{metrics.get('http_requests', 0)}</strong><p>Uso real da interface web.</p></article>
      </div>
    </section>

    <section class="section">
      <h2>Ajuda e onboarding</h2>
      <p class="lead">Glossario, filosofia oficial e Help Center entram como apoio direto ao produto.</p>
      <div class="grid help">
        {help_cards}
      </div>
    </section>

    <section class="section" id="faq">
      <h2>FAQ</h2>
      <p class="lead">Respostas diretas para reduzir atrito na primeira visita.</p>
      <div class="faq-wrap">
        {faq_cards}
      </div>
    </section>

    <section class="section">
      <div class="panel" style="padding:22px; display:grid; gap:12px;">
        <span class="eyebrow">CTA</span>
        <h2 style="margin:0;">Pronto para testar o produto?</h2>
        <p class="lead" style="margin:0;">Entre pelo workspace, veja oportunidades e use o Telegram como extensao da mesa de decisao.</p>
        <div class="cta-row">
          <a class="cta primary" href="/web/terminal/ui">Testar Gratuitamente</a>
          <a class="cta secondary" href="/web/terminal/ui#rankings">Ver Oportunidades</a>
          <a class="cta secondary" href="/web/terminal/ui#ticker-rooms">Entrar no Telegram</a>
        </div>
      </div>
    </section>

    <footer class="footer">
      <span>www.stocknewsbr.com</span>
      <span>Web, app e Telegram com leitura institucional pronta para lancamento</span>
      <span>Upload: {storage.get('provider', 'local')} | Push: {'pronto' if push.get('android_ready') else 'pendente'} | CDN: {'pronta' if media.get('cdn_ready') else 'pendente'}</span>
    </footer>
  </div>
</body>
</html>
"""
