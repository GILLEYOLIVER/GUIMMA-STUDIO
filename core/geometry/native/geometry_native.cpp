// Backend opcional em C++ (pybind11) para operações geométricas críticas.
// Build (exemplo): c++ -O3 -Wall -shared -std=c++17 -fPIC \
//   $(python -m pybind11 --includes) geometry_native.cpp \
//   -o geometry_native$(python-config --extension-suffix)

#include <cmath>
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

PYBIND11_MODULE(geometry_native, m) {
    m.doc() = "Operações geométricas nativas para GUIMMA Studio";
    m.def("internal_angle", &internal_angle, "Ângulo interno entre três pontos");
    m.def("point_in_polygon", &point_in_polygon, "Teste ponto em polígono");
    m.def("point_segment_distance", &point_segment_distance, "Distância mínima entre ponto e segmento");
    m.def("polyline_perimeter", &polyline_perimeter, "Perímetro de polyline");
}

