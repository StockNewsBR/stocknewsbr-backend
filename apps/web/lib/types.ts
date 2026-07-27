export type WorkspaceTab = {
  id: string;
  title: string;
  icon?: string;
  route?: string;
  popout_route?: string;
  detachable?: boolean;
  monitor_ready?: boolean;
};

export type StrategicPanelBlock = Record<string, unknown> & {
  title?: string;
};

export type StrategicPanelWhyItem = {
  tool?: string;
  label?: string;
  source?: string;
  symbol?: string | null;
  reason?: string;
};

export type StrategicPanel = {
  ticker?: string;
  symbol?: string;
  strategic_panel_version?: string;
  master_score_block?: StrategicPanelBlock;
  auditor_block?: StrategicPanelBlock;
  risk_block?: StrategicPanelBlock & {
    level?: string;
    visual_level?: string;
    source?: string;
    score?: number | null;
    summary?: string | null;
  };
  probable_direction_block?: StrategicPanelBlock & {
    direction?: string;
    label?: string;
    visual_label?: string;
  };
  recommended_action_block?: StrategicPanelBlock & {
    action?: string;
    no_trade_now?: boolean;
    reasons?: string[];
  };
  recommended_action?: string;
  liquidez_alvo?: number | null;
  strategic_panel_summary?: string;
  llm_conclusion?: string | null;
  why?: StrategicPanelWhyItem[];
  opinion_change_conditions?: string[];
  no_trade_now?: boolean;
  no_trade_reasons?: string[];
  source_contracts?: string[];
  blocks?: StrategicPanelBlock[];
  canonical_analysis?: CanonicalAnalysis | null;
};

export type CanonicalAnalysis = {
  version?: string;
  direction: "BULLISH" | "BEARISH" | "NEUTRAL";
  decision: "READY" | "NO_TRADE" | "BLOCKED" | "STALE_DATA" | "INSUFFICIENT_DATA" | "CONFLICT" | "ERROR";
  suggested_trade: "BUY" | "SELL" | "SHORT" | "COVER" | "NO_TRADE";
  regime: "BULL_TREND" | "BEAR_TREND" | "RANGE" | "HIGH_VOLATILITY" | "UNKNOWN";
  bias: "BULLISH" | "BEARISH" | "NEUTRAL" | "CONFLICT";
  conclusion?: "OPPORTUNITY_CONFIRMED" | "OPPORTUNITY_FORMING" | "OBSERVE" | "WAIT" | "NO_TRADE" | "CONFLICT";
  validation_status?: "VALID" | "NORMALIZED" | "REJECTED";
  validation_reasons?: string[];
  status?: "READY" | "BLOCKED" | "NO_TRADE" | "CONFLICT" | string;
  reason?: string | null;
  conclusion_key?: string | null;
};

export type DecisionEnvelope = {
  symbol?: string;
  canonical_symbol?: string | null;
  action?: string | null;
  decision_status?: "READY" | "BLOCKED" | "NO_TRADE" | "STALE_DATA" | "INSUFFICIENT_DATA" | "CONFLICT" | "ERROR" | string;
  decision_ready?: boolean;
  confidence?: number | null;
  master_score?: number | null;
  master_score_raw?: number | null;
  data_quality?: string | null;
  blockers?: string[];
  warnings?: string[];
  reasons?: string[];
  invalidation_reason?: string | null;
  market_context?: Record<string, unknown>;
  timestamp?: string | number | null;
  source_snapshot_id?: string | number | null;
  human_message?: string | null;
  operational_status?: string | null;
  auditor_status?: string | null;
  auditor_blocked?: boolean;
  risk_level?: string | null;
  regime?: string | null;
  price_valid?: boolean;
  volume_valid?: boolean;
  stale?: boolean;
  source?: string | null;
};

