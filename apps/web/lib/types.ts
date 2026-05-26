export type WorkspaceTab = {
  id: string;
  title: string;
  icon?: string;
  route?: string;
  popout_route?: string;
  detachable?: boolean;
  monitor_ready?: boolean;
};

export type RankingRow = {
  symbol: string;
  score: number;
  trend?: string | null;
  rsi?: number | string | null;
  rel_volume?: number | string | null;
  breakout?: boolean;
  price?: number | null;
};

export type SignalRow = {
  ticker?: string;
  symbol?: string;
  score?: number;
  trend?: string | null;
  breakout?: boolean;
  price?: number | null;
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
  last_bar_at?: string | number | null;
  bar_time?: string | number | null;
  time?: string | number | null;
  timestamp?: string | number | null;
  quote_time?: string | number | null;
  provider_timestamp?: string | number | null;
  created_at?: string | number | null;
  updated_at?: string;
  detected_at?: string;
  last_seen_at?: string;
  active?: boolean;
};

export type WorkspaceAiTools = {
  heat_map: AiToolRow[];
  radar: AiToolRow[];
  breakout_probability: AiToolRow[];
  institutional_flow: AiToolRow[];
  smart_money: AiToolRow[];
  accumulation: AiToolRow[];
  volatility_squeeze: AiToolRow[];
  liquidity_sweep: AiToolRow[];
  liquidity_map: AiToolRow[];
  market_regime: AiToolRow[];
  master_score: AiToolRow[];
};

export type PublicAiToolsPayload = {
  reset_key: string;
  updated_at?: string | null;
  max_rows_per_tool: number;
  reset_hour: number;
  timezone: string;
  tools: Partial<WorkspaceAiTools>;
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
  };
  updated_at?: number;
};

export type FeedComment = {
  id: number;
  user: string;
  user_id?: number;
  user_email?: string | null;
  user_avatar_url?: string | null;
  text: string;
  image_url?: string | null;
  timestamp?: number;
};

export type FeedPost = {
  id: number;
  user: string;
  user_id: number;
  user_email?: string | null;
  user_avatar_url?: string | null;
  text: string;
  ticker?: string | null;
  sentiment?: string | null;
  image_url?: string | null;
  timestamp?: number;
  likes?: number;
  liked_by_me?: boolean;
  reposts?: number;
  reposted_by_me?: boolean;
  my_repost_quote_text?: string | null;
  is_followed_by_me?: boolean;
  comments?: FeedComment[];
  discussion_relevance_score?: number;
  discussion_relevance_reason?: string[];
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

export type WorkspaceData = {
  brand: string;
  workspace_mode: string;
  tabs: WorkspaceTab[];
  top_signals: SignalRow[];
  ranking: RankingRow[];
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
  };
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
  summary?: string;
  card_summary?: string | null;
  source: string;
  source_domain?: string | null;
  url?: string | null;
  published_at?: string | null;
  sector?: string | null;
  industry?: string | null;
  labels?: string[];
  entities?: string[];
  impact?: string | null;
  impact_label?: string | null;
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
  debug_otp_code?: string | null;
  session_policy?: string | null;
  channel?: string | null;
  detail?: string | null;
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
  price?: number;
  change?: number;
  change_pct?: number;
  volume?: number;
  high?: number;
  low?: number;
  source?: string;
  quote_status?: "valid" | "partial" | "empty" | "stale" | string;
  stale?: boolean;
};

export type PublicInsightPayload = {
  symbol: string;
  score?: number | null;
  rsi?: number | null;
  rel_volume?: number | null;
  trend_bias?: string | null;
  signal?: string | null;
  summary?: Record<string, unknown>;
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
};
