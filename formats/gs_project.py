from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from core.projeto import Projeto


class GSProjectIO:
    """Leitor/gravador inicial do formato .gstudio (zip estruturado)."""

    PROJECT_FILE = "project.json"
    VERSION_FILE = "meta/version.json"

    @classmethod
    def salvar(cls, projeto: Projeto, arquivo: str | Path) -> Path:
        destino = Path(arquivo)
        dados = projeto.para_dict()
        dados["atualizado_em"] = datetime.now(timezone.utc).isoformat()

        with ZipFile(destino, mode="w", compression=ZIP_DEFLATED) as pacote:
            pacote.writestr(cls.PROJECT_FILE, json.dumps(dados, ensure_ascii=False, indent=2))
            pacote.writestr(
                cls.VERSION_FILE,
                json.dumps({"format": "gstudio", "schema": 1}, ensure_ascii=False, indent=2),
            )

        return destino

    @classmethod
    def abrir(cls, arquivo: str | Path) -> Projeto:
        origem = Path(arquivo)
        with ZipFile(origem, mode="r") as pacote:
            dados = json.loads(pacote.read(cls.PROJECT_FILE).decode("utf-8"))
        return Projeto.de_dict(dados)
