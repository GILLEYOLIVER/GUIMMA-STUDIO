#pragma once

#include <optional>
#include <vector>
#include "guimma_engine.h"

namespace guimma {

struct SegmentPairIntersection {
    bool valid = false;
    Point point{0.0, 0.0};
    int first_index = -1;
    int second_index = -1;
};

std::optional<Point> segment_intersection(const Point& a, const Point& b, const Point& c, const Point& d, double tolerance = 1e-9);
bool point_on_segment(const Point& p, const Point& a, const Point& b, double tolerance = 1e-9);
std::vector<Point> intersections_from_segments(const std::vector<Point>& polyline_a, const std::vector<Point>& polyline_b, double tolerance = 1e-9);

}
