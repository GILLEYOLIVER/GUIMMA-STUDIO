// Backend opcional em C++ (pybind11) para operações geométricas críticas.
// Build (exemplo): c++ -O3 -Wall -shared -std=c++17 -fPIC \
//   $(python -m pybind11 --includes) geometry_native.cpp \
//   -o geometry_native$(python-config --extension-suffix)

#include <cmath>
#include <algorithm>
#include <vector>
#include <utility>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

namespace py = pybind11;

static double internal_angle(
    const std::pair<double, double>& a,
    const std::pair<double, double>& b,
    const std::pair<double, double>& c) {
    const double bax = a.first - b.first;
    const double bay = a.second - b.second;
    const double bcx = c.first - b.first;
    const double bcy = c.second - b.second;
    const double na = std::sqrt((bax * bax) + (bay * bay));
    const double nb = std::sqrt((bcx * bcx) + (bcy * bcy));
    if (na <= 1e-9 || nb <= 1e-9) {
        return 180.0;
    }
    double cosv = ((bax * bcx) + (bay * bcy)) / (na * nb);
    if (cosv < -1.0) cosv = -1.0;
    if (cosv > 1.0) cosv = 1.0;
    return std::acos(cosv) * (180.0 / 3.14159265358979323846);
}

static bool point_in_polygon(
    const std::pair<double, double>& point,
    const std::vector<std::pair<double, double>>& polygon) {
    if (polygon.size() < 3) {
        return false;
    }
    bool inside = false;
    std::size_t j = polygon.size() - 1;
    const double x = point.first;
    const double y = point.second;
    for (std::size_t i = 0; i < polygon.size(); ++i) {
        const auto& pi = polygon[i];
        const auto& pj = polygon[j];
        const bool intersects = ((pi.second > y) != (pj.second > y))
            && (x < ((pj.first - pi.first) * (y - pi.second) / std::max((pj.second - pi.second), 1e-12)) + pi.first);
        if (intersects) inside = !inside;
        j = i;
    }
    return inside;
}


static double point_segment_distance(
    const std::pair<double, double>& p,
    const std::pair<double, double>& a,
    const std::pair<double, double>& b) {
    const double px = p.first;
    const double py = p.second;
    const double ax = a.first;
    const double ay = a.second;
    const double bx = b.first;
    const double by = b.second;
    const double abx = bx - ax;
    const double aby = by - ay;
    const double denom = (abx * abx) + (aby * aby);
    if (denom <= 1e-12) {
        return std::sqrt(((px - ax) * (px - ax)) + ((py - ay) * (py - ay)));
    }
    double t = (((px - ax) * abx) + ((py - ay) * aby)) / denom;
    if (t < 0.0) t = 0.0;
    if (t > 1.0) t = 1.0;
    const double qx = ax + (abx * t);
    const double qy = ay + (aby * t);
    return std::sqrt(((px - qx) * (px - qx)) + ((py - qy) * (py - qy)));
}

static double polyline_perimeter(const std::vector<std::pair<double, double>>& points) {
    if (points.size() < 2) {
        return 0.0;
    }
    double acc = 0.0;
    for (std::size_t i = 1; i < points.size(); ++i) {
        const double dx = points[i].first - points[i - 1].first;
        const double dy = points[i].second - points[i - 1].second;
        acc += std::sqrt((dx * dx) + (dy * dy));
    }
    return acc;
}

static double quadratic_bezier_parameter_for_point(
    const std::pair<double, double>& p0,
    const std::pair<double, double>& p_mid,
    const std::pair<double, double>& p2) {
    const double vx = p2.first - p0.first;
    const double vy = p2.second - p0.second;
    const double denom = (vx * vx) + (vy * vy);
    if (denom <= 1e-9) {
        return 0.5;
    }
    const double raw = (((p_mid.first - p0.first) * vx) + ((p_mid.second - p0.second) * vy)) / denom;
    return std::max(0.05, std::min(0.95, raw));
}

static std::pair<double, double> quadratic_bezier_control_for_point(
    const std::pair<double, double>& p0,
    const std::pair<double, double>& p_mid,
    const std::pair<double, double>& p2) {
    const double t = quadratic_bezier_parameter_for_point(p0, p_mid, p2);
    const double u = 1.0 - t;
    const double denom = std::max(1e-9, 2.0 * u * t);
    return {
        (p_mid.first - (u * u * p0.first) - (t * t * p2.first)) / denom,
        (p_mid.second - (u * u * p0.second) - (t * t * p2.second)) / denom,
    };
}

static std::vector<std::pair<double, double>> sample_quadratic_bezier(
    const std::pair<double, double>& p0,
    const std::pair<double, double>& control,
    const std::pair<double, double>& p2,
    int segments) {
    const int n = std::max(2, segments);
    std::vector<std::pair<double, double>> out;
    out.reserve(static_cast<std::size_t>(n + 1));
    for (int i = 0; i <= n; ++i) {
        const double t = static_cast<double>(i) / static_cast<double>(n);
        const double u = 1.0 - t;
        out.push_back({
            (u * u * p0.first) + (2.0 * u * t * control.first) + (t * t * p2.first),
            (u * u * p0.second) + (2.0 * u * t * control.second) + (t * t * p2.second),
        });
    }
    return out;
}

PYBIND11_MODULE(geometry_native, m) {
    m.def("quadratic_bezier_parameter_for_point", &quadratic_bezier_parameter_for_point, "Parametro t da parabola por projecao na corda");
    m.def("quadratic_bezier_control_for_point", &quadratic_bezier_control_for_point, "Controle quadratico que passa por tres pontos");
    m.def("sample_quadratic_bezier", &sample_quadratic_bezier, "Amostra Bezier quadratica");
    m.doc() = "Operações geométricas nativas para GUIMMA Studio";
    m.def("internal_angle", &internal_angle, "Ângulo interno entre três pontos");
    m.def("point_in_polygon", &point_in_polygon, "Teste ponto em polígono");
    m.def("point_segment_distance", &point_segment_distance, "Distância mínima entre ponto e segmento");
    m.def("polyline_perimeter", &polyline_perimeter, "Perímetro de polyline");
}

