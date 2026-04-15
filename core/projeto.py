from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, UTC
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class Ponto:
    x: float
    y: float


@dataclass(slots=True)
class Segmento:
    inicio: Ponto
    fim: Ponto


@dataclass(slots=True)
class Curva:
    pontos_controle: list[Ponto] = field(default_factory=list)


@dataclass(slots=True)
class Parte:
    id: str = field(default_factory=lambda: str(uuid4()))
    nome: str = "Parte"
    pontos: list[Ponto] = field(default_factory=list)
    segmentos: list[Segmento] = field(default_factory=list)
    curvas: list[Curva] = field(default_factory=list)
    piques: list[Ponto] = field(default_factory=list)
    marcacoes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Molde:
    id: str = field(default_factory=lambda: str(uuid4()))
    nome: str = "Molde"
    partes: list[Parte] = field(default_factory=list)


@dataclass(slots=True)
class Documento:
    id: str = field(default_factory=lambda: str(uuid4()))
    nome: str = "Documento"
    moldes: list[Molde] = field(default_factory=list)


@dataclass(slots=True)
class Projeto:
    id: str = field(default_factory=lambda: str(uuid4()))
    nome: str = "Novo Projeto"
    criado_em: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    atualizado_em: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    documentos: list[Documento] = field(default_factory=list)
    preferencias_usuario: dict[str, Any] = field(default_factory=dict)
    configuracao_snap: dict[str, bool] = field(
        default_factory=lambda: {
            "snap_ponto": True,
            "snap_segmento": True,
            "snap_curva": True,
            "snap_grade": True,
        }
    )

    def para_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def de_dict(cls, dados: dict[str, Any]) -> "Projeto":
        documentos: list[Documento] = []
        for doc in dados.get("documentos", []):
            moldes: list[Molde] = []
            for mol in doc.get("moldes", []):
                partes: list[Parte] = []
                for parte in mol.get("partes", []):
                    pontos = [Ponto(**p) for p in parte.get("pontos", [])]
                    segmentos = [
                        Segmento(inicio=Ponto(**s["inicio"]), fim=Ponto(**s["fim"]))
                        for s in parte.get("segmentos", [])
                    ]
                    curvas = [Curva(pontos_controle=[Ponto(**p) for p in c.get("pontos_controle", [])]) for c in parte.get("curvas", [])]
                    piques = [Ponto(**p) for p in parte.get("piques", [])]
                    partes.append(
                        Parte(
                            id=parte.get("id", str(uuid4())),
                            nome=parte.get("nome", "Parte"),
                            pontos=pontos,
                            segmentos=segmentos,
                            curvas=curvas,
                            piques=piques,
                            marcacoes=parte.get("marcacoes", []),
                        )
                    )
                moldes.append(Molde(id=mol.get("id", str(uuid4())), nome=mol.get("nome", "Molde"), partes=partes))
            documentos.append(Documento(id=doc.get("id", str(uuid4())), nome=doc.get("nome", "Documento"), moldes=moldes))

        return cls(
            id=dados.get("id", str(uuid4())),
            nome=dados.get("nome", "Novo Projeto"),
            criado_em=dados.get("criado_em", datetime.now(UTC).isoformat()),
            atualizado_em=dados.get("atualizado_em", datetime.now(UTC).isoformat()),
            documentos=documentos,
            preferencias_usuario=dados.get("preferencias_usuario", {}),
            configuracao_snap=dados.get("configuracao_snap", {}),
        )
