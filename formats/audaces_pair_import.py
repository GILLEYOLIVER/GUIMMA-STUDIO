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

    @staticmethod
    def _classificar_contornos_unidos(elementos, xml_doc=None):
        fechados = [e for e in elementos if e.fechado and len(e.pontos) >= 4]
        abertos = [e for e in elementos if not e.fechado and len(e.pontos) >= 2]
        if not fechados:
            return elementos, 0, 0, len(abertos), 0
        areas = []
        for e in fechados:
            area = abs(AudacesEMFImport._area_assinada(e.pontos))
            e.metadados["area_contorno"] = area
            areas.append(area)
        area_ref = max(areas) if areas else 0.0
        area_min = max(0.08, area_ref * 0.003)
        fechados_validos = [e for e in fechados if e.metadados.get("area_contorno", 0.0) >= area_min]
        ignorados = len(fechados) - len(fechados_validos)
        fechados_ordenados = sorted(fechados_validos, key=lambda e: e.metadados.get("area_contorno", 0.0), reverse=True)
        principais = []
        costuras = 0
        internas = 0
        alvo_xml = len(getattr(xml_doc, "pecas", []) or [])
        for e in fechados_ordenados:
            pt = e.pontos[0]
            dentro_de_principal = any(AudacesEMFImport._ponto_em_poligono(pt, p.pontos) for p in principais)
            if not dentro_de_principal and (alvo_xml <= 0 or len(principais) < alvo_xml):
                e.metadados["subtipo_audaces"] = "contorno"
                principais.append(e)
            elif dentro_de_principal:
                e.metadados["subtipo_audaces"] = "costura"
                costuras += 1
            else:
                e.metadados["subtipo_audaces"] = "linha_interna"
                internas += 1
        for e in abertos:
            e.metadados["subtipo_audaces"] = "linha_interna"
        return elementos, len(principais), costuras, internas + len(abertos), ignorados

    @staticmethod
    def _converter_moldes_para_canvas(moldes: list[Molde]) -> list[dict]:
        elementos: list[dict] = []
        for molde in moldes:
            for parte in molde.partes:
                pts = [(p.x, p.y) for p in parte.pontos]
                if len(pts) < 2:
                    continue
                if pts[0] != pts[-1]:
                    pts.append(pts[0])
                base = pts[:-1]
                xs = [x for x, _ in base]
                ys = [y for _, y in base]
                cx = sum(xs) / len(xs)
                cy = sum(ys) / len(ys)
                largura = max(xs) - min(xs)
                margem = largura * 0.20
                elementos.append({
                    "tipo": "polyline",
                    "pontos": pts,
                    "origem": "audaces_emf_xml_molde_real",
                    "subtipo_audaces": "contorno",
                    "molde": True,
                    "molde_id": molde.id,
                    "nome_molde": molde.nome,
                    "fio_angulo": 0.0,
                    "fio_origem": (min(xs) + margem, cy),
                    "fio_fim": (max(xs) - margem, cy),
                    "ponto_texto": (cx, cy),
                    "mostrar_nome": True,
                    "mostrar_fio": True,
                    "metadados": {"origem": "audaces_emf_xml", "importado_como_molde_real": True, "subtipo_audaces": "contorno"},
                    "cor": "#ff7b00",
                    "bloqueado": False,
                })
        return elementos

    @classmethod
    def importar(cls, emf_path: str | Path, xml_path: str | Path, projeto: Projeto) -> Projeto:
        xml_doc = AudacesXMLImport.abrir(xml_path)
        emf_doc = AudacesEMFImport.abrir(emf_path)

        fator_escala_final = cls._fator_escala_calibrado(xml_doc, emf_doc)
        cls._aplicar_escala_emf_doc(emf_doc, fator_escala_final)

        projeto.nome = xml_doc.nome_modelo or projeto.nome
        if not projeto.documentos:
            projeto.documentos.append(Documento(nome="Documento 1"))
        doc = projeto.documentos[0]
        doc.moldes = []

        parser_ops = AudacesEMFImport(b"", emf_path)
        antes = {
            "elementos_emf": len(emf_doc.elementos),
            "segmentos_soltos": sum(1 for e in emf_doc.elementos if not e.fechado),
            "contorno": sum(1 for e in emf_doc.elementos if e.metadados.get("subtipo_audaces") == "contorno"),
            "costura": sum(1 for e in emf_doc.elementos if e.metadados.get("subtipo_audaces") == "costura"),
            "linha_interna": sum(1 for e in emf_doc.elementos if e.metadados.get("subtipo_audaces") == "linha_interna"),
        }
        unidos = parser_ops._unir_segmentos_em_contornos(emf_doc.elementos)
        unidos, total_contornos_principais, total_costuras, total_linhas_internas, total_ignorados = cls._classificar_contornos_unidos(unidos, xml_doc)
        reconstruidos: list = []
        for el in unidos:
            subtipo = str(el.metadados.get("subtipo_audaces") or "")
            if subtipo in {"contorno", "costura"} and len(el.pontos) >= 5:
                reconstruidos.append(parser_ops._reconstruir_curvas_do_contorno(el))
            else:
                reconstruidos.append(el)
        emf_doc.elementos = reconstruidos
        elementos_canvas = AudacesEMFImport(b"", emf_path).converter_para_elementos_guimma(emf_doc)
        depois = {
            "segmentos_unidos": parser_ops._join_stats.get("segmentos_unidos", 0),
            "contornos_fechados_encontrados": sum(1 for e in emf_doc.elementos if e.fechado),
            "contornos_classificados_como_contorno": total_contornos_principais,
            "contornos_classificados_como_costura": total_costuras,
            "contornos_classificados_como_linha_interna": total_linhas_internas,
            "contornos_ignorados": total_ignorados,
            "contornos_abertos_restantes": sum(1 for e in emf_doc.elementos if not e.fechado),
            "curvas_reconstruidas": parser_ops._join_stats.get("curvas_reconstruidas", 0),
            "elementos_canvas_final": len(elementos_canvas),
        }
        contornos = [el for el in emf_doc.elementos if el.fechado and len(el.pontos) >= 4 and el.metadados.get("subtipo_audaces") == "contorno"]
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
            parte.marcacoes.append("contorno")
            for extra in emf_doc.elementos:
                if extra is contorno:
                    continue
                subtipo = str(extra.metadados.get("subtipo_audaces") or "")
                if subtipo not in {"costura", "linha_interna", "fio", "pique"}:
                    continue
                if extra.pontos and contorno.pontos and AudacesEMFImport._ponto_em_poligono(extra.pontos[0], contorno.pontos):
                    parte.marcacoes.append(subtipo)
            molde = Molde(nome=nome, partes=[parte])
            doc.moldes.append(molde)
            aplicados += 1 if peca else 0
            if peca:
                tamanho = peca.tamanhos[0] if peca.tamanhos else None
                meta = {
                    "tecido": peca.tecido,
                    "quantidade": peca.quantidade,
                    "tamanho": tamanho.tamanho if tamanho else None,
                    "area": tamanho.area if tamanho else None,
                    "perimetro": tamanho.perimetro if tamanho else None,
                    "largura": tamanho.largura if tamanho else None,
                    "altura": tamanho.altura if tamanho else None,
                }
                parte.marcacoes.append(f"xml_meta:{json.dumps(meta, ensure_ascii=False)}")

        if len(contornos) != len(xml_doc.pecas):
            avisos.append("Alguns contornos EMF não puderam ser associados automaticamente às peças do XML.")

        projeto.preferencias_usuario["audaces_emf_xml_importacao"] = {
            "origem": "audaces_emf_xml",
            "emf_path": str(emf_path),
            "xml_path": str(xml_path),
            "vetores": len([el for el in elementos_canvas if el.get("tipo") == "polyline"]),
            "elementos_canvas_antes_uniao": antes["elementos_emf"],
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
            "segmentos_originais_lidos_emf": parser_ops._join_stats.get("segmentos_originais", 0),
            "segmentos_unidos": parser_ops._join_stats.get("segmentos_unidos", 0),
            "curvas_reconstruidas": parser_ops._join_stats.get("curvas_reconstruidas", 0),
            "contornos_abertos_restantes": depois["contornos_abertos_restantes"],
            "bounds_emf": emf_doc.bounds,
            "escala": dict(emf_doc.relatorio.get("escala", {})),
            "escala_manual_aplicada": fator_escala_final,
            "medida_guimma_referencia_mm": 544.28,
            "medida_audaces_referencia_mm": 400.17,
            "fator_escala_final": fator_escala_final,
            "unidade_resultado": "cm_calibrado_por_referencia_mm",
        }
        projeto.preferencias_usuario["audaces_emf_xml_importacao"]["diagnostico_antes"] = antes
        projeto.preferencias_usuario["audaces_emf_xml_importacao"]["diagnostico_depois"] = {
            **depois,
            "moldes_reais_criados": len(doc.moldes),
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
        if doc.moldes:
            elementos_moldes_canvas = cls._converter_moldes_para_canvas(doc.moldes)
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["elementos_canvas"] = elementos_moldes_canvas
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["canvas_origem"] = "moldes_reais"
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["canvas_moldes_renderizados"] = len(doc.moldes)
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["canvas_elementos_emf_renderizados"] = 0
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["mensagem_final"] = (
                f"Audaces EMF + XML importado: {len(doc.moldes)} moldes reais criados, "
                f"{parser_ops._join_stats.get('segmentos_unidos', 0)} contornos unidos, "
                f"{parser_ops._join_stats.get('curvas_reconstruidas', 0)} curvas reconstruídas."
            )
        else:
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["canvas_origem"] = "elementos_emf"
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["canvas_moldes_renderizados"] = 0
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["canvas_elementos_emf_renderizados"] = len(elementos_canvas)
            if depois["contornos_fechados_encontrados"] > 0:
                projeto.preferencias_usuario["audaces_emf_xml_importacao"]["mensagem_final"] = (
                    "Foram encontrados contornos fechados, mas nenhum foi classificado como molde principal. Verifique regras de classificação."
                )
            else:
                projeto.preferencias_usuario["audaces_emf_xml_importacao"]["mensagem_final"] = (
                    "Nenhum contorno fechado confiável foi encontrado. O arquivo foi importado como linhas técnicas, mas não como moldes."
                )

        elementos_crus_ignorados = max(0, antes["elementos_emf"] - len(emf_doc.elementos))
        alterou_geometria = len(unidos) != len(emf_doc.elementos) or parser_ops._join_stats.get("curvas_reconstruidas", 0) > 0
        if not alterou_geometria:
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["mensagem_diagnostico"] = "Pós-processamento não alterou geometria."
        print(f"[AUDACES_IMPORT] usando elementos processados no canvas: SIM")
        print(f"[AUDACES_IMPORT] moldes reais criados: {len(doc.moldes)}")
        print(f"[AUDACES_IMPORT] moldes no projeto.documentos[0].moldes: {len(doc.moldes)}")
        print(f"[AUDACES_IMPORT] canvas renderizando moldes reais: {'SIM' if len(doc.moldes) > 0 else 'NAO'}")
        print(f"[AUDACES_IMPORT] canvas renderizando elementos EMF crus: {'NAO' if len(doc.moldes) > 0 else 'SIM'}")
        print(f"[AUDACES_IMPORT] contornos fechados encontrados: {depois['contornos_fechados_encontrados']}")
        print(f"[AUDACES_IMPORT] elementos crus ignorados: {elementos_crus_ignorados}")

        relatorio = cls._gerar_relatorio_importacao(xml_doc, emf_doc, projeto.preferencias_usuario["audaces_emf_xml_importacao"])
        report_path = cls._salvar_relatorio_debug(relatorio)
        projeto.preferencias_usuario["audaces_emf_xml_importacao"]["debug_report_path"] = str(report_path)

        if doc.moldes:
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["mensagem_final"] = (
                f"Audaces EMF + XML importado: {len(doc.moldes)} moldes reais criados, "
                f"{parser_ops._join_stats.get('segmentos_unidos', 0)} contornos unidos, "
                f"{parser_ops._join_stats.get('curvas_reconstruidas', 0)} curvas reconstruídas."
            )
        else:
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["mensagem_final"] = (
                "Nenhum contorno fechado confiável foi encontrado. O arquivo foi importado como linhas técnicas, mas não como moldes."
            )

        elementos_crus_ignorados = max(0, antes["elementos_emf"] - len(emf_doc.elementos))
        alterou_geometria = len(unidos) != len(emf_doc.elementos) or parser_ops._join_stats.get("curvas_reconstruidas", 0) > 0
        if not alterou_geometria:
            projeto.preferencias_usuario["audaces_emf_xml_importacao"]["mensagem_diagnostico"] = "Pós-processamento não alterou geometria."
        print(f"[AUDACES_IMPORT] usando elementos processados no canvas: SIM")
        print(f"[AUDACES_IMPORT] moldes reais criados: {len(doc.moldes)}")
        print(f"[AUDACES_IMPORT] contornos fechados encontrados: {depois['contornos_fechados_encontrados']}")
        print(f"[AUDACES_IMPORT] elementos crus ignorados: {elementos_crus_ignorados}")

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
            "diagnostico_antes": info.get("diagnostico_antes", {}),
            "diagnostico_depois": info.get("diagnostico_depois", {}),
            "mensagem_final": info.get("mensagem_final"),
            "mensagem_diagnostico": info.get("mensagem_diagnostico"),
            "canvas_origem": info.get("canvas_origem"),
            "canvas_moldes_renderizados": info.get("canvas_moldes_renderizados"),
            "canvas_elementos_emf_renderizados": info.get("canvas_elementos_emf_renderizados"),
        }

    @staticmethod
    def _salvar_relatorio_debug(relatorio: dict) -> Path:
        out = Path("debug") / "audaces_emf_xml_import_report.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
        return out