export type RankingRow = {
  symbol: string;
  score: number;
  source_score?: number | string | null;
  master_score?: number | null;
  master_direction?: "BULLISH" | "BEARISH" | "NEUTRAL" | string | null;
  master_conviction?: string | null;
  master_confidence?: string | null;
  master_summary?: string | null;
  master_reasoning?: Record<string, unknown> | null;
  master_risk?: string | null;
  master_status?: "APPROVED" | "CAUTION" | "BLOCKED" | string | null;
  master_visual_status?: string | null;
  master_visual_label?: string | null;
  opinion_change_conditions?: string[] | null;
  strategic_panel?: StrategicPanel | null;
  strategic_panel_summary?: string | null;
  recommended_action?: string | null;
  ranking_opportunity_score?: number | null;
  ranking_classification?: string | null;
  ranking_reason?: string | null;
  ranking_summary?: string | null;
  ranking_eligible?: boolean | null;
  ranking_excluded_reasons?: string[] | null;
  historical_confidence_score?: number | null;
  historical_confidence_label?: string | null;
  historical_sample_size?: number | null;
  historical_win_rate?: number | null;
  historical_context_match?: number | null;
  historical_reason?: string | null;
  historical_warning?: string | null;
  operational_status?: string | null;
  operational_ready?: boolean | null;
  operational_score?: number | null;
  operational_blocks?: string[] | null;
  operational_warnings?: string[] | null;
  operational_summary?: string | null;
  conviction_score?: number | null;
  conviction_level?: string | null;
  conviction_summary?: string | null;
  conviction_factors?: string[] | null;
  conviction_conflicts?: string[] | null;
  priority_score?: number | null;
  priority_level?: string | null;
  priority_rank?: number | null;
  priority_summary?: string | null;
  priority_factors?: string[] | null;
  final_decision?: string | null;
  final_decision_score?: number | null;
  final_decision_summary?: string | null;
  final_decision_reason?: string | null;
  final_decision_blocks?: string[] | null;
  final_decision_confidence?: string | null;
  radar_score?: number | null;
  radar_prioritization_score?: number | null;
  radar_priority_score?: number | null;
  radar_priority?: string | null;
  radar_level?: string | null;
  radar_reason?: string | null;
  radar_summary?: string | null;
  radar_no_trade_now?: boolean | null;
  radar_blocked_reasons?: string[] | null;
  radar_discarded?: boolean | null;
  trend?: string | null;
  rsi?: number | string | null;
  rel_volume?: number | string | null;
  breakout?: boolean;
  price?: number | null;
  close?: number | null;
  last_price?: number | null;
  change?: number | string | null;
  change_pct?: number | string | null;
  volume?: number | string | null;
  avg_volume?: number | string | null;
  average_volume?: number | string | null;
  vwap?: number | string | null;
  macd?: number | string | null;
  macd_signal?: number | string | null;
  macd_histogram?: number | string | null;
  data_quality?: string | null;
  signal?: string | null;
  trade_action?: string | null;
  decision_ready?: boolean | null;
  decision_status?: DecisionEnvelope["decision_status"] | null;
  decision_envelope?: DecisionEnvelope | null;
  market_data_updated_at?: string | number | null;
  last_bar_at?: string | number | null;
  quote_time?: string | number | null;
  provider_timestamp?: string | number | null;
  blocked_reasons?: string[] | string | null;
  warnings?: string[] | string | null;
  audit_status?: string | null;
  audit_score?: number | null;
  audit_confidence?: string | null;
  audit_summary?: string | null;
  audit_blocks?: string[] | null;
  audit_warnings?: string[] | null;
  auditor_approved?: boolean | null;
  blocked_by_auditor?: boolean | null;
};

export type SignalRow = {
  ticker?: string;
  symbol?: string;
  score?: number;
  master_score?: number | null;
  master_direction?: "BULLISH" | "BEARISH" | "NEUTRAL" | string | null;
  master_conviction?: string | null;
  master_confidence?: string | null;
  master_summary?: string | null;
  master_reasoning?: Record<string, unknown> | null;
  master_risk?: string | null;
  master_status?: "APPROVED" | "CAUTION" | "BLOCKED" | string | null;
  master_visual_status?: string | null;
  master_visual_label?: string | null;
  opinion_change_conditions?: string[] | null;
  strategic_panel?: StrategicPanel | null;
  strategic_panel_summary?: string | null;
  recommended_action?: string | null;
  ranking_opportunity_score?: number | null;
  ranking_classification?: string | null;
  ranking_reason?: string | null;
  ranking_summary?: string | null;
  ranking_eligible?: boolean | null;
  ranking_excluded_reasons?: string[] | null;
  historical_confidence_score?: number | null;
  historical_confidence_label?: string | null;
  historical_sample_size?: number | null;
  historical_win_rate?: number | null;
  historical_context_match?: number | null;
  historical_reason?: string | null;
  historical_warning?: string | null;
  operational_status?: string | null;
  operational_ready?: boolean | null;
  operational_score?: number | null;
  operational_blocks?: string[] | null;
  operational_warnings?: string[] | null;
  operational_summary?: string | null;
  conviction_score?: number | null;
  conviction_level?: string | null;
  conviction_summary?: string | null;
  conviction_factors?: string[] | null;
  conviction_conflicts?: string[] | null;
  priority_score?: number | null;
  priority_level?: string | null;
  priority_rank?: number | null;
  priority_summary?: string | null;
  priority_factors?: string[] | null;
  final_decision?: string | null;
  final_decision_score?: number | null;
  final_decision_summary?: string | null;
  final_decision_reason?: string | null;
  final_decision_blocks?: string[] | null;
  final_decision_confidence?: string | null;
  radar_score?: number | null;
  radar_prioritization_score?: number | null;
  radar_priority_score?: number | null;
  radar_priority?: string | null;
  radar_level?: string | null;
  radar_reason?: string | null;
  radar_summary?: string | null;
  radar_no_trade_now?: boolean | null;
  radar_blocked_reasons?: string[] | null;
  radar_discarded?: boolean | null;
  trend?: string | null;
  breakout?: boolean;
  price?: number | null;
  close?: number | null;
  last_price?: number | null;
  change?: number | string | null;
  change_pct?: number | string | null;
  volume?: number | string | null;
  avg_volume?: number | string | null;
  average_volume?: number | string | null;
  rel_volume?: number | string | null;
  vwap?: number | string | null;
  rsi?: number | string | null;
  macd?: number | string | null;
  macd_signal?: number | string | null;
  macd_histogram?: number | string | null;
  data_quality?: string | null;
  signal?: string | null;
  trade_action?: string | null;
  decision_ready?: boolean | null;
  decision_status?: DecisionEnvelope["decision_status"] | null;
  decision_envelope?: DecisionEnvelope | null;
  market_data_updated_at?: string | number | null;
  last_bar_at?: string | number | null;
  quote_time?: string | number | null;
  provider_timestamp?: string | number | null;
  blocked_reasons?: string[] | string | null;
  warnings?: string[] | string | null;
  audit_status?: string | null;
  audit_score?: number | null;
  audit_confidence?: string | null;
  audit_summary?: string | null;
  audit_blocks?: string[] | null;
  audit_warnings?: string[] | null;
  auditor_approved?: boolean | null;
  blocked_by_auditor?: boolean | null;
};

