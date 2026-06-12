from app.services.legal_service import LEGAL_NOTICE_TEXT


def format_signal_alert(signal, regime=None):
    ticker = signal.get("ticker", "N/A")
    price = signal.get("price", "N/A")
    score = signal.get("score", 0)
    master_score = signal.get("master_score", score)
    master_direction = signal.get("master_direction") or "N/A"
    master_risk = signal.get("master_risk") or signal.get("risk_level") or "N/A"
    master_status = signal.get("master_status") or signal.get("audit_status") or "N/A"
    momentum = signal.get("momentum", 0)
    volume = signal.get("volume_spike", 0)
    signal_name = signal.get("signal", "Sinal de IA")
    notice = LEGAL_NOTICE_TEXT.split(". ")[0]

    message = (
        "*StockNewsBR AI Alert*\n\n"
        f"*Ticker:* {ticker}\n"
        f"*Sinal:* {signal_name}\n"
        f"*Preco:* {price}\n"
        f"*Score Mestre:* {master_score}\n"
        f"*Direcao:* {master_direction}\n"
        f"*Risco:* {master_risk}\n"
        f"*Status:* {master_status}\n"
        f"*Momentum:* {momentum}\n"
        f"*Volume Spike:* {volume}\n"
        f"*Regime:* {regime or 'indefinido'}\n\n"
        f"_Aviso legal: {notice}._"
    )

    return message
