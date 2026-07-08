#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/dcima/stocknewsbr-backend')

from app.social.guardian import SocialGuardian

def test_betting_variations():
    """Test variações de apostas com separadores"""
    test_cases = [
        ("b.e.t", "betting_detected"),
        ("b-e-t", "betting_detected"),
        ("b e t", "betting_detected"),
        ("b_e_t", "betting_detected"),
        ("c.a.s.s.i.n.o", "betting_detected"),
        ("c-a-s-s-i-n-o", "betting_detected"),
        ("a.p.o.s.t.a", "betting_detected"),
        ("a-p-o-s-t-a", "betting_detected"),
        ("t.i.g.r.i.n.h.o", "betting_detected"),
        ("t-i-g-r-i-n-h-o", "betting_detected"),
    ]

    for text, expected_reason in test_cases:
        decision = SocialGuardian.validate_content(text)
        if decision.allowed:
            print(f"[FAIL] '{text}' foi permitido (esperava {expected_reason})")
            return False
        if decision.reason != expected_reason:
            print(f"[FAIL] '{text}' retornou {decision.reason} (esperava {expected_reason})")
            return False
        print(f"[OK] '{text}' bloqueado corretamente")

    return True

def test_new_betting_terms():
    """Test novos termos de apostas"""
    test_cases = [
        "kto", "betboom", "aviator", "fortune tiger", "foguetinho",
        "mines", "crash", "betar", "fezinha", "palpite", "tipster",
        "renda garantida", "lucro garantido", "ganho garantido",
    ]

    for term in test_cases:
        decision = SocialGuardian.validate_content(term)
        if decision.allowed:
            print(f"[FAIL] '{term}' foi permitido")
            return False
        if decision.reason != "betting_detected":
            print(f"[FAIL] '{term}' retornou {decision.reason}")
            return False
        print(f"[OK] '{term}' bloqueado")

    return True

def test_adult_content():
    """Test bloqueio de conteúdo adulto"""
    test_cases = [
        "onlyfans", "sexo", "anal", "puta", "cu", "cuzão",
        "buceta", "pau", "pênis", "caralho", "pornô", "porno",
    ]

    for term in test_cases:
        decision = SocialGuardian.validate_content(term)
        if decision.allowed:
            print(f"[FAIL] '{term}' foi permitido")
            return False
        if decision.reason != "adult_content_detected":
            print(f"[WARN] '{term}' bloqueado mas com reason: {decision.reason}")
        print(f"[OK] '{term}' bloqueado como conteúdo adulto")

    return True

def test_swear_words():
    """Test bloqueio de palavrões"""
    test_cases = [
        "merda", "porra", "bosta", "desgraça", "maldito", "idiota",
    ]

    for term in test_cases:
        decision = SocialGuardian.validate_content(term)
        if decision.allowed:
            print(f"[FAIL] '{term}' foi permitido")
            return False
        if decision.reason != "swear_detected":
            print(f"[WARN] '{term}' bloqueado mas com reason: {decision.reason}")
        print(f"[OK] '{term}' bloqueado como palavrão")

    return True

def test_hate_speech():
    """Test bloqueio de discurso de ódio explícito"""
    blocked_cases = [
        "racista", "racismo", "transfóbico", "homofóbico",
    ]

    for term in blocked_cases:
        decision = SocialGuardian.validate_content(term)
        if decision.allowed:
            print(f"[FAIL] '{term}' foi permitido")
            return False
        if decision.reason != "hate_speech_detected":
            print(f"[WARN] '{term}' bloqueado mas com reason: {decision.reason}")
        print(f"[OK] '{term}' bloqueado como discurso de ódio")

    return True

def test_identity_terms_allowed():
    """Test que termos de identidade/religião/história passam em contexto legítimo"""
    allowed_cases = [
        "Judeu premiado por inovação",
        "Holocausto: lição de história",
        "Orgulho viado",
        "Comunidade LGBTQ+ forte",
        "Preto é lindo",
        "Identidade trans",
    ]

    for text in allowed_cases:
        decision = SocialGuardian.validate_content(text)
        if not decision.allowed:
            print(f"[FAIL] '{text}' foi bloqueado ({decision.reason})")
            return False
        print(f"[OK] '{text}' permitido corretamente")

    return True

def test_clean_content():
    """Test que conteúdo limpo passa"""
    test_cases = [
        "PETR4 em alta",
        "Boa oportunidade de compra",
        "Análise técnica muito boa",
    ]

    for text in test_cases:
        decision = SocialGuardian.validate_content(text)
        if not decision.allowed:
            print(f"[FAIL] '{text}' foi bloqueado ({decision.reason})")
            return False
        print(f"[OK] '{text}' permitido corretamente")

    return True

if __name__ == "__main__":
    print("=" * 60)
    print("TESTE 1: Variações com separadores")
    print("=" * 60)
    test1 = test_betting_variations()

    print("\n" + "=" * 60)
    print("TESTE 2: Novos termos de apostas")
    print("=" * 60)
    test2 = test_new_betting_terms()

    print("\n" + "=" * 60)
    print("TESTE 3: Conteúdo adulto")
    print("=" * 60)
    test3 = test_adult_content()

    print("\n" + "=" * 60)
    print("TESTE 4: Palavrões")
    print("=" * 60)
    test4 = test_swear_words()

    print("\n" + "=" * 60)
    print("TESTE 5: Discurso de ódio explícito")
    print("=" * 60)
    test5 = test_hate_speech()

    print("\n" + "=" * 60)
    print("TESTE 6: Termos de identidade/religião/história (permitidos)")
    print("=" * 60)
    test6 = test_identity_terms_allowed()

    print("\n" + "=" * 60)
    print("TESTE 7: Conteúdo limpo financeiro")
    print("=" * 60)
    test7 = test_clean_content()

    print("\n" + "=" * 60)
    if all([test1, test2, test3, test4, test5, test6, test7]):
        print("[OK] TODOS OS TESTES PASSARAM!")
        sys.exit(0)
    else:
        print("[FAIL] ALGUNS TESTES FALHARAM")
        sys.exit(1)
