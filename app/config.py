import os

DATABASE_URL = os.getenv("DATABASE_URL")

UPDATE_INTERVAL = 60

# =====================================================
# AÇÕES BRASIL
# =====================================================

BR_SYMBOLS = [
    "PETR4.SA", "VALE3.SA", "ITUB4.SA", "BBDC4.SA",
    "BBAS3.SA", "ABEV3.SA", "SUZB3.SA", "WEGE3.SA",
    "GGBR4.SA", "LREN3.SA", "ENGI11.SA", "RENT3.SA"
]

# =====================================================
# BDRs (USA via B3)
# =====================================================

BDR_SYMBOLS = [
    "AAPL34.SA",  # Apple
    "AMZO34.SA",  # Amazon
    "BABA34.SA",  # Alibaba
    "BERK34.SA",  # Berkshire
    "M1TA34.SA",  # Meta
    "MELI34.SA",  # Mercado Livre
    "MSFT34.SA",  # Microsoft
    "NFLX34.SA",  # Netflix
    "NVDC34.SA",  # Nvidia
    "PFIZ34.SA",  # Pfizer
    "PYPL34.SA",  # PayPal
    "ROXO34.SA"   # Roblox
]

# =====================================================
# LISTA FINAL USADA PELO SISTEMA
# =====================================================

SYMBOLS = BR_SYMBOLS + BDR_SYMBOLS