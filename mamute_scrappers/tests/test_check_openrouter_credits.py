"""Alerta de créditos baixos do OpenRouter (CS-31).

O alerta roda de hora em hora. Sem controle de repetição, um saldo baixo por
três dias viraria 72 e-mails e o time pararia de ler — que é o mesmo que não
ter alerta. As regras de quando reenviar são o miolo deste módulo.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mamute_scrappers.scripts import check_openrouter_credits as cc


AGORA = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)


class TestQuandoAlertar:
    def test_saldo_ok_nao_alerta(self) -> None:
        assert cc.should_alert("ok", estado_anterior=None, agora=AGORA) is False

    def test_primeira_vez_em_atencao_alerta(self) -> None:
        assert cc.should_alert("atencao", estado_anterior=None, agora=AGORA) is True

    def test_nao_repete_o_mesmo_estado_dentro_do_intervalo(self) -> None:
        anterior = {"status": "atencao", "enviado_em": (AGORA - timedelta(hours=3)).isoformat()}

        assert cc.should_alert("atencao", anterior, AGORA, intervalo_horas=24) is False

    def test_repete_depois_do_intervalo(self) -> None:
        anterior = {"status": "atencao", "enviado_em": (AGORA - timedelta(hours=25)).isoformat()}

        assert cc.should_alert("atencao", anterior, AGORA, intervalo_horas=24) is True

    def test_piora_alerta_na_hora_mesmo_dentro_do_intervalo(self) -> None:
        """Ir de atenção para crítico é notícia nova — não pode esperar 24h."""

        anterior = {"status": "atencao", "enviado_em": (AGORA - timedelta(minutes=5)).isoformat()}

        assert cc.should_alert("critico", anterior, AGORA, intervalo_horas=24) is True

    def test_melhora_nao_dispara_alerta(self) -> None:
        anterior = {"status": "critico", "enviado_em": (AGORA - timedelta(minutes=5)).isoformat()}

        assert cc.should_alert("atencao", anterior, AGORA, intervalo_horas=24) is False

    def test_recuperacao_para_ok_nao_alerta(self) -> None:
        anterior = {"status": "critico", "enviado_em": AGORA.isoformat()}

        assert cc.should_alert("ok", anterior, AGORA) is False

    def test_estado_corrompido_nao_impede_o_alerta(self) -> None:
        """Na dúvida, alertar. Perder aviso de saldo é pior que um e-mail a mais."""

        assert cc.should_alert("critico", {"lixo": True}, AGORA) is True


class TestEstadoEmDisco:
    def test_grava_e_le(self, tmp_path: Path) -> None:
        caminho = tmp_path / "estado.json"
        cc.save_state(caminho, "critico", AGORA)

        lido = cc.load_state(caminho)
        assert lido["status"] == "critico"
        assert lido["enviado_em"] == AGORA.isoformat()

    def test_arquivo_ausente_vira_none(self, tmp_path: Path) -> None:
        assert cc.load_state(tmp_path / "nao-existe") is None

    def test_arquivo_invalido_vira_none(self, tmp_path: Path) -> None:
        caminho = tmp_path / "estado.json"
        caminho.write_text("{{{", encoding="utf-8")

        assert cc.load_state(caminho) is None


class TestConteudoDoAlerta:
    def _dados(self, **over):
        base = {
            "status": "critico",
            "disponivel_usd": 3.5,
            "total_credits_usd": 22.0,
            "total_usage_usd": 18.5,
            "chatbot_usd": 4.0,
            "embeddings_usd": 14.5,
            "limiar_atencao_usd": 10.0,
            "limiar_critico_usd": 5.0,
        }
        base.update(over)
        return base

    def test_mostra_saldo_e_reparticao(self) -> None:
        html = cc.build_alert_html(self._dados())

        assert "3.50" in html or "3,50" in html
        assert "4.00" in html or "4,00" in html   # chatbot
        assert "14.50" in html or "14,50" in html  # embeddings

    def test_deixa_claro_o_impacto_de_zerar(self) -> None:
        """Quem lê precisa entender que zerar derruba o chat inteiro."""

        html = cc.build_alert_html(self._dados())

        assert "chat" in html.lower()
        assert "openrouter.ai" in html

    def test_assunto_diferencia_critico_de_atencao(self) -> None:
        assert cc.build_subject("critico") != cc.build_subject("atencao")
        assert "crítico" in cc.build_subject("critico").lower()


class TestDestinatarios:
    def test_le_a_lista_de_admins(self, monkeypatch) -> None:
        monkeypatch.setenv("MAMUTE_ADMIN_EMAILS", "a@x.com, b@x.com ,, c@x.com")

        assert cc.admin_recipients() == ["a@x.com", "b@x.com", "c@x.com"]

    def test_sem_admins_retorna_lista_vazia(self, monkeypatch) -> None:
        monkeypatch.delenv("MAMUTE_ADMIN_EMAILS", raising=False)

        assert cc.admin_recipients() == []
