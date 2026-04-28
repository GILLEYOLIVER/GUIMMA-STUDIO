from __future__ import annotations

import base64
import json
from pathlib import Path

from core.projeto import Documento, Molde, Parte, Ponto, Projeto
from formats.audaces_emf_import import AudacesEMFImport, emf_doc_para_dict
from formats.audaces_xml_import import AudacesXMLImport, xml_doc_para_dict


class AudacesPairImport:
    # Calibração manual temporária medida no teste real ATUAL.
    # A versão anterior ficou grande demais:
    #   referência 1: Audaces 400.17 mm / GUIMMA 544.28 mm = 0.7352281914
    #   referência 2: Audaces 407.25 mm / GUIMMA 549.57 mm = 0.7410338992
    #   correção média = 0.7381310453
    #
    # Fator anterior fino: 19.2020894467
    # Fator final corrigido: 19.2020894467 * 0.7381310453 = 14.1736583552598
    ESCALA_CALIBRACAO_PADRAO = 14.1736583552598

    @classmethod
    def importar(cls, emf_path: str | Path, xml_path: str | Path, projeto: Projeto) -> Projeto:
        xml_doc = AudacesXMLImport.abrir(xml_path)
        emf_doc = AudacesEMFImport.abrir(emf_path)

        fator_escala_final = cls._fator_escala_calibrado(xml_doc, emf_doc)
        cls._aplicar_escala_emf_doc(emf_doc, fator_escala_final)

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
            "escala_manual_aplicada": fator_escala_final,
            "medida_guimma_referencia_mm": 544.28,
            "medida_audaces_referencia_mm": 400.17,
            "fator_escala_final": fator_escala_final,
            "unidade_resultado": "cm_calibrado_por_referencia_mm",
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
        fator_escala_final = cls.ESCALA_CALIBRACAO_PADRAO
        cls._aplicar_escala_emf_doc(emf_doc, fator_escala_final)
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
            "escala_manual_aplicada": fator_escala_final,
            "medida_guimma_referencia_mm": 544.28,
            "medida_audaces_referencia_mm": 400.17,
            "fator_escala_final": fator_escala_final,
            "unidade_resultado": "cm_calibrado_por_referencia_mm",
        }
        projeto.preferencias_usuario.setdefault("audaces_importados_originais", {})["emf"] = {
            "nome": Path(emf_path).name,
            "conteudo_base64": base64.b64encode(Path(emf_path).read_bytes()).decode("ascii"),
        }
        return projeto


    @classmethod
    def _fator_escala_calibrado(cls, xml_doc, emf_doc) -> float:
        """Retorna o fator final de escala para EMF do Audaces.

        A escala automática do EMF exportado como Metafile nesta instalação
        não bate com a régua técnica do Audaces. O fator abaixo foi calibrado
        com a medida real enviada: 544.28 mm no GUIMMA corresponde a 400.17 mm no Audaces,
        com validação secundária de 549.57 mm para 407.25 mm. Depois a interface pode expor esse fator como calibração
        manual editável.
        """
        return float(cls.ESCALA_CALIBRACAO_PADRAO)

    @staticmethod
    def _aplicar_escala_emf_doc(emf_doc, fator: float):
        fator = float(fator or 1.0)
        if abs(fator - 1.0) < 1e-12:
            return

        def _scale_pt(pt):
            x, y = pt
            return float(x) * fator, float(y) * fator

        for el in getattr(emf_doc, "elementos", []):
            el.pontos = [_scale_pt(p) for p in el.pontos]
            if el.pontos:
                xs = [p[0] for p in el.pontos]
                ys = [p[1] for p in el.pontos]
                el.bbox = (min(xs), min(ys), max(xs), max(ys))
            el.metadados["escala_manual_aplicada"] = fator
            el.metadados["unidade_resultado"] = "cm_calibrado"

        for tx in getattr(emf_doc, "textos", []):
            if "pos" in tx:
                tx["pos"] = _scale_pt(tx["pos"])

        try:
            l, t, r, b = emf_doc.bounds
            emf_doc.bounds = (l * fator, t * fator, r * fator, b * fator)
            emf_doc.largura = max(emf_doc.bounds[2] - emf_doc.bounds[0], 0.0)
            emf_doc.altura = max(emf_doc.bounds[3] - emf_doc.bounds[1], 0.0)
        except Exception:
            pass

        rel = getattr(emf_doc, "relatorio", {})
        if isinstance(rel, dict):
            rel["escala_manual_aplicada"] = fator
            rel["medida_guimma_referencia_mm"] = 544.28
            rel["medida_audaces_referencia_mm"] = 400.17
            rel["fator_escala_final"] = fator
            rel["unidade_resultado"] = "cm_calibrado_por_referencia_mm"
            rel.setdefault("avisos", []).append(
                f"Escala calibrada manualmente aplicada ao EMF: fator {fator:.8f}."
            )

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
            "escala_manual_aplicada": info.get("escala_manual_aplicada"),
            "medida_guimma_referencia_mm": info.get("medida_guimma_referencia_mm"),
            "medida_audaces_referencia_mm": info.get("medida_audaces_referencia_mm"),
            "fator_escala_final": info.get("fator_escala_final") or info.get("escala_manual_aplicada"),
            "unidade_resultado": info.get("unidade_resultado"),
            "records_nao_suportados": rel.get("records_nao_suportados", {}),
            "avisos": list(info.get("avisos", [])) + list(rel.get("avisos", [])),
        }

    @staticmethod
    def _salvar_relatorio_debug(relatorio: dict) -> Path:
        out = Path("debug") / "audaces_emf_xml_import_report.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
        return out
