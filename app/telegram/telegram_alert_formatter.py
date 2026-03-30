from app.services.legal_service import LEGAL_NOTICE_TEXT


def format_signal_alert(signal, regime=None):
    ticker = signal.get("ticker", "N/A")
    price = signal.get("price", "N/A")
    score = signal.get("score", 0)
    momentum = signal.get("momentum", 0)
    volume = signal.get("volume_spike", 0)
    signal_name = signal.get("signal", "Sinal de IA")
    notice = LEGAL_NOTICE_TEXT.split(". ")[0]

    message = (
        "*StockNewsBR AI Alert*\n\n"
        f"*Ticker:* {ticker}\n"
        f"*Sinal:* {signal_name}\n"
        f"*Preco:* {price}\n"
        f"*Score:* {score}\n"
        f"*Momentum:* {momentum}\n"
        f"*Volume Spike:* {volume}\n"
        f"*Regime:* {regime or 'indefinido'}\n\n"
        f"_Aviso legal: {notice}._"
    )

    return message
