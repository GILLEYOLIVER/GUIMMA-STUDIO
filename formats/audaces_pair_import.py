from __future__ import annotations

import base64
import json
from pathlib import Path

from core.projeto import Documento, Molde, Parte, Ponto, Projeto
from formats.audaces_emf_import import AudacesEMFImport, emf_doc_para_dict
from formats.audaces_xml_import import AudacesXMLImport, xml_doc_para_dict


class AudacesPairImport:
    @classmethod
    def importar(cls, emf_path: str | Path, xml_path: str | Path, projeto: Projeto) -> Projeto:
        xml_doc = AudacesXMLImport.abrir(xml_path)
        emf_doc = AudacesEMFImport.abrir(emf_path)
        elementos_canvas = AudacesEMFImport(b"", emf_path).converter_para_elementos_guimma(emf_doc)

        projeto.nome = xml_doc.nome_modelo or projeto.nome
        if not projeto.documentos:
            projeto.documentos.append(Documento(nome="Documento 1"))
        doc = projeto.documentos[0]
        doc.moldes = []

        contornos = [el for el in emf_doc.elementos if el.fechado and len(el.pontos) >= 4]
        avisos: list[str] = []
        aplicados = 0
        total_assoc = min(len(contornos), len(xml_doc.pecas))

        for idx, contorno in enumerate(contornos):
            peca = xml_doc.pecas[idx] if idx < len(xml_doc.pecas) else None
            nome = peca.nome if peca else f"Molde EMF {idx + 1}"
            parte = Parte(
                nome=nome,
                pontos=[Ponto(x=float(x), y=float(y)) for x, y in contorno.pontos],
                marcacoes=["origem:audaces_emf_xml"],
            )
            molde = Molde(nome=nome, partes=[parte])
            doc.moldes.append(molde)
            aplicados += 1 if peca else 0

        if len(contornos) != len(xml_doc.pecas):
            avisos.append("Alguns contornos EMF não puderam ser associados automaticamente às peças do XML.")

        projeto.preferencias_usuario["audaces_emf_xml_importacao"] = {
            "origem": "audaces_emf_xml",
            "emf_path": str(emf_path),
            "xml_path": str(xml_path),
            "vetores": len([el for el in elementos_canvas if el.get("tipo") == "polyline"]),
            "moldes_detectados": len(contornos),
            "metadados_xml_aplicados": aplicados,
            "avisos": avisos,
            "elementos_canvas": elementos_canvas,
            "xml": xml_doc_para_dict(xml_doc),
            "emf": emf_doc_para_dict(emf_doc),
            "associacoes": total_assoc,
            "pecas_xml": len(xml_doc.pecas),
            "pecas_xml_sem_associacao": max(0, len(xml_doc.pecas) - total_assoc),
            "contornos_fechados": len(contornos),
            "moldes_reais": len(doc.moldes),
            "bounds_emf": emf_doc.bounds,
            "escala": dict(emf_doc.relatorio.get("escala", {})),
        }

        projeto.preferencias_usuario["audaces_importados_originais"] = {
            "emf": {
                "nome": Path(emf_path).name,
                "conteudo_base64": base64.b64encode(Path(emf_path).read_bytes()).decode("ascii"),
            },
            "xml": {
                "nome": Path(xml_path).name,
                "conteudo_base64": base64.b64encode(Path(xml_path).read_bytes()).decode("ascii"),
            },
        }
        relatorio = cls._gerar_relatorio_importacao(xml_doc, emf_doc, projeto.preferencias_usuario["audaces_emf_xml_importacao"])
        report_path = cls._salvar_relatorio_debug(relatorio)
        projeto.preferencias_usuario["audaces_emf_xml_importacao"]["debug_report_path"] = str(report_path)

        return projeto

    @classmethod
    def importar_apenas_emf(cls, emf_path: str | Path, projeto: Projeto) -> Projeto:
        emf_doc = AudacesEMFImport.abrir(emf_path)
        elementos_canvas = AudacesEMFImport(b"", emf_path).converter_para_elementos_guimma(emf_doc)
        if not projeto.documentos:
            projeto.documentos.append(Documento(nome="Documento 1"))
        doc = projeto.documentos[0]
        doc.moldes = []
        for idx, el in enumerate([e for e in emf_doc.elementos if e.fechado and len(e.pontos) >= 4], start=1):
            parte = Parte(nome=f"Molde EMF {idx}", pontos=[Ponto(x=float(x), y=float(y)) for x, y in el.pontos])
            doc.moldes.append(Molde(nome=f"Molde EMF {idx}", partes=[parte]))

        projeto.preferencias_usuario["audaces_emf_importacao"] = {
            "origem": "audaces_emf",
            "emf_path": str(emf_path),
            "elementos_canvas": elementos_canvas,
            "relatorio": dict(emf_doc.relatorio),
        }
        projeto.preferencias_usuario.setdefault("audaces_importados_originais", {})["emf"] = {
            "nome": Path(emf_path).name,
            "conteudo_base64": base64.b64encode(Path(emf_path).read_bytes()).decode("ascii"),
        }
        return projeto

    @staticmethod
    def _gerar_relatorio_importacao(xml_doc, emf_doc, info: dict) -> dict:
        rel = dict(emf_doc.relatorio)
        records_tipos = rel.get("records_tipos", {})
        return {
            "arquivo_emf": str(emf_doc.caminho),
            "records_emf_total": rel.get("records_total", 0),
            "records_emf_tipos": records_tipos,
            "quantidade_polyline": rel.get("quantidade_polylines", 0),
            "quantidade_polygon": rel.get("quantidade_polygons", 0),
            "quantidade_polybezier": rel.get("quantidade_beziers", 0),
            "quantidade_textos": rel.get("quantidade_textos", 0),
            "elementos_vetoriais_convertidos": rel.get("elementos_convertidos", 0),
            "contornos_fechados": info.get("contornos_fechados", 0),
            "moldes_reais_criados": info.get("moldes_reais", 0),
            "pecas_xml_lidas": len(xml_doc.pecas),
            "pecas_xml_associadas": info.get("associacoes", 0),
            "pecas_xml_sem_associacao": info.get("pecas_xml_sem_associacao", 0),
            "bounds_emf": emf_doc.bounds,
            "escala_usada": rel.get("escala", {}),
            "records_nao_suportados": rel.get("records_nao_suportados", {}),
            "avisos": list(info.get("avisos", [])) + list(rel.get("avisos", [])),
        }

    @staticmethod
    def _salvar_relatorio_debug(relatorio: dict) -> Path:
        out = Path("debug") / "audaces_emf_xml_import_report.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
        return out
