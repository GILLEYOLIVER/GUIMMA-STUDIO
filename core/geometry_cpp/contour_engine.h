#pragma once

#include <optional>
#include <vector>
#include "guimma_engine.h"

namespace guimma {

struct Segment2D {
    Point a{0.0, 0.0};
    Point b{0.0, 0.0};
};

struct ContourResult {
    bool valid = false;
    std::vector<Point> points;
    double area = 0.0;
    double perimeter = 0.0;
};

std::vector<Point> ensure_closed(const std::vector<Point>& polyline, double tolerance = 1e-9);
double polygon_area(const std::vector<Point>& polygon);
double polyline_length(const std::vector<Point>& polyline);
bool point_in_polygon(const Point& point, const std::vector<Point>& polygon);
bool point_in_polygon_or_boundary(const Point& point, const std::vector<Point>& polygon, double tolerance = 1e-7);
bool contour_is_valid(const std::vector<Point>& polygon, double tolerance = 1e-9);
std::vector<Segment2D> explode_segments(const std::vector<std::vector<Point>>& polylines);
std::vector<Segment2D> split_segments_at_intersections(const std::vector<Segment2D>& segments, double tolerance = 0.001);
std::vector<std::vector<Point>> find_cycles(const std::vector<Segment2D>& segments, double tolerance = 0.001);
std::vector<std::vector<Point>> faces_from_segments(const std::vector<Segment2D>& segments, double tolerance = 0.001);
std::vector<Point> normalize_closed_polyline(const std::vector<Point>& polyline, bool clockwise = true, double tolerance = 1e-9);
std::optional<ContourResult> smallest_enclosing_contour(const std::vector<std::vector<Point>>& polylines, const Point& point, double tolerance = 1e-6);
std::optional<ContourResult> local_enclosing_contour(const std::vector<std::vector<Point>>& polylines, const Point& point, double search_radius = 20.0, double tolerance = 0.01);

}