export type WorkspaceSymbolSnapshot = Partial<RankingRow & SignalRow> & Record<string, unknown>;

export type WorkspaceMarketSnapshot = {
  schema_version?: string;
  generated_at?: string | null;
  source?: string | null;
  stale?: boolean;
  market_snapshot_interval_seconds?: number;
  ai_snapshot_interval_seconds?: number;
  stats?: Record<string, unknown>;
  data_status?: Record<string, unknown>;
  market_pulse?: Record<string, unknown>;
  auditor?: Record<string, unknown>;
  institutional_auditor?: Record<string, unknown>;
  master_score?: Record<string, unknown>;
  master_scores?: Record<string, unknown>[];
  strategic_panel?: StrategicPanel;
  strategic_panels?: StrategicPanel[];
  strategic_panel_summary?: string;
  institutional_radar?: SignalRow[];
  radar_metrics?: Record<string, number>;
  institutional_ranking?: SignalRow[];
  ranking_metrics?: Record<string, number>;
  historical_confidence?: Record<string, unknown>;
  historical_confidences?: SignalRow[];
  historical_confidence_metrics?: Record<string, unknown>;
  operational_rules?: SignalRow[];
  operational_rules_metrics?: Record<string, unknown>;
  institutional_convictions?: SignalRow[];
  conviction_metrics?: Record<string, unknown>;
  institutional_priorities?: SignalRow[];
  priority_metrics?: Record<string, unknown>;
  final_decisions?: SignalRow[];
  final_decision_metrics?: Record<string, unknown>;
  decision_envelope?: DecisionEnvelope;
  decision_envelopes?: DecisionEnvelope[];
  symbol_count?: number;
};

export type AiToolMetrics = Record<string, string | number | boolean | null>;

export type AiToolRow = {
  ticker: string;
  name: string;
  tool: string;
  score: number;
  signal: string;
  state: string;
  confidence: number;
  price?: number | null;
  change_pct?: number | null;
  volume?: number | null;
  rel_volume?: number | null;
  vwap?: number | null;
  rsi?: number | null;
  adx?: number | null;
  atr_pct?: number | null;
  metrics?: AiToolMetrics;
  ai_comment?: string;
  trigger?: string;
  invalidation?: string;
  market_data_updated_at?: string | number | null;
  published_at?: string | number | null;
  news_published_at?: string | number | null;
  provider_publish_time?: string | number | null;
  last_bar_at?: string | number | null;
  bar_time?: string | number | null;
  time?: string | number | null;
  timestamp?: string | number | null;
  quote_time?: string | number | null;
  provider_timestamp?: string | number | null;
  created_at?: string | number | null;
  found_at?: string | number | null;
  first_seen_at?: string | number | null;
  updated_at?: string;
  detected_at?: string;
  last_seen_at?: string;
  source_as_of?: string | null;
  evaluated_at?: string | null;
  freshness_status?: string | null;
  freshness_basis?: string | null;
  freshness_reason?: string | null;
  active?: boolean;
  decision_state?: string | null;
  decision_ready?: boolean | null;
  can_trade?: boolean | null;
  operational_message?: string | null;
  no_trade_reasons?: string[] | null;
  blocked_signals?: string[] | null;
  blocked_by_auditor?: boolean | null;
  audit_status?: string | null;
  audit_score?: number | null;
  auditor_score?: number | null;
  audit_confidence?: string | null;
  audit_reason?: string | null;
  audit_summary?: string | null;
  auditor_summary?: string | null;
  audit_blocks?: string[] | null;
  audit_warnings?: string[] | null;
  auditor_approved?: boolean | null;
  auditor?: Record<string, unknown> | null;
  institutional_auditor?: Record<string, unknown> | null;
  conflict_detected?: boolean | null;
  conflict_level?: string | null;
  official_ai?: boolean | null;
  internal_engines?: string[] | null;
  risk_score?: number | null;
  risk_summary?: string | null;
  risk_blocks?: string[] | null;
  no_trade_reason?: string | null;
  master_score?: number | null;
  master_direction?: "BULLISH" | "BEARISH" | "NEUTRAL" | string | null;
  master_conviction?: string | null;
  master_confidence?: string | null;
  master_summary?: string | null;
  master_reasoning?: Record<string, unknown> | null;
  master_risk?: string | null;
  master_status?: "APPROVED" | "CAUTION" | "BLOCKED" | string | null;
  master_visual_status?: string | null;
  master_visual_label?: string | null;
  opinion_change_conditions?: string[] | null;
};

