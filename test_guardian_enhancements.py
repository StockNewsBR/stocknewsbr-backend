#!/usr/bin/env python3
import sys

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
        assert not decision.allowed, f"'{text}' foi permitido (esperava {expected_reason})"
        assert decision.reason == expected_reason, f"'{text}' retornou {decision.reason} (esperava {expected_reason})"
        print(f"[OK] '{text}' bloqueado corretamente")


def test_new_betting_terms():
    """Test novos termos de apostas"""
    test_cases = [
        "kto", "betboom", "aviator", "fortune tiger", "foguetinho",
        "mines", "crash", "betar", "fezinha", "palpite", "tipster",
        "renda garantida", "lucro garantido", "ganho garantido",
    ]

    for term in test_cases:
        decision = SocialGuardian.validate_content(term)
        assert not decision.allowed, f"'{term}' foi permitido"
        assert decision.reason == "betting_detected", f"'{term}' retornou {decision.reason}"
        print(f"[OK] '{term}' bloqueado")


def test_adult_content():
    """Test bloqueio de conteúdo adulto"""
    test_cases = [
        "onlyfans", "sexo", "anal", "puta", "cu", "cuzão",
        "buceta", "pau", "pênis", "caralho", "pornô", "porno",
    ]

    for term in test_cases:
        decision = SocialGuardian.validate_content(term)
        assert not decision.allowed, f"'{term}' foi permitido"
        assert decision.reason == "adult_content_detected", f"'{term}' retornou {decision.reason}"
        print(f"[OK] '{term}' bloqueado como conteúdo adulto")


def test_swear_words():
    """Test bloqueio de palavrões"""
    test_cases = [
        "merda", "porra", "bosta", "desgraça", "maldito", "idiota",
    ]

    for term in test_cases:
        decision = SocialGuardian.validate_content(term)
        assert not decision.allowed, f"'{term}' foi permitido"
        assert decision.reason == "swear_detected", f"'{term}' retornou {decision.reason}"
        print(f"[OK] '{term}' bloqueado como palavrão")


def test_hate_speech():
    """Test bloqueio de discurso de ódio explícito"""
    blocked_cases = [
        "racista", "racismo", "transfóbico", "homofóbico",
    ]

    for term in blocked_cases:
        decision = SocialGuardian.validate_content(term)
        assert not decision.allowed, f"'{term}' foi permitido"
        assert decision.reason == "hate_speech_detected", f"'{term}' retornou {decision.reason}"
        print(f"[OK] '{term}' bloqueado como discurso de ódio")


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
        assert decision.allowed, f"'{text}' foi bloqueado ({decision.reason})"
        print(f"[OK] '{text}' permitido corretamente")


def test_clean_content():
    """Test que conteúdo limpo passa"""
    test_cases = [
        "PETR4 em alta",
        "Boa oportunidade de compra",
        "Análise técnica muito boa",
    ]

    for text in test_cases:
        decision = SocialGuardian.validate_content(text)
        assert decision.allowed, f"'{text}' foi bloqueado ({decision.reason})"
        print(f"[OK] '{text}' permitido corretamente")


if __name__ == "__main__":
    print("=" * 60)
    print("TESTE 1: Variações com separadores")
    print("=" * 60)
    test_betting_variations()

    print("\n" + "=" * 60)
    print("TESTE 2: Novos termos de apostas")
    print("=" * 60)
    test_new_betting_terms()

    print("\n" + "=" * 60)
    print("TESTE 3: Conteúdo adulto")
    print("=" * 60)
    test_adult_content()

    print("\n" + "=" * 60)
    print("TESTE 4: Palavrões")
    print("=" * 60)
    test_swear_words()

    print("\n" + "=" * 60)
    print("TESTE 5: Discurso de ódio explícito")
    print("=" * 60)
    test_hate_speech()

    print("\n" + "=" * 60)
    print("TESTE 6: Termos de identidade/religião/história (permitidos)")
    print("=" * 60)
    test_identity_terms_allowed()

    print("\n" + "=" * 60)
    print("TESTE 7: Conteúdo limpo financeiro")
    print("=" * 60)
    test_clean_content()

    print("\n" + "=" * 60)
    print("[OK] TODOS OS TESTES PASSARAM!")
