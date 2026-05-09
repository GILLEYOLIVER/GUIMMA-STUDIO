from __future__ import annotations

from math import atan2, degrees

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QFormLayout, QLineEdit

from tools.tool_base import FerramentaBase
from ui.posicao_janelas import instalar_memoria_posicao, restaurar_posicao


class Ferramenta(FerramentaBase):
    id_ferramenta = "manipular_pontos"
    nome = "Manipular Pontos"
    _dlg_global: QDialog | None = None
    _edt_dx_global: QLineEdit | None = None
    _edt_dy_global: QLineEdit | None = None
    _cmb_n_pontos_global: QComboBox | None = None
    _chk_discreto_global: QCheckBox | None = None

    def __init__(self):
        super().__init__()
        self._arrastando_ponto_poly: tuple[int, int] | None = None
        self._arrastando_controle_molde: tuple[int, str, int] | None = None
        self._hover_ponto_poly: tuple[int, int] | None = None
        self._hover_controle_molde: tuple[int, str, int] | None = None
        self._hover_elemento_idx: int | None = None
        self._hover_molde_idx: int | None = None
        self._guia_ponto_poly: tuple[QPointF, QPointF | None, QPointF | None] | None = None
        self._angulo_info: tuple[QPointF, QPointF, QPointF, float] | None = None
        self._ponto_selecionado: tuple[int, int] | None = None
        self._dlg_passo: QDialog | None = Ferramenta._dlg_global
        self._edt_dx: QLineEdit | None = Ferramenta._edt_dx_global
        self._edt_dy: QLineEdit | None = Ferramenta._edt_dy_global
        self._cmb_n_pontos: QComboBox | None = Ferramenta._cmb_n_pontos_global
        self._chk_discreto: QCheckBox | None = Ferramenta._chk_discreto_global

    def on_activate(self, canvas):
        self._arrastando_ponto_poly = None
        self._arrastando_controle_molde = None
        self._hover_ponto_poly = None
        self._hover_controle_molde = None
        self._hover_elemento_idx = None
        self._hover_molde_idx = None
        self._guia_ponto_poly = None
        self._angulo_info = None
        self._ponto_selecionado = None
        self._abrir_caixa_passo(canvas)
        self.set_status("Mover ponto: ajuste DX/DY, escolha 1 ponto ou N pontos e clique no vértice.")

    def on_deactivate(self, canvas):
        if self._dlg_passo:
            self._dlg_passo.hide()

    def on_canvas_resize(self, canvas) -> None:
        self._reposicionar_caixa_passo(canvas)

    def _abrir_caixa_passo(self, canvas):
        if Ferramenta._dlg_global is not None:
            try:
                Ferramenta._dlg_global.isVisible()
            except RuntimeError:
                Ferramenta._dlg_global = None
                Ferramenta._edt_dx_global = None
                Ferramenta._edt_dy_global = None
                Ferramenta._cmb_n_pontos_global = None
                Ferramenta._chk_discreto_global = None
        if Ferramenta._dlg_global is None:
            Ferramenta._dlg_global = QDialog(canvas)
            Ferramenta._dlg_global.setObjectName("guimma_mover_ponto_dialog")
            Ferramenta._dlg_global.setWindowTitle("Mover ponto")
            Ferramenta._dlg_global.setWindowFlags(Qt.Tool)
            lay = QFormLayout(Ferramenta._dlg_global)
            Ferramenta._edt_dx_global = QLineEdit("0")
            Ferramenta._edt_dy_global = QLineEdit("0")
            Ferramenta._cmb_n_pontos_global = QComboBox()
            Ferramenta._cmb_n_pontos_global.addItems(["1 ponto", "N pontos"])
            Ferramenta._chk_discreto_global = QCheckBox("Discreto")
            lay.addRow("DX (cm)", Ferramenta._edt_dx_global)
            lay.addRow("DY (cm)", Ferramenta._edt_dy_global)
            lay.addRow("Nº pontos", Ferramenta._cmb_n_pontos_global)
            lay.addRow("", Ferramenta._chk_discreto_global)
            Ferramenta._dlg_global.setFixedWidth(210)
            instalar_memoria_posicao(Ferramenta._dlg_global, "dialog:manipular_pontos")
        self._dlg_passo = Ferramenta._dlg_global
        self._edt_dx = Ferramenta._edt_dx_global
        self._edt_dy = Ferramenta._edt_dy_global
        self._cmb_n_pontos = Ferramenta._cmb_n_pontos_global
        self._chk_discreto = Ferramenta._chk_discreto_global
        if not self._dlg_passo.isVisible():
            self._dlg_passo.show()
        self._reposicionar_caixa_passo(canvas)

    def _reposicionar_caixa_passo(self, canvas):
        if not self._dlg_passo:
            return
        if hasattr(canvas, "calcular_posicao_painel_auxiliar"):
            pos_local = canvas.calcular_posicao_painel_auxiliar(
                self._dlg_passo.width(),
                self._dlg_passo.height(),
                abaixo_coordenadas=True,
            )
            restaurar_posicao(self._dlg_passo, "dialog:manipular_pontos", fallback=canvas.mapToGlobal(pos_local))

    def _ler_delta_configurado(self) -> tuple[float, float]:
        try:
            dx = float((self._edt_dx.text() if self._edt_dx else "0").replace(",", "."))
        except Exception:
            dx = 0.0
        try:
            dy = float((self._edt_dy.text() if self._edt_dy else "0").replace(",", "."))
        except Exception:
            dy = 0.0
        return dx, dy

    def _modo_n_pontos(self) -> bool:
        if not self._cmb_n_pontos:
            return False
        return self._cmb_n_pontos.currentText().strip().lower() == "n pontos"

    def _modo_discreto(self) -> bool:
        return bool(self._chk_discreto.isChecked()) if self._chk_discreto else False

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())

        controle = self._controle_molde_em_ponto(canvas, pos)
        if controle is not None:
            self._arrastando_controle_molde = controle
            self._hover_controle_molde = controle
            self._hover_molde_idx = controle[0]
            self._ponto_selecionado = None
            event.accept()
            canvas.update()
            return True

        ponto_poly = self._ponto_polilinha_em_ponto(canvas, pos)
        if ponto_poly is None:
            return False
        idx, p_idx = ponto_poly
        self._arrastando_ponto_poly = (idx, p_idx)
        self._ponto_selecionado = (idx, p_idx)
        self._hover_ponto_poly = (idx, p_idx)
        dx, dy = self._ler_delta_configurado()
        if abs(dx) > 1e-9 or abs(dy) > 1e-9:
            delta_x = dx
            # Convenção solicitada: DY negativo move para baixo, DY positivo para cima.
            delta_y = -dy
            el = canvas.cena.elementos[idx]
            pontos = el.get("pontos", [])
            if 0 <= p_idx < len(pontos):
                x, y = pontos[p_idx]
                destino = QPointF(float(x) + delta_x, float(y) + delta_y)
                if self._modo_discreto():
                    destino = QPointF(round(destino.x(), 2), round(destino.y(), 2))
                self._atualizar_ponto(canvas, idx, p_idx, destino)
                self._mover_ponto_proporcional(canvas, idx, p_idx, delta_x, delta_y, mover_n_pontos=self._modo_n_pontos())
                canvas._registrar_historico()
        self._guia_ponto_poly = self._gerar_guia(canvas, idx, p_idx)
        canvas.update()
        event.accept()
        return True

    def _mover_ponto_proporcional(self, canvas, idx: int, p_idx: int, dx: float, dy: float, mover_n_pontos: bool = False):
        if not (0 <= idx < len(canvas.cena.elementos)):
            return
        el = canvas.cena.elementos[idx]
        pontos = list(el.get("pontos", []))
        pontos_anteriores = list(pontos)
        if len(pontos) < 3:
            return
        fechado = len(pontos) >= 2 and canvas._dist(QPointF(float(pontos[0][0]), float(pontos[0][1])), QPointF(float(pontos[-1][0]), float(pontos[-1][1]))) <= 1e-6
        n = len(pontos) - 1 if fechado else len(pontos)
        if n < 2:
            return

        if mover_n_pontos and el.get("molde") and self._mover_molde_n_pontos(canvas, el, p_idx, dx, dy):
            pontos = list(el.get("pontos", []))
        elif mover_n_pontos:
            alcance = max(2, n // 2)
            for i in range(n):
                if i == p_idx:
                    continue
                if fechado:
                    dist_passos = min((i - p_idx) % n, (p_idx - i) % n)
                else:
                    dist_passos = abs(i - p_idx)
                peso = max(0.0, 1.0 - (dist_passos / float(alcance + 1)))
                if peso <= 0.0:
                    continue
                fator = 0.60 * peso
                x, y = pontos[i]
                nx = float(x) + (dx * fator)
                ny = float(y) + (dy * fator)
                if self._modo_discreto():
                    nx = round(nx, 2)
                    ny = round(ny, 2)
                pontos[i] = (nx, ny)
        else:
            # Modo "1 ponto": move exclusivamente o ponto clicado.
            # (o deslocamento do ponto selecionado já foi aplicado em _atualizar_ponto)
            if el.get("molde"):
                # Reajusta apenas os pontos intermediários/auxiliares para que não
                # "segurem" a linha quando um ponto principal é movido.
                self._mover_molde_n_pontos(canvas, el, p_idx, dx, dy)
                pontos = list(el.get("pontos", []))

        if fechado and len(pontos) >= 2:
            pontos[-1] = pontos[0]
        el["pontos"] = pontos
        if el.get("molde"):
            for antigo, novo in zip(pontos_anteriores, pontos):
                anterior_pt = QPointF(float(antigo[0]), float(antigo[1]))
                novo_pt = QPointF(float(novo[0]), float(novo[1]))
                if canvas._dist(anterior_pt, novo_pt) > 1e-9:
                    self._mover_controles_correspondentes(canvas, el, anterior_pt, novo_pt)
            self._reajustar_fio_no_molde(el)

    def _mover_molde_n_pontos(self, canvas, el: dict, p_idx: int, dx: float, dy: float) -> bool:
        pontos_base = list(el.get("pontos", []))
        if len(pontos_base) < 4:
            return False
        fechado = len(pontos_base) >= 2 and canvas._dist(
            QPointF(float(pontos_base[0][0]), float(pontos_base[0][1])),
            QPointF(float(pontos_base[-1][0]), float(pontos_base[-1][1])),
        ) <= 1e-6
        n = len(pontos_base) - 1 if fechado else len(pontos_base)
        if not (0 <= p_idx < n):
            return False

        principais = sorted(i for i in self._indices_pontos_principais_molde(canvas, el) if 0 <= i < n)
        if len(principais) < 2 or p_idx not in principais:
            return False

        # No modo N pontos do molde, apenas o ponto principal selecionado
        # recebe deslocamento direto. Os demais principais ficam estáveis e
        # os pontos intermediários são redistribuídos proporcionalmente.
        disp_principais: dict[int, tuple[float, float]] = {p_idx: (dx, dy)}
        for p in principais:
            if p == p_idx:
                continue
            disp_principais[p] = (0.0, 0.0)

        novos = list(pontos_base)
        for p in principais:
            if p == p_idx:
                continue
            ddx, ddy = disp_principais[p]
            x, y = pontos_base[p]
            nx = float(x) + ddx
            ny = float(y) + ddy
            if self._modo_discreto():
                nx = round(nx, 2)
                ny = round(ny, 2)
            novos[p] = (nx, ny)

        pares: list[tuple[int, int]] = []
        if fechado:
            for i, a in enumerate(principais):
                b = principais[(i + 1) % len(principais)]
                pares.append((a, b))
        else:
            pares.extend((a, b) for a, b in zip(principais, principais[1:]))

        for a, b in pares:
            indices = self._indices_intervalo(a, b, n, fechado)
            if len(indices) <= 2:
                continue
            dxa, dya = disp_principais.get(a, (0.0, 0.0))
            dxb, dyb = disp_principais.get(b, (0.0, 0.0))
            denom = max(1, len(indices) - 1)
            for pos, idx_local in enumerate(indices[1:-1], start=1):
                t = max(0.0, min(1.0, pos / float(denom)))
                ddx = (dxa * (1.0 - t)) + (dxb * t)
                ddy = (dya * (1.0 - t)) + (dyb * t)
                nx = float(pontos_base[idx_local][0]) + ddx
                ny = float(pontos_base[idx_local][1]) + ddy
                if self._modo_discreto():
                    nx = round(nx, 2)
                    ny = round(ny, 2)
                novos[idx_local] = (nx, ny)

        if fechado and len(novos) >= 2:
            novos[-1] = novos[0]
        el["pontos"] = novos
        return True

    def _indices_intervalo(self, a: int, b: int, n: int, fechado: bool) -> list[int]:
        if n <= 0:
            return []
        if not fechado:
            if a <= b:
                return list(range(a, b + 1))
            return list(range(b, a + 1))
        out = [a]
        i = a
        while i != b:
            i = (i + 1) % n
            out.append(i)
            if len(out) > (n + 1):
                break
        return out

    def on_mouse_move(self, canvas, event) -> bool:
        pos = canvas._ponto_com_snap(event.position())
        if self._arrastando_controle_molde is not None:
            idx, tipo, controle_idx = self._arrastando_controle_molde
            self._arrastar_controle_molde(canvas, idx, tipo, controle_idx, pos)
            self._hover_controle_molde = self._arrastando_controle_molde
            self._hover_molde_idx = idx
            canvas.update()
            event.accept()
            return True

        if self._arrastando_ponto_poly is not None:
            idx, p_idx = self._arrastando_ponto_poly
            self._atualizar_ponto(canvas, idx, p_idx, pos)
            self._guia_ponto_poly = self._gerar_guia(canvas, idx, p_idx)
            self._atualizar_info_angulo(canvas, idx, p_idx, pos)
            canvas.update()
            event.accept()
            return True

        self._hover_ponto_poly = self._ponto_polilinha_em_ponto(canvas, pos)
        self._hover_controle_molde = self._controle_molde_em_ponto(canvas, pos)
        self._hover_molde_idx = self._hover_controle_molde[0] if self._hover_controle_molde is not None else None
        self._hover_elemento_idx = self._elemento_em_hover(canvas, pos)
        canvas.update()
        event.accept()
        return True

    def on_mouse_release(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        if self._arrastando_ponto_poly is None and self._arrastando_controle_molde is None:
            return False
        self._arrastando_ponto_poly = None
        self._arrastando_controle_molde = None
        self._guia_ponto_poly = None
        canvas._registrar_historico()
        canvas.update()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        self._desenhar_molde_em_manipulacao(canvas, painter)
        self._desenhar_controles_molde_hover(canvas, painter)
        self._desenhar_guia(canvas, painter)
        self._desenhar_hover(canvas, painter)
        self._desenhar_angulo(canvas, painter)

    def _ponto_polilinha_em_ponto(self, canvas, ponto: QPointF) -> tuple[int, int] | None:
        tolerancia = 8.0 / max(canvas.zoom, 0.001)
        candidatos = sorted(canvas._selecionados) if canvas._selecionados else list(range(len(canvas.cena.elementos)))
        for idx in candidatos:
            if idx < 0 or idx >= len(canvas.cena.elementos):
                continue
            el = canvas.cena.elementos[idx]
            if el.get("tipo") != "polyline":
                continue
            pontos = el.get("pontos", [])
            if el.get("molde"):
                indices_permitidos = self._indices_pontos_principais_molde(canvas, el)
                if not indices_permitidos:
                    continue
                indices_para_testar = sorted(indices_permitidos)
            else:
                indices_para_testar = range(len(pontos))
            for p_idx in indices_para_testar:
                if not (0 <= p_idx < len(pontos)):
                    continue
                x, y = pontos[p_idx]
                if canvas._dist(QPointF(float(x), float(y)), ponto) <= tolerancia:
                    return idx, p_idx
        return None

    def _indices_pontos_principais_molde(self, canvas, el: dict) -> set[int]:
        """
        Em moldes, a ferramenta Mover ponto deve operar apenas em pontos principais
        (controle_cantos), ignorando pontos auxiliares intermediários do contorno.
        """
        pontos = list(el.get("pontos", []))
        if not pontos:
            return set()
        fechado = len(pontos) >= 2 and canvas._dist(
            QPointF(float(pontos[0][0]), float(pontos[0][1])),
            QPointF(float(pontos[-1][0]), float(pontos[-1][1])),
        ) <= 1e-6
        n_base = len(pontos) - 1 if fechado else len(pontos)
        if n_base <= 0:
            return set()

        controles = el.get("controle_cantos", []) or []
        if not controles:
            return set(range(n_base))

        tol = 8.0 / max(canvas.zoom, 0.001)
        usados: set[int] = set()
        indices: set[int] = set()
        for item in controles:
            cp = self._ponto_qt(item)
            if cp is None:
                continue
            melhor_idx = -1
            melhor_dist = float("inf")
            for i in range(n_base):
                x, y = pontos[i]
                if i in usados:
                    continue
                dist = canvas._dist(cp, QPointF(float(x), float(y)))
                if dist < melhor_dist:
                    melhor_dist = dist
                    melhor_idx = i
            if melhor_idx >= 0 and melhor_dist <= tol:
                indices.add(melhor_idx)
                usados.add(melhor_idx)
        return {i for i in indices if 0 <= i < n_base}

    def _controle_molde_em_ponto(self, canvas, ponto: QPointF) -> tuple[int, str, int] | None:
        tolerancia = 8.0 / max(canvas.zoom, 0.001)
        melhor: tuple[int, str, int] | None = None
        melhor_dist = float("inf")
        candidatos = sorted(canvas._selecionados) if canvas._selecionados else list(range(len(canvas.cena.elementos)))
        for idx in candidatos:
            if idx < 0 or idx >= len(canvas.cena.elementos):
                continue
            el = canvas.cena.elementos[idx]
            if not el.get("molde"):
                continue
            for tipo, chave in (("canto", "controle_cantos"), ("aux", "controle_auxiliares")):
                for c_idx, item in enumerate(el.get(chave, [])):
                    controle = self._ponto_qt(item)
                    if controle is None:
                        continue
                    dist = canvas._dist(controle, ponto)
                    if dist <= tolerancia and dist < melhor_dist:
                        melhor = (idx, tipo, c_idx)
                        melhor_dist = dist
        return melhor

    def _molde_em_ponto(self, canvas, pos: QPointF) -> int | None:
        if not hasattr(canvas, "_indices_elementos_em_ponto"):
            return None
        for idx in canvas._indices_elementos_em_ponto(pos):
            if 0 <= idx < len(canvas.cena.elementos) and canvas.cena.elementos[idx].get("molde"):
                return idx
        return None

    def _elemento_em_hover(self, canvas, pos: QPointF) -> int | None:
        if canvas._snap_resultado is not None and canvas._snap_resultado.elemento_idx is not None:
            idx = int(canvas._snap_resultado.elemento_idx)
            if 0 <= idx < len(canvas.cena.elementos):
                return idx
        if not hasattr(canvas, "_indices_elementos_em_ponto"):
            return None
        candidatos = canvas._indices_elementos_em_ponto(pos)
        if not candidatos:
            return None
        return candidatos[0]

    def _gerar_guia(self, canvas, idx: int, p_idx: int):
        el = canvas.cena.elementos[idx]
        pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
        anterior = pontos[p_idx - 1] if p_idx > 0 else None
        proximo = pontos[p_idx + 1] if p_idx + 1 < len(pontos) else None
        return QPointF(pontos[p_idx]), anterior, proximo

    def _atualizar_ponto(self, canvas, idx: int, p_idx: int, pos: QPointF):
        el = canvas.cena.elementos[idx]
        pontos = list(el.get("pontos", []))
        if not (0 <= p_idx < len(pontos)):
            return
        anterior = QPointF(float(pontos[p_idx][0]), float(pontos[p_idx][1]))
        pontos[p_idx] = (pos.x(), pos.y())
        if len(pontos) >= 2:
            p0 = QPointF(float(pontos[0][0]), float(pontos[0][1]))
            pn = QPointF(float(pontos[-1][0]), float(pontos[-1][1]))
            if canvas._dist(p0, pn) <= 0.0001:
                if p_idx == 0:
                    pontos[-1] = pontos[0]
                elif p_idx == len(pontos) - 1:
                    pontos[0] = pontos[-1]
        el["pontos"] = pontos
        if el.get("molde"):
            self._mover_controles_correspondentes(canvas, el, anterior, pos)
            self._reajustar_fio_no_molde(el)

    def _mover_controles_correspondentes(self, canvas, el: dict, anterior: QPointF, novo: QPointF):
        tol = 10.0 / max(canvas.zoom, 0.001)
        dx = novo.x() - anterior.x()
        dy = novo.y() - anterior.y()
        for chave in ("controle_cantos", "controle_auxiliares"):
            atualizados: list[tuple[float, float]] = []
            for cx, cy in el.get(chave, []):
                cp = QPointF(float(cx), float(cy))
                if canvas._dist(cp, anterior) <= tol:
                    atualizados.append((cp.x() + dx, cp.y() + dy))
                else:
                    atualizados.append((cp.x(), cp.y()))
            if atualizados:
                el[chave] = atualizados

    def _arrastar_controle_molde(self, canvas, idx: int, tipo: str, controle_idx: int, destino: QPointF):
        if not (0 <= idx < len(canvas.cena.elementos)):
            return
        el = canvas.cena.elementos[idx]
        if el.get("tipo") != "polyline":
            return
        if tipo == "canto":
            self._arrastar_canto_molde(canvas, el, controle_idx, destino)
        else:
            self._arrastar_auxiliar_molde(canvas, el, controle_idx, destino)
        self._recravar_auxiliares_no_perimetro(el)
        self._reajustar_fio_no_molde(el)

    def _arrastar_canto_molde(self, canvas, el: dict, controle_idx: int, destino: QPointF):
        cantos = list(el.get("controle_cantos", []))
        if not (0 <= controle_idx < len(cantos)):
            return
        anterior = self._ponto_qt(cantos[controle_idx])
        if anterior is None:
            return
        cantos[controle_idx] = (destino.x(), destino.y())
        el["controle_cantos"] = cantos
        self._atualizar_espelho_controle(el, "pontos_controle_principais", controle_idx, destino)

        pontos = list(el.get("pontos", []))
        tol = 10.0 / max(canvas.zoom, 0.001)
        for p_idx, (x, y) in enumerate(pontos):
            if canvas._dist(QPointF(float(x), float(y)), anterior) <= tol:
                pontos[p_idx] = (destino.x(), destino.y())
        if len(pontos) >= 2:
            p0 = QPointF(float(pontos[0][0]), float(pontos[0][1]))
            pn = QPointF(float(pontos[-1][0]), float(pontos[-1][1]))
            if canvas._dist(p0, pn) <= tol:
                pontos[-1] = pontos[0]
        el["pontos"] = pontos

    def _arrastar_auxiliar_molde(self, canvas, el: dict, controle_idx: int, destino: QPointF):
        aux = list(el.get("controle_auxiliares", []))
        if not (0 <= controle_idx < len(aux)):
            return

        origem_aux = self._ponto_qt(aux[controle_idx])
        if origem_aux is None:
            return
        dx = destino.x() - origem_aux.x()
        dy = destino.y() - origem_aux.y()
        if abs(dx) <= 1e-9 and abs(dy) <= 1e-9:
            return
        aux[controle_idx] = (destino.x(), destino.y())
        el["controle_auxiliares"] = aux
        self._atualizar_espelho_controle(el, "pontos_auxiliares", controle_idx, destino)

        cantos = list(el.get("controle_cantos", []))
        a_idx, b_idx = self._segmento_controle_mais_proximo(cantos, origem_aux)
        pontos_para_mover: list[tuple[QPointF, QPointF]] = [(origem_aux, destino)]
        if a_idx is not None and b_idx is not None:
            for canto_idx in (a_idx, b_idx):
                canto = self._ponto_qt(cantos[canto_idx])
                if canto is None:
                    continue
                novo_canto = QPointF(canto.x() + dx, canto.y() + dy)
                cantos[canto_idx] = (novo_canto.x(), novo_canto.y())
                self._atualizar_espelho_controle(el, "pontos_controle_principais", canto_idx, novo_canto)
                pontos_para_mover.append((canto, novo_canto))
            el["controle_cantos"] = cantos

        tol = 10.0 / max(canvas.zoom, 0.001)
        pontos = list(el.get("pontos", []))
        for p_idx, (x, y) in enumerate(pontos):
            pt = QPointF(float(x), float(y))
            for origem, novo in pontos_para_mover:
                if canvas._dist(pt, origem) <= tol:
                    pontos[p_idx] = (novo.x(), novo.y())
                    break
        if len(pontos) >= 2:
            p0 = QPointF(float(pontos[0][0]), float(pontos[0][1]))
            pn = QPointF(float(pontos[-1][0]), float(pontos[-1][1]))
            if canvas._dist(p0, pn) <= tol:
                pontos[-1] = pontos[0]
        el["pontos"] = pontos

    def _recravar_auxiliares_no_perimetro(self, el: dict) -> None:
        cantos = [p for p in (self._ponto_qt(item) for item in el.get("controle_cantos", [])) if p is not None]
        if len(cantos) < 2:
            return
        auxiliares: list[tuple[float, float]] = []
        limite = len(cantos) if len(cantos) >= 3 else len(cantos) - 1
        for i in range(max(0, limite)):
            a = cantos[i]
            b = cantos[(i + 1) % len(cantos)]
            auxiliares.append(((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0))
        el["controle_auxiliares"] = auxiliares
        el["pontos_auxiliares"] = [{"x": x, "y": y} for x, y in auxiliares]

    def _atualizar_espelho_controle(self, el: dict, chave: str, idx: int, destino: QPointF) -> None:
        itens = el.get(chave)
        if not isinstance(itens, list) or not (0 <= idx < len(itens)):
            return
        item = itens[idx]
        if isinstance(item, dict):
            item["x"] = destino.x()
            item["y"] = destino.y()
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            itens[idx] = (destino.x(), destino.y())

    def _segmento_controle_mais_proximo(self, cantos: list, ponto: QPointF) -> tuple[int | None, int | None]:
        if len(cantos) < 2:
            return None, None
        fechado = len(cantos) >= 3
        melhor_a: int | None = None
        melhor_b: int | None = None
        melhor_dist = float("inf")
        limite = len(cantos) if fechado else len(cantos) - 1
        for i in range(max(limite, 0)):
            j = (i + 1) % len(cantos)
            if not fechado and j <= i:
                continue
            a = self._ponto_qt(cantos[i])
            b = self._ponto_qt(cantos[j])
            if a is None or b is None:
                continue
            dist = self._dist_ponto_segmento(ponto, a, b)
            if dist < melhor_dist:
                melhor_dist = dist
                melhor_a, melhor_b = i, j
        return melhor_a, melhor_b

    def _dist_ponto_segmento(self, p: QPointF, a: QPointF, b: QPointF) -> float:
        abx = b.x() - a.x()
        aby = b.y() - a.y()
        apx = p.x() - a.x()
        apy = p.y() - a.y()
        den = (abx * abx) + (aby * aby)
        if den <= 1e-12:
            return ((p.x() - a.x()) ** 2 + (p.y() - a.y()) ** 2) ** 0.5
        t = ((apx * abx) + (apy * aby)) / den
        t = max(0.0, min(1.0, t))
        px = a.x() + (abx * t)
        py = a.y() + (aby * t)
        return ((p.x() - px) ** 2 + (p.y() - py) ** 2) ** 0.5

    def _reajustar_fio_no_molde(self, el: dict):
        pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
        if not pontos:
            return
        base = pontos[:-1] if len(pontos) >= 2 and pontos[0] == pontos[-1] else pontos
        if not base:
            return
        xs = [p.x() for p in base]
        ys = [p.y() for p in base]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        largura = max(max_x - min_x, 1e-6)
        margem = largura * 0.12
        y_fio = min_y + ((max_y - min_y) * 0.24)
        el["fio_origem"] = (min_x + margem, y_fio)
        el["fio_fim"] = (max_x - margem, y_fio)

    def _desenhar_guia(self, canvas, painter):
        if self._guia_ponto_poly is None or self._arrastando_ponto_poly is None:
            return
        origem, anterior, proximo = self._guia_ponto_poly
        if anterior is not None:
            canvas._desenhar_segmento(painter, anterior, origem, tracejado=True, cor="#ff48ff", espessura=1.0)
        if proximo is not None:
            canvas._desenhar_segmento(painter, origem, proximo, tracejado=True, cor="#ff48ff", espessura=1.0)

    def _desenhar_controles_molde_hover(self, canvas, painter):
        idx = self._hover_molde_idx
        if idx is None or not (0 <= idx < len(canvas.cena.elementos)):
            return
        el = canvas.cena.elementos[idx]
        if not el.get("molde"):
            return

        cantos = [p for p in (self._ponto_qt(item) for item in el.get("controle_cantos", [])) if p is not None]
        painter.setPen(QPen(QColor("#2da8ff"), 1.0))
        painter.setBrush(QColor("#001522"))
        for pt in cantos:
            tela = canvas._cena_para_tela(pt)
            painter.drawRect(int(tela.x() - 3), int(tela.y() - 3), 6, 6)

    def _desenhar_molde_em_manipulacao(self, canvas, painter):
        idx = None
        if self._arrastando_controle_molde is not None:
            idx = self._arrastando_controle_molde[0]
        elif self._arrastando_ponto_poly is not None:
            idx = self._arrastando_ponto_poly[0]
        elif self._hover_controle_molde is not None:
            idx = self._hover_controle_molde[0]
        if idx is None or not (0 <= idx < len(canvas.cena.elementos)):
            return
        el = canvas.cena.elementos[idx]
        if not el.get("molde") or el.get("tipo") != "polyline":
            return
        pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
        if len(pontos) < 2:
            return
        painter.save()
        painter.setBrush(Qt.NoBrush)
        cor = "#2da8ff"
        esp = max(1.6, float(el.get("espessura", 1.0)) + 0.7)
        canvas._desenhar_polilinha(painter, pontos, cor=cor, espessura=esp, estilo="solid", amplitude=1.0)
        painter.restore()

    def _desenhar_hover(self, canvas, painter):
        if self._hover_ponto_poly is not None:
            idx, p_idx = self._hover_ponto_poly
            if 0 <= idx < len(canvas.cena.elementos):
                el = canvas.cena.elementos[idx]
                pontos = el.get("pontos", [])
                if 0 <= p_idx < len(pontos):
                    x, y = pontos[p_idx]
                    pt = canvas._cena_para_tela(QPointF(float(x), float(y)))
                    painter.setPen(QPen(QColor("#2da8ff"), 1.4))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawEllipse(int(pt.x() - 9), int(pt.y() - 9), 18, 18)

        if self._ponto_selecionado is not None:
            idx, p_idx = self._ponto_selecionado
            if 0 <= idx < len(canvas.cena.elementos):
                pontos = canvas.cena.elementos[idx].get("pontos", [])
                if 0 <= p_idx < len(pontos):
                    x, y = pontos[p_idx]
                    pt = canvas._cena_para_tela(QPointF(float(x), float(y)))
                    painter.setPen(QPen(QColor("#66d9ff"), 2.0))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawEllipse(int(pt.x() - 11), int(pt.y() - 11), 22, 22)

        if self._hover_controle_molde is not None:
            idx, tipo, c_idx = self._hover_controle_molde
            if 0 <= idx < len(canvas.cena.elementos):
                el = canvas.cena.elementos[idx]
                chave = "controle_cantos" if tipo == "canto" else "controle_auxiliares"
                controles = el.get(chave, [])
                if 0 <= c_idx < len(controles):
                    controle = self._ponto_qt(controles[c_idx])
                    if controle is None:
                        return
                    pt = canvas._cena_para_tela(controle)
                    painter.setPen(QPen(QColor("#2da8ff"), 1.4))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawEllipse(int(pt.x() - 8), int(pt.y() - 8), 16, 16)

    def _atualizar_info_angulo(self, canvas, idx: int, p_idx: int, atual: QPointF):
        self._angulo_info = None
        if idx < 0 or idx >= len(canvas.cena.elementos):
            return
        el = canvas.cena.elementos[idx]
        if el.get("tipo") != "polyline":
            return
        pts = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
        if len(pts) < 3:
            return
        fechado = canvas._dist(pts[0], pts[-1]) <= 1e-6
        if fechado and p_idx == len(pts) - 1:
            p_idx = 0
        prev_idx = p_idx - 1
        next_idx = p_idx + 1
        if fechado:
            if prev_idx < 0:
                prev_idx = len(pts) - 2
            if next_idx >= len(pts) - 1:
                next_idx = 1
        if not (0 <= prev_idx < len(pts)) or not (0 <= next_idx < len(pts)):
            return
        p_prev = pts[prev_idx]
        p_next = pts[next_idx]
        ang = self._angulo_interno(p_prev, atual, p_next)
        self._angulo_info = (atual, p_prev, p_next, ang)
        if getattr(canvas, "lbl_status", None) is not None:
            canvas.lbl_status.setText(f"Ângulo: {ang:.0f}°")

    def _angulo_interno(self, a: QPointF, c: QPointF, b: QPointF) -> float:
        v1x, v1y = a.x() - c.x(), a.y() - c.y()
        v2x, v2y = b.x() - c.x(), b.y() - c.y()
        ang1 = atan2(v1y, v1x)
        ang2 = atan2(v2y, v2x)
        deg = abs(degrees(ang2 - ang1))
        while deg > 360.0:
            deg -= 360.0
        if deg > 180.0:
            deg = 360.0 - deg
        return max(0.0, min(360.0, deg))

    @staticmethod
    def _ponto_qt(p) -> QPointF | None:
        try:
            if isinstance(p, QPointF):
                return QPointF(p)
            if isinstance(p, dict):
                return QPointF(float(p["x"]), float(p["y"]))
            if isinstance(p, (list, tuple)) and len(p) >= 2:
                return QPointF(float(p[0]), float(p[1]))
        except Exception:
            return None
        return None

    def _desenhar_angulo(self, canvas, painter):
        if self._angulo_info is None:
            return
        centro, p1, p2, ang = self._angulo_info
        c_tela = canvas._cena_para_tela(centro)
        a_tela = canvas._cena_para_tela(p1)
        b_tela = canvas._cena_para_tela(p2)
        raio = 44
        painter.setPen(QPen(QColor("#ff2bd6"), 1.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(int(c_tela.x() - raio), int(c_tela.y() - raio), raio * 2, raio * 2)
        painter.drawLine(c_tela, a_tela)
        painter.drawLine(c_tela, b_tela)
        painter.drawText(int(c_tela.x() + 8), int(c_tela.y() - 8), f"{ang:.0f}°")
