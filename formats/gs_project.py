from __future__ import annotations

import base64
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
            for caminho_zip, conteudo in cls._anexos_importados_para_zip(dados):
                pacote.writestr(caminho_zip, conteudo)

        return destino

    @classmethod
    def abrir(cls, arquivo: str | Path) -> Projeto:
        origem = Path(arquivo)
        with ZipFile(origem, mode="r") as pacote:
            dados = json.loads(pacote.read(cls.PROJECT_FILE).decode("utf-8"))
            cls._hidratar_anexos_importados_do_zip(dados, pacote)
        return Projeto.de_dict(dados)

    @staticmethod
    def _anexos_importados_para_zip(dados: dict) -> list[tuple[str, bytes]]:
        prefs = dados.get("preferencias_usuario") if isinstance(dados, dict) else {}
        anexos = prefs.get("arquivos_importados_anexos") if isinstance(prefs, dict) else []
        if not isinstance(anexos, list):
            return []
        saida: list[tuple[str, bytes]] = []
        usados: set[str] = set()
        for item in anexos:
            if not isinstance(item, dict):
                continue
            caminho_zip = GSProjectIO._caminho_zip_anexo_importado(item)
            if not caminho_zip or caminho_zip in usados:
                continue
            conteudo_b64 = str(item.get("conteudo_base64") or "").strip()
            if not conteudo_b64:
                continue
            try:
                conteudo = base64.b64decode(conteudo_b64)
            except Exception:
                continue
            saida.append((caminho_zip, conteudo))
            usados.add(caminho_zip)
        return saida

    @staticmethod
    def _hidratar_anexos_importados_do_zip(dados: dict, pacote: ZipFile) -> None:
        prefs = dados.get("preferencias_usuario") if isinstance(dados, dict) else {}
        anexos = prefs.get("arquivos_importados_anexos") if isinstance(prefs, dict) else []
        if not isinstance(anexos, list):
            return
        nomes_zip = set(pacote.namelist())
        for item in anexos:
            if not isinstance(item, dict) or str(item.get("conteudo_base64") or "").strip():
                continue
            caminho_zip = GSProjectIO._caminho_zip_anexo_importado(item)
            if not caminho_zip or caminho_zip not in nomes_zip:
                continue
            try:
                item["conteudo_base64"] = base64.b64encode(pacote.read(caminho_zip)).decode("ascii")
            except Exception:
                continue

    @staticmethod
    def _caminho_zip_anexo_importado(item: dict) -> str:
        caminho = str(item.get("anexo_zip") or "").strip().replace("\\", "/")
        if caminho.startswith("attachments/imports/") and ".." not in Path(caminho).parts:
            return caminho
        nome = Path(str(item.get("nome") or "arquivo_importado")).name or "arquivo_importado"
        anexo_id = str(item.get("id") or item.get("sha256") or "importado").strip()[:16] or "importado"
        return f"attachments/imports/{anexo_id}_{nome}"
