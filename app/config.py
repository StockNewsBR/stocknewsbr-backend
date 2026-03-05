import os

# =====================================================
# DATABASE
# =====================================================

DATABASE_URL = os.getenv("DATABASE_URL")

# =====================================================
# ENGINE CONFIG
# =====================================================

# Atualiza a cada 15 minutos
UPDATE_INTERVAL = 900

# =====================================================
# AÇÕES BRASIL (Alta Liquidez)
# =====================================================

BR_SYMBOLS = [

    "PETR3.SA","PETR4.SA","VALE3.SA","ITUB4.SA",
    "BBDC3.SA","BBDC4.SA","BBAS3.SA","B3SA3.SA",

    "MGLU3.SA","LREN3.SA","PRIO3.SA","CSNA3.SA",
    "GGBR4.SA","USIM5.SA","SUZB3.SA","KLBN11.SA",

    "JHSF3.SA","MULT3.SA","CYRE3.SA","EZTC3.SA",

    "CVCB3.SA","AZUL4.SA","GOLL4.SA",

    "NTCO3.SA","HAPV3.SA","RDOR3.SA",

    "VIVT3.SA","TIMS3.SA",

    "EMBR3.SA","WEGE3.SA",

    "BRFS3.SA","JBSS3.SA",

    "MRVE3.SA",

    "CPLE6.SA","CMIG4.SA","ELET3.SA","ELET6.SA",
    "ENBR3.SA","TAEE11.SA","TRPL4.SA",

    "YDUQ3.SA"

]

# =====================================================
# BDRs (USA negociadas na B3)
# =====================================================

BDR_SYMBOLS = [

    # Big Tech

    "AAPL34.SA","MSFT34.SA","AMZO34.SA","GOGL34.SA",
    "FBOK34.SA","TSLA34.SA","NFLX34.SA","NVDC34.SA",

    # Finance

    "JPMN34.SA","VISA34.SA","PYPL34.SA",

    # Consumo

    "MCDC34.SA","DISB34.SA","NKE34.SA","KO34.SA",

    # Tecnologia

    "ORCL34.SA","INTC34.SA","ADBE34.SA",

    # Saúde

    "PFE34.SA",

    # Outros

    "BERK34.SA","ADID34.SA",

    # BDR adicionais

    "A1MD34.SA","AIRB34.SA","B1NT34.SA",
    "CMCS34.SA","COW34.SA","EXXO34.SA",
    "GMCO34.SA","GSGI34.SA","JNJB34.SA",
    "JPMC34.SA","M1RN34.SA","MSCD34.SA",
    "MUTC34.SA","PGCO34.SA","SSFO34.SA",
    "WFCO34.SA"

]

# =====================================================
# LISTA FINAL DO SCANNER
# =====================================================

SYMBOLS = BR_SYMBOLS + BDR_SYMBOLS

# =====================================================
# LIMITES
# =====================================================

TOP_RANKING_LIMIT = 10
MIN_SCORE_ALERT = 80