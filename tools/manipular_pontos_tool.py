from __future__ import annotations

from copy import deepcopy
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
        self._arrastando_dobra_pontilhada: tuple[int, int, int] | None = None
        self._hover_ponto_poly: tuple[int, int] | None = None
        self._hover_controle_molde: tuple[int, str, int] | None = None
        self._hover_dobra_pontilhada: tuple[int, int, int] | None = None
        self._hover_elemento_idx: int | None = None
        self._hover_molde_idx: int | None = None
        self._guia_ponto_poly: tuple[QPointF, QPointF | None, QPointF | None] | None = None
        self._angulo_info: tuple[QPointF, QPointF, QPointF, float] | None = None
        self._ponto_selecionado: tuple[int, int] | None = None
        self._controles_selecionados: set[tuple[int, str, int]] = set()
        self._estado_arraste_controle: dict | None = None
        self._estado_arraste_ponto: dict | None = None
        cls = type(self)
        self._dlg_passo: QDialog | None = cls._dlg_global
        self._edt_dx: QLineEdit | None = cls._edt_dx_global
        self._edt_dy: QLineEdit | None = cls._edt_dy_global
        self._cmb_n_pontos: QComboBox | None = cls._cmb_n_pontos_global
        self._chk_discreto: QCheckBox | None = cls._chk_discreto_global

    def on_activate(self, canvas):
        self._arrastando_ponto_poly = None
        self._arrastando_controle_molde = None
        self._arrastando_dobra_pontilhada = None
        self._hover_ponto_poly = None
        self._hover_controle_molde = None
        self._hover_dobra_pontilhada = None
        self._hover_elemento_idx = None
        self._hover_molde_idx = None
        self._guia_ponto_poly = None
        self._angulo_info = None
        self._ponto_selecionado = None
        self._controles_selecionados.clear()
        self._estado_arraste_controle = None
        self._estado_arraste_ponto = None
        self._abrir_caixa_passo(canvas)
        self.set_status(f"{self.nome}: arraste um ponto, use Shift para selecionar vários, ou use DX/DY para mover com precisão.")

    def on_deactivate(self, canvas):
        if self._dlg_passo:
            self._dlg_passo.hide()

    def on_canvas_resize(self, canvas) -> None:
        self._reposicionar_caixa_passo(canvas)

    def _abrir_caixa_passo(self, canvas):
        cls = type(self)
        if cls._dlg_global is not None:
            try:
                cls._dlg_global.isVisible()
            except RuntimeError:
                cls._dlg_global = None
                cls._edt_dx_global = None
                cls._edt_dy_global = None
                cls._cmb_n_pontos_global = None
                cls._chk_discreto_global = None
        if cls._dlg_global is None:
            cls._dlg_global = QDialog(canvas)
            cls._dlg_global.setObjectName(f"guimma_{self.id_ferramenta}_dialog")
            cls._dlg_global.setWindowTitle(self.nome)
            cls._dlg_global.setWindowFlags(Qt.Tool)
            lay = QFormLayout(cls._dlg_global)
            cls._edt_dx_global = QLineEdit("0")
            cls._edt_dy_global = QLineEdit("0")
            cls._cmb_n_pontos_global = QComboBox()
            cls._cmb_n_pontos_global.addItems(["1 ponto", "N pontos"])
            cls._chk_discreto_global = QCheckBox("Discreto")
            lay.addRow("DX (cm)", cls._edt_dx_global)
            lay.addRow("DY (cm)", cls._edt_dy_global)
            lay.addRow("Nº pontos", cls._cmb_n_pontos_global)
            lay.addRow("", cls._chk_discreto_global)
            cls._dlg_global.setFixedWidth(210)
            instalar_memoria_posicao(cls._dlg_global, f"dialog:{self.id_ferramenta}")
        self._dlg_passo = cls._dlg_global
        self._edt_dx = cls._edt_dx_global
        self._edt_dy = cls._edt_dy_global
        self._cmb_n_pontos = cls._cmb_n_pontos_global
        self._chk_discreto = cls._chk_discreto_global
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
            restaurar_posicao(self._dlg_passo, f"dialog:{self.id_ferramenta}", fallback=canvas.mapToGlobal(pos_local))

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

    def _shift_pressionado(self, event) -> bool:
        try:
            return bool(event.modifiers() & Qt.ShiftModifier)
        except Exception:
            return False

    def _elemento_curva_suave(self, elemento: dict) -> bool:
        if not isinstance(elemento, dict):
            return False
        return bool(
            elemento.get("curva_suave")
            or elemento.get("suavizar")
            or str(elemento.get("tipo_curva") or "").lower().startswith("spline")
            or str(elemento.get("renderizacao") or "").lower() == "curva_suave"
        )

    def _sincronizar_curva_suave(self, el: dict) -> None:
        if el.get("molde"):
            return
        # Curva com traçado real: manter somente os controles como controles.
        if self._curva_tracado_real(el):
            controles = self._pontos_controle_curva(el)
            if len(controles) >= 2:
                self._salvar_controles_curva_real(el, controles)
            return
        if not self._elemento_curva_suave(el):
            return
        pontos = list(el.get("pontos") or [])
        normalizados: list[tuple[float, float]] = []
        for item in pontos:
            pt = self._ponto_qt(item)
            if pt is not None:
                normalizados.append((pt.x(), pt.y()))
        if len(normalizados) < 2:
            return
        el["pontos"] = list(normalizados)
        el["pontos_controle_curva"] = list(normalizados)
        el["pontos_principais"] = list(normalizados)
        el["curva_suave"] = True
        el["tipo_curva"] = str(el.get("tipo_curva") or "spline_np_controle")
        el["renderizacao"] = "curva_suave"

    def on_mouse_press(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        pos = canvas._ponto_com_snap(event.position())
        shift = self._shift_pressionado(event)

        dobra_pontilhada = self._dobra_pontilhada_em_ponto(canvas, pos)
        if dobra_pontilhada is not None:
            self._arrastando_dobra_pontilhada = dobra_pontilhada
            self._hover_dobra_pontilhada = dobra_pontilhada
            self._hover_controle_molde = None
            self._hover_ponto_poly = None
            event.accept()
            canvas.update()
            return True

        controle = self._controle_molde_em_ponto(canvas, pos)
        if controle is not None:
            if shift:
                if controle in self._controles_selecionados:
                    self._controles_selecionados.remove(controle)
                else:
                    self._controles_selecionados.add(controle)
                self._hover_controle_molde = controle
                self._hover_molde_idx = controle[0]
                self._ponto_selecionado = None
                event.accept()
                canvas.update()
                return True

            if controle not in self._controles_selecionados:
                self._controles_selecionados = {controle}
            self._arrastando_controle_molde = controle
            self._hover_controle_molde = controle
            self._hover_molde_idx = controle[0]
            self._ponto_selecionado = None
            self._estado_arraste_controle = self._criar_estado_arraste_controle(canvas, controle)
            dx, dy = self._ler_delta_configurado()
            if abs(dx) > 1e-9 or abs(dy) > 1e-9:
                self._mover_controles_por_delta(canvas, self._alvos_controle_para_arraste(controle), dx, -dy)
                canvas._registrar_historico()
                self._arrastando_controle_molde = None
                self._estado_arraste_controle = None
            event.accept()
            canvas.update()
            return True

        ponto_poly = self._ponto_polilinha_em_ponto(canvas, pos)
        if ponto_poly is None:
            if not shift:
                self._controles_selecionados.clear()
            return False
        idx, p_idx = ponto_poly
        self._arrastando_ponto_poly = (idx, p_idx)
        self._ponto_selecionado = (idx, p_idx)
        self._hover_ponto_poly = (idx, p_idx)
        self._estado_arraste_ponto = self._criar_estado_arraste_ponto(canvas, idx, p_idx)
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
                self._estado_arraste_ponto = None
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
        self._sincronizar_curva_suave(el)
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
        self._sincronizar_curva_suave(el)
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
        if self._arrastando_dobra_pontilhada is not None:
            self._atualizar_dobra_pontilhada(canvas, self._arrastando_dobra_pontilhada, self._normalizar_destino(pos))
            self._hover_dobra_pontilhada = self._arrastando_dobra_pontilhada
            canvas.update()
            event.accept()
            return True

        if self._arrastando_controle_molde is not None:
            idx, tipo, controle_idx = self._arrastando_controle_molde
            estado = self._estado_arraste_controle
            if estado is not None:
                destino = self._normalizar_destino(pos)
                origem = estado.get("origem")
                if isinstance(origem, QPointF):
                    dx = destino.x() - origem.x()
                    dy = destino.y() - origem.y()
                    self._restaurar_estado_arraste(canvas, estado)
                    self._mover_controles_por_delta(canvas, set(estado.get("alvos", set())), dx, dy)
            else:
                atual = self._ponto_controle_molde(canvas, idx, tipo, controle_idx)
                if atual is not None:
                    destino = self._normalizar_destino(pos)
                    dx = destino.x() - atual.x()
                    dy = destino.y() - atual.y()
                    self._mover_controles_por_delta(canvas, self._alvos_controle_para_arraste((idx, tipo, controle_idx)), dx, dy)
            self._hover_controle_molde = self._arrastando_controle_molde
            self._hover_molde_idx = idx
            canvas.update()
            event.accept()
            return True

        if self._arrastando_ponto_poly is not None:
            idx, p_idx = self._arrastando_ponto_poly
            estado = self._estado_arraste_ponto
            destino = self._normalizar_destino(pos)
            if estado is not None:
                origem = estado.get("origem")
                if isinstance(origem, QPointF):
                    self._restaurar_estado_arraste(canvas, estado)
                    dx = destino.x() - origem.x()
                    dy = destino.y() - origem.y()
                    self._atualizar_ponto(canvas, idx, p_idx, destino)
                    self._mover_ponto_proporcional(canvas, idx, p_idx, dx, dy, mover_n_pontos=self._modo_n_pontos())
            else:
                self._atualizar_ponto(canvas, idx, p_idx, destino)
            self._guia_ponto_poly = self._gerar_guia(canvas, idx, p_idx)
            self._atualizar_info_angulo(canvas, idx, p_idx, destino)
            canvas.update()
            event.accept()
            return True

        self._hover_ponto_poly = self._ponto_polilinha_em_ponto(canvas, pos)
        self._hover_controle_molde = self._controle_molde_em_ponto(canvas, pos)
        self._hover_dobra_pontilhada = self._dobra_pontilhada_em_ponto(canvas, pos)
        self._hover_molde_idx = self._hover_controle_molde[0] if self._hover_controle_molde is not None else None
        self._hover_elemento_idx = self._elemento_em_hover(canvas, pos)
        canvas.update()
        event.accept()
        return True

    def on_mouse_release(self, canvas, event) -> bool:
        if event.button() != Qt.LeftButton:
            return False
        if self._arrastando_ponto_poly is None and self._arrastando_controle_molde is None and self._arrastando_dobra_pontilhada is None:
            return False
        self._arrastando_ponto_poly = None
        self._arrastando_controle_molde = None
        self._arrastando_dobra_pontilhada = None
        self._estado_arraste_controle = None
        self._estado_arraste_ponto = None
        self._guia_ponto_poly = None
        canvas._registrar_historico()
        canvas.update()
        event.accept()
        return True

    def on_paint_overlay(self, canvas, painter):
        self._desenhar_linha_curva_selecionada(canvas, painter)
        self._desenhar_pontos_controle_curvas_visiveis(canvas, painter)
        self._desenhar_molde_em_manipulacao(canvas, painter)
        self._desenhar_controles_molde_hover(canvas, painter)
        self._desenhar_guia(canvas, painter)
        self._desenhar_hover(canvas, painter)
        self._desenhar_hover_dobra_pontilhada(canvas, painter)

    def _curva_tracado_real(self, el: dict) -> bool:
        if not isinstance(el, dict) or el.get("molde"):
            return False
        return bool(
            el.get("pontos_tracado_real")
            or el.get("curva_editavel")
            or el.get("pontos_principais")
            or el.get("pontos_controle_curva")
        )

    def _dist_pontos_local(self, a: QPointF, b: QPointF) -> float:
        dx = a.x() - b.x()
        dy = a.y() - b.y()
        return (dx * dx + dy * dy) ** 0.5

    def _resolver_segundas_derivadas_local(self, valores: list[float], t: list[float]) -> list[float]:
        n = len(valores)
        if n <= 2:
            return [0.0] * n
        m = n - 2
        a = [0.0] * m
        b = [0.0] * m
        c = [0.0] * m
        d = [0.0] * m
        for j in range(m):
            i = j + 1
            h0 = max(t[i] - t[i - 1], 1e-9)
            h1 = max(t[i + 1] - t[i], 1e-9)
            a[j] = h0
            b[j] = 2.0 * (h0 + h1)
            c[j] = h1
            d[j] = 6.0 * (((valores[i + 1] - valores[i]) / h1) - ((valores[i] - valores[i - 1]) / h0))
        for i in range(1, m):
            w = a[i] / b[i - 1]
            b[i] -= w * c[i - 1]
            d[i] -= w * d[i - 1]
        internos = [0.0] * m
        internos[-1] = d[-1] / b[-1]
        for i in range(m - 2, -1, -1):
            internos[i] = (d[i] - c[i] * internos[i + 1]) / b[i]
        return [0.0] + internos + [0.0]

    def _avaliar_spline_local(self, ti: float, tj: float, yi: float, yj: float, mi: float, mj: float, u: float) -> float:
        h = max(tj - ti, 1e-9)
        a = (tj - u) / h
        b = (u - ti) / h
        return a * yi + b * yj + (((a ** 3) - a) * mi + ((b ** 3) - b) * mj) * (h * h) / 6.0

    def _gerar_tracado_curva_real(self, controles: list[QPointF], fechado: bool = False) -> list[tuple[float, float]]:
        controles = [QPointF(p) for p in controles]
        if len(controles) <= 1:
            return [(p.x(), p.y()) for p in controles]
        if len(controles) == 2:
            return [(controles[0].x(), controles[0].y()), (controles[1].x(), controles[1].y())]

        saida: list[QPointF] = []
        total = len(controles)
        limite = total if fechado else total - 1
        for i in range(limite):
            p0 = controles[(i - 1) % total] if fechado or i > 0 else controles[i]
            p1 = controles[i]
            p2 = controles[(i + 1) % total]
            p3 = controles[(i + 2) % total] if fechado or i + 2 < total else p2
            if i == 0:
                saida.append(QPointF(p1))
            dist = self._dist_pontos_local(p1, p2)
            amostras = max(8, min(22, int(dist * 0.10) + 8))
            for s in range(1, amostras + 1):
                saida.append(self._catmull_rom(p0, p1, p2, p3, s / float(amostras)))
        if fechado and saida:
            saida[-1] = QPointF(saida[0])
        return [(float(p.x()), float(p.y())) for p in saida]

    def _catmull_rom(self, p0: QPointF, p1: QPointF, p2: QPointF, p3: QPointF, t: float) -> QPointF:
        t2 = t * t
        t3 = t2 * t
        x = 0.5 * (
            (2.0 * p1.x())
            + (-p0.x() + p2.x()) * t
            + (2.0 * p0.x() - 5.0 * p1.x() + 4.0 * p2.x() - p3.x()) * t2
            + (-p0.x() + 3.0 * p1.x() - 3.0 * p2.x() + p3.x()) * t3
        )
        y = 0.5 * (
            (2.0 * p1.y())
            + (-p0.y() + p2.y()) * t
            + (2.0 * p0.y() - 5.0 * p1.y() + 4.0 * p2.y() - p3.y()) * t2
            + (-p0.y() + 3.0 * p1.y() - 3.0 * p2.y() + p3.y()) * t3
        )
        return QPointF(x, y)

    def _salvar_controles_curva_real(self, el: dict, controles: list[QPointF]) -> None:
        lista = [(float(p.x()), float(p.y())) for p in controles]
        el["pontos_principais"] = list(lista)
        el["pontos_controle_curva"] = list(lista)
        el["pontos_controle_principais"] = list(lista)
        el["pontos_controle"] = list(lista)
        el["curva_editavel"] = True
        el["curva_suave"] = True
        el["pontos_tracado_real"] = True
        el["renderizacao"] = "polyline"
        el["tipo_curva"] = el.get("tipo_curva") or "spline_catmull_rom"

    def _pontos_controle_curva(self, el: dict) -> list[QPointF]:
        """Retorna somente os pontos principais/controláveis da curva."""
        origem = el.get("pontos_principais") or el.get("pontos_controle_curva") or el.get("pontos") or []
        pontos: list[QPointF] = []
        if not isinstance(origem, list):
            return pontos
        for item in origem:
            pt = self._ponto_qt(item)
            if pt is None:
                continue
            if not pontos:
                pontos.append(QPointF(pt))
                continue
            dx = pt.x() - pontos[-1].x()
            dy = pt.y() - pontos[-1].y()
            if ((dx * dx) + (dy * dy)) > 1e-9:
                pontos.append(QPointF(pt))
        return pontos

    def _indice_ponto_controle_para_ponto_real(self, canvas, el: dict, controle_idx: int) -> int | None:
        """Converte o ponto de controle visível para o índice real em el["pontos"]."""
        if self._curva_tracado_real(el):
            return controle_idx
        pontos = list(el.get("pontos", []) or [])
        controles = self._pontos_controle_curva(el)
        if not (0 <= controle_idx < len(controles)):
            return None
        alvo = controles[controle_idx]
        melhor_idx = None
        melhor_dist = float("inf")
        for i, item in enumerate(pontos):
            pt = self._ponto_qt(item)
            if pt is None:
                continue
            dist = canvas._dist(pt, alvo)
            if dist < melhor_dist:
                melhor_dist = dist
                melhor_idx = i
        return melhor_idx

    def _indices_curvas_para_mostrar(self, canvas) -> set[int]:
        indices: set[int] = set()
        for idx in getattr(canvas, "_selecionados", set()) or set():
            if 0 <= int(idx) < len(canvas.cena.elementos):
                indices.add(int(idx))
        if self._hover_elemento_idx is not None:
            indices.add(int(self._hover_elemento_idx))
        if self._hover_ponto_poly is not None:
            indices.add(int(self._hover_ponto_poly[0]))
        if self._ponto_selecionado is not None:
            indices.add(int(self._ponto_selecionado[0]))
        if self._arrastando_ponto_poly is not None:
            indices.add(int(self._arrastando_ponto_poly[0]))
        return indices

    def _desenhar_linha_curva_selecionada(self, canvas, painter) -> None:
        """Realça a curva em azul quando ela está em hover/selecionada/manipulação."""
        for idx in sorted(self._indices_curvas_para_mostrar(canvas)):
            if not (0 <= idx < len(canvas.cena.elementos)):
                continue
            el = canvas.cena.elementos[idx]
            if el.get("tipo") != "polyline" or not self._elemento_curva_suave(el):
                continue
            pontos = [self._ponto_qt(p) for p in (el.get("pontos", []) or [])]
            pontos = [p for p in pontos if p is not None]
            if len(pontos) < 2:
                continue
            painter.save()
            try:
                painter.setBrush(Qt.NoBrush)
                esp = max(1.8, float(el.get("espessura", 1.0)) + 0.8)
                if el.get("pontos_tracado_real"):
                    canvas._desenhar_polilinha(
                        painter, pontos, cor="#2da8ff", espessura=esp, estilo="solid", amplitude=1.0
                    )
                elif hasattr(canvas, "_desenhar_curva_suave_por_pontos"):
                    canvas._desenhar_curva_suave_por_pontos(
                        painter, pontos, cor="#2da8ff", espessura=esp, estilo="solid"
                    )
                else:
                    canvas._desenhar_polilinha(
                        painter, pontos, cor="#2da8ff", espessura=esp, estilo="solid", amplitude=1.0
                    )
            finally:
                painter.restore()

    def _desenhar_pontos_controle_curvas_visiveis(self, canvas, painter) -> None:
        """Mostra os pontos de controle principais em vermelho para poder mover."""
        for idx in sorted(self._indices_curvas_para_mostrar(canvas)):
            if not (0 <= idx < len(canvas.cena.elementos)):
                continue
            el = canvas.cena.elementos[idx]
            if el.get("tipo") != "polyline" or not self._elemento_curva_suave(el):
                continue
            if el.get("molde"):
                controles = self._pontos_polyline_editaveis_molde(el)
            else:
                controles = self._pontos_controle_curva(el)
            if not controles:
                continue
            painter.save()
            try:
                painter.setPen(QPen(QColor("#ff2f5f"), 1.2))
                painter.setBrush(QColor("#ff2f5f"))
                for pt_cena in controles:
                    pt = canvas._cena_para_tela(pt_cena)
                    painter.drawRect(int(pt.x() - 4), int(pt.y() - 4), 8, 8)
            finally:
                painter.restore()

    def _dobra_pontilhada_em_ponto(self, canvas, ponto: QPointF) -> tuple[int, int, int] | None:
        tolerancia = 8.0 / max(canvas.zoom, 0.001)
        melhor: tuple[int, int, int] | None = None
        melhor_dist = float("inf")
        candidatos = sorted(canvas._selecionados) if canvas._selecionados else list(range(len(canvas.cena.elementos)))
        for idx in candidatos:
            if not (0 <= idx < len(canvas.cena.elementos)):
                continue
            el = canvas.cena.elementos[idx]
            registros = el.get("contornos_dobra_original")
            if not isinstance(registros, list):
                continue
            for reg_idx, registro in enumerate(registros):
                if not isinstance(registro, dict):
                    continue
                pontos = registro.get("contorno_pontilhado") or registro.get("metade_movida")
                if not isinstance(pontos, list):
                    continue
                limite = len(pontos)
                if limite >= 2 and self._pontos_lista_mesmos(pontos[0], pontos[-1]):
                    limite -= 1
                for p_idx in range(limite):
                    pt = self._ponto_qt(pontos[p_idx])
                    if pt is None:
                        continue
                    dist = canvas._dist(pt, ponto)
                    if dist <= tolerancia and dist < melhor_dist:
                        melhor = (idx, reg_idx, p_idx)
                        melhor_dist = dist
        return melhor

    def _atualizar_dobra_pontilhada(self, canvas, alvo: tuple[int, int, int], destino: QPointF) -> None:
        idx, reg_idx, p_idx = alvo
        if not (0 <= idx < len(canvas.cena.elementos)):
            return
        registros = canvas.cena.elementos[idx].get("contornos_dobra_original")
        if not isinstance(registros, list) or not (0 <= reg_idx < len(registros)):
            return
        registro = registros[reg_idx]
        if not isinstance(registro, dict):
            return
        for chave in ("contorno_pontilhado", "metade_movida"):
            pontos = list(registro.get(chave) or [])
            if not (0 <= p_idx < len(pontos)):
                continue
            fechado = len(pontos) >= 2 and self._pontos_lista_mesmos(pontos[0], pontos[-1])
            pontos[p_idx] = (destino.x(), destino.y())
            if fechado:
                if p_idx == 0:
                    pontos[-1] = pontos[0]
                elif p_idx == len(pontos) - 1:
                    pontos[0] = pontos[-1]
            registro[chave] = pontos

    def _pontos_lista_mesmos(self, a, b) -> bool:
        pa = self._ponto_qt(a)
        pb = self._ponto_qt(b)
        if pa is None or pb is None:
            return False
        return abs(pa.x() - pb.x()) <= 1e-7 and abs(pa.y() - pb.y()) <= 1e-7

    def _desenhar_hover_dobra_pontilhada(self, canvas, painter) -> None:
        alvo = self._arrastando_dobra_pontilhada or self._hover_dobra_pontilhada
        if alvo is None:
            return
        idx, reg_idx, p_idx = alvo
        if not (0 <= idx < len(canvas.cena.elementos)):
            return
        registros = canvas.cena.elementos[idx].get("contornos_dobra_original")
        if not isinstance(registros, list) or not (0 <= reg_idx < len(registros)):
            return
        registro = registros[reg_idx]
        if not isinstance(registro, dict):
            return
        pontos = registro.get("contorno_pontilhado") or registro.get("metade_movida")
        if not isinstance(pontos, list) or not (0 <= p_idx < len(pontos)):
            return
        pt = self._ponto_qt(pontos[p_idx])
        if pt is None:
            return
        tela = canvas._cena_para_tela(pt)
        painter.setPen(QPen(QColor("#66d9ff"), 2.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(int(tela.x() - 11), int(tela.y() - 11), 22, 22)

    def _ponto_polilinha_em_ponto(self, canvas, ponto: QPointF) -> tuple[int, int] | None:
        tolerancia = 10.0 / max(canvas.zoom, 0.001)
        candidatos = sorted(canvas._selecionados) if canvas._selecionados else list(range(len(canvas.cena.elementos)))
        for idx in candidatos:
            if idx < 0 or idx >= len(canvas.cena.elementos):
                continue
            el = canvas.cena.elementos[idx]
            if el.get("tipo") != "polyline":
                continue

            if el.get("molde"):
                pontos = el.get("pontos", [])
                fechado = self._polyline_fechada(canvas, pontos)
                limite = len(pontos) - 1 if fechado else len(pontos)
                for p_idx in range(max(0, limite)):
                    ponto_real = self._ponto_qt(pontos[p_idx])
                    if ponto_real is not None and canvas._dist(ponto_real, ponto) <= tolerancia:
                        return idx, p_idx
                continue

            # Curva suave: só os pontos principais/controláveis aparecem e podem ser pegos.
            if self._elemento_curva_suave(el):
                controles = self._pontos_controle_curva(el)
                for controle_idx, controle in enumerate(controles):
                    if canvas._dist(controle, ponto) <= tolerancia:
                        p_real = self._indice_ponto_controle_para_ponto_real(canvas, el, controle_idx)
                        if p_real is not None:
                            return idx, p_real
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

    def _pontos_polyline_editaveis_molde(self, el: dict) -> list[QPointF]:
        pontos = el.get("pontos", [])
        if not isinstance(pontos, list):
            return []
        saida: list[QPointF] = []
        limite = len(pontos)
        if limite >= 2:
            p0 = self._ponto_qt(pontos[0])
            pn = self._ponto_qt(pontos[-1])
            if p0 is not None and pn is not None and self._dist_pontos_local(p0, pn) <= 1e-6:
                limite -= 1
        for item in pontos[:limite]:
            pt = self._ponto_qt(item)
            if pt is not None:
                saida.append(pt)
        return saida

    def _polyline_fechada(self, canvas, pontos: list) -> bool:
        if len(pontos) < 2:
            return False
        p0 = self._ponto_qt(pontos[0])
        pn = self._ponto_qt(pontos[-1])
        if p0 is None or pn is None:
            return False
        return canvas._dist(p0, pn) <= 1e-6

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
        if self._curva_tracado_real(el):
            pontos = self._pontos_controle_curva(el)
        else:
            pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
        if not (0 <= p_idx < len(pontos)):
            return None
        anterior = pontos[p_idx - 1] if p_idx > 0 else None
        proximo = pontos[p_idx + 1] if p_idx + 1 < len(pontos) else None
        return QPointF(pontos[p_idx]), anterior, proximo

    def _atualizar_ponto(self, canvas, idx: int, p_idx: int, pos: QPointF):
        el = canvas.cena.elementos[idx]

        if self._curva_tracado_real(el):
            controles = self._pontos_controle_curva(el)
            if not (0 <= p_idx < len(controles)):
                return
            controles[p_idx] = QPointF(pos)
            self._salvar_controles_curva_real(el, controles)
            el["pontos"] = self._gerar_tracado_curva_real(controles, fechado=bool(el.get("fechado")))
            return

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
        self._sincronizar_curva_suave(el)
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

    def _alvos_controle_para_arraste(self, controle: tuple[int, str, int]) -> set[tuple[int, str, int]]:
        if controle in self._controles_selecionados:
            return set(self._controles_selecionados)
        return {controle}

    def _normalizar_destino(self, destino: QPointF) -> QPointF:
        if self._modo_discreto():
            return QPointF(round(destino.x(), 2), round(destino.y(), 2))
        return QPointF(destino)

    def _criar_estado_arraste_controle(self, canvas, controle: tuple[int, str, int]) -> dict | None:
        origem = self._ponto_controle_molde(canvas, *controle)
        if origem is None:
            return None
        alvos = self._alvos_controle_para_arraste(controle)
        indices = {idx for idx, _tipo, _controle_idx in alvos}
        return {
            "origem": QPointF(origem),
            "alvos": set(alvos),
            "elementos": self._capturar_elementos(canvas, indices),
        }

    def _criar_estado_arraste_ponto(self, canvas, idx: int, p_idx: int) -> dict | None:
        if not (0 <= idx < len(canvas.cena.elementos)):
            return None
        el = canvas.cena.elementos[idx]
        if self._curva_tracado_real(el):
            pontos = self._pontos_controle_curva(el)
        else:
            pontos = el.get("pontos", [])
        if not (0 <= p_idx < len(pontos)):
            return None
        origem = self._ponto_qt(pontos[p_idx])
        if origem is None:
            return None
        return {
            "origem": QPointF(origem),
            "elementos": self._capturar_elementos(canvas, {idx}),
        }

    def _capturar_elementos(self, canvas, indices: set[int]) -> dict[int, dict]:
        capturados: dict[int, dict] = {}
        for idx in indices:
            if 0 <= idx < len(canvas.cena.elementos) and isinstance(canvas.cena.elementos[idx], dict):
                capturados[idx] = deepcopy(canvas.cena.elementos[idx])
        return capturados

    def _restaurar_estado_arraste(self, canvas, estado: dict) -> None:
        elementos = estado.get("elementos", {})
        if not isinstance(elementos, dict):
            return
        for idx, elemento in elementos.items():
            if 0 <= int(idx) < len(canvas.cena.elementos):
                canvas.cena.elementos[int(idx)] = deepcopy(elemento)

    def _ponto_controle_molde(self, canvas, idx: int, tipo: str, controle_idx: int) -> QPointF | None:
        if not (0 <= idx < len(canvas.cena.elementos)):
            return None
        el = canvas.cena.elementos[idx]
        chave = "controle_cantos" if tipo == "canto" else "controle_auxiliares"
        controles = el.get(chave, [])
        if not (0 <= controle_idx < len(controles)):
            return None
        return self._ponto_qt(controles[controle_idx])

    def _mover_controles_por_delta(self, canvas, controles: set[tuple[int, str, int]], dx: float, dy: float) -> None:
        if abs(dx) <= 1e-9 and abs(dy) <= 1e-9:
            return
        for idx, tipo, controle_idx in sorted(controles):
            atual = self._ponto_controle_molde(canvas, idx, tipo, controle_idx)
            if atual is None:
                continue
            destino = QPointF(atual.x() + dx, atual.y() + dy)
            destino = self._normalizar_destino(destino)
            self._arrastar_controle_molde(canvas, idx, tipo, controle_idx, destino)

    def _arrastar_controle_molde(self, canvas, idx: int, tipo: str, controle_idx: int, destino: QPointF):
        if not (0 <= idx < len(canvas.cena.elementos)):
            return
        el = canvas.cena.elementos[idx]
        if el.get("tipo") != "polyline":
            return
        destino = self._normalizar_destino(destino)
        if tipo == "canto":
            self._arrastar_canto_molde(canvas, el, controle_idx, destino)
            self._recravar_auxiliares_no_perimetro(el)
        else:
            self._arrastar_auxiliar_molde(canvas, el, controle_idx, destino)
        self._reajustar_fio_no_molde(el)

    def _arrastar_canto_molde(self, canvas, el: dict, controle_idx: int, destino: QPointF):
        cantos = list(el.get("controle_cantos", []))
        if not (0 <= controle_idx < len(cantos)):
            return
        anterior = self._ponto_qt(cantos[controle_idx])
        if anterior is None:
            return
        dx = destino.x() - anterior.x()
        dy = destino.y() - anterior.y()
        pontos_originais = list(el.get("pontos", []))
        ponto_idx = self._indice_ponto_mais_proximo(canvas, pontos_originais, anterior)
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
        if ponto_idx is not None:
            self._redistribuir_molde_por_deslocamentos(canvas, el, pontos_originais, {ponto_idx: (dx, dy)})

    def _indice_ponto_mais_proximo(self, canvas, pontos: list, alvo: QPointF) -> int | None:
        if not pontos:
            return None
        tol = 10.0 / max(canvas.zoom, 0.001)
        melhor_idx: int | None = None
        melhor_dist = float("inf")
        for idx, item in enumerate(pontos):
            pt = self._ponto_qt(item)
            if pt is None:
                continue
            dist = canvas._dist(pt, alvo)
            if dist < melhor_dist:
                melhor_dist = dist
                melhor_idx = idx
        if melhor_idx is None or melhor_dist > tol:
            return None
        return melhor_idx

    def _arrastar_auxiliar_molde(self, canvas, el: dict, controle_idx: int, destino: QPointF):
        aux = list(el.get("controle_auxiliares", []))
        if not (0 <= controle_idx < len(aux)):
            return

        origem_aux = self._ponto_qt(aux[controle_idx])
        if origem_aux is None:
            return
        aux[controle_idx] = (destino.x(), destino.y())
        el["controle_auxiliares"] = aux
        self._atualizar_espelho_controle(el, "pontos_auxiliares", controle_idx, destino)

        cantos = list(el.get("controle_cantos", []))
        pontos_originais = list(el.get("pontos", []))
        if len(cantos) < 2 or len(pontos_originais) < 2:
            return

        a_idx, b_idx = self._segmento_indices_do_auxiliar(cantos, aux, controle_idx, origem_aux)
        if a_idx is None or b_idx is None:
            return
        a = self._ponto_qt(cantos[a_idx])
        b = self._ponto_qt(cantos[b_idx])
        if a is None or b is None:
            return

        ponto_a_idx = self._indice_ponto_mais_proximo(canvas, pontos_originais, a)
        ponto_b_idx = self._indice_ponto_mais_proximo(canvas, pontos_originais, b)
        if ponto_a_idx is None or ponto_b_idx is None or ponto_a_idx == ponto_b_idx:
            return

        fechado = len(pontos_originais) >= 2 and canvas._dist(
            self._ponto_qt(pontos_originais[0]) or QPointF(),
            self._ponto_qt(pontos_originais[-1]) or QPointF(),
        ) <= 1e-6
        n = len(pontos_originais) - 1 if fechado else len(pontos_originais)
        indices = self._indices_intervalo(ponto_a_idx, ponto_b_idx, n, fechado)
        if len(indices) < 2:
            return

        pontos = list(pontos_originais)
        denom = max(1, len(indices) - 1)
        controle_bezier = self._controle_quadratico_passando_por_meio(a, destino, b)
        for pos, idx_local in enumerate(indices):
            t = pos / float(denom)
            novo = self._bezier_quadratica(a, controle_bezier, b, t)
            if self._modo_discreto():
                novo = QPointF(round(novo.x(), 2), round(novo.y(), 2))
            pontos[idx_local] = (novo.x(), novo.y())
        if fechado and len(pontos) >= 2:
            pontos[-1] = pontos[0]
        el["pontos"] = pontos
        self._sincronizar_curva_suave(el)

    def _segmento_indices_do_auxiliar(
        self,
        cantos: list,
        auxiliares: list,
        controle_idx: int,
        origem_aux: QPointF,
    ) -> tuple[int | None, int | None]:
        total = len(cantos)
        if total < 2:
            return None, None
        fechado = total >= 3 and len(auxiliares) == total
        if fechado and 0 <= controle_idx < total:
            return controle_idx, (controle_idx + 1) % total
        if len(auxiliares) == total - 1 and 0 <= controle_idx < total - 1:
            return controle_idx, controle_idx + 1
        return self._segmento_controle_mais_proximo(cantos, origem_aux)

    def _bezier_quadratica(self, a: QPointF, controle: QPointF, b: QPointF, t: float) -> QPointF:
        u = 1.0 - t
        x = (u * u * a.x()) + (2.0 * u * t * controle.x()) + (t * t * b.x())
        y = (u * u * a.y()) + (2.0 * u * t * controle.y()) + (t * t * b.y())
        return QPointF(x, y)

    def _controle_quadratico_passando_por_meio(self, a: QPointF, meio: QPointF, b: QPointF) -> QPointF:
        return QPointF(
            (2.0 * meio.x()) - ((a.x() + b.x()) * 0.5),
            (2.0 * meio.y()) - ((a.y() + b.y()) * 0.5),
        )

    def _redistribuir_molde_por_deslocamentos(
        self,
        canvas,
        el: dict,
        pontos_base: list,
        deslocamentos_principais: dict[int, tuple[float, float]],
    ) -> bool:
        if len(pontos_base) < 4 or not deslocamentos_principais:
            return False
        fechado = len(pontos_base) >= 2 and canvas._dist(
            QPointF(float(pontos_base[0][0]), float(pontos_base[0][1])),
            QPointF(float(pontos_base[-1][0]), float(pontos_base[-1][1])),
        ) <= 1e-6
        n = len(pontos_base) - 1 if fechado else len(pontos_base)
        if n < 2:
            return False

        principais = sorted(i for i in self._indices_pontos_principais_molde(canvas, el) if 0 <= i < n)
        if len(principais) < 2:
            return False
        deslocamentos = {idx: disp for idx, disp in deslocamentos_principais.items() if idx in principais}
        if not deslocamentos:
            return False

        novos = list(pontos_base)
        for idx, (dx, dy) in deslocamentos.items():
            x, y = pontos_base[idx]
            nx = float(x) + dx
            ny = float(y) + dy
            if self._modo_discreto():
                nx = round(nx, 2)
                ny = round(ny, 2)
            novos[idx] = (nx, ny)

        pares: list[tuple[int, int]] = []
        if fechado:
            for i, a in enumerate(principais):
                pares.append((a, principais[(i + 1) % len(principais)]))
        else:
            pares.extend((a, b) for a, b in zip(principais, principais[1:]))

        for a, b in pares:
            indices = self._indices_intervalo(a, b, n, fechado)
            if len(indices) <= 2:
                continue
            dxa, dya = deslocamentos.get(a, (0.0, 0.0))
            dxb, dyb = deslocamentos.get(b, (0.0, 0.0))
            if abs(dxa) <= 1e-9 and abs(dya) <= 1e-9 and abs(dxb) <= 1e-9 and abs(dyb) <= 1e-9:
                continue
            denom = max(1, len(indices) - 1)
            for pos, idx_local in enumerate(indices[1:-1], start=1):
                t = max(0.0, min(1.0, pos / float(denom)))
                ddx = (dxa * (1.0 - t)) + (dxb * t)
                ddy = (dya * (1.0 - t)) + (dyb * t)
                x, y = pontos_base[idx_local]
                nx = float(x) + ddx
                ny = float(y) + ddy
                if self._modo_discreto():
                    nx = round(nx, 2)
                    ny = round(ny, 2)
                novos[idx_local] = (nx, ny)

        if fechado and len(novos) >= 2:
            novos[-1] = novos[0]
        el["pontos"] = novos
        self._sincronizar_curva_suave(el)
        return True

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
        if el.get("tipo") != "polyline":
            return
        pontos = [QPointF(float(x), float(y)) for x, y in el.get("pontos", [])]
        if len(pontos) < 2:
            return
        painter.save()
        painter.setBrush(Qt.NoBrush)
        cor = "#2da8ff"
        esp = max(1.6, float(el.get("espessura", 1.0)) + 0.7)
        if self._elemento_curva_suave(el) and hasattr(canvas, "_desenhar_curva_suave_por_pontos"):
            canvas._desenhar_curva_suave_por_pontos(painter, pontos, cor=cor, espessura=esp, estilo="solid")
        else:
            canvas._desenhar_polilinha(painter, pontos, cor=cor, espessura=esp, estilo="solid", amplitude=1.0)
        painter.restore()

    def _desenhar_hover(self, canvas, painter):
        if self._hover_ponto_poly is not None:
            idx, p_idx = self._hover_ponto_poly
            if 0 <= idx < len(canvas.cena.elementos):
                el = canvas.cena.elementos[idx]
                pontos = self._pontos_controle_curva(el) if self._curva_tracado_real(el) else el.get("pontos", [])
                if 0 <= p_idx < len(pontos):
                    ponto = self._ponto_qt(pontos[p_idx])
                    if ponto is None:
                        return
                    pt = canvas._cena_para_tela(ponto)
                    painter.setPen(QPen(QColor("#2da8ff"), 1.4))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawEllipse(int(pt.x() - 9), int(pt.y() - 9), 18, 18)

        if self._ponto_selecionado is not None:
            idx, p_idx = self._ponto_selecionado
            if 0 <= idx < len(canvas.cena.elementos):
                el = canvas.cena.elementos[idx]
                pontos = self._pontos_controle_curva(el) if self._curva_tracado_real(el) else el.get("pontos", [])
                if 0 <= p_idx < len(pontos):
                    ponto = self._ponto_qt(pontos[p_idx])
                    if ponto is None:
                        return
                    pt = canvas._cena_para_tela(ponto)
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

        for idx, tipo, c_idx in self._controles_selecionados:
            if not (0 <= idx < len(canvas.cena.elementos)):
                continue
            el = canvas.cena.elementos[idx]
            chave = "controle_cantos" if tipo == "canto" else "controle_auxiliares"
            controles = el.get(chave, [])
            if not (0 <= c_idx < len(controles)):
                continue
            controle = self._ponto_qt(controles[c_idx])
            if controle is None:
                continue
            pt = canvas._cena_para_tela(controle)
            painter.setPen(QPen(QColor("#66d9ff"), 2.0))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(int(pt.x() - 11), int(pt.y() - 11), 22, 22)

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