export type WorkspaceAiTools = {
  flow: AiToolRow[];
  liquidity: AiToolRow[];
  trend: AiToolRow[];
  momentum: AiToolRow[];
  smart_money: AiToolRow[];
  risk: AiToolRow[];
  news: AiToolRow[];
  macro: AiToolRow[];
  regime: AiToolRow[];
};

export type PublicAiToolsPayload = {
  symbol?: string | null;
  reset_key: string;
  updated_at?: string | null;
  max_rows_per_tool: number;
  reset_hour: number;
  timezone: string;
  source?: string;
  tools: Partial<WorkspaceAiTools>;
  historical_tools?: Partial<WorkspaceAiTools>;
  selected_symbol?: string | null;
  selected_tool?: keyof WorkspaceAiTools | null;
  timeframe?: string | null;
  status?: "READY" | "PENDING" | "PENDING_EXPIRED" | "REFRESHING" | "INSUFFICIENT_DATA" | "UNSUPPORTED" | "PROVIDER_ERROR" | "HISTORICAL" | "STALE" | "EMPTY" | "NO_QUALIFIED_FINDING" | "SNAPSHOT_UNAVAILABLE" | "STALE_DATA" | "ERROR" | "KILL_SWITCHED" | string;
  reason?: string | null;
  analyzed_at?: string | null;
  displayable_count?: number;
  actionable_count?: number;
  locked?: boolean;
  access_status?: string | null;
};

export type HelpGuide = {
  slug: string;
  title: string;
  tagline?: string;
  description?: string;
  how_to_use?: string[];
  demo_video_url?: string | null;
  video_status?: string | null;
  mp4_url?: string | null;
};

export type WorkspaceLayout = {
  tabs: string[];
  pinned_ticker: string;
  opened_popouts: string[];
  chart_settings?: {
    show_markers?: boolean;
    show_zones?: boolean;
    show_price_line?: boolean;
    show_vwap?: boolean;
    show_macd?: boolean;
    show_rsi?: boolean;
    show_support?: boolean;
    show_resistance?: boolean;
    show_supertrend?: boolean;
    show_volume?: boolean;
  };
  updated_at?: number;
};

export type FeedComment = {
  id: number;
  user: string;
  user_id?: number;
  user_avatar_url?: string | null;
  text: string;
  image_url?: string | null;
  timestamp?: number;
  created_at?: string | null;
  social_guardian_score?: number | null;
  social_guardian_label?: string | null;
};

export type FeedPost = {
  id: number;
  user: string;
  user_id: number;
  user_avatar_url?: string | null;
  text: string;
  ticker?: string | null;
  sentiment?: string | null;
  image_url?: string | null;
  timestamp?: number;
  created_at?: string | null;
  likes?: number;
  liked_by_me?: boolean;
  reposts?: number;
  reposted_by_me?: boolean;
  my_repost_quote_text?: string | null;
  is_followed_by_me?: boolean;
  comments?: FeedComment[];
  discussion_relevance_score?: number;
  discussion_relevance_reason?: string[];
  social_guardian_score?: number | null;
  social_guardian_label?: string | null;
};

export type ChatMessage = {
  id: string;
  symbol: string;
  user_id: number;
  user_name: string;
  text: string;
  image_url?: string | null;
  created_at: number;
};

