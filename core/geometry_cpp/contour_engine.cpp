#include "contour_engine.h"
#include "intersection_engine.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <map>
#include <set>
#include <utility>

namespace guimma {

namespace {

using PointKey = std::pair<long long, long long>;
using DirectedEdge = std::pair<PointKey, PointKey>;

bool near_point(const Point& a, const Point& b, double tol) {
    return std::abs(a.x - b.x) <= tol && std::abs(a.y - b.y) <= tol;
}

PointKey key_point(const Point& p, double tol) {
    const double safe_tol = std::max(std::abs(tol), 1e-12);
    return {
        static_cast<long long>(std::llround(p.x / safe_tol)),
        static_cast<long long>(std::llround(p.y / safe_tol))
    };
}

std::vector<Point> dedup_consecutive(const std::vector<Point>& points, double tol) {
    std::vector<Point> out;
    for (const auto& p : points) {
        if (out.empty() || !near_point(out.back(), p, tol)) {
            out.push_back(p);
        }
    }
    return out;
}

std::vector<PointKey> canonical_cycle(const std::vector<PointKey>& cycle) {
    if (cycle.empty()) {
        return {};
    }
    std::vector<PointKey> best;
    auto consider = [&best](const std::vector<PointKey>& source) {
        for (std::size_t offset = 0; offset < source.size(); ++offset) {
            std::vector<PointKey> candidate;
            candidate.reserve(source.size());
            for (std::size_t index = 0; index < source.size(); ++index) {
                candidate.push_back(source[(offset + index) % source.size()]);
            }
            if (best.empty() || candidate < best) {
                best = std::move(candidate);
            }
        }
    };
    consider(cycle);
    consider(std::vector<PointKey>(cycle.rbegin(), cycle.rend()));
    return best;
}

std::optional<ContourResult> select_smallest_contour(
    const std::vector<std::vector<Point>>& candidates,
    const Point& point,
    double tolerance
) {
    std::optional<ContourResult> best;
    double best_area = std::numeric_limits<double>::infinity();
    double best_perimeter = std::numeric_limits<double>::infinity();

    for (const auto& source : candidates) {
        auto poly = normalize_closed_polyline(source, true, tolerance);
        if (!contour_is_valid(poly, tolerance)) {
            continue;
        }
        if (!point_in_polygon_or_boundary(point, poly, tolerance)) {
            continue;
        }
        const double area = std::abs(polygon_area(poly));
        const double perimeter = polyline_length(poly);
        if (area < best_area - 1e-8 || (std::abs(area - best_area) <= 1e-8 && perimeter < best_perimeter)) {
            best_area = area;
            best_perimeter = perimeter;
            best = ContourResult{true, poly, area, perimeter};
        }
    }

    return best;
}

}

std::vector<Point> ensure_closed(const std::vector<Point>& polyline, double tolerance) {
    auto out = dedup_consecutive(polyline, tolerance);
    if (out.size() >= 2 && !near_point(out.front(), out.back(), tolerance)) {
        out.push_back(out.front());
    }
    return out;
}

double polygon_area(const std::vector<Point>& polygon) {
    if (polygon.size() < 3) {
        return 0.0;
    }
    double acc = 0.0;
    for (std::size_t i = 1; i < polygon.size(); ++i) {
        const auto& a = polygon[i - 1];
        const auto& b = polygon[i];
        acc += (a.x * b.y) - (b.x * a.y);
    }
    return 0.5 * acc;
}

double polyline_length(const std::vector<Point>& polyline) {
    if (polyline.size() < 2) {
        return 0.0;
    }
    double total = 0.0;
    for (std::size_t i = 1; i < polyline.size(); ++i) {
        total += distance(polyline[i - 1], polyline[i]);
    }
    return total;
}

bool point_in_polygon(const Point& point, const std::vector<Point>& polygon) {
    const auto poly = ensure_closed(polygon, 1e-9);
    if (poly.size() < 4) {
        return false;
    }
    for (std::size_t i = 1; i < poly.size(); ++i) {
        if (point_on_segment(point, poly[i - 1], poly[i], 1e-7)) {
            return true;
        }
    }
    bool inside = false;
    const double px = point.x;
    const double py = point.y;
    for (std::size_t i = 0, j = poly.size() - 2; i < poly.size() - 1; j = i++) {
        const auto& a = poly[i];
        const auto& b = poly[j];
        const bool crosses = ((a.y > py) != (b.y > py));
        if (!crosses) {
            continue;
        }
        const double x_intersection = (b.x - a.x) * (py - a.y) / ((b.y - a.y) + 1e-30) + a.x;
        if (px < x_intersection) {
            inside = !inside;
        }
    }
    return inside;
}

bool point_in_polygon_or_boundary(const Point& point, const std::vector<Point>& polygon, double tolerance) {
    const auto poly = ensure_closed(polygon, tolerance);
    if (poly.size() < 4) {
        return false;
    }
    for (std::size_t i = 1; i < poly.size(); ++i) {
        if (point_on_segment(point, poly[i - 1], poly[i], tolerance)) {
            return true;
        }
    }
    return point_in_polygon(point, poly);
}

bool contour_is_valid(const std::vector<Point>& polygon, double tolerance) {
    const auto poly = ensure_closed(polygon, tolerance);
    if (poly.size() < 4) {
        return false;
    }
    if (std::abs(polygon_area(poly)) <= tolerance) {
        return false;
    }
    if (polyline_length(poly) <= tolerance) {
        return false;
    }
    return true;
}

std::vector<Segment2D> explode_segments(const std::vector<std::vector<Point>>& polylines) {
    std::vector<Segment2D> out;
    for (const auto& poly : polylines) {
        if (poly.size() < 2) {
            continue;
        }
        for (std::size_t i = 1; i < poly.size(); ++i) {
            if (distance(poly[i - 1], poly[i]) > 1e-12) {
                out.push_back({poly[i - 1], poly[i]});
            }
        }
    }
    return out;
}

std::vector<Segment2D> split_segments_at_intersections(const std::vector<Segment2D>& segments, double tolerance) {
    std::vector<Segment2D> out;
    for (std::size_t i = 0; i < segments.size(); ++i) {
        const auto& segment = segments[i];
        std::vector<Point> points_on_segment = {segment.a, segment.b};
        for (std::size_t j = 0; j < segments.size(); ++j) {
            if (i == j) {
                continue;
            }
            const auto intersection = segment_intersection(
                segment.a,
                segment.b,
                segments[j].a,
                segments[j].b,
                tolerance
            );
            if (intersection.has_value()) {
                points_on_segment.push_back(intersection.value());
            }
        }

        std::sort(points_on_segment.begin(), points_on_segment.end(), [&segment](const Point& lhs, const Point& rhs) {
            const double lhs_dx = lhs.x - segment.a.x;
            const double lhs_dy = lhs.y - segment.a.y;
            const double rhs_dx = rhs.x - segment.a.x;
            const double rhs_dy = rhs.y - segment.a.y;
            return ((lhs_dx * lhs_dx) + (lhs_dy * lhs_dy)) < ((rhs_dx * rhs_dx) + (rhs_dy * rhs_dy));
        });

        std::vector<Point> dedup;
        for (const auto& point : points_on_segment) {
            if (dedup.empty() || !near_point(dedup.back(), point, tolerance)) {
                dedup.push_back(point);
            }
        }
        for (std::size_t index = 1; index < dedup.size(); ++index) {
            if (!near_point(dedup[index - 1], dedup[index], tolerance)) {
                out.push_back({dedup[index - 1], dedup[index]});
            }
        }
    }
    return out;
}

std::vector<std::vector<Point>> find_cycles(const std::vector<Segment2D>& segments, double tolerance) {
    std::map<PointKey, Point> node_points;
    std::map<PointKey, std::set<PointKey>> adjacency;
    for (const auto& segment : segments) {
        const auto a = key_point(segment.a, tolerance);
        const auto b = key_point(segment.b, tolerance);
        if (a == b) {
            continue;
        }
        node_points.emplace(a, segment.a);
        node_points.emplace(b, segment.b);
        adjacency[a].insert(b);
        adjacency[b].insert(a);
    }

    std::map<std::vector<PointKey>, std::vector<Point>> cycles;
    const std::size_t max_depth = std::max<std::size_t>(64, std::min<std::size_t>(1024, adjacency.size() + 8));
    for (const auto& [start, unused] : adjacency) {
        (void) unused;
        std::vector<std::pair<PointKey, std::vector<PointKey>>> stack = {{start, {start}}};
        while (!stack.empty()) {
            auto [node, path] = std::move(stack.back());
            stack.pop_back();
            if (path.size() > max_depth) {
                continue;
            }
            for (const auto& next : adjacency[node]) {
                if (path.size() >= 2 && next == path[path.size() - 2]) {
                    continue;
                }
                if (next == start && path.size() >= 3) {
                    const auto canonical = canonical_cycle(path);
                    if (cycles.find(canonical) == cycles.end()) {
                        std::vector<Point> points;
                        points.reserve(path.size() + 1);
                        for (const auto& key : path) {
                            points.push_back(node_points[key]);
                        }
                        points.push_back(points.front());
                        cycles.emplace(canonical, std::move(points));
                    }
                    continue;
                }
                if (std::find(path.begin(), path.end(), next) != path.end()) {
                    continue;
                }
                auto extended_path = path;
                extended_path.push_back(next);
                stack.emplace_back(next, std::move(extended_path));
            }
        }
    }

    std::vector<std::vector<Point>> out;
    out.reserve(cycles.size());
    for (auto& [unused, points] : cycles) {
        (void) unused;
        out.push_back(std::move(points));
    }
    return out;
}

std::vector<std::vector<Point>> faces_from_segments(const std::vector<Segment2D>& segments, double tolerance) {
    constexpr double pi = 3.14159265358979323846;
    std::map<PointKey, Point> node_points;
    std::map<PointKey, std::vector<std::pair<PointKey, double>>> outgoing;
    for (const auto& segment : segments) {
        const auto a = key_point(segment.a, tolerance);
        const auto b = key_point(segment.b, tolerance);
        if (a == b) {
            continue;
        }
        node_points.emplace(a, segment.a);
        node_points.emplace(b, segment.b);
        outgoing[a].push_back({b, std::atan2(segment.b.y - segment.a.y, segment.b.x - segment.a.x)});
        outgoing[b].push_back({a, std::atan2(segment.a.y - segment.b.y, segment.a.x - segment.b.x)});
    }
    for (auto& [unused, edges] : outgoing) {
        (void) unused;
        std::sort(edges.begin(), edges.end(), [](const auto& lhs, const auto& rhs) {
            return lhs.second < rhs.second;
        });
    }

    auto next_left_face = [&outgoing, &node_points](const PointKey& node, const PointKey& from_node) -> std::optional<PointKey> {
        const auto found = outgoing.find(node);
        if (found == outgoing.end() || found->second.empty()) {
            return std::nullopt;
        }
        const auto& node_point = node_points.at(node);
        const auto& from_point = node_points.at(from_node);
        const double back_angle = std::atan2(from_point.y - node_point.y, from_point.x - node_point.x);
        double best_delta = std::numeric_limits<double>::infinity();
        std::optional<PointKey> best;
        for (const auto& [next, angle] : found->second) {
            double delta = std::fmod(back_angle - angle + (2.0 * pi), 2.0 * pi);
            if (delta <= 1e-12) {
                delta += 2.0 * pi;
            }
            if (delta < best_delta) {
                best_delta = delta;
                best = next;
            }
        }
        return best;
    };

    std::set<DirectedEdge> visited;
    std::vector<std::vector<Point>> faces;
    const std::size_t max_steps = std::max<std::size_t>(16, segments.size() * 4);
    for (const auto& [start, edges] : outgoing) {
        for (const auto& [next, unused] : edges) {
            (void) unused;
            const DirectedEdge edge{start, next};
            if (visited.find(edge) != visited.end()) {
                continue;
            }
            std::vector<PointKey> face_nodes;
            auto current_start = start;
            auto current_end = next;
            for (std::size_t step = 0; step < max_steps; ++step) {
                const DirectedEdge current_edge{current_start, current_end};
                if (visited.find(current_edge) != visited.end()) {
                    break;
                }
                visited.insert(current_edge);
                face_nodes.push_back(current_start);
                const auto following = next_left_face(current_end, current_start);
                if (!following.has_value()) {
                    break;
                }
                current_start = current_end;
                current_end = following.value();
                if (current_start == start && current_end == next) {
                    face_nodes.push_back(current_start);
                    std::vector<Point> points;
                    points.reserve(face_nodes.size());
                    for (const auto& key : face_nodes) {
                        points.push_back(node_points[key]);
                    }
                    if (points.size() >= 4 && std::abs(polygon_area(points)) > 1e-8) {
                        faces.push_back(std::move(points));
                    }
                    break;
                }
            }
        }
    }
    return faces;
}

std::vector<Point> normalize_closed_polyline(const std::vector<Point>& polyline, bool clockwise, double tolerance) {
    auto poly = ensure_closed(polyline, tolerance);
    if (poly.size() < 4) {
        return poly;
    }
    const double area = polygon_area(poly);
    const bool is_clockwise = area < 0.0;
    if (is_clockwise != clockwise) {
        std::reverse(poly.begin(), poly.end());
        if (!near_point(poly.front(), poly.back(), tolerance)) {
            poly = ensure_closed(poly, tolerance);
        }
    }
    return poly;
}

std::vector<Point> unfold_mirrored_contour(
    const std::vector<Point>& polyline,
    int axis_kind,
    double axis_value,
    Point axis_p1,
    Point axis_p2,
    double tolerance
) {
    const double tol = std::max(std::abs(tolerance), 1e-9);
    auto base = dedup_consecutive(polyline, tol);
    if (base.size() >= 2 && near_point(base.front(), base.back(), tol)) {
        base.pop_back();
    }
    if (base.size() < 3) {
        return {};
    }

    auto side_value = [&](const Point& p) -> double {
        if (axis_kind == 0) {
            return p.y - axis_value;
        }
        if (axis_kind == 1) {
            return p.x - axis_value;
        }
        const double dx = axis_p2.x - axis_p1.x;
        const double dy = axis_p2.y - axis_p1.y;
        return (dx * (p.y - axis_p1.y)) - (dy * (p.x - axis_p1.x));
    };

    auto mirror = [&](const Point& p) -> Point {
        if (axis_kind == 0) {
            return {p.x, (2.0 * axis_value) - p.y};
        }
        if (axis_kind == 1) {
            return {(2.0 * axis_value) - p.x, p.y};
        }
        const double dx = axis_p2.x - axis_p1.x;
        const double dy = axis_p2.y - axis_p1.y;
        const double denom = (dx * dx) + (dy * dy);
        if (denom <= 1e-12) {
            return p;
        }
        const double t = (((p.x - axis_p1.x) * dx) + ((p.y - axis_p1.y) * dy)) / denom;
        const Point proj{axis_p1.x + (t * dx), axis_p1.y + (t * dy)};
        return {(2.0 * proj.x) - p.x, (2.0 * proj.y) - p.y};
    };

    auto intersection = [&](const Point& a, const Point& b) -> std::optional<Point> {
        const double va = side_value(a);
        const double vb = side_value(b);
        const double denom = va - vb;
        if (std::abs(denom) <= 1e-12) {
            return std::nullopt;
        }
        const double t = std::clamp(va / denom, 0.0, 1.0);
        return Point{a.x + ((b.x - a.x) * t), a.y + ((b.y - a.y) * t)};
    };

    std::vector<Point> augmented;
    augmented.reserve(base.size() + 4);
    auto append_unique = [&](const Point& p) {
        if (augmented.empty() || !near_point(augmented.back(), p, tol)) {
            augmented.push_back(p);
        }
    };
    for (std::size_t i = 0; i < base.size(); ++i) {
        const Point& a = base[i];
        const Point& b = base[(i + 1) % base.size()];
        append_unique(a);
        const double va = side_value(a);
        const double vb = side_value(b);
        if ((va < -tol && vb > tol) || (va > tol && vb < -tol)) {
            if (auto p = intersection(a, b); p.has_value()) {
                append_unique(p.value());
            }
        }
    }
    if (augmented.size() >= 2 && near_point(augmented.front(), augmented.back(), tol)) {
        augmented.pop_back();
    }
    if (augmented.size() < 3) {
        return {};
    }

    std::vector<int> axis_indices;
    for (std::size_t i = 0; i < augmented.size(); ++i) {
        if (std::abs(side_value(augmented[i])) <= tol) {
            axis_indices.push_back(static_cast<int>(i));
        }
    }
    if (axis_indices.size() < 2) {
        std::vector<Point> mirrored;
        mirrored.reserve(augmented.size());
        for (const auto& p : augmented) {
            mirrored.push_back(mirror(p));
        }
        std::reverse(mirrored.begin(), mirrored.end());
        std::vector<Point> out = augmented;
        out.insert(out.end(), mirrored.begin(), mirrored.end());
        return ensure_closed(out, tol);
    }

    auto axis_coord = [&](const Point& p) -> double {
        if (axis_kind == 0) {
            return p.x;
        }
        if (axis_kind == 1) {
            return p.y;
        }
        const double dx = axis_p2.x - axis_p1.x;
        const double dy = axis_p2.y - axis_p1.y;
        const double len = std::sqrt((dx * dx) + (dy * dy));
        if (len <= 1e-12) {
            return 0.0;
        }
        return (((p.x - axis_p1.x) * dx) + ((p.y - axis_p1.y) * dy)) / len;
    };

    int i0 = axis_indices.front();
    int i1 = axis_indices.front();
    double min_coord = axis_coord(augmented[i0]);
    double max_coord = min_coord;
    for (int idx : axis_indices) {
        const double coord = axis_coord(augmented[idx]);
        if (coord < min_coord) {
            min_coord = coord;
            i0 = idx;
        }
        if (coord > max_coord) {
            max_coord = coord;
            i1 = idx;
        }
    }
    if (i0 == i1) {
        return {};
    }

    auto path_between = [&](int start, int end) -> std::vector<Point> {
        std::vector<Point> out;
        const int total = static_cast<int>(augmented.size());
        int idx = ((start % total) + total) % total;
        int guard = total + 1;
        while (guard-- > 0) {
            out.push_back(augmented[idx]);
            if (idx == end) {
                break;
            }
            idx = (idx + 1) % total;
        }
        return out;
    };

    auto path_length = [](const std::vector<Point>& pts) -> double {
        double total = 0.0;
        for (std::size_t i = 1; i < pts.size(); ++i) {
            total += distance(pts[i - 1], pts[i]);
        }
        return total;
    };

    auto max_side = [&](const std::vector<Point>& pts) -> double {
        double max_value = 0.0;
        for (const auto& p : pts) {
            max_value = std::max(max_value, std::abs(side_value(p)));
        }
        return max_value;
    };

    auto p_forward = path_between(i0, i1);
    auto p_backward = path_between(i1, i0);
    const double f_side = max_side(p_forward);
    const double b_side = max_side(p_backward);
    if (std::min(f_side, b_side) > tol * 10.0) {
        std::vector<Point> mirrored;
        mirrored.reserve(augmented.size());
        for (const auto& p : augmented) {
            mirrored.push_back(mirror(p));
        }
        std::reverse(mirrored.begin(), mirrored.end());
        std::vector<Point> out = augmented;
        for (const auto& p : mirrored) {
            if (!out.empty() && near_point(out.back(), p, tol)) {
                continue;
            }
            out.push_back(p);
        }
        return ensure_closed(out, tol);
    }
    std::vector<Point> outside = (f_side > b_side + tol || (std::abs(f_side - b_side) <= tol && path_length(p_forward) >= path_length(p_backward)))
        ? p_forward
        : p_backward;
    outside = dedup_consecutive(outside, tol);
    if (outside.size() < 2) {
        return {};
    }

    std::vector<Point> mirrored;
    mirrored.reserve(outside.size());
    for (const auto& p : outside) {
        mirrored.push_back(mirror(p));
    }
    std::reverse(mirrored.begin(), mirrored.end());

    std::vector<Point> result = outside;
    for (std::size_t i = 1; i < mirrored.size(); ++i) {
        if (!result.empty() && near_point(result.back(), mirrored[i], tol)) {
            continue;
        }
        result.push_back(mirrored[i]);
    }
    result = dedup_consecutive(result, tol);
    return ensure_closed(result, tol);
}

std::optional<ContourResult> smallest_enclosing_contour(const std::vector<std::vector<Point>>& polylines, const Point& point, double tolerance) {
    const auto split_segments = split_segments_at_intersections(explode_segments(polylines), tolerance);
    if (split_segments.empty()) {
        return std::nullopt;
    }
    return select_smallest_contour(find_cycles(split_segments, tolerance), point, tolerance);
}

std::optional<ContourResult> local_enclosing_contour(
    const std::vector<std::vector<Point>>& polylines,
    const Point& point,
    double search_radius,
    double tolerance
) {
    std::vector<Segment2D> local_segments;
    const double min_x = point.x - search_radius;
    const double max_x = point.x + search_radius;
    const double min_y = point.y - search_radius;
    const double max_y = point.y + search_radius;
    for (const auto& segment : explode_segments(polylines)) {
        const double segment_min_x = std::min(segment.a.x, segment.b.x);
        const double segment_max_x = std::max(segment.a.x, segment.b.x);
        const double segment_min_y = std::min(segment.a.y, segment.b.y);
        const double segment_max_y = std::max(segment.a.y, segment.b.y);
        if (search_radius > 0.0 && (
            segment_max_x < min_x ||
            segment_min_x > max_x ||
            segment_max_y < min_y ||
            segment_min_y > max_y
        )) {
            continue;
        }
        local_segments.push_back(segment);
    }

    const auto split_segments = split_segments_at_intersections(local_segments, tolerance);
    if (split_segments.empty()) {
        return std::nullopt;
    }
    auto candidates = faces_from_segments(split_segments, tolerance);
    const auto cycles = find_cycles(split_segments, tolerance);
    candidates.insert(candidates.end(), cycles.begin(), cycles.end());
    return select_smallest_contour(candidates, point, tolerance);
}

}
