#pragma once

#include <cstddef>
#include <vector>
#include "guimma_engine.h"

namespace guimma {

struct BBox {
    double min_x;
    double min_y;
    double max_x;
    double max_y;
};

struct Segment {
    int element_index;
    Point a;
    Point b;
    BBox bbox;
};

BBox make_bbox(const Point& a, const Point& b, double margin = 0.0);
bool bbox_intersects(const BBox& a, const BBox& b);
bool bbox_contains_point(const BBox& box, const Point& p);

class SpatialIndex {
public:
    void clear();
    void add_segment(int element_index, const Point& a, const Point& b);
    std::vector<Segment> query(const BBox& area) const;
    std::size_t size() const;

private:
    std::vector<Segment> segments_;
};

}