export type WorkspaceObservabilityDashboard = {
  system_status: string;
  providers?: {
    status?: string;
    items?: Array<{ provider?: string; status?: string }>;
    counts?: Record<string, number>;
  };
  snapshot_health?: {
    status?: string;
    signals_generated?: number;
    invalid?: number;
    discarded?: number;
    blocked?: number;
  };
  auditor_health?: {
    status?: string;
    counts?: Record<string, number>;
    blocked_ratio?: number;
  };
  score_health?: {
    status?: string;
    distribution?: Record<string, number>;
  };
  radar_health?: {
    status?: string;
    generated?: number;
    filtered?: number;
    blocked?: number;
    counts?: Record<string, number>;
  };
  ranking_health?: {
    status?: string;
    eligible?: number;
    discarded?: number;
    blocked?: number;
    counts?: Record<string, number>;
  };
  telegram_health?: {
    status?: string;
    sent?: number;
    blocked?: number;
    discarded?: number;
    errors?: number;
    counts?: Record<string, number>;
  };
  recent_errors?: Array<{ kind?: string; message?: string; severity?: string; source?: string; timestamp?: number }>;
  error_center?: {
    total?: number;
    groups?: Record<string, number>;
  };
  alerts?: Array<{ kind?: string; message?: string; severity?: string } | null>;
};

export type WorkspaceData = {
  brand: string;
  workspace_mode: string;
  tabs: WorkspaceTab[];
  top_signals: SignalRow[];
  institutional_radar?: SignalRow[];
  institutional_ranking?: SignalRow[];
  historical_confidence?: Record<string, unknown>;
  historical_confidences?: SignalRow[];
  operational_rules?: SignalRow[];
  institutional_convictions?: SignalRow[];
  institutional_priorities?: SignalRow[];
  final_decisions?: SignalRow[];
  ranking: RankingRow[];
  blocked_signals?: SignalRow[];
  symbol_snapshots?: Record<string, WorkspaceSymbolSnapshot>;
  market_snapshot?: WorkspaceMarketSnapshot;
  auditor?: Record<string, unknown>;
  institutional_auditor?: Record<string, unknown>;
  master_score?: Record<string, unknown>;
  master_scores?: Record<string, unknown>[];
  strategic_panel?: StrategicPanel;
  strategic_panels?: StrategicPanel[];
  strategic_panel_summary?: string;
  observability?: WorkspaceObservabilityDashboard;
  ai_tools: WorkspaceAiTools;
  featured_posts: FeedPost[];
  ticker_room_preview: {
    symbol: string;
    messages: ChatMessage[];
  };
  help_center: {
    guides: HelpGuide[];
    video_status?: {
      available_videos?: number;
      planned_videos?: number;
      mp4_recordings_ready?: boolean;
      next_step?: string;
    };
  };
  media: {
    provider: string;
    cdn_ready: boolean;
    next_step?: string;
  };
  push: {
    android_ready: boolean;
    apple_ready: boolean;
    next_step?: string;
    registered_tokens?: number;
  };
  pricing: {
    trial_days: number;
    premium_monthly?: { price_brl: number };
    premium_annual?: { price_brl: number };
  };
  launch_roadmap: {
    current?: string;
    next?: string;
    domain?: string;
  };
  ai_modules: string[];
  social_features: Record<string, boolean>;
  layout: WorkspaceLayout;
  status: {
    engine_cycles?: number;
    signals_generated?: number;
    assets_scanned?: number;
    cache_age?: number | null;
    snapshot_signals?: number;
    http_requests?: number;
    ws_connections?: number;
    chat_messages?: number;
    snapshot_generated_at?: string | null;
    snapshot_source?: string | null;
    snapshot_stale?: boolean;
    snapshot_actionable?: number;
    snapshot_priced?: number;
    snapshot_score_only?: number;
  };
  chart_capabilities: Record<string, boolean>;
};

export type ChartBar = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  ema9?: number;
  ema21?: number;
  supertrend?: number | null;
  supertrend_side?: "buy" | "sell" | "neutral" | string | null;
  source?: string;
};

export type ChartMarker = {
  type?: string;
  side?: "buy" | "sell" | "neutral";
  ticker?: string;
  shape?: string;
  color?: string;
  price?: number;
  time?: string;
  label?: string;
  action_label?: string;
  operational_note?: string;
  score?: number | null;
  reason?: string | null;
  reason_text?: string | null;
  trigger?: string | null;
  confirmation?: string | null;
  invalidation?: string | null;
  risk?: string | null;
  risk_level?: string | null;
  coherence_status?: string | null;
  derived?: boolean | null;
};

export type ChartZone = {
  label: string;
  price: number;
  kind?: "support" | "resistance" | string;
  symbol?: string | null;
  timeframe?: string | null;
  as_of?: string | null;
  source?: string | null;
  algorithm_version?: string | null;
  stale?: boolean;
  status?: "READY" | "INSUFFICIENT_SEPARATION" | string;
  operational?: boolean;
  micro_timeframe?: string | null;
  distance_pct?: number | null;
  atr14?: number | null;
  distance_atr?: number | null;
  strength_score?: number | null;
  touches?: number | null;
  rejections?: number | null;
};

