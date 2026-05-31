#include "spatial_index.h"
#include <algorithm>

namespace guimma {

BBox make_bbox(const Point& a, const Point& b, double margin) {
    return {
        std::min(a.x, b.x) - margin,
        std::min(a.y, b.y) - margin,
        std::max(a.x, b.x) + margin,
        std::max(a.y, b.y) + margin
    };
}

bool bbox_intersects(const BBox& a, const BBox& b) {
    return !(a.max_x < b.min_x || a.min_x > b.max_x || a.max_y < b.min_y || a.min_y > b.max_y);
}

bool bbox_contains_point(const BBox& box, const Point& p) {
    return p.x >= box.min_x && p.x <= box.max_x && p.y >= box.min_y && p.y <= box.max_y;
}

void SpatialIndex::clear() {
    segments_.clear();
}

void SpatialIndex::add_segment(int element_index, const Point& a, const Point& b) {
    segments_.push_back({element_index, a, b, make_bbox(a, b)});
}

std::vector<Segment> SpatialIndex::query(const BBox& area) const {
    std::vector<Segment> result;
    result.reserve(segments_.size());

    for (const auto& segment : segments_) {
        if (bbox_intersects(segment.bbox, area)) {
            result.push_back(segment);
        }
    }

    return result;
}

std::size_t SpatialIndex::size() const {
    return segments_.size();
}

}
