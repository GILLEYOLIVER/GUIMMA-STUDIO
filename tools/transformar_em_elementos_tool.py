from __future__ import annotations

try:  # pragma: no cover - exercitado com Qt no aplicativo
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QPen

    from tools.tool_base import FerramentaBase
except Exception:  # pragma: no cover - permite testar a conversao sem PySide6
    QPointF = None
    QColor = None
    QPen = None

    class _QtFallback:
        LeftButton = 1
        RightButton = 2
        SolidLine = 1

    Qt = _QtFallback()

    class FerramentaBase:
        def __init__(self):
            pass

        def on_activate(self, canvas):
            return None

        def set_status(self, texto: str):
            return None


class Ferramenta(FerramentaBase):
    id_ferramenta = "transformar_em_elementos"
    nome = "Converter em linha"
    usa_painel_auxiliar = False
    descricao_painel = "Converte o molde clicado em uma polyline comum no canvas."

    CHAVES_MOLDE = {
        "molde_id",
        "molde_dobrado",
        "estado_dobra",
        "referencia_dobra_original",
        "controle_cantos",
        "controle_auxiliares",
        "pontos_controle_principais",
        "pontos_auxiliares",
        "pontos_graduacao",
        "pontos_principais",
        "pontos_controle_curva",
        "pontos_controle",
        "controle_pontos",
        "pontos_controle_pique",
        "segment_ids",
        "node_ids",
        "mostrar_controles",
        "mostrar_numeros",
        "mostrar_graduacao",
        "mostrar_costura",
        "mostrar_linhas_auxiliares",
        "mostrar_fio",
        "mostrar_nome",
        "mostrar_descricao",
        "mostrar_observacoes",
        "visual_descricao",
        "visual_observacoes",
        "fio_origem",
        "fio_fim",
        "fio_angulo",
        "fio_rotulo",
        "fio_texto",
        "titulo_fio",
        "nome_fio",
        "nome_molde",
        "descricao",
        "observacoes",
        "observacao",
        "tecido",
        "quantidade",
        "ponto_texto_nome",
        "ponto_texto",
        "nome_posicao",
        "nome_centro",
        "ponto_texto_descricao",
        "ponto_texto_observacoes",
        "espessura_graduacao",
        "cor_graduacao",
    }
    PREFIXOS_MOLDE = (
        "graduacao_",
        "costura_",
        "margem_costura",
        "acabamento_",
        "pique_costura",
        "numero_",
        "texto_",
        "tam_fio",
        "tamanho_fio",
        "fonte_fio",
    )
    CHAVES_VINCULO = {
        "molde_id",
        "costura_de_molde_id",
        "molde_linha_vinculada",
        "parte_do_molde",
        "selecionavel_individual",
        "costura_graduacao",
        "graduacao_tamanho",
        "subtipo_audaces",
        "tipo_ferramenta",
        "tipo_costura",
        "posicao_costura",
    }
    PREFIXOS_VINCULO = (
        "costura_",
        "margem_costura",
        "acabamento_",
        "pique_costura",
        "graduacao_",
    )
    METADADOS_VINCULO = {
        "molde_id",
        "costura_de_molde_id",
        "tipo_ferramenta",
        "subtipo_audaces",
        "origem_nome_molde",
        "costura_graduacao",
        "graduacao_tamanho",
        "costura_segmentos",
        "tipo_costura",
        "posicao_costura",
        "pique_costura",
        "acabamento_inicial",
        "acabamento_final",
        "margem_costura_cm",
        "margem_costura_fim_cm",
        "costura_fim_ativa",
    }

    def __init__(self):
        super().__init__()
        self._hover_idx: int | None = None

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._hover_idx = None
        self._status(canvas, "Converter em linha: clique no molde para transformar em desenho comum.")

    def on_deactivate(self, canvas):
        self._hover_idx = None
        if canvas is not None and hasattr(canvas, "update"):
            canvas.update()

    def on_mouse_move(self, canvas, event) -> bool:
        pos = self._posicao_cena(canvas, event)
        self._hover_idx = self._molde_em_posicao(canvas, pos)
        if hasattr(canvas, "update"):
            canvas.update()
        return False

    def on_mouse_press(self, canvas, event) -> bool:
        botao = event.button()
        if botao == Qt.RightButton:
            if hasattr(canvas, "set_ferramenta_ativa"):
                canvas.set_ferramenta_ativa("selecionar")
            self._status(canvas, "Converter em linha finalizado. Voltando para Selecionar.")
            event.accept()
            return True
        if botao != Qt.LeftButton:
            return False

        pos = self._posicao_cena(canvas, event)
        molde_idx = self._molde_em_posicao(canvas, pos)
        if molde_idx is None:
            self._status(canvas, "Converter em linha: clique sobre um molde.")
            event.accept()
            return True

        indices = self.converter_molde_em_linhas(canvas, molde_idx)
        if not indices:
            self._status(canvas, "O item indicado nao e um molde convertivel.")
            event.accept()
            return True

        canvas._selecionados = set(indices)
        if hasattr(canvas, "_limpar_cache_runtime_elementos"):
            canvas._limpar_cache_runtime_elementos()
        if hasattr(canvas, "_invalidar_indice_vinculos"):
            canvas._invalidar_indice_vinculos()
        if hasattr(canvas, "_registrar_historico"):
            canvas._registrar_historico()
        elif hasattr(canvas, "elementos_alterados"):
            canvas.elementos_alterados.emit()
        if hasattr(canvas, "update"):
            canvas.update()
        self._hover_idx = None
        self._status(canvas, "Molde convertido em linha.")
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter) -> None:
        if QPen is None or QColor is None or self._hover_idx is None:
            return
        if not (0 <= self._hover_idx < len(canvas.cena.elementos)):
            return
        elemento = canvas.cena.elementos[self._hover_idx]
        if not isinstance(elemento, dict) or not elemento.get("molde"):
            return
        pontos = canvas._pontos_render_elemento(elemento) if hasattr(canvas, "_pontos_render_elemento") else []
        if len(pontos) < 2:
            return
        painter.save()
        painter.setPen(QPen(QColor("#00a8ff"), 1.6, Qt.SolidLine))
        if hasattr(canvas, "_desenhar_polilinha"):
            canvas._desenhar_polilinha(painter, pontos, cor="#00a8ff", espessura=1.6)
        painter.restore()

    @classmethod
    def converter_molde_em_linhas(cls, canvas, molde_idx: int) -> list[int]:
        elementos = getattr(getattr(canvas, "cena", None), "elementos", None)
        if not isinstance(elementos, list) or not (0 <= int(molde_idx) < len(elementos)):
            return []
        molde = elementos[int(molde_idx)]
        if not isinstance(molde, dict) or not molde.get("molde"):
            return []

        molde_id = cls._id_molde(molde)
        vinculados = cls._indices_vinculados(canvas, int(molde_idx), molde_id)

        cls._converter_principal(molde)
        convertidos = {int(molde_idx)}
        for idx in vinculados:
            if idx == int(molde_idx) or not (0 <= idx < len(elementos)):
                continue
            elemento = elementos[idx]
            if isinstance(elemento, dict):
                cls._converter_vinculado(elemento)
                convertidos.add(idx)
        return sorted(convertidos)

    @classmethod
    def _converter_principal(cls, molde: dict) -> None:
        molde["tipo"] = "polyline"
        molde["molde"] = False
        molde.pop("subtipo_audaces", None)
        molde.pop("parte_do_molde", None)
        molde["selecionavel_individual"] = True
        for chave in list(molde.keys()):
            if chave in cls.CHAVES_MOLDE or cls._tem_prefixo(chave, cls.PREFIXOS_MOLDE):
                molde.pop(chave, None)
        cls._limpar_metadados(molde, remover_molde=True)

    @classmethod
    def _converter_vinculado(cls, elemento: dict) -> None:
        elemento["tipo"] = "polyline"
        elemento["molde"] = False
        for chave in list(elemento.keys()):
            if chave in cls.CHAVES_VINCULO or cls._tem_prefixo(chave, cls.PREFIXOS_VINCULO):
                elemento.pop(chave, None)
        elemento["selecionavel_individual"] = True
        cls._limpar_metadados(elemento, remover_molde=False)

    @classmethod
    def _limpar_metadados(cls, elemento: dict, *, remover_molde: bool) -> None:
        metadados = elemento.get("metadados")
        if not isinstance(metadados, dict):
            return
        remover = set(cls.METADADOS_VINCULO)
        if remover_molde:
            remover.update(cls.CHAVES_MOLDE)
        for chave in list(metadados.keys()):
            if chave in remover or cls._tem_prefixo(chave, cls.PREFIXOS_MOLDE + cls.PREFIXOS_VINCULO):
                metadados.pop(chave, None)
        if not metadados:
            elemento.pop("metadados", None)

    @staticmethod
    def _id_molde(molde: dict) -> str:
        return str(molde.get("molde_id") or molde.get("id") or "").strip()

    @classmethod
    def _indices_vinculados(cls, canvas, molde_idx: int, molde_id: str) -> set[int]:
        vinculados: set[int] = set()
        if hasattr(canvas, "_indices_costuras_vinculadas"):
            try:
                vinculados.update(int(idx) for idx in canvas._indices_costuras_vinculadas(molde_idx))
            except Exception:
                pass
        elementos = getattr(getattr(canvas, "cena", None), "elementos", []) or []
        alvo = str(molde_id or "").strip()
        if not alvo:
            return vinculados
        for idx, elemento in enumerate(elementos):
            if idx == molde_idx or not isinstance(elemento, dict) or elemento.get("molde"):
                continue
            metadados = elemento.get("metadados") if isinstance(elemento.get("metadados"), dict) else {}
            ids = {
                str(elemento.get("molde_id") or "").strip(),
                str(elemento.get("costura_de_molde_id") or "").strip(),
                str(metadados.get("molde_id") or "").strip(),
                str(metadados.get("costura_de_molde_id") or "").strip(),
            }
            subtipo = str(elemento.get("subtipo_audaces") or metadados.get("subtipo_audaces") or "").strip()
            vinculado = bool(
                elemento.get("molde_linha_vinculada")
                or elemento.get("parte_do_molde")
                or str(elemento.get("costura_de_molde_id") or metadados.get("costura_de_molde_id") or "").strip()
                or subtipo in {"costura", "linha_interna", "fio", "pique", "texto", "anotacao"}
            )
            if alvo in ids and vinculado:
                vinculados.add(idx)
        return vinculados

    @staticmethod
    def _tem_prefixo(chave: object, prefixos: tuple[str, ...]) -> bool:
        nome = str(chave)
        return any(nome.startswith(prefixo) for prefixo in prefixos)

    def _molde_em_posicao(self, canvas, pos) -> int | None:
        if hasattr(canvas, "_indice_molde_em_ponto"):
            idx = canvas._indice_molde_em_ponto(pos)
            if idx is not None:
                return int(idx)
        for idx, el in enumerate(getattr(canvas.cena, "elementos", []) or []):
            if isinstance(el, dict) and el.get("molde") and self._ponto_dentro_bbox(el, pos):
                return idx
        return None

    @staticmethod
    def _posicao_cena(canvas, event):
        if hasattr(canvas, "_ponto_com_snap"):
            return canvas._ponto_com_snap(event.position())
        if QPointF is not None:
            return QPointF(event.position())
        return event.position()

    @staticmethod
    def _ponto_dentro_bbox(molde: dict, pos) -> bool:
        pontos = molde.get("pontos") or []
        coords = []
        for item in pontos:
            try:
                if isinstance(item, dict):
                    coords.append((float(item["x"]), float(item["y"])))
                else:
                    coords.append((float(item[0]), float(item[1])))
            except Exception:
                continue
        if not coords:
            return False
        x = pos.x() if hasattr(pos, "x") else float(pos[0])
        y = pos.y() if hasattr(pos, "y") else float(pos[1])
        xs = [p[0] for p in coords]
        ys = [p[1] for p in coords]
        return min(xs) <= float(x) <= max(xs) and min(ys) <= float(y) <= max(ys)

    def _status(self, canvas, texto: str) -> None:
        self.set_status(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)
