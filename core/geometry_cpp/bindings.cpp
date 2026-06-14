#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "contour_engine.h"
#include "curve_engine.h"
#include "guimma_engine.h"
#include "seam_engine.h"
#include "snap_engine.h"
#include "spatial_index.h"

namespace py = pybind11;

namespace {

using PointTuple = std::pair<double, double>;

std::vector<guimma::Point> to_points(const std::vector<PointTuple>& points) {
    std::vector<guimma::Point> out;
    out.reserve(points.size());
    for (const auto& [x, y] : points) {
        out.push_back({x, y});
    }
    return out;
}

std::vector<std::vector<guimma::Point>> to_polylines(const std::vector<std::vector<PointTuple>>& polylines) {
    std::vector<std::vector<guimma::Point>> out;
    out.reserve(polylines.size());
    for (const auto& polyline : polylines) {
        out.push_back(to_points(polyline));
    }
    return out;
}

std::vector<PointTuple> to_tuples(const std::vector<guimma::Point>& points) {
    std::vector<PointTuple> out;
    out.reserve(points.size());
    for (const auto& point : points) {
        out.push_back({point.x, point.y});
    }
    return out;
}

py::object contour_result_to_python(const std::optional<guimma::ContourResult>& result) {
    if (!result.has_value()) {
        return py::none();
    }
    py::dict out;
    out["valid"] = result->valid;
    out["points"] = to_tuples(result->points);
    out["area"] = result->area;
    out["perimeter"] = result->perimeter;
    return std::move(out);
}

}

