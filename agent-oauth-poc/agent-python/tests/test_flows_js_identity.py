"""
Test estructural sobre ../docs/html/static/flows.js.

Verifica que el flujo C ya no menciona campos de voz y sí menciona
los campos de identidad DNI+DOB.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


FLOWS_JS = Path(__file__).parent.parent.parent / "docs" / "html" / "static" / "flows.js"


def test_flows_js_existe():
    assert FLOWS_JS.exists()


def test_flowC_sin_voiceprint_score_en_claims():
    """Los claims del flowC no deben incluir voiceprint_score (campo de voz)."""
    src = FLOWS_JS.read_text(encoding="utf-8")
    # "voiceprint" puede aparecer en comentarios explicativos
    # ("en lugar de voiceprint"), pero "voiceprint_score" NO debe aparecer.
    assert "voiceprint_score" not in src, (
        "El flowC no debe usar voiceprint_score (campo de voz)"
    )


def test_flowC_incluye_dni_verified_y_dob_verified():
    """El flowC debe incluir los nuevos claims de identidad."""
    src = FLOWS_JS.read_text(encoding="utf-8")
    assert "dni_verified" in src, "El flowC debe incluir dni_verified en claims"
    assert "dob_verified" in src, "El flowC debe incluir dob_verified en claims"


def test_flowC_incluye_identity_method_en_claims():
    """Los claims del paso final deben declarar identity_method=dni+dob."""
    src = FLOWS_JS.read_text(encoding="utf-8")
    # Buscamos el objeto claims del paso final (última ocurrencia de tokenClaims)
    last_token_claims = src.rsplit("tokenClaims", 1)[-1]
    assert "identity_method" in last_token_claims
    assert "dni+dob" in last_token_claims


def test_flowC_no_deberia_incluir_voice_verified_ni_voiceprint_score_ni_caller_phone():
    """Los claims del flowC no deben incluir campos específicos de voz."""
    src = FLOWS_JS.read_text(encoding="utf-8")
    flow_c_match = re.search(
        r"export const flowC = \{(.*?)\n\};",
        src,
        re.DOTALL,
    )
    assert flow_c_match is not None, "Debe existir flowC"
    flow_c_src = flow_c_match.group(1)
    # Permitimos la mención "voiceprint" en comentarios explicativos (línea de cabecera
    # "datos identificativos en lugar de voiceprint") pero NO en los claims concretos.
    # Buscamos las strings en contexto de claim (entre comillas).
    assert "voice_verified" not in flow_c_src, (
        "flowC no debe contener 'voice_verified' (sustituido por dni_verified/dob_verified)"
    )
    assert "voiceprint_score" not in flow_c_src, (
        "flowC no debe contener 'voiceprint_score'"
    )
    assert "caller_phone" not in flow_c_src, (
        "flowC no debe contener 'caller_phone' (campo de voz)"
    )
    assert "phone-voice" not in flow_c_src, (
        "flowC no debe contener 'phone-voice' como acr"
    )


def test_flowC_acr_id_claim_no_phone_voice():
    """El acr debe usar id-claim, no phone-voice."""
    src = FLOWS_JS.read_text(encoding="utf-8")
    flow_c_match = re.search(
        r"export const flowC = \{(.*?)\n\};",
        src,
        re.DOTALL,
    )
    flow_c_src = flow_c_match.group(1)
    # El acr actual podría decir "phone-voice+push-biometric" o similar
    # Si lo cambiamos a "id-claim+push-biometric", debe aparecer este último
    # y NO debe aparecer phone-voice.
    if "acr" in flow_c_src:
        # No debe decir phone-voice (lo que tenía)
        assert "phone-voice" not in flow_c_src, (
            "flowC.acr no debe seguir siendo phone-voice"
        )
