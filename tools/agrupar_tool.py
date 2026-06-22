from __future__ import annotations

from copy import deepcopy
from math import hypot, isfinite

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen

from canvas.visualizacao import VisualizacaoCanvas
from tools.elemento_runtime_utils import copiar_elemento_sem_runtime
from tools.tool_base import FerramentaBase


class Ferramenta(FerramentaBase):
    id_ferramenta = "agrupar"
    nome = "Agrupar"
    descricao_painel = "Reagrupa a graduação do molde pelo ponto indicado."

    EPS = 1e-7

    def __init__(self):
        super().__init__()
        self._hover_alvo: tuple[int, int] | None = None
        self._preview_original: dict | None = None
        self._preview_alvo: tuple[int, int] | None = None
        self._aguardando_largar = False

    def on_activate(self, canvas):
        super().on_activate(canvas)
        self._limpar_estado()
        self._status(canvas, "Agrupar: passe sobre o ponto que deve virar 0 DX / 0 DY; esquerdo confirma.")

    def on_deactivate(self, canvas):
        self._cancelar_preview(canvas, atualizar=True)
        self._limpar_estado()
        if hasattr(canvas, "update"):
            canvas.update()

    def on_mouse_move(self, canvas, event) -> bool:
        pos = self._pos_cena(canvas, event.position())
        alvo = self._molde_e_ponto_em_posicao(canvas, pos)
        self._hover_alvo = alvo
        if alvo is not None:
            self._aplicar_preview(canvas, alvo[0], alvo[1])
        elif self._preview_original is not None:
            self._cancelar_preview(canvas, atualizar=False)
        if hasattr(canvas, "update"):
            canvas.update()
        event.accept()
        return True

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() == Qt.RightButton:
            if self._preview_original is not None:
                self._cancelar_preview(canvas, atualizar=True)
                self._aguardando_largar = True
                self._status(canvas, "Agrupar cancelado. Clique direito novamente para largar a ferramenta.")
                event.accept()
                return True
            if self._aguardando_largar:
                canvas.set_ferramenta_ativa("selecionar")
                self._status(canvas, "Agrupar finalizado. Voltando para Selecionar.")
                event.accept()
                return True
            canvas.set_ferramenta_ativa("selecionar")
            self._status(canvas, "Agrupar finalizado. Voltando para Selecionar.")
            event.accept()
            return True
        if event.button() != Qt.LeftButton:
            return False

        if self._preview_original is None:
            pos = self._pos_cena(canvas, event.position())
            alvo = self._molde_e_ponto_em_posicao(canvas, pos)
            if alvo is None and hasattr(canvas, "_ponto_com_snap"):
                alvo = self._molde_e_ponto_em_posicao(canvas, canvas._ponto_com_snap(event.position()))
            if alvo is None:
                if self._tamanho_separado_em_posicao(canvas, pos):
                    self._status(canvas, "Agrupar atua no molde graduado; tamanhos separados não voltam ao molde de origem.")
                else:
                    self._status(canvas, "Agrupar: passe ou clique diretamente em um ponto de um molde graduado.")
                event.accept()
                return True
            self._aplicar_preview(canvas, alvo[0], alvo[1])

        if self._preview_original is None or self._preview_alvo is None:
            self._status(canvas, "Agrupar: nenhum ponto válido para confirmar.")
            event.accept()
            return True

        molde_idx, ponto_idx = self._preview_alvo
        if hasattr(canvas, "_registrar_historico"):
            canvas._registrar_historico()
        elif hasattr(canvas, "elementos_alterados"):
            canvas.elementos_alterados.emit()
        if hasattr(canvas, "_selecionados"):
            canvas._selecionados = {int(molde_idx)}
        self._preview_original = None
        self._preview_alvo = None
        self._aguardando_largar = False
        if hasattr(canvas, "update"):
            canvas.update()
        self._status(canvas, f"Graduação agrupada no ponto {ponto_idx + 1}: DX 0 / DY 0.")
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        if self._hover_alvo is None:
            return
        molde_idx, ponto_idx = self._hover_alvo
        if not (0 <= int(molde_idx) < len(canvas.cena.elementos)):
            return
        pontos = self._pontos_contorno(canvas.cena.elementos[int(molde_idx)])
        if not (0 <= int(ponto_idx) < len(pontos)):
            return
        try:
            tela = canvas._cena_para_tela(pontos[int(ponto_idx)])
        except Exception:
            return
        painter.save()
        cor = QColor("#00d6ff")
        painter.setPen(QPen(cor, 2.4))
        painter.setBrush(QColor(0, 214, 255, 70))
        painter.drawEllipse(tela, 9.0, 9.0)
        painter.restore()

    def _aplicar_preview(self, canvas, molde_idx: int, ponto_idx: int) -> bool:
        alvo = (int(molde_idx), int(ponto_idx))
        if self._preview_alvo == alvo and self._preview_original is not None:
            return True

        if self._preview_original is not None:
            self._restaurar_preview(canvas, atualizar=False)

        if not (0 <= alvo[0] < len(canvas.cena.elementos)):
            return False
        self._preview_original = {
            "molde_idx": alvo[0],
            "elemento": copiar_elemento_sem_runtime(canvas.cena.elementos[alvo[0]]),
            "selecionados": set(getattr(canvas, "_selecionados", set()) or set()),
        }
        self._preview_alvo = alvo
        self._aguardando_largar = False
        if not self._agrupar_molde_no_ponto(canvas, alvo[0], alvo[1], registrar_historico=False):
            self._restaurar_preview(canvas, atualizar=True)
            return False
        self._status(canvas, f"Prévia no ponto {alvo[1] + 1}: esquerdo confirma, direito cancela.")
        return True

    def _cancelar_preview(self, canvas, *, atualizar: bool) -> bool:
        cancelou = self._restaurar_preview(canvas, atualizar=atualizar)
        self._hover_alvo = None
        return cancelou

    def _restaurar_preview(self, canvas, *, atualizar: bool) -> bool:
        original = self._preview_original
        self._preview_original = None
        self._preview_alvo = None
        if not isinstance(original, dict):
            return False
        molde_idx = int(original.get("molde_idx", -1))
        if 0 <= molde_idx < len(canvas.cena.elementos):
            canvas.cena.elementos[molde_idx] = copiar_elemento_sem_runtime(
                original.get("elemento", canvas.cena.elementos[molde_idx])
            )
        if hasattr(canvas, "_selecionados"):
            canvas._selecionados = set(original.get("selecionados", set()) or set())
        if atualizar and hasattr(canvas, "update"):
            canvas.update()
        return True

    def _limpar_estado(self) -> None:
        self._hover_alvo = None
        self._preview_original = None
        self._preview_alvo = None
        self._aguardando_largar = False

    def _agrupar_molde_no_ponto(self, canvas, molde_idx: int, ponto_idx: int, *, registrar_historico: bool = True) -> bool:
        if not (0 <= int(molde_idx) < len(canvas.cena.elementos)):
            return False
        molde = canvas.cena.elementos[int(molde_idx)]
        if not self._eh_molde_graduavel(molde):
            self._status(canvas, "Agrupar: o ponto indicado não pertence a um molde graduável.")
            return False

        pontos = self._pontos_contorno(molde)
        total = len(pontos)
        if total < 2 or not (0 <= int(ponto_idx) < total):
            self._status(canvas, "Agrupar: ponto inválido para este molde.")
            return False

        tamanhos = self._linhas_tamanhos(molde)
        if len(tamanhos) < 2:
            self._status(canvas, "Agrupar: este molde não possui tamanhos graduados para reagrupar.")
            return False

        pontos_cfg_original = self._pontos_cfg_graduacao(molde)
        if self._graduacao_dxf_agrupada_usa_pontos_principais(molde):
            pontos_cfg_original = self._filtrar_pontos_cfg_para_pontos(pontos_cfg_original, pontos)
        if not pontos_cfg_original:
            self._status(canvas, "Agrupar: este molde ainda não possui tabela de graduação.")
            return False

        nomes = [self._nome_tamanho(linha) for linha in tamanhos]
        if not any(nome for nome in nomes):
            self._status(canvas, "Agrupar: tamanhos da graduação sem nome.")
            return False

        referencias = VisualizacaoCanvas._pontos_referencia_graduacao(molde)
        deslocamentos_por_tamanho: dict[str, list[tuple[float, float]]] = {}
        for linha, nome in zip(tamanhos, nomes):
            if not nome:
                continue
            if bool(linha.get("base", False)):
                deslocamentos_por_tamanho[nome] = [(0.0, 0.0) for _ in range(total)]
                continue
            deslocamentos = VisualizacaoCanvas._deslocamentos_graduacao_tamanho(
                pontos_cfg_original,
                nome,
                total,
                contorno=pontos,
                referencias=referencias,
            )
            if not deslocamentos:
                deslocamentos = [(0.0, 0.0) for _ in range(total)]
            deslocamentos_por_tamanho[nome] = deslocamentos

        nova_cfg: dict[str, dict] = {}
        for idx, ponto in enumerate(pontos):
            valores: dict[str, dict[str, float]] = {}
            for nome in nomes:
                if not nome:
                    continue
                deslocamentos = deslocamentos_por_tamanho.get(nome) or [(0.0, 0.0) for _ in range(total)]
                dx_base, dy_base = deslocamentos[int(ponto_idx)]
                dx_atual, dy_atual = deslocamentos[idx]
                valores[nome] = {
                    "dx": self._zero_pequeno(dx_atual - dx_base),
                    "dy": self._zero_pequeno(dy_atual - dy_base),
                }
            nova_cfg[str(idx)] = {
                "indice": int(idx),
                "numero": int(idx) + 1,
                "ponto": (float(ponto.x()), float(ponto.y())),
                "valores": valores,
            }

        tabela = deepcopy(molde.get("graduacao_tabela")) if isinstance(molde.get("graduacao_tabela"), dict) else {}
        tabela["modo"] = "dx_dy"
        if self._graduacao_dxf_agrupada_usa_pontos_principais(molde):
            tabela["pontos_principais_apenas"] = True
        tabela["pontos"] = nova_cfg
        molde["graduacao_tabela"] = tabela
        molde["graduacao_pontos"] = deepcopy(nova_cfg)
        molde["graduacao_tamanhos_ativos"] = [nome for nome in nomes if nome]
        molde["mostrar_graduacao"] = True
        molde["graduacao_preferir_tabela_dxdy"] = True
        molde["graduacao_renderizar_por_tabela_derivada"] = False

        if registrar_historico and hasattr(canvas, "_registrar_historico"):
            canvas._registrar_historico()
        elif registrar_historico and hasattr(canvas, "elementos_alterados"):
            canvas.elementos_alterados.emit()
        if hasattr(canvas, "_selecionados"):
            canvas._selecionados = {int(molde_idx)}
        if hasattr(canvas, "update"):
            canvas.update()
        return True

    def _molde_e_ponto_em_posicao(self, canvas, pos: QPointF) -> tuple[int, int] | None:
        melhor: tuple[float, int, int] | None = None
        tolerancia = max(0.18, 24.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001))
        for idx, molde in enumerate(getattr(canvas.cena, "elementos", []) or []):
            if not self._eh_molde_graduavel(molde):
                continue
            for pontos in self._contornos_para_clique(molde):
                if len(pontos) < 2:
                    continue
                dist, ponto_idx = min((self._dist(ponto, pos), p_idx) for p_idx, ponto in enumerate(pontos))
                if dist <= tolerancia and (melhor is None or dist < melhor[0]):
                    melhor = (dist, int(idx), int(ponto_idx))
        if melhor is None:
            return None
        return melhor[1], melhor[2]

    def _contornos_para_clique(self, molde: dict) -> list[list[QPointF]]:
        base = self._pontos_contorno(molde)
        if not base:
            return []
        contornos = [base]
        for _nome, _cor, pontos in VisualizacaoCanvas._contornos_graduacao_tabela(molde, base):
            aberto = self._abrir_contorno([QPointF(p) for p in pontos])
            if len(aberto) == len(base):
                contornos.append(aberto)
        return contornos

    def _tamanho_separado_em_posicao(self, canvas, pos: QPointF) -> bool:
        tolerancia = max(0.18, 24.0 / max(float(getattr(canvas, "zoom", 1.0)), 0.001))
        for molde in getattr(canvas.cena, "elementos", []) or []:
            if not self._eh_tamanho_separado(molde):
                continue
            pontos = self._pontos_contorno(molde, permitir_separado=True)
            if not pontos:
                continue
            if min(self._dist(ponto, pos) for ponto in pontos) <= tolerancia:
                return True
        return False

    def _pontos_cfg_graduacao(self, molde: dict) -> dict:
        tabela = molde.get("graduacao_tabela")
        if isinstance(tabela, dict) and isinstance(tabela.get("pontos"), dict):
            return deepcopy(tabela.get("pontos") or {})
        legado = molde.get("graduacao_pontos")
        if isinstance(legado, dict):
            return deepcopy(legado)
        return {}

    def _pontos_contorno(self, molde: dict | None, *, permitir_separado: bool = False) -> list[QPointF]:
        if not self._eh_molde_graduavel(molde, permitir_separado=permitir_separado):
            return []
        tabela = molde.get("graduacao_tabela") if isinstance(molde, dict) else None
        pontos_tabela = tabela.get("pontos") if isinstance(tabela, dict) else None
        controles = molde.get("pontos_controle_principais") or molde.get("controle_cantos") or []
        usar_principais = self._graduacao_dxf_agrupada_usa_pontos_principais(molde)
        preferir_base = bool(
            not usar_principais
            and (
                molde.get("graduacao_preferir_tabela_dxdy")
                or (
                    isinstance(pontos_tabela, dict)
                    and isinstance(controles, list)
                    and len(pontos_tabela) > len(controles)
                )
            )
        )
        origem = None
        if usar_principais:
            chaves = ("pontos_controle_principais", "controle_cantos", "pontos_controle", "pontos")
        elif preferir_base:
            chaves = ("pontos", "pontos_controle_principais", "controle_cantos", "pontos_graduacao", "pontos_controle_curva", "pontos_controle")
        else:
            chaves = ("pontos_controle_principais", "controle_cantos", "pontos_graduacao", "pontos_controle_curva", "pontos_controle", "pontos")
        for chave in chaves:
            valor = molde.get(chave)
            if isinstance(valor, list) and valor:
                origem = valor
                break
        pontos = [p for p in (self._ponto_qt(item) for item in origem or []) if p is not None]
        return self._abrir_contorno(pontos)

    @staticmethod
    def _graduacao_dxf_agrupada_usa_pontos_principais(molde: dict | None) -> bool:
        if not isinstance(molde, dict):
            return False
        if molde.get("graduacao_tabela_apenas_pontos_principais"):
            return True
        if str(molde.get("origem") or "").strip() == "dxf_matriz_graduada":
            return True
        metadados = molde.get("metadados") if isinstance(molde.get("metadados"), dict) else {}
        return bool(metadados.get("matriz_tamanhos_dxf"))

    @classmethod
    def _filtrar_pontos_cfg_para_pontos(cls, pontos_cfg: dict | None, pontos: list[QPointF]) -> dict:
        if not isinstance(pontos_cfg, dict) or not pontos:
            return {}
        xs = [p.x() for p in pontos]
        ys = [p.y() for p in pontos]
        diagonal = hypot(max(xs) - min(xs), max(ys) - min(ys)) if xs and ys else 0.0
        tolerancia = max(1e-6, diagonal * 0.001)
        saida: dict[str, dict] = {}
        ocupados: set[int] = set()
        for chave, cfg in sorted(pontos_cfg.items(), key=lambda item: str(item[0])):
            if not isinstance(cfg, dict):
                continue
            ponto_cfg = cls._ponto_qt(cfg.get("ponto"))
            idx = None
            if ponto_cfg is not None:
                dist, idx_candidato = min(
                    (cls._dist(ponto_cfg, ponto), p_idx)
                    for p_idx, ponto in enumerate(pontos)
                )
                if dist <= tolerancia:
                    idx = int(idx_candidato)
            if idx is None and ponto_cfg is None:
                try:
                    idx_cfg = int(cfg.get("indice", chave))
                except Exception:
                    idx_cfg = -1
                if 0 <= idx_cfg < len(pontos):
                    idx = int(idx_cfg)
            if idx is None or idx in ocupados:
                continue
            ocupados.add(idx)
            novo = deepcopy(cfg)
            novo["indice"] = int(idx)
            novo["numero"] = int(idx) + 1
            novo["ponto"] = (float(pontos[idx].x()), float(pontos[idx].y()))
            saida[str(idx)] = novo
        return saida

    def _linhas_tamanhos(self, molde: dict) -> list[dict]:
        linhas = molde.get("graduacao_tamanhos")
        if not isinstance(linhas, list):
            return []
        return [dict(linha) for linha in linhas if isinstance(linha, dict) and linha.get("ativo", True)]

    @staticmethod
    def _nome_tamanho(linha: dict) -> str:
        return str(linha.get("tamanho") or linha.get("nome") or "").strip()

    def _eh_molde_graduavel(self, elemento, *, permitir_separado: bool = False) -> bool:
        if not isinstance(elemento, dict) or not elemento.get("molde"):
            return False
        if self._eh_tamanho_separado(elemento) and not permitir_separado:
            return False
        tipo = str(elemento.get("tipo") or "").strip().lower()
        return not tipo or tipo in {"polyline", "molde"}

    @staticmethod
    def _eh_tamanho_separado(elemento) -> bool:
        if not isinstance(elemento, dict):
            return False
        return str(elemento.get("origem_extracao") or "").strip() == "separar_tamanho"

    def _abrir_contorno(self, pontos: list[QPointF]) -> list[QPointF]:
        saida = [QPointF(p) for p in pontos]
        if len(saida) > 1 and self._dist(saida[0], saida[-1]) <= self.EPS:
            saida.pop()
        return saida

    @staticmethod
    def _ponto_qt(valor) -> QPointF | None:
        try:
            if isinstance(valor, QPointF):
                x, y = valor.x(), valor.y()
            elif isinstance(valor, dict):
                x, y = valor["x"], valor["y"]
            elif isinstance(valor, (list, tuple)) and len(valor) >= 2:
                x, y = valor[0], valor[1]
            else:
                return None
            x = float(x)
            y = float(y)
            if not isfinite(x) or not isfinite(y):
                return None
            return QPointF(x, y)
        except Exception:
            return None

    @staticmethod
    def _pos_cena(canvas, pos) -> QPointF:
        ponto = QPointF(pos)
        if hasattr(canvas, "_tela_para_cena"):
            try:
                return QPointF(canvas._tela_para_cena(ponto))
            except Exception:
                pass
        return ponto

    @staticmethod
    def _dist(a: QPointF, b: QPointF) -> float:
        return hypot(a.x() - b.x(), a.y() - b.y())

    @staticmethod
    def _zero_pequeno(valor: float) -> float:
        valor = float(valor)
        return 0.0 if abs(valor) <= 1e-9 else valor

    def _status(self, canvas, texto: str) -> None:
        self.set_status(texto)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(texto)
