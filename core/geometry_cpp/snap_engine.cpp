#include "snap_engine.h"
#include <algorithm>
#include <cmath>
#include <limits>

namespace guimma {

namespace {

bool better_snap(const SnapPoint& a, const SnapPoint& b) {
    if (a.priority != b.priority) {
        return a.priority < b.priority;
    }
    return a.distance < b.distance;
}

}

std::string snap_kind_to_string(SnapKind kind) {
    switch (kind) {
        case SnapKind::Node: return "no";
        case SnapKind::Control: return "controle";
        case SnapKind::MainControl: return "controle principal";
        case SnapKind::HelperControl: return "controle auxiliar";
        case SnapKind::Border: return "borda";
        case SnapKind::Midpoint: return "ponto medio";
        case SnapKind::Center: return "centro";
        case SnapKind::Intersection: return "intersecao";
        case SnapKind::Grid: return "grade";
        case SnapKind::Coord: return "coord";
        case SnapKind::Grainline: return "fio";
        case SnapKind::Label: return "nome";
        case SnapKind::None:
        default: return "";
    }
}

void SnapEngine::clear() {
    elements_.clear();
    index_.clear();
}

void SnapEngine::set_tolerance_px(double tolerance_px) {
    tolerance_px_ = std::max(0.1, tolerance_px);
}

void SnapEngine::set_grid(bool enabled, double step) {
    snap_grid_ = enabled;
    grid_step_ = std::max(0.000001, step);
}

void SnapEngine::add_polyline(const PolylineElement& element) {
    if (!element.participates || element.points.size() < 2) {
        elements_.push_back(element);
        return;
    }

    elements_.push_back(element);
    for (std::size_t i = 1; i < element.points.size(); ++i) {
        const Point& a = element.points[i - 1];
        const Point& b = element.points[i];
        if (distance(a, b) <= 1e-12) {
            continue;
        }
        index_.add_segment(element.element_index, a, b);
    }
}

std::vector<SnapPoint> SnapEngine::candidates(const Point& cursor, double zoom, double tolerance_px) const {
    const double effective_tolerance = tolerance_px > 0.0 ? tolerance_px : tolerance_px_;
    const double tolerance_scene = effective_tolerance / std::max(zoom, 0.001);
    const BBox search_box{
        cursor.x - (tolerance_scene * 2.5),
        cursor.y - (tolerance_scene * 2.5),
        cursor.x + (tolerance_scene * 2.5),
        cursor.y + (tolerance_scene * 2.5)
    };

    std::vector<SnapPoint> out;

    for (const auto& element : elements_) {
        if (!element.participates) {
            continue;
        }

        for (const auto& p : element.main_controls) {
            add_point_candidate(out, cursor, p, SnapKind::MainControl, element.element_index, element.element_priority);
        }
        for (const auto& p : element.helper_controls) {
            add_point_candidate(out, cursor, p, SnapKind::HelperControl, element.element_index, element.element_priority);
        }

        if (!element.official_controls.empty()) {
            for (const auto& p : element.official_controls) {
                add_point_candidate(out, cursor, p, SnapKind::Node, element.element_index, element.element_priority);
            }
        } else {
            for (const auto& p : element.points) {
                add_point_candidate(out, cursor, p, SnapKind::Node, element.element_index, element.element_priority);
            }
        }
    }

    const auto segments = index_.query(search_box);
    for (const auto& segment : segments) {
        add_segment_candidates(out, cursor, segment, priority_for_element(segment.element_index));
    }

    add_grid_candidate(out, cursor, tolerance_scene);

    out.erase(
        std::remove_if(out.begin(), out.end(), [tolerance_scene](const SnapPoint& sp) {
            return sp.distance > tolerance_scene;
        }),
        out.end()
    );

    std::sort(out.begin(), out.end(), better_snap);
    return out;
}

std::optional<SnapPoint> SnapEngine::nearest(const Point& cursor, double zoom, double tolerance_px) const {
    auto list = candidates(cursor, zoom, tolerance_px);
    if (list.empty()) {
        return std::nullopt;
    }
    return list.front();
}

std::size_t SnapEngine::element_count() const {
    return elements_.size();
}

std::size_t SnapEngine::segment_count() const {
    return index_.size();
}

void SnapEngine::add_point_candidate(std::vector<SnapPoint>& out, const Point& cursor, const Point& point, SnapKind kind, int element_index, int element_priority) const {
    SnapPoint candidate;
    candidate.point = point;
    candidate.kind = kind;
    candidate.element_index = element_index;
    candidate.distance = distance(cursor, point);
    candidate.priority = (element_priority * 100) + kind_priority(kind);
    out.push_back(candidate);
}

void SnapEngine::add_segment_candidates(std::vector<SnapPoint>& out, const Point& cursor, const Segment& segment, int element_priority) const {
    const Point midpoint{(segment.a.x + segment.b.x) * 0.5, (segment.a.y + segment.b.y) * 0.5};
    add_point_candidate(out, cursor, midpoint, SnapKind::Midpoint, segment.element_index, element_priority);

    const Point projected = project_on_segment(cursor, segment.a, segment.b);
    add_point_candidate(out, cursor, projected, SnapKind::Border, segment.element_index, element_priority);
}

void SnapEngine::add_grid_candidate(std::vector<SnapPoint>& out, const Point& cursor, double tolerance_scene) const {
    if (!snap_grid_) {
        return;
    }
    const double gx = std::round(cursor.x / grid_step_) * grid_step_;
    const double gy = std::round(cursor.y / grid_step_) * grid_step_;
    const Point grid_point{gx, gy};
    const double d = distance(cursor, grid_point);
    if (d > tolerance_scene * 0.55) {
        return;
    }
    SnapPoint candidate;
    candidate.point = grid_point;
    candidate.kind = SnapKind::Grid;
    candidate.element_index = -1;
    candidate.distance = d;
    candidate.priority = 400 + kind_priority(SnapKind::Grid);
    out.push_back(candidate);
}

int SnapEngine::kind_priority(SnapKind kind) const {
    switch (kind) {
        case SnapKind::Intersection: return 0;
        case SnapKind::MainControl:
        case SnapKind::HelperControl:
        case SnapKind::Control: return 1;
        case SnapKind::Node: return 2;
        case SnapKind::Center: return 3;
        case SnapKind::Midpoint: return 4;
        case SnapKind::Border:
        case SnapKind::Grid: return 5;
        case SnapKind::Coord: return 6;
        case SnapKind::Grainline: return 7;
        case SnapKind::Label: return 8;
        case SnapKind::None:
        default: return 9;
    }
}

int SnapEngine::priority_for_element(int element_index) const {
    for (const auto& element : elements_) {
        if (element.element_index == element_index) {
            return element.element_priority;
        }
    }
    return 3;
}

}