export type ChartPayload = {
  ticker: string;
  interval: string;
  ohlc: ChartBar[];
  series: ChartBar[];
  markers: ChartMarker[];
  zones: ChartZone[];
  summary: {
    ticker?: string;
    latest_close?: number;
    trend_bias?: string;
    latest_signal?: string;
    markers?: number;
    bullish_markers?: number;
    bearish_markers?: number;
    source?: string;
    fallback?: boolean;
    synthetic?: boolean;
    interval?: string;
    as_of?: string | null;
  };
  // Mission 68: per-timeframe RSI computed on this chart's candle series.
  rsi?: number | null;
  rsi_metadata?: {
    symbol?: string;
    timeframe?: string;
    as_of?: string | null;
    source?: string;
    candle_count?: number | null;
    required_count?: number | null;
    status?: string | null;
    reason?: string | null;
  } | null;
  fallback?: boolean;
  synthetic?: boolean;
};

export type FeedPayload = {
  symbol: string;
  count: number;
  posts: FeedPost[];
  featured_posts?: FeedPost[];
  discussion_state?: {
    symbol?: string;
    status?: string;
    message?: string;
    count?: number;
    featured_count?: number;
  };
};

export type NewsItem = {
  id: string;
  ticker: string;
  title: string;
  original_title?: string | null;
  content_locale?: "pt-BR" | "en-US" | string | null;
  summary?: string;
  card_summary?: string | null;
    source: string;
    source_name?: string | null;
    source_domain?: string | null;
    url?: string | null;
    source_url?: string | null;
    published_at?: string | null;
    published_at_source?: string | null;
    detected_at?: string | null;
    fetched_at?: string | null;
    age_minutes?: number | null;
    is_today?: boolean | null;
    is_stale?: boolean | null;
    freshness_bucket?: string | null;
    freshness_label?: string | null;
    matched_symbol?: string | null;
    language?: string | null;
    relevance?: number | null;
    publication_status?: string | null;
    is_incomplete?: boolean | null;
    source_published_at?: boolean | null;
    sector?: string | null;
    industry?: string | null;
    labels?: string[];
    entities?: string[];
    related_tickers?: string[];
  impact?: string | null;
  impact_label?: string | null;
  sentiment?: string | null;
  impact_reason?: string | null;
  why_it_matters?: string | null;
  editorial?: string | null;
  market_context?: string | null;
  relevance_score?: number | null;
  ranking_score?: number | null;
  confidence_score?: number | null;
  useful?: boolean | null;
  story_key?: string | null;
  same_story_count?: number | null;
  source_count?: number | null;
  sources?: string[];
  direct_ticker_match?: boolean | null;
  directness_score?: number | null;
  ambiguity_score?: number | null;
  ambiguity_flags?: string[];
  trader_takeaway?: string | null;
};

export type NewsPayload = {
  symbol: string;
  items: NewsItem[];
  count: number;
  requested_symbol?: string;
  status?: string;
  message?: string;
  state?: Record<string, unknown>;
  scope?: Record<string, unknown>;
  report?: Record<string, unknown>;
  cache?: Record<string, unknown>;
  locale?: "pt-BR" | "en-US" | string;
};

export type PollOption = {
  key: string;
  label: string;
  votes: number;
  pct?: number;
};

export type PollPayload = {
  symbol: string;
  question?: string;
  options?: PollOption[];
  total_votes?: number;
  status?: string;
  timing_bucket?: string;
  earnings_week?: boolean;
  template_id?: string;
  context?: Record<string, unknown>;
  report?: Record<string, unknown>;
  quality?: Record<string, unknown>;
  event_type?: string | null;
  event_date?: string | null;
  event_source?: string | null;
  valid_from?: string | null;
  valid_until?: string | null;
  reason?: string | null;
};

export type GifSearchItem = {
  id: string;
  title: string;
  preview_url: string;
  media_url: string;
  width?: number | null;
  height?: number | null;
  provider?: string | null;
};

export type GifSearchPayload = {
  status: "READY" | "EMPTY" | "UNAVAILABLE" | "ERROR" | string;
  query: string;
  items: GifSearchItem[];
  reason?: string | null;
};

export type ChatHistoryPayload = {
  symbol: string;
  items: ChatMessage[];
};

