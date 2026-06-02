from __future__ import annotations

from types import SimpleNamespace

from api.routers.propositions import _build_proposition_link


def test_camara_doc_link_uses_full_text_url_when_available() -> None:
    proposition = SimpleNamespace(
        proposition_acronym="DOC",
        proposition_code=2629435,
        link="https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao=2629435",
        details={
            "urlInteiroTeor": "https://www.camara.leg.br/proposicoesWeb/prop_mostrarintegra?codteor=3140177"
        },
    )

    assert (
        _build_proposition_link(proposition)
        == "https://www.camara.leg.br/proposicoesWeb/prop_mostrarintegra?codteor=3140177"
    )