PYBIND11_MODULE(guimma_geometry_cpp, m) {
    m.doc() = "Motor geometrico C++ do GUIMMA STUDIO";

    py::class_<guimma::Point>(m, "Point")
        .def(py::init<>())
        .def(py::init<double, double>())
        .def_readwrite("x", &guimma::Point::x)
        .def_readwrite("y", &guimma::Point::y);

    py::enum_<guimma::SnapKind>(m, "SnapKind")
        .value("NONE", guimma::SnapKind::None)
        .value("NODE", guimma::SnapKind::Node)
        .value("CONTROL", guimma::SnapKind::Control)
        .value("MAIN_CONTROL", guimma::SnapKind::MainControl)
        .value("HELPER_CONTROL", guimma::SnapKind::HelperControl)
        .value("BORDER", guimma::SnapKind::Border)
        .value("MIDPOINT", guimma::SnapKind::Midpoint)
        .value("CENTER", guimma::SnapKind::Center)
        .value("INTERSECTION", guimma::SnapKind::Intersection)
        .value("GRID", guimma::SnapKind::Grid)
        .value("COORD", guimma::SnapKind::Coord)
        .value("GRAINLINE", guimma::SnapKind::Grainline)
        .value("LABEL", guimma::SnapKind::Label);

    py::class_<guimma::SnapPoint>(m, "SnapPoint")
        .def(py::init<>())
        .def_readwrite("point", &guimma::SnapPoint::point)
        .def_readwrite("kind", &guimma::SnapPoint::kind)
        .def_readwrite("element_index", &guimma::SnapPoint::element_index)
        .def_readwrite("distance", &guimma::SnapPoint::distance)
        .def_readwrite("priority", &guimma::SnapPoint::priority)
        .def_property_readonly("kind_text", [](const guimma::SnapPoint& p) {
            return guimma::snap_kind_to_string(p.kind);
        });

    py::class_<guimma::PolylineElement>(m, "PolylineElement")
        .def(py::init<>())
        .def_readwrite("element_index", &guimma::PolylineElement::element_index)
        .def_readwrite("points", &guimma::PolylineElement::points)
        .def_readwrite("main_controls", &guimma::PolylineElement::main_controls)
        .def_readwrite("helper_controls", &guimma::PolylineElement::helper_controls)
        .def_readwrite("official_controls", &guimma::PolylineElement::official_controls)
        .def_readwrite("participates", &guimma::PolylineElement::participates)
        .def_readwrite("element_priority", &guimma::PolylineElement::element_priority);

    py::class_<guimma::SnapEngine>(m, "SnapEngine")
        .def(py::init<>())
        .def("clear", &guimma::SnapEngine::clear)
        .def("set_tolerance_px", &guimma::SnapEngine::set_tolerance_px)
        .def("set_grid", &guimma::SnapEngine::set_grid)
        .def("add_polyline", &guimma::SnapEngine::add_polyline)
        .def("candidates", &guimma::SnapEngine::candidates, py::arg("cursor"), py::arg("zoom"), py::arg("tolerance_px") = -1.0)
        .def("nearest", &guimma::SnapEngine::nearest, py::arg("cursor"), py::arg("zoom"), py::arg("tolerance_px") = -1.0)
        .def("element_count", &guimma::SnapEngine::element_count)
        .def("segment_count", &guimma::SnapEngine::segment_count);

    m.def("distance", [](double ax, double ay, double bx, double by) {
        return guimma::distance({ax, ay}, {bx, by});
    });

    m.def("project_on_segment", [](double px, double py, double ax, double ay, double bx, double by) {
        const auto p = guimma::project_on_segment({px, py}, {ax, ay}, {bx, by});
        return py::make_tuple(p.x, p.y);
    });

    m.def("snap_kind_to_string", &guimma::snap_kind_to_string);

    m.def("sample_quadratic_bezier", [](PointTuple p0, PointTuple control, PointTuple p2, int segments) {
        return to_tuples(guimma::sample_quadratic_bezier({p0.first, p0.second}, {control.first, control.second}, {p2.first, p2.second}, segments));
    }, py::arg("p0"), py::arg("control"), py::arg("p2"), py::arg("segments") = 48);

    m.def("sample_parabola_3p", [](PointTuple p0, PointTuple middle, PointTuple p2, int segments) {
        return to_tuples(guimma::sample_parabola_3p({p0.first, p0.second}, {middle.first, middle.second}, {p2.first, p2.second}, segments));
    }, py::arg("p0"), py::arg("middle"), py::arg("p2"), py::arg("segments") = 48);

    m.def("sample_catmull_rom", [](const std::vector<PointTuple>& controls, int samples_per_span, bool closed) {
        return to_tuples(guimma::sample_catmull_rom(to_points(controls), samples_per_span, closed));
    }, py::arg("controls"), py::arg("samples_per_span") = 18, py::arg("closed") = false);

    m.def("polygon_area", [](const std::vector<PointTuple>& polygon) {
        return guimma::polygon_area(to_points(polygon));
    });

    m.def("polyline_length", [](const std::vector<PointTuple>& polyline) {
        return guimma::polyline_length(to_points(polyline));
    });

    m.def("normalize_closed_polyline", [](const std::vector<PointTuple>& polyline, bool clockwise, double tolerance) {
        return to_tuples(guimma::normalize_closed_polyline(to_points(polyline), clockwise, tolerance));
    }, py::arg("polyline"), py::arg("clockwise") = true, py::arg("tolerance") = 1e-9);

    m.def("seam_offset_closed", [](const std::vector<PointTuple>& polyline, double margin) {
        return to_tuples(guimma::seam_offset_closed(to_points(polyline), margin));
    }, py::arg("polyline"), py::arg("margin"));

    m.def("point_in_polygon", [](double x, double y, const std::vector<PointTuple>& polygon) {
        return guimma::point_in_polygon({x, y}, to_points(polygon));
    });

    m.def("point_in_polygon_or_boundary", [](double x, double y, const std::vector<PointTuple>& polygon, double tolerance) {
        return guimma::point_in_polygon_or_boundary({x, y}, to_points(polygon), tolerance);
    }, py::arg("x"), py::arg("y"), py::arg("polygon"), py::arg("tolerance") = 1e-7);

    m.def("extract_smallest_enclosing_contour", [](const std::vector<std::vector<PointTuple>>& polylines, double x, double y, double tolerance) {
        return contour_result_to_python(guimma::smallest_enclosing_contour(to_polylines(polylines), {x, y}, tolerance));
    }, py::arg("polylines"), py::arg("x"), py::arg("y"), py::arg("tolerance") = 1e-6);

    m.def("extract_local_enclosing_contour", [](const std::vector<std::vector<PointTuple>>& polylines, double x, double y, double search_radius, double tolerance) {
        return contour_result_to_python(guimma::local_enclosing_contour(to_polylines(polylines), {x, y}, search_radius, tolerance));
    }, py::arg("polylines"), py::arg("x"), py::arg("y"), py::arg("search_radius") = 20.0, py::arg("tolerance") = 0.01);
}