export type UserAccess = {
  id: number;
  email: string;
  display_name?: string | null;
  phone?: string | null;
  avatar_url?: string | null;
  // Mission 31B.1: forge-proof identity flags from backend (the ONLY badge source).
  official?: boolean;
  verified?: boolean;
  role?: string;
  is_bot?: boolean;
  plan: string;
  plan_status: string;
  telegram_linked?: boolean;
  telegram_username?: string | null;
  session_policy?: string | null;
  otp_required_on_login?: boolean;
  access: {
    app: boolean;
    web: boolean;
    telegram: boolean;
  };
  trial_expires_at?: string | null;
  plan_expires_at?: string | null;
  subscription_provider?: string | null;
  subscription_origin?: string | null;
  subscription_product_id?: string | null;
  legal_notice_version?: string | null;
  accepted_terms_at?: string | null;
  accepted_privacy_at?: string | null;
  accepted_risk_notice_at?: string | null;
};

export type AuthFlowResponse = {
  access_token?: string | null;
  token_type?: string;
  otp_required?: boolean;
  login_token?: string | null;
  otp_expires_at?: string | null;
  session_policy?: string | null;
  channel?: string | null;
  detail?: string | null;
};

export type LoginCodeRequestResponse = {
  detail: string;
  login_token?: string | null;
  otp_expires_at?: string | null;
};

export type TelegramLinkSessionResponse = {
  link_code: string;
  deep_link?: string | null;
  bot_username?: string | null;
  expires_at: string;
  status?: string;
};

export type QuotePayload = {
  symbol: string;
  logo_url?: string | null;
  icon_url?: string | null;
  price?: number;
  change?: number;
  change_pct?: number;
  volume?: number;
  average_volume?: number;
  avg_volume?: number;
  rel_volume?: number;
  vwap?: number;
  rsi?: number;
  macd?: number;
  macd_signal?: number;
  macd_histogram?: number;
  high?: number;
  low?: number;
  source?: string;
  data_quality?: string | null;
  quote_status?: "valid" | "partial" | "empty" | "stale" | string;
  status?: string | null;
  stale?: boolean;
  core_data?: boolean | null;
  strategic_core_data?: boolean | null;
  missing_fields?: string[] | null;
  quote_missing_fields?: string[] | null;
  field_status?: Record<string, boolean> | null;
  snapshot_exists?: boolean | null;
  quote_exists?: boolean | null;
  market_data_updated_at?: string | number | null;
  quote_time?: string | number | null;
  provider_timestamp?: string | number | null;
};

export type SymbolMetricComponent = {
  symbol?: string | null;
  value?: number | string | null;
  score?: number | null;
  label?: string | null;
  status: string;
  timeframe?: string | null;
  as_of?: string | null;
  data_as_of?: string | null;
  session_date?: string | null;
  freshness_status?: string | null;
  age_sessions?: number | null;
  updated_at?: string | null;
  source?: string | null;
  reason?: string | null;
  thresholds?: Record<string, number> | null;
  side?: "BUY_SIDE" | "SELL_SIDE" | "BOTH_SIDES" | null;
  low?: number | null;
  high?: number | null;
  midpoint?: number | null;
  distance_from_price_pct?: number | null;
};

export type SymbolOperationalView = {
  symbol: string;
  canonical_symbol: string;
  timeframe: string;
  session_date?: string | null;
  as_of?: string | null;
  updated_at?: string | null;
  source?: string | null;
  timeframes?: { chart_data?: string | null; operational?: string | null; structural?: string | null };
  technical_context: {
    technical_bias?: SymbolMetricComponent;
    trend_d1: SymbolMetricComponent;
    rsi_d1: SymbolMetricComponent;
    intraday_direction_5m: SymbolMetricComponent;
    institutional_flow: SymbolMetricComponent;
  };
  operational_context: {
    volume_vs_daily_average?: SymbolMetricComponent & { ratio?: number | null; percent?: number | null; informational_only?: boolean };
    intraday_rvol?: SymbolMetricComponent & { rvol_ratio?: number | null; rvol_percent?: number | null; operational_ready?: boolean };
    rvol?: SymbolMetricComponent & { rvol_ratio?: number | null; rvol_percent?: number | null; operational_ready?: boolean };
    sentiment?: SymbolMetricComponent;
    liquidity?: SymbolMetricComponent;
    levels?: { status: string; items?: Array<Record<string, unknown>>; micro_range?: Record<string, unknown> | null; as_of?: string | null };
    master_score?: SymbolMetricComponent & { used_components?: string[]; missing_components?: string[]; data_completeness?: number | null };
  };
  pending_components: Array<{ component: string; status: string; reason?: string | null }>;
  operational_blocks: Array<{ component: string; status: string; reason?: string | null }>;
  decision: string;
  decision_reason?: string | null;
  confidence?: number | null;
  confidence_status?: string;
  conviction?: number | null;
  conviction_status?: string;
  risk?: string | null;
  levels?: Array<Record<string, unknown>>;
};

