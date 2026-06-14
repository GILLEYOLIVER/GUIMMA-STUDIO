#pragma once

#include <optional>
#include <string>
#include <vector>
#include "guimma_engine.h"
#include "spatial_index.h"

namespace guimma {

enum class SnapKind {
    None = 0,
    Node = 1,
    Control = 2,
    MainControl = 3,
    HelperControl = 4,
    Border = 5,
    Midpoint = 6,
    Center = 7,
    Intersection = 8,
    Grid = 9,
    Coord = 10,
    Grainline = 11,
    Label = 12
};

struct SnapPoint {
    Point point{0.0, 0.0};
    SnapKind kind = SnapKind::None;
    int element_index = -1;
    double distance = 0.0;
    int priority = 100;
};

struct PolylineElement {
    int element_index = -1;
    std::vector<Point> points;
    std::vector<Point> main_controls;
    std::vector<Point> helper_controls;
    std::vector<Point> official_controls;
    bool participates = true;
    int element_priority = 3;
};

class SnapEngine {
public:
    SnapEngine() = default;

    void clear();
    void set_tolerance_px(double tolerance_px);
    void set_grid(bool enabled, double step);
    void add_polyline(const PolylineElement& element);

    std::vector<SnapPoint> candidates(const Point& cursor, double zoom, double tolerance_px = -1.0) const;
    std::optional<SnapPoint> nearest(const Point& cursor, double zoom, double tolerance_px = -1.0) const;
    std::size_t element_count() const;
    std::size_t segment_count() const;

private:
    double tolerance_px_ = 10.0;
    bool snap_grid_ = false;
    double grid_step_ = 0.1;
    std::vector<PolylineElement> elements_;
    std::vector<BBox> element_bboxes_;
    std::vector<bool> element_has_bbox_;
    SpatialIndex index_;

    void add_point_candidate(std::vector<SnapPoint>& out, const Point& cursor, const Point& point, SnapKind kind, int element_index, int element_priority) const;
    void add_segment_candidates(std::vector<SnapPoint>& out, const Point& cursor, const Segment& segment, int element_priority) const;
    void add_grid_candidate(std::vector<SnapPoint>& out, const Point& cursor, double tolerance_scene) const;
    int kind_priority(SnapKind kind) const;
    int priority_for_element(int element_index) const;
};

std::string snap_kind_to_string(SnapKind kind);

}
