import matplotlib.pyplot as plt
import numpy as np
from scipy.special import binom

# ---------- Função para Bezier cúbica ----------
def bezier_cubica(p0, p1, p2, p3, t):
    """Retorna ponto na curva Bezier cúbica para t em [0,1]."""
    return (1-t)**3 * p0 + 3*(1-t)**2*t * p1 + 3*(1-t)*t**2 * p2 + t**3 * p3

def curva_bezier_cubica(pontos_controle, num=100):
    """pontos_controle = [p0, p1, p2, p3] como arrays (x,y)"""
    p0, p1, p2, p3 = pontos_controle
    ts = np.linspace(0, 1, num)
    return np.array([bezier_cubica(p0, p1, p2, p3, t) for t in ts])

# ---------- Função para Catmull-Rom centrípeta ----------
def catmull_rom_centripetal(p0, p1, p2, p3, num=20):
    """Segmento entre p1 e p2 para Catmull-Rom centrípeta (alpha=0.5)."""
    alpha = 0.5
    def tj(ti, pi, pj):
        d = np.linalg.norm(pi - pj)
        return ti + d**alpha
    t0 = 0.0
    t1 = tj(t0, p0, p1)
    t2 = tj(t1, p1, p2)
    t3 = tj(t2, p2, p3)
    pts = []
    for i in range(num):
        t = t1 + (t2 - t1) * i / (num - 1)
        # Interpolações
        a1 = ((t2 - t)/(t2 - t0)) * p0 + ((t - t0)/(t2 - t0)) * p2 if t2 != t0 else p0
        a2 = ((t3 - t)/(t3 - t1)) * p1 + ((t - t1)/(t3 - t1)) * p3 if t3 != t1 else p1
        # (versão simplificada para demonstração, mas funcional)
        # Método completo:
        a1 = ((t2 - t)/(t2 - t0))*p0 + ((t - t0)/(t2 - t0))*p2 if abs(t2-t0)>1e-9 else p0
        a2 = ((t3 - t)/(t3 - t1))*p1 + ((t - t1)/(t3 - t1))*p3 if abs(t3-t1)>1e-9 else p1
        b1 = ((t2 - t)/(t2 - t1))*a1 + ((t - t1)/(t2 - t1))*a2 if abs(t2-t1)>1e-9 else a1
        pts.append(b1)
    return np.array(pts)

def curva_catmullrom_completa(pontos, num_por_trecho=30):
    """pontos = lista de (x,y) arrays. Gera curva completa."""
    if len(pontos) < 2:
        return np.array(pontos)
    if len(pontos) == 2:
        return np.linspace(pontos[0], pontos[1], num_por_trecho)
    resultado = []
    for i in range(len(pontos)-1):
        p0 = pontos[i-1] if i > 0 else 2*pontos[i] - pontos[i+1]
        p1 = pontos[i]
        p2 = pontos[i+1]
        p3 = pontos[i+2] if i+2 < len(pontos) else 2*pontos[i+1] - pontos[i]
        trecho = catmull_rom_centripetal(p0, p1, p2, p3, num_por_trecho)
        if i == 0:
            resultado.extend(trecho)
        else:
            resultado.extend(trecho[1:])
    return np.array(resultado)

# ---------- Função para Bezier quadrática ----------
def bezier_quadratica(p0, p1, p2, t):
    return (1-t)**2 * p0 + 2*(1-t)*t * p1 + t**2 * p2

def curva_bezier_quadratica(pontos_controle, num=100):
    p0, p1, p2 = pontos_controle
    ts = np.linspace(0, 1, num)
    return np.array([bezier_quadratica(p0, p1, p2, t) for t in ts])

# ---------- DEFINIR PONTOS PARA EXEMPLO ----------
# Mesmos pontos de controle (para curvas cúbica e Catmull-Rom usam os mesmos 4 pontos)
pt_controle = [
    np.array([0.0, 0.0]),   # p0
    np.array([1.0, 2.0]),   # p1 (handle de controle para cúbica / ponto para CR)
    np.array([3.0, 2.5]),   # p2
    np.array([4.0, 0.0])    # p3
]

# Para Catmull-Rom, usamos esses mesmos pontos como pontos de passagem (curva passa por eles)
pontos_cr = pt_controle.copy()

# Para Bezier quadrática, preciso de 3 pontos: p0, (handle), p2 (o ponto médio não é usado diretamente)
# Vou definir usando p0, p1, p3 para ter uma forma comparável.
pt_quad = [pt_controle[0], pt_controle[1], pt_controle[3]]

# ---------- GERAR CURVAS ----------
curva_cubica = curva_bezier_cubica(pt_controle, num=200)
curva_cr = curva_catmullrom_completa(pontos_cr, num_por_trecho=40)
curva_quad = curva_bezier_quadratica(pt_quad, num=200)

# ---------- PLOTAR ----------
fig, axes = plt.subplots(1, 3, figsize=(15, 5))

# Plot 1: Bezier Cúbica
ax = axes[0]
ax.plot(curva_cubica[:,0], curva_cubica[:,1], 'b-', linewidth=2, label='Curva Bezier cúbica')
# Desenhar pontos de controle e handles
ctrl = np.array(pt_controle)
ax.plot(ctrl[:,0], ctrl[:,1], 'ro', markersize=6, label='Pontos de controle')
for i in range(len(ctrl)-1):
    ax.plot([ctrl[i,0], ctrl[i+1,0]], [ctrl[i,1], ctrl[i+1,1]], 'k--', alpha=0.5)
ax.legend()
ax.set_title("Bezier Cúbica (com handles visíveis)\nAlças = linhas tracejadas")
ax.set_aspect('equal')
ax.grid(True)

# Plot 2: Catmull-Rom
ax = axes[1]
ax.plot(curva_cr[:,0], curva_cr[:,1], 'g-', linewidth=2, label='Catmull-Rom centrípeta')
# Pontos de passagem
pts = np.array(pontos_cr)
ax.plot(pts[:,0], pts[:,1], 'ro', markersize=6, label='Pontos clicados (curva passa exatamente)')
ax.legend()
ax.set_title("Catmull-Rom (modo NP atual)\nSem handles - passa por todos os pontos")
ax.set_aspect('equal')
ax.grid(True)

# Plot 3: Bezier Quadrática
ax = axes[2]
ax.plot(curva_quad[:,0], curva_quad[:,1], 'm-', linewidth=2, label='Bezier quadrática')
ctrl_q = np.array(pt_quad)
ax.plot(ctrl_q[:,0], ctrl_q[:,1], 'ro', markersize=6, label='Pontos de controle')
ax.plot([ctrl_q[0,0], ctrl_q[1,0]], [ctrl_q[0,1], ctrl_q[1,1]], 'k--', alpha=0.5)
ax.plot([ctrl_q[1,0], ctrl_q[2,0]], [ctrl_q[1,1], ctrl_q[2,1]], 'k--', alpha=0.5)
ax.legend()
ax.set_title("Bezier Quadrática (2P / 3P)\nApenas 1 ponto de controle")
ax.set_aspect('equal')
ax.grid(True)

plt.tight_layout()
plt.show()