export type PublicMarketMetrics = {
  symbol: string;
  canonical_symbol: string;
  timeframe: string;
  session_date?: string | null;
  as_of?: string | null;
  status: string;
  data_quality: string;
  volume_vs_daily_average?: SymbolMetricComponent & { current_volume?: number | null; daily_average_volume?: number | null; ratio?: number | null; percent?: number | null; method?: string | null; informational_only?: boolean };
  intraday_rvol?: SymbolMetricComponent & { current_volume?: number | null; average_volume_comparable?: number | null; rvol_ratio?: number | null; rvol_percent?: number | null; method?: string | null; operational_ready?: boolean };
  rvol: SymbolMetricComponent & { current_volume?: number | null; average_volume_comparable?: number | null; rvol_ratio?: number | null; rvol_percent?: number | null; method?: string | null; operational_ready?: boolean };
  sentiment: SymbolMetricComponent & { components?: Record<string, number>; last_historical_source_at?: string | null };
  levels?: { status: string; items?: Array<Record<string, unknown>>; micro_range?: Record<string, unknown> | null; as_of?: string | null } | null;
  liquidity?: SymbolMetricComponent | null;
  operational_view?: SymbolOperationalView | null;
};

export type PublicInsightPayload = {
  symbol: string;
  score?: number | null;
  master_score?: number | null;
  master_direction?: string | null;
  master_conviction?: string | null;
  master_confidence?: string | null;
  master_summary?: string | null;
  master_reasoning?: Record<string, unknown> | null;
  master_risk?: string | null;
  master_status?: string | null;
  opinion_change_conditions?: string[] | null;
  strategic_panel?: StrategicPanel | null;
  strategic_panel_summary?: string | null;
  recommended_action?: string | null;
  historical_confidence_score?: number | null;
  historical_confidence_label?: string | null;
  historical_sample_size?: number | null;
  historical_win_rate?: number | null;
  historical_context_match?: number | null;
  historical_reason?: string | null;
  historical_warning?: string | null;
  operational_status?: string | null;
  operational_ready?: boolean | null;
  operational_score?: number | null;
  operational_blocks?: string[] | null;
  operational_warnings?: string[] | null;
  operational_summary?: string | null;
  conviction_score?: number | null;
  conviction_level?: string | null;
  conviction_summary?: string | null;
  conviction_factors?: string[] | null;
  conviction_conflicts?: string[] | null;
  priority_score?: number | null;
  priority_level?: string | null;
  priority_rank?: number | null;
  priority_summary?: string | null;
  priority_factors?: string[] | null;
  final_decision?: string | null;
  final_decision_score?: number | null;
  final_decision_summary?: string | null;
  final_decision_reason?: string | null;
  final_decision_blocks?: string[] | null;
  final_decision_confidence?: string | null;
  decision_status?: DecisionEnvelope["decision_status"] | null;
  decision_envelope?: DecisionEnvelope | null;
  rsi?: number | null;
  rsi_metadata?: {
    symbol: string;
    timeframe: string;
    as_of?: string | null;
    source?: string | null;
    candle_count: number;
    required_count: number;
    status: "AVAILABLE" | "INSUFFICIENT_DATA" | "PENDING" | "PROVIDER_UNAVAILABLE" | "STALE_DATA" | string;
    reason?: string | null;
  } | null;
  rel_volume?: number | null;
  trend_bias?: string | null;
  signal?: string | null;
  market_metrics?: PublicMarketMetrics | null;
  summary?: Record<string, unknown>;
};

export type PublicMarketBundlePayload = {
  symbol: string;
  quote?: QuotePayload | null;
  insight?: PublicInsightPayload | null;
  chart?: ChartPayload | null;
  news?: NewsPayload | null;
  ai_tools?: PublicAiToolsPayload | null;
  market_metrics?: PublicMarketMetrics | null;
  data_status?: Record<string, string>;
  retry_after_seconds?: number | null;
  source?: string;
};

export type WorkspaceTickerBundlePayload = {
  symbol: string;
  chart?: ChartPayload | null;
  insight?: PublicInsightPayload | null;
  feed?: FeedPayload | null;
  news?: NewsPayload | null;
  room?: ChatHistoryPayload | null;
  quote?: QuotePayload | null;
  source?: string;
};

export type UploadResponse = {
  url: string;
  relative_url?: string;
  filename: string;
};

export type PublicBootstrap = {
  brand: string;
  ai_modules: string[];
  social_features: Record<string, boolean>;
  pricing: {
    trial_days: number;
    premium_monthly?: { price_brl: number };
    premium_annual?: { price_brl: number };
  };
  launch_roadmap: {
    current?: string;
    next?: string;
    domain?: string;
  };
  market_universe?: {
    items: Array<{
      symbol: string;
      label?: string | null;
      category: "B3" | "BDR" | "Crypto" | "USA" | string;
      market?: string | null;
      exchange?: string | null;
      logo_url?: string | null;
      icon_url?: string | null;
    }>;
    counts: Record<string, number>;
    total: number;
    version?: string | null;
  };
};